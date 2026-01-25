import streamlit as st
import pandas as pd
import math

# --- KONFIGURACE ---
st.set_page_config(page_title="Kalkulátor Zastřešení", layout="wide")

# --- NAČTENÍ DAT ---
@st.cache_data
def load_data():
    try:
        # 1. Načtení ceníků (očekáváme středník)
        df_c = pd.read_csv('ceniky.csv', sep=';', header=None, encoding='utf-8')
        
        # 2. Načtení příplatků (zkusíme detekovat oddělovač)
        try:
            # Zkusíme středník
            df_p = pd.read_csv('priplatky.csv', sep=';', header=None, encoding='utf-8')
            if df_p.shape[1] < 2: # Pokud se načetl jen jeden sloupec, je to špatně
                raise ValueError()
        except:
            # Fallback na čárku (častý formát Excel exportu)
            df_p = pd.read_csv('priplatky.csv', sep=',', header=None, encoding='utf-8')
            
        return df_c, df_p
    except Exception as e:
        return None, None

# --- POMOCNÉ FUNKCE ---
def parse_value(raw_value):
    """Převede text '15%' nebo '1 500 Kč' na číslo."""
    if pd.isna(raw_value): return 0
    s = str(raw_value).strip().replace(' ', '').replace('Kč', '').replace('Kc', '')
    
    if '%' in s:
        # Je to procento (např. 15% -> 0.15)
        return float(s.replace('%', '').replace(',', '.')) / 100.0
    
    try:
        # Je to číslo
        return float(s.replace(',', '.'))
    except:
        return 0

def get_surcharge(df, search_term, is_rock=False):
    """Najde cenu v CSV. Pokud je model ROCK, hledá ve 3. sloupci (index 2)."""
    if df is None: return 0
    
    # Hledáme řádek (case insensitive)
    mask = df[0].astype(str).str.contains(search_term, case=False, na=False)
    row = df[mask]
    
    if row.empty: return 0
    
    # Sloupec: 1 = Standard, 2 = Rock
    # (Ověříme, zda má CSV dost sloupců)
    col_idx = 2 if (is_rock and row.shape[1] > 2) else 1
    
    try:
        val = row.iloc[0, col_idx]
        if pd.isna(val) or str(val).strip() == "":
            val = row.iloc[0, 1] # Fallback na standard, pokud je Rock prázdný
        return parse_value(val)
    except:
        return parse_value(row.iloc[0, 1])

# --- GEOMETRIE (Pro výpočet plochy polykarbonátu) ---
def calculate_geometry(width_mm, height_mm, length_mm):
    w = width_mm / 1000.0
    h = height_mm / 1000.0
    l = length_mm / 1000.0
    
    # Aproximace délky oblouku (elipsa)
    a = w / 2
    b = h
    # Ramanujanova aproximace obvodu elipsy
    perimeter = math.pi * (3*(a+b) - math.sqrt((3*a + b) * (a + 3*b)))
    arc_length = perimeter / 2 # Půlka obvodu
    
    roof_area = arc_length * l
    face_area = (math.pi * a * b) / 2 # Půlka obsahu elipsy
    
    return roof_area, face_area

def get_length_from_ceniky(df_c, modules):
    """Vytáhne délku zastřešení z řádku 4 ceníku."""
    try:
        col_idx = 1 + (modules - 2) * 2
        val = df_c.iloc[4, col_idx]
        return parse_value(val)
    except:
        return modules * 2150 # Odhad kdyby chybělo v CSV

# --- JÁDRO VÝPOČTU ---
def calculate_base_price(model, width, modules, df_c):
    # Najít řádek modelu
    try:
        mask = df_c[0].astype(str).str.lower() == model.lower()
        start_index = df_c.index[mask].tolist()[0]
    except:
        return 0, 0, 0, "Model nenalezen v ceníku"

    # Posun řádku dle šířky
    offset = 1750 if model.upper() == "TERRACE" else 2750
    if width < (offset + 250):
        row_shift = 0
    else:
        row_shift = math.ceil((width - (offset + 250)) / 250)
        if row_shift < 0: row_shift = 0

    target_row = start_index + 1 + row_shift

    # Sloupec dle modulů
    col_price = 1 + (modules - 2) * 2
    col_height = col_price + 1

    try:
        price = parse_value(df_c.iloc[target_row, col_price])
        height = parse_value(df_c.iloc[target_row, col_height]) * 1000
        length = get_length_from_ceniky(df_c, modules)
        return price, height, length, None
    except:
        return 0, 0, 0, "Mimo rozsah ceníku"

