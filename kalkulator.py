import streamlit as st
import pandas as pd
import math

# --- KONFIGURACE STRÁNKY ---
st.set_page_config(page_title="Kalkulátor Zastřešení", layout="wide")

# --- NAČTENÍ DAT ---
@st.cache_data
def load_data():
    try:
        # Načítáme CSV, předpokládáme středník jako oddělovač
        df_ceniky = pd.read_csv('ceniky.csv', sep=';', header=None)
        df_priplatky = pd.read_csv('priplatky.csv', sep=';', header=None)
        return df_ceniky, df_priplatky
    except FileNotFoundError:
        return None, None

# --- POMOCNÉ FUNKCE ---
def parse_value(raw_value):
    """
    Zjistí, jestli je hodnota fixní částka (5000) nebo procento (0.15).
    Vrací tuple: (typ, hodnota). Typ může být 'fix' nebo 'pct'.
    """
    if pd.isna(raw_value): return 'fix', 0
    s = str(raw_value).strip().replace(' ', '').replace('Kč', '').replace('Kc', '')
    
    if '%' in s:
        try:
            val = float(s.replace('%', '').replace(',', '.')) / 100.0
            return 'pct', val
        except:
            return 'fix', 0
    else:
        try:
            val = float(s.replace(',', '.'))
            return 'fix', val
        except:
            return 'fix', 0

def get_surcharge_data(df_priplatky, search_term):
    """Najde řádek v příplatcích a vrátí jeho hodnotu (fix nebo %)"""
    if df_priplatky is None: return 'fix', 0
    
    # Hledáme text bez ohledu na velká/malá písmena
    mask = df_priplatky[0].astype(str).str.contains(search_term, case=False, na=False)
    row = df_priplatky[mask]
    
    if not row.empty:
        # Sloupec 1 obvykle obsahuje cenu pro standardní modely
        raw = row.iloc[0, 1] 
        return parse_value(raw)
    return 'fix', 0

# --- VÝPOČET ZÁKLADNÍ CENY (Jádro z VBA) ---
def calculate_base_price(model, width, modules, df_ceniky):
    try:
        # Najít startovní řádek modelu
        mask = df_ceniky[0].astype(str).str.lower() == model.lower()
        start_index = df_ceniky.index[mask].tolist()[0]
    except IndexError:
        return 0, 0, "Model nenalezen"

    # Offsety (Terrace vs Ostatní) - převzato z VBA logiky
    offset = 1750 if model.upper() == "TERRACE" else 2750
    
    # Výpočet řádku (skoky po 250mm)
    if width < (offset + 250):
        row_shift = 0
    else:
        row_shift = math.ceil((width - (offset + 250)) / 250)
        if row_shift < 0: row_shift = 0

    target_row = start_index + 1 + row_shift

    # Výpočet sloupce
    col_price = 1 + (modules - 2) * 2
    col_height = col_price + 1

    try:
        raw_p = df_ceniky.iloc[target_row, col_price]
        raw_h = df_ceniky.iloc[target_row, col_height]
        
        _, price = parse_value(raw_p)
        _, height = parse_value(raw_h)
        return price, height * 1000, None # Výška je v metrech, převádíme na mm
    except:
        return 0, 0, "Rozměr mimo ceník"

# --- HLAVNÍ APLIKACE ---
st.title("🛠 Kalkulátor Zastřešení")

df_c, df_p = load_data()

if df_c is None:
    st.error("Chyba: Nahrajte soubory ceniky.csv a priplatky.csv na GitHub.")
    st.stop()

# 1. ČÁST: Vstupy (Levý panel)
with st.sidebar:
    st.header("Zadání parametrů")
    
    model = st.selectbox("Model", ["PRACTIC", "HARMONY", "DREAM", "HORIZONT", "STAR", "ROCK", "TERRACE", "WAVE", "FLASH", "WING", "SUNSET"])
    sirka = st.number_input("Šířka (mm)", 2000, 8000, 3500, step=10)
    moduly = st.slider("Počet modulů", 2, 7, 3)
    
    st.markdown("---")
    st.subheader("Konfigurace")
    
    # Logika zobrazení checkboxů (dynamická)
    opt_ral = st.checkbox("Nástřik RAL")
    opt_podhori = st.checkbox("Zpevnění pro podhorskou oblast")
    
    # Plný polykarbonát (často se počítá za modul)
    opt_poly_modul = st.checkbox("Plný polykarbonát v modulech")
    
    st.markdown("---")
    st.subheader("Doplňky")
    opt_dvere_vc = st.checkbox("Dveře ve velkém čele")
    opt_klapka = st.checkbox("Větrací klapka")
    opt_koleje = st.checkbox("Pochozí koleje")
    
    st.markdown("---")
    # Montáž je specifická - výběr typu
    typ_montaze = st.radio("Montáž", ["Bez montáže", "Montáž v ČR", "Montáž v zahraničí"])

