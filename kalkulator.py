import streamlit as st
import pandas as pd
import math

# --- KONFIGURACE ---
st.set_page_config(page_title="Kalkulátor Zastřešení", layout="wide")

# --- NAČTENÍ DAT ---
@st.cache_data
def load_data():
    try:
        # Zkusíme načíst ceníky (středník)
        df_c = pd.read_csv('ceniky.csv', sep=';', header=None, encoding='utf-8')
        # Zkusíme načíst příplatky (detekce oddělovače)
        try:
            df_p = pd.read_csv('priplatky.csv', sep=';', header=None, encoding='utf-8')
            if df_p.shape[1] < 2: # Pokud se to načetlo špatně do jednoho sloupce
                df_p = pd.read_csv('priplatky.csv', sep=',', header=None, encoding='utf-8')
        except:
            df_p = pd.read_csv('priplatky.csv', sep=',', header=None, encoding='utf-8')
            
        return df_c, df_p
    except Exception as e:
        return None, None

# --- POMOCNÉ FUNKCE ---
def parse_value(raw_value):
    """Převede string na číslo."""
    if pd.isna(raw_value): return 0
    s = str(raw_value).strip().replace(' ', '').replace('Kč', '').replace('Kc', '')
    if '%' in s:
        return float(s.replace('%', '').replace(',', '.')) / 100.0
    try:
        return float(s.replace(',', '.'))
    except:
        return 0

def get_surcharge(df, search_term, is_rock=False):
    """Vrátí hodnotu příplatku (prioritizuje sloupec pro Rock, pokud existuje)"""
    if df is None: return 0
    mask = df[0].astype(str).str.contains(search_term, case=False, na=False)
    row = df[mask]
    if row.empty: return 0
    
    # Indexy: 1=Standard, 2=Rock (pokud existuje)
    col_idx = 2 if is_rock and row.shape[1] > 2 else 1
    
    try:
        val = row.iloc[0, col_idx]
        if pd.isna(val) or str(val).strip() == "":
            val = row.iloc[0, 1] # Fallback na standard
        return parse_value(val)
    except:
        return parse_value(row.iloc[0, 1])

# --- GEOMETRIE A VÝPOČTY ---
def calculate_geometry(width_mm, height_mm, length_mm):
    """
    Aproximace plochy zastřešení pro výpočet polykarbonátu.
    Protože nemáme přesné R1/R2 z Excelu, použijeme aproximaci kruhové úseče/elipsy.
    """
    w = width_mm / 1000.0
    h = height_mm / 1000.0
    l = length_mm / 1000.0
    
    # 1. Délka oblouku (Ramanujanova aproximace pro elipsu - horní polovina)
    # Obvod elipsy ~ pi * (3(a+b) - sqrt((3a+b)(a+3b)))
    # Zde a=w/2, b=h. Potřebujeme polovinu obvodu.
    a = w / 2
    b = h
    perimeter = math.pi * (3*(a+b) - math.sqrt((3*a + b) * (a + 3*b)))
    arc_length = perimeter / 2
    
    # Plocha střechy (modulů)
    roof_area = arc_length * l
    
    # Plocha čel (přibližně plocha elipsy / 2)
    # Obsah elipsy = pi * a * b. Půlka = (pi * a * b) / 2
    face_area = (math.pi * a * b) / 2
    
    return roof_area, face_area

def get_length_from_ceniky(df_c, modules):
    """Vytáhne délku zastřešení z řádku 4 v ceníku"""
    try:
        # Předpokládáme, že řádek 4 obsahuje délky (index 4)
        # Sloupec: 2 moduly -> col 1, 3 moduly -> col 3...
        col_idx = 1 + (modules - 2) * 2
        val = df_c.iloc[4, col_idx] # Řádek 4
        return parse_value(val) # Vrací mm
    except:
        return modules * 2150 # Fallback 2.15m na modul