# --- HLAVNÍ APLIKACE ---
st.title("🛠 Kalkulátor Zastřešení 5.0")

df_c, df_p = load_data()

if df_c is None:
    st.error("Chyba: Data nebyla načtena. Zkontrolujte soubory na GitHubu.")
    st.stop()

# ================= LEVÝ PANEL (VSTUPY) =================
with st.sidebar:
    st.header("1. Parametry Zastřešení")
    model = st.selectbox("Model", ["PRACTIC", "HARMONY", "DREAM", "HORIZONT", "STAR", "ROCK", "TERRACE", "WAVE", "FLASH", "WING", "SUNSET"])
    is_rock = (model.upper() == "ROCK")
    
    sirka = st.number_input("Šířka (mm)", 2000, 9000, 3500, step=10)
    moduly = st.slider("Počet modulů", 2, 7, 3)
    
    st.markdown("---")
    st.header("2. Konstrukce a Výplň")
    
    barva_typ = st.selectbox("Barva konstrukce", 
                             ["Stříbrný Elox (Bonus -10 000 Kč)", 
                              "Bronzový Elox", 
                              "Antracitový Elox", 
                              "RAL Nástřik"])
    
    st.info("Standard: Dutinkový čirý 8mm")
    st.write("**Příplatky za plný polykarbonát (dle m²):**")
    poly_strecha = st.checkbox("Plný polykarbonát - STŘECHA")
    poly_cela = st.checkbox("Plný polykarbonát - ČELA (VČ+MČ)")
    change_color_poly = st.checkbox("Změna barvy polykarbonátu")
    
    st.markdown("---")
    st.header("3. Dveře a Vstupy")
    st.caption("ℹ️ První vybrané dveře jsou vždy ZDARMA.")
    
    pocet_dvere_vc = st.number_input("Počet dveří v čele", 0, 2, 0)
    pocet_dvere_bok = st.number_input("Počet bočních vstupů", 0, 4, 0)
    
    zamykaci_klika = st.checkbox("Zamykací klika (pro všechny dveře)")
    klapka = st.checkbox("Větrací klapka")

    st.markdown("---")
    st.header("4. Koleje a Doplňky")
    
    # Koleje
    pochozi_koleje = st.checkbox("Pochozí koleje (komplet)")
    st.write("Prodloužení kolejiště:")
    ext_draha_m = st.number_input("O kolik metrů prodloužit dráhu?", 0.0, 20.0, 0.0, step=0.5)
    
    podhori = st.checkbox("Zpevnění pro podhorskou oblast")

    st.markdown("---")
    st.header("5. Služby a Cena")
    
    km = st.number_input("Doprava (km tam i zpět)", 0, 5000, 0)
    montaz = st.checkbox("Montáž (vždy ČR)", value=True)
    sleva_pct = st.number_input("Sleva pro zákazníka (%)", 0, 100, 0)
    dph_sazba = st.selectbox("Sazba DPH", [21, 12, 0], index=0)


# ================= PRAVÝ PANEL (VÝPOČET) =================
base_price, height, length, err = calculate_base_price(model, sirka, moduly, df_c)

if err:
    st.warning(f"⚠ {err}")