# 2. ČÁST: Výpočet a Výstup (Hlavní okno)
base_price, height, err = calculate_base_price(model, sirka, moduly, df_c)

if err:
    st.warning(f"⚠ {err}")
else:
    # --- LOGIKA CENOTVORBY ---
    final_price = base_price
    offer_items = [] # Seznam pro výpis položek
    
    # 1. Základ
    offer_items.append({"polozka": f"Zastřešení {model} ({moduly} moduly)", "cena": base_price, "info": f"Šířka: {sirka} mm, Výška: {height:.0f} mm"})
    
    # 2. Procentuální příplatky (počítají se ze základu)
    pct_surcharges = 0
    
    if opt_ral:
        typ, val = get_surcharge_data(df_p, "RAL") # Hledá v CSV "RAL"
        # Pokud v CSV nic nenajde, použije 15% jako fallback
        if typ == 'fix' and val == 0: val = 0.15 
        
        cost = base_price * val
        pct_surcharges += cost
        offer_items.append({"polozka": "Nástřik RAL", "cena": cost, "info": f"Příplatek {val*100:.0f}%"})

    if opt_podhori:
        typ, val = get_surcharge_data(df_p, "podhorskou")
        if val == 0: val = 0.15
        cost = base_price * val
        pct_surcharges += cost
        offer_items.append({"polozka": "Zpevnění (Podhorská obl.)", "cena": cost, "info": f"Příplatek {val*100:.0f}%"})

    final_price += pct_surcharges

    # 3. Fixní příplatky a příplatky za kus/modul
    fix_surcharges = 0
    
    if opt_poly_modul:
        # Většinou cena za modul * počet modulů
        typ, val = get_surcharge_data(df_p, "Plný polykarbonát")
        if val == 0: val = 1000 # Fallback
        cost = val * moduly # Počítáme krát počet modulů
        fix_surcharges += cost
        offer_items.append({"polozka": "Plný polykarbonát (čirý)", "cena": cost, "info": f"{val:,.0f} Kč x {moduly} modulů"})

    if opt_dvere_vc:
        typ, val = get_surcharge_data(df_p, "Jednokřídlé dveře")
        if val == 0: val = 5000
        fix_surcharges += val
        offer_items.append({"polozka": "Dveře ve velkém čele", "cena": val, "info": ""})

    if opt_klapka:
        typ, val = get_surcharge_data(df_p, "klapka")
        if val == 0: val = 7000
        fix_surcharges += val
        offer_items.append({"polozka": "Větrací klapka", "cena": val, "info": ""})
        
    if opt_koleje:
        # Pochozí koleje - ve VBA je to často zdarma nebo příplatek
        typ, val = get_surcharge_data(df_p, "Pochozí kolejnice") 
        # Zde záleží na logice - někdy je to za bm, někdy paušál. 
        # Pro ukázku bereme paušál z CSV
        fix_surcharges += val
        offer_items.append({"polozka": "Pochozí koleje", "cena": val, "info": ""})

    final_price += fix_surcharges

    # 4. Montáž (Počítá se obvykle z celkové ceny materiálu nebo ze základu? 
    # Většinou ze základu, ale upravíme dle potřeby)
    montaz_price = 0
    if typ_montaze != "Bez montáže":
        search = "zahraničí" if "zahraničí" in typ_montaze else "v ČR"
        typ, val = get_surcharge_data(df_p, f"Montáž zastřešení {search}")
        
        if val == 0: val = 0.08 # Fallback 8%
        
        montaz_price = base_price * val
        offer_items.append({"polozka": typ_montaze, "cena": montaz_price, "info": f"Sazba {val*100:.1f}%"})
    
    final_price += montaz_price

    # --- VIZUÁLNÍ VÝSTUP (CENOVÁ NABÍDKA) ---
    st.subheader("Cenová kalkulace")
    
    # Tabulka položek
    df_offer = pd.DataFrame(offer_items)
    # Formátování čísel pro hezčí zobrazení
    if not df_offer.empty:
        col1, col2, col3 = st.columns([3, 2, 1])
        with col1:
            st.write("**Položka**")
        with col2:
            st.write("**Detail**")
        with col3:
            st.write("**Cena**")
        st.divider()
        
        for index, row in df_offer.iterrows():
            c1, c2, c3 = st.columns([3, 2, 1])
            c1.write(row['polozka'])
            c2.caption(row['info'])
            c3.write(f"{row['cena']:,.0f} Kč")
            
    st.divider()
    
    # Celkové součty
    total_col1, total_col2 = st.columns([4, 2])
    
    with total_col2:
        st.write(f"Cena bez DPH: **{final_price:,.0f} Kč**")
        dph = final_price * 0.21
        st.write(f"DPH (21%): {dph:,.0f} Kč")
        st.markdown(f"### Celkem: {final_price * 1.21:,.0f} Kč")
