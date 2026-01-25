import streamlit as st
import pandas as pd
import math

# --- KONFIGURACE STRÁNKY ---
st.set_page_config(page_title="Kalkulátor Zastřešení", layout="wide")

# --- INTELIGENTNÍ NAČÍTÁNÍ DAT ---
def load_csv_robust(filename):
    """Zkouší různé oddělovače a kódování, dokud nenajde čitelná data."""
    separators = [';', ',']
    encodings = ['utf-8', 'cp1250', 'latin1'] # cp1250 je časté pro český Excel
    
    for enc in encodings:
        for sep in separators:
            try:
                df = pd.read_csv(filename, sep=sep, header=None, encoding=enc)
                # Základní kontrola: Musí to mít víc než 1 sloupec, aby to bylo použitelné
                if df.shape[1] > 1:
                    return df
            except:
                continue
    return None

@st.cache_data
def load_data():
    df_c = load_csv_robust('ceniky.csv')
    df_p = load_csv_robust('priplatky.csv')
    return df_c, df_p

# --- POMOCNÉ FUNKCE ---
def parse_value(raw_value):
    """Převede text '15%', '1 500 Kč' nebo '1.500' na číslo."""
    if pd.isna(raw_value): return 0
    s = str(raw_value).strip().replace(' ', '').replace('Kč', '').replace('Kc', '')
    
    # Procenta
    if '%' in s:
        try:
            return float(s.replace('%', '').replace(',', '.')) / 100.0
        except: return 0
    
    # Čísla
    try:
        return float(s.replace(',', '.'))
    except:
        return 0

def get_surcharge(df, search_term, is_rock=False):
    """Najde příplatek. Pokud Rock, hledá ve sloupci 2, jinak 1."""
    if df is None: return 0
    
    # Case-insensitive hledání
    mask = df[0].astype(str).str.contains(search_term, case=False, na=False)
    row = df[mask]
    
    if row.empty: return 0
    
    # Detekce sloupce
    # Pokud má DF dost sloupců, použijeme index 2 pro Rock
    col_idx = 2 if (is_rock and row.shape[1] > 2) else 1
    
    try:
        val = row.iloc[0, col_idx]
        # Pokud je buňka prázdná (NaN), zkusíme fallback na standard (sloupec 1)
        if pd.isna(val) or str(val).strip() == "":
            val = row.iloc[0, 1]
        return parse_value(val)
    except:
        # Fallback při chybě indexu
        try:
            return parse_value(row.iloc[0, 1])
        except:
            return 0

# --- VÝPOČTY ---
def calculate_geometry(width_mm, height_mm, length_mm):
    """Spočítá plochu střechy a čel (pro polykarbonát)."""
    w = width_mm / 1000.0
    h = height_mm / 1000.0
    l = length_mm / 1000.0
    
    # Aproximace elipsy
    a = w / 2
    b = h
    # Ramanujanův obvod
    perimeter = math.pi * (3*(a+b) - math.sqrt((3*a + b) * (a + 3*b)))
    arc_length = perimeter / 2
    
    roof_area = arc_length * l
    face_area = (math.pi * a * b) / 2
    
    return roof_area, face_area

def get_length_from_ceniky(df_c, modules):
    try:
        # Hledáme v řádku 4 (index 4), sloupec podle modulů
        col_idx = 1 + (modules - 2) * 2
        if col_idx < df_c.shape[1]:
            val = df_c.iloc[4, col_idx]
            return parse_value(val)
    except:
        pass
    return modules * 2150 # Fallback

def calculate_base_price(model, width, modules, df_c):
    if df_c is None: return 0,0,0, "Chyba ceníku"
    
    # 1. Najít model
    try:
        mask = df_c[0].astype(str).str.lower() == model.lower()
        if not mask.any(): return 0,0,0, f"Model '{model}' nenalezen v ceníku"
        start_index = df_c.index[mask].tolist()[0]
    except:
        return 0,0,0, "Chyba při hledání modelu"

    # 2. Najít řádek (šířka)
    offset = 1750 if model.upper() == "TERRACE" else 2750
    if width < (offset + 250):
        row_shift = 0
    else:
        row_shift = math.ceil((width - (offset + 250)) / 250)
        if row_shift < 0: row_shift = 0

    target_row = start_index + 1 + row_shift
    
    # Kontrola, zda jsme nepřejeli konec souboru
    if target_row >= len(df_c): return 0,0,0, "Šířka mimo rozsah ceníku"

    # 3. Najít sloupec (moduly)
    col_price = 1 + (modules - 2) * 2
    col_height = col_price + 1
    
    if col_height >= df_c.shape[1]: return 0,0,0, f"Počet modulů {modules} není v ceníku"

    # 4. Číst data
    try:
        raw_p = df_c.iloc[target_row, col_price]
        raw_h = df_c.iloc[target_row, col_height]
        
        price = parse_value(raw_p)
        height = parse_value(raw_h) * 1000
        length = get_length_from_ceniky(df_c, modules)
        
        if price == 0: return 0,0,0, "Cena nenalezena (0)"
        
        return price, height, length, None
    except Exception as e:
        return 0, 0, 0, f"Chyba čtení dat: {str(e)}"