else:
    # Seznam položek pro výpis
    items = []
    
    # 1. Základ
    items.append({"pol": f"Zastřešení {model}", "det": f"{moduly} segmentů, Š: {sirka}mm, D: {length}mm", "cen": base_price})
    
    running_total = base_price
    
    # 2. Barva konstrukce
    if "Stříbrný" in barva_typ:
        val = -10000
        items.append({"pol": "BONUS: Stříbrný Elox", "det": "Sleva z ceny", "cen": val})
        running_total += val
    
    elif "RAL" in barva_typ:
        val = get_surcharge(df_p, "RAL", is_rock) # 0.20
        if val == 0: val = 0.20
        cost = base_price * val
        items.append({"pol": "Příplatek RAL", "det": f"+{val*100:.0f}%", "cen": cost})
        running_total += cost
        
    elif "Bronz" in barva_typ:
        val = get_surcharge(df_p, "BR elox", is_rock) # 0.05
        if val == 0: val = 0.05
        cost = base_price * val
        items.append({"pol": "Příplatek Bronz Elox", "det": f"+{val*100:.0f}%", "cen": cost})
        running_total += cost

    elif "Antracit" in barva_typ:
        val = get_surcharge(df_p, "antracit elox", is_rock) # 0.05
        if val == 0: val = 0.05
        cost = base_price * val
        items.append({"pol": "Příplatek Antracit Elox", "det": f"+{val*100:.0f}%", "cen": cost})
        running_total += cost

    # 3. Polykarbonát (Plocha)
    area_roof, area_face = calculate_geometry(sirka, height, length)
    poly_price_m2 = get_surcharge(df_p, "Plný polykarbonát", is_rock)
    if poly_price_m2 == 0: poly_price_m2 = 1000

    if poly_strecha:
        cost = area_roof * poly_price_m2
        items.append({"pol": "Plný polykarbonát (Střecha)", "det": f"{area_roof:.1f} m² x {poly_price_m2} Kč", "cen": cost})
        running_total += cost
        
    if poly_cela:
        cost = (area_face * 2) * poly_price_m2
        items.append({"pol": "Plný polykarbonát (Čela)", "det": f"{(area_face*2):.1f} m² x {poly_price_m2} Kč", "cen": cost})
        running_total += cost

    if change_color_poly:
        val = get_surcharge(df_p, "barvy poly", is_rock) # 0.07
        cost = base_price * val
        items.append({"pol": "Změna barvy polykarbonátu", "det": f"+{val*100:.0f}%", "cen": cost})
        running_total += cost

    # 4. Podhorská oblast
    if podhori:
        val = get_surcharge(df_p, "podhorskou", is_rock) # 0.15
        cost = base_price * val
        items.append({"pol": "Zpevnění (Podhorská obl.)", "det": f"+{val*100:.0f}%", "cen": cost})
        running_total += cost

    # 5. Dveře (Logika 1. zdarma)
    # Ceny
    cena_dvere_vc = get_surcharge(df_p, "Jednokřídlé dveře", is_rock)
    if cena_dvere_vc == 0: cena_dvere_vc = 5000
    
    cena_dvere_bok = get_surcharge(df_p, "boční vstup", is_rock)
    if cena_dvere_bok == 0: cena_dvere_bok = 7000
    
    # Seznam dveří k zaplacení
    doors = []
    for _ in range(pocet_dvere_vc): doors.append(("Dveře v čele", cena_dvere_vc))
    for _ in range(pocet_dvere_bok): doors.append(("Boční vstup", cena_dvere_bok))
    
    # Seřadit podle ceny (nejdražší první) a první odebrat
    if doors:
        doors.sort(key=lambda x: x[1], reverse=True)
        free_door = doors.pop(0)
        items.append({"pol": f"{free_door[0]} (1. ks)", "det": "ZDARMA", "cen": 0})
        
        # Zbytek naúčtovat
        for name, price in doors:
            items.append({"pol": name, "det": "Další kus", "cen": price})
            running_total += price

    # Zamykací klika (pro všechny vybrané dveře)
    total_doors_count = pocet_dvere_vc + pocet_dvere_bok
    if zamykaci_klika and total_doors_count > 0:
        val = get_surcharge(df_p, "Uzamykání dveří", is_rock) # 800
        cost = total_doors_count * val
        items.append({"pol": "Zamykací klika", "det": f"{total_doors_count} ks x {val} Kč", "cen": cost})
        running_total += cost

    # Klapka
    if klapka:
        val = get_surcharge(df_p, "klapka", is_rock) # 7000
        items.append({"pol": "Větrací klapka", "det": "", "cen": val})
        running_total += val

    # 6. Koleje
    if pochozi_koleje:
        # Cena v CSV (330 Kč) je obvykle za metr JEDNÉ koleje.
        # Dráha má dvě strany. Délka dráhy = délka zastřešení.
        total_m_rail = (length / 1000.0) * 2
        val = get_surcharge(df_p, "Pochozí kolejnice", is_rock) # 330/380
        cost = total_m_rail * val
        items.append({"pol": "Pochozí koleje (typ)", "det": f"{total_m_rail:.1f} m kolejnice", "cen": cost})
        running_total += cost
        
    if ext_draha_m > 0:
        # Prodloužení dráhy o X metrů = 2 * X metrů kolejnice
        total_ext_rail = ext_draha_m * 2
        val = get_surcharge(df_p, "Jeden metr koleje", is_rock) # 220
        cost = total_ext_rail * val
        items.append({"pol": "Prodloužení kolejiště", "det": f"+{ext_draha_m} m dráhy ({total_ext_rail} m kolejnic)", "cen": cost})
        running_total += cost

    # 7. Montáž (Vždy ČR)
    montaz_cena = 0
    if montaz:
        # Hledáme "Montáž v ČR"
        val = get_surcharge(df_p, "Montáž zastřešení v ČR", is_rock) # 0.06 / 0.08
        if val == 0: val = 0.08
        
        # Montáž se