def calculate_base_price(model, width, modules, df_c):
    try:
        mask = df_c[0].astype(str).str.lower() == model.lower()
        start_index = df_c.index[mask].tolist()[0]
    except:
        return 0, 0, 0, "Model nenalezen"

    offset = 1750 if model.upper() == "TERRACE" else 2750
    row_shift = math.ceil((width - (offset + 250)) / 250) if width >= (offset + 250) else 0
    target_row = start_index + 1 + max(0, row_shift)

    col_price = 1 + (modules - 2) * 2
    col_height = col_price + 1

    try:
        price = parse_value(df_c.iloc[target_row, col_price])
        height = parse_value(df_c.iloc[target_row, col_height]) * 1000
        length = get_length_from_ceniky(df_c, modules)
        return price, height, length, None
    except:
        return 0, 0, 0, "Mimo rozsah"

# --- APLIKACE ---
st.title("🛠 Kalkulátor Zastřešení")
df_c, df_p = load_data()

if df_c is None:
    st.error("Chyba načítání dat. Zkontrolujte CSV soubory na GitHubu.")
    st.stop()

# --- SIDEBAR: Vstupy ---
with st.sidebar:
    st.header("1. Rozměry a Typ")
    model = st.selectbox("Model", ["PRACTIC", "HARMONY", "DREAM", "HORIZONT", "STAR", "ROCK", "TERRACE", "WAVE", "FLASH", "WING", "SUNSET"])
    is_rock = (model.upper() == "ROCK")
    
    sirka = st.number_input("Šířka (mm)", 2000, 9000, 3500, step=10)
    moduly = st.slider("Počet modulů", 2, 7, 3)
    
    st.markdown("---")
    st.header("2. Konstrukce a Výplň")
    
    # Barva konstrukce
    barva_typ = st.selectbox("Barva konstrukce", 
                             ["Stříbrný Elox (Bonus -10 000 Kč)", 
                              "Bronzový Elox", 
                              "Antracitový Elox", 
                              "RAL Nástřik"])
    
    # Polykarbonát
    st.info("Standard: Dutinkový čirý 8mm")
    st.write("Příplatek za plný polykarbonát (přepočet na m²):")
    poly_strecha = st.checkbox("Plný polykarbonát ve střeše")
    poly_cela = st.checkbox("Plný polykarbonát v čelech (VČ/MČ)")
    change_color_poly = st.checkbox("Změna barvy polykarbonátu (Kouř/Modrá)")
    
    st.markdown("---")
    st.header("3. Dveře a Vstupy")
    st.caption("První vybrané dveře jsou ZDARMA.")
     pocet_dvere_vc = st.number_input("Počet dveří v čele", 0, 2, 0)
    pocet_dvere_bok = st.number_input("Počet bočních vstupů", 0, 4, 0)
    zamykaci_klika = st.checkbox("Uzamykání dveří (klika)")
    klapka = st.checkbox("Větrací klapka")

    st.markdown("---")
    st.header("4. Koleje a Doplňky")
    ext_koleje_m = st.number_input("Prodloužení kolejí (m)", 0.0, 20.0, 0.0, step=0.5)
    pochozi_koleje = st.checkbox("Pochozí koleje (komplet)")
    podhori = st.checkbox("Zpevnění pro podhorskou oblast")

    st.markdown("---")
    st.header("5. Služby a DPH")
    km = st.number_input("Doprava (km tam i zpět)", 0, 2000, 0)
    montaz = st.checkbox("Montáž (vždy ČR)", value=True)
    sleva_pct = st.number_input("Sleva pro zákazníka (%)", 0, 100, 0)
    dph_sazba = st.selectbox("Sazba DPH", [12, 21, 0], index=1)

# --- VÝPOČET ---
base_price, height, length, err = calculate_base_price(model, sirka, moduly, df_c)

if err:
    st.warning(f"⚠ {err}")