# --- APLIKACE ---
st.title("🛠 Kalkulátor Zastřešení 6.0")

df_c, df_p = load_data()

# Diagnostika načtení
if df_c is None:
    st.error("❌ Chyba: Soubor 'ceniky.csv' se nepodařilo načíst. Zkontrolujte, zda je nahraný na GitHubu a zda není prázdný.")
    st.stop()
if df_p is None:
    st.error("❌ Chyba: Soubor 'priplatky.csv' se nepodařilo načíst.")
    st.stop()

# ================= VSTUPY =================
with st.sidebar:
    st.header("1. Parametry")
    model = st.selectbox("Model", ["PRACTIC", "HARMONY", "DREAM", "HORIZONT", "STAR", "ROCK", "TERRACE", "WAVE", "FLASH", "WING", "SUNSET"])
    is_rock = (model.upper() == "ROCK")
    
    sirka = st.number_input("Šířka (mm)", 2000, 9000, 3500, step=10)
    moduly = st.slider("Počet modulů", 2, 7, 3)
    
    st.markdown("---")
    st.header("2. Konstrukce")
    barva_typ = st.selectbox("Barva konstrukce", 
                             ["Stříbrný Elox (Bonus -10 000 Kč)", 
                              "Bronzový Elox", 
                              "Antracitový Elox", 
                              "RAL Nástřik"])
    
    st.write("Polykarbonát:")
    poly_strecha = st.checkbox("Plný polykarbonát - STŘECHA")
    poly_cela = st.checkbox("Plný polykarbonát - ČELA")
    change_color_poly = st.checkbox("Změna barvy polykarbonátu")
    
    st.markdown("---")
    st.header("3. Dveře")
    pocet_dvere_vc = st.number_input("Dveře v čele (ks)", 0, 2, 0)
    pocet_dvere_bok = st.number_input("Boční vstup (ks)", 0, 4, 0)
    zamykaci_klika = st.checkbox("Zamykací klika (všechny dveře)")
    klapka = st.checkbox("Větrací klapka")
    
    st.markdown("---")
    st.header("4. Koleje")
    pochozi_koleje = st.checkbox("Pochozí koleje")
    ext_draha_m = st.number_input("Prodloužení dráhy (m)", 0.0, 20.0, 0.0, step=0.5)
    podhori = st.checkbox("Zpevnění pro podhorskou oblast")
    
    st.markdown("---")
    st.header("5. Ostatní")
    km = st.number_input("Doprava (km celkem)", 0, 5000, 0)
    montaz = st.checkbox("Montáž", value=True)
    sleva_pct = st.number_input("Sleva (%)", 0, 100, 0)
    dph_sazba = st.selectbox("DPH", [21, 12, 0])

# ================= VÝPOČET =================
base_price, height, length, err = calculate_base_price(model, sirka, moduly, df_c)

if err:
    st.error(f"⚠️ Nelze vypočítat cenu: {err}")
    # Debug info
    with st.expander("Technické detaily chyby"):
        st.write(f"Načteno ceníků: {df_c.shape}")
        st.write(f"Načteno příplatků: {df_p.shape}")
else:
    items = []
    items.append({"pol": f"Zastřešení {model}", "det": f"{moduly} seg., Š: {sirka}mm", "cen": base_price})
    
    running = base_price
    
    # --- BARVY ---
    if "Stříbrný" in barva_typ:
        val = -10000
        items.append({"pol": "BONUS: Stříbrný Elox", "det": "", "cen": val})
        running += val
    elif "RAL" in barva_typ:
        val = get_surcharge(df_p, "RAL", is_rock) or 0.20
        c = base_price * val
        items.append({"pol": "Příplatek RAL", "det": f"{val*100:.0f}%", "cen": c})
        running += c
    elif "Bronz" in barva_typ:
        val = get_surcharge(df_p, "BR elox", is_rock) or 0.05
        c = base_price * val
        items.append({"pol":