else:
    items = []
    # 1. Základní cena
    items.append({"pol": f"Zastřešení {model}", "det": f"{moduly} segmentů, Š: {sirka}mm, D: {length}mm", "cen": base_price})
    
    running_total = base_price

    # 2. Barva konstrukce (Bonus nebo Příplatek)
    if "Stříbrný" in barva_typ:
        sleva_elox = -10000
        items.append({"pol": "BONUS: Stříbrný Elox", "det": "Sleva z ceny", "cen": sleva_elox})
        running_total += sleva_elox
    
    elif "RAL" in barva_typ:
        p_val = get_surcharge(df_p, "RAL", is_rock) # 0.2
        if p_val == 0: p_val = 0.20
        cost = base_price * p_val
        items.append({"pol": "Příplatek RAL", "det": f"+{p_val*100:.0f}%", "cen": cost})
        running_total += cost
        
    elif "Bronz" in barva_typ:
        p_val = get_surcharge(df_p, "BR elox", is_rock) # 0.05
        if p_val == 0: p_val = 0.05
        cost = base_price * p_val
        items.append({"pol": "Příplatek Bronz Elox", "det": f"+{p_val*100:.0f}%", "cen": cost})
        running_total += cost

    elif "Antracit" in barva_typ:
        p_val = get_surcharge(df_p, "antracit elox", is_rock)
        if p_val == 0: p_val = 0.05 # Odhad, pokud není v CSV
        cost = base_price * p_val
        items.append({"pol": "Příplatek Antracit Elox", "det": f"+{p_val*100:.0f}%", "cen": cost})
        running_total += cost

    # 3. Polykarbonát (Plocha)
    area_roof, area_face = calculate_geometry(sirka, height, length)
    poly_surcharge_m2 = get_surcharge(df_p, "Plný polykarbonát", is_rock)
    if poly_surcharge_m2 == 0: poly_surcharge_m2 = 1000

    if poly_strecha:
        cost = area_roof * poly_surcharge_m2
        items.append({"pol": "Plný polykarbonát (Střecha)", "det": f"{area_roof:.1f} m² x {poly_surcharge_m2} Kč", "cen": cost})
        running_total += cost
        
    if poly_cela:
        cost = (area_face * 2) * poly_surcharge_m2 # 2 čela
        items.append({"pol": "Plný polykarbonát (Čela)", "det": f"{(area_face*2):.1f} m² x {poly_surcharge_m2} Kč", "cen": cost})
        running_total += cost

    if change_color_poly:
        p_val = get_surcharge(df_p, "barvy poly", is_rock) # 0.07
        cost = base_price * p_val
        items.append({"pol": "Změna barvy polykarbonátu", "det": f"+{p_val*100:.0f}%", "cen": cost})
        running_total += cost

    # 4. Podhorská oblast
    if podhori:
        p_val = get_surcharge(df_p, "podhorskou", is_rock) # 0.15
        cost = base_price * p_val
        items.append({"pol": "Zpevnění (Podhorská obl.)", "det": f"+{p_val*100:.0f}%", "cen": cost})
        running_total += cost

    # 5. Dveře (Logika 1. zdarma)
    doors_to_pay = []
    
    price_dvere_vc = get_surcharge(df_p, "Jednokřídlé dveře", is_rock)
    if price_dvere_vc == 0: price_dvere_vc = 5000
    
    price_dvere_bok = get_surcharge(df_p, "boční vstup", is_rock)
    if price_dvere_bok == 0: price_dvere_bok = 7000

    # Přidáme všechny vybrané dveře do seznamu
    for _ in range(pocet_dvere_vc): doors_to_pay.append(("Dveře v čele", price_dvere_vc))
    for _ in range(pocet_dvere_bok): doors_to_pay.append(("Boční vstup", price_dvere_bok))
    
    # Seřadíme podle ceny (od nejdražší), odebereme první
    if doors_to_pay:
        # Sort descending to make sure user gets the better deal (most expensive free)? 
        # Or usually standard door is free? Assuming just 'one door free'.
        doors_to_pay.sort(key=lambda x: x[1], reverse=True)
        free_door = doors_to_pay.pop(0)
        items.append({"pol": f"{free_door[0]} (1. ks)", "det": "ZDARMA", "cen": 0})
        
        # Zbytek platíme
        for d_name, d_price in doors_to_pay:
             items.append({"pol": d_name, "det": "Příplatek za další ks", "cen": d_price})
             running_total += d_price

    if zamykaci_klika:
        # Počítáme kliku pro všechny dveře nebo paušál? Obvykle za kus.
        # Zde počítám za každý vybraný dveřní otvor
        total_doors = pocet_dvere_vc + pocet_dvere_bok
        if total_doors > 0:
            p_val = get_surcharge(df_p, "Uzamykání dveří", is_rock) # 800
            if p_val == 0: p_val = 800
            cost = total_doors * p_val
            items.append({"pol": "Uzamykání dveří", "det": f"{total_doors} ks x {p_val} Kč", "cen": cost})
            running_total += cost

    if klapka:
        p_val = get_surcharge(df_p, "klapka", is_rock)
        if p_val == 0: p_val = 7000
        items.append({"pol": "Větrací klapka", "det": "", "cen": p_val})
        running_total += p_val

    # 6. Koleje
    if pochozi_koleje:
        # Cena paušál za délku bazénu nebo fix?
        # CSV má: Pochozí kolejnice 330 Kč. Zřejmě za bm.
        # Délka kolejí = Délka zastřešení * 2
        delka_trasy = (length / 1000.0) * 2
        p_val = get_surcharge(df_p, "Pochozí kolejnice", is_rock)
        cost = delka_trasy * p_val
        items.append({"pol": "Pochozí koleje", "det": f"{delka_trasy:.1f} m x {p_val} Kč", "cen": cost})
        running_total += cost
        
    if ext_koleje_m > 0:
        # Cena za prodloužení
        p_val = get_surcharge(df_p, "Jeden metr koleje", is_rock) # 220
        cost = ext_koleje_m * p_val
        items.append({"pol": "Prodloužení kolejí", "det": f"{ext_koleje_m} m x {p_val} Kč", "cen": cost})
        running_total += cost

    # 7. Montáž (vždy ČR)
    montaz_cena = 0
    if montaz:
        p_pct = get_surcharge(df_p, "Montáž zastřešení v ČR", is_rock) # 0.06 / 0.08
        if p_pct == 0: p_pct = 0.08
        montaz_cena = running_total * p_pct # Montáž z ceny materiálu s příplatky
        items.append({"pol": "Montáž (ČR)", "det": f"{p_pct*100:.0f}% z ceny", "cen": montaz_cena})
    
    # Mezisoučet před dopravou
    total_material_service = running_total + montaz_cena
    
    # 8. Doprava
    doprava_cena = 0
    if km > 0:
        doprava_cena = km * 18
        items.append({"pol": "Doprava", "det": f"{km} km x 18 Kč", "cen": doprava_cena})
        
    final_price_no_vat = total_material_service + doprava_cena
    
    # 9. Sleva
    if sleva_pct > 0:
        sleva_val = final_price_no_vat * (sleva_pct / 100.0)
        items.append({"pol": "SLEVA", "det": f"-{sleva_pct}%", "cen": -sleva_val})
        final_price_no_vat -= sleva_val

    # --- VÝSTUPNÍ TABULKA ---
    st.subheader("Cenová kalkulace")
    
    df_out = pd.DataFrame(items)
    
    col_l, col_r = st.columns([2, 1])
    
    with col_l:
        st.write("### Položkový rozpočet")
        if not df_out.empty:
            for i, row in df_out.iterrows():
                c1, c2, c3 = st.columns([3, 2, 2])
                c1.write(f"**{row['pol']}**")
                c2.caption(row['det'])
                c3.write(f"{row['cen']:,.0f} Kč")
                st.markdown("<hr style='margin: 0; opacity: 0.2'>", unsafe_allow_html=True)

    with col_r:
        st.write("### Rekapitulace")
        st.metric("Cena bez DPH", f"{final_price_no_vat:,.0f} Kč")
        
        dph_val = final_price_no_vat * (dph_sazba / 100.0)
        st.write(f"DPH ({dph_sazba}%) : {dph_val:,.0f} Kč")
        
        final_with_vat = final_price_no_vat + dph_val
        st.markdown(f"# {final_with_vat:,.0f} Kč")
        st.caption("Cena celkem s DPH")
