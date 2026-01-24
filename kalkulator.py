import streamlit as st
import pandas as pd
import math

# --- KONFIGURACE ---
st.set_page_config(page_title="Kalkulátor zastřešení", layout="wide")

# --- FUNKCE PRO NAČTENÍ DAT ---
@st.cache_data
def load_data():
    try:
        # Načítáme data, oddělovač je středník
        df_ceniky = pd.read_csv('ceniky.csv', sep=';', header=None)
        df_priplatky = pd.read_csv('priplatky.csv', sep=';', header=None)
        return df_ceniky, df_priplatky
    except FileNotFoundError:
        st.error("CHYBA: Nenalezeny soubory 'ceniky.csv' nebo 'priplatky.csv'. Nahrajte je prosím.")
        return None, None

# --- POMOCNÉ FUNKCE ---
def clean_price(value):
    """Převede text '1 200 Kč' nebo '15%' na číslo."""
    if pd.isna(value): return 0
    val_str = str(value).strip().replace(' ', '').replace('Kč', '').replace('Kc', '')
    
    # Detekce procent
    if '%' in val_str:
        return float(val_str.replace('%', '').replace(',', '.')) / 100.0
    
    # Detekce čísla
    try:
        return float(val_str.replace(',', '.'))
    except ValueError:
        return 0

# --- HLAVNÍ VÝPOČET ---
def calculate_price(model, width, modules, df_ceniky):
    # 1. Najít řádek modelu
    # Hledáme v prvním sloupci (index 0) název modelu
    try:
        # Převedeme na string a lowercase pro bezpečné hledání
        mask = df_ceniky[0].astype(str).str.lower() == model.lower()
        start_index = df_ceniky.index[mask].tolist()[0]
    except IndexError:
        return 0, 0, "Model nenalezen v ceníku"

    # 2. Určit posun řádku podle šířky (Logika z VBA)
    # Terrace má offset 1750, ostatní 2750
    offset = 1750 if model.upper() == "TERRACE" else 2750
    
    # Výpočet řádku: Každých 250mm je nový řádek
    # Logika: pokud je šířka 3000 a offset 2750 -> (250)/250 = 1. řádek posunu
    # Zaokrouhlujeme nahoru (ceil), protože "do 3m" zahrnuje vše pod 3m
    if width < (offset + 250):
        row_shift = 0
    else:
        row_shift = math.ceil((width - (offset + 250)) / 250)
        if row_shift < 0: row_shift = 0

    target_row = start_index + 1 + row_shift # +1 protože první řádek je název

    # 3. Určit sloupec podle modulů
    # 2 moduly = sloupec 1 (cena), sloupec 2 (výška)
    # 3 moduly = sloupec 3, 4 atd.
    # Vzorec: 1 + (moduly - 2) * 2
    col_price = 1 + (modules - 2) * 2
    col_height = col_price + 1

    # 4. Vytáhnout hodnotu
    try:
        raw_price = df_ceniky.iloc[target_row, col_price]
        raw_height = df_ceniky.iloc[target_row, col_height]
        
        price = clean_price(raw_price)
        # Výška je v tabulce v metrech (např. 0,91), převedeme na mm
        height = clean_price(raw_height) * 1000 
        
        return price, height, None
    except Exception as e:
        return 0, 0, f"Mimo rozsah ceníku (chyba: {e})"

# --- APLIKACE ---
st.title("🛠 Konfigurátor Zastřešení")
df_ceniky, df_priplatky = load_data()

if df_ceniky is not None:
    # 1. SLOUPEC - VSTUPY
    col_input, col_result = st.columns([1, 1.5])
    
    with col_input:
        st.subheader("1. Rozměry a Typ")
        models_list = ["PRACTIC", "HARMONY", "DREAM", "HORIZONT", "STAR", "ROCK", "TERRACE", "WAVE", "FLASH", "WING", "SUNSET"]
        
        sel_model = st.selectbox("Model zastřešení", models_list)
        sel_width = st.number_input("Šířka (mm)", min_value=2000, max_value=8000, value=3500, step=10)
        sel_modules = st.slider("Počet modulů", 2, 7, 3)

        st.subheader("2. Doplňky")
        # Checkboxy pro příplatky
        opt_ral = st.checkbox("Nástřik RAL (+15%)")
        opt_door = st.checkbox("Dveře v čele")
        opt_klapka = st.checkbox("Větrací klapka")
        opt_koleje = st.checkbox("Pochozí koleje")
        opt_montaz = st.selectbox("Montáž", ["Bez montáže", "Montáž ČR", "Montáž Zahraničí"])

    # 2. SLOUPEC - VÝPOČET
    with col_result:
        st.subheader("Kalkulace")
        
        base_price, height, error = calculate_price(sel_model, sel_width, sel_modules, df_ceniky)

        if error:
            st.warning(f"⚠ {error}. Zkuste upravit rozměry.")
        else:
            final_price = base_price
            items = []
            
            # Výpis základu
            items.append(f"**Základ ({sel_model}):** {base_price:,.0f} Kč")
            st.info(f"📏 Výška nejvyššího modulu: cca {height:.0f} mm")

            # Výpočet příplatků
            def get_surcharge(search_term):
                """Najde cenu v priplatky.csv podle názvu"""
                row = df_priplatky[df_priplatky[0].astype(str).str.contains(search_term, case=False, na=False)]
                if not row.empty:
                    return clean_price(row.iloc[0, 1])
                return 0

            # Logika příplatků
            surcharges = 0
            
            if opt_ral:
                # RAL je procentuální
                ral_cost = base_price * 0.15 
                surcharges += ral_cost
                items.append(f"Nástřik RAL (15%): {ral_cost:,.0f} Kč")

            if opt_door:
                door_cost = get_surcharge("Jednokřídlé dveře")
                # Fallback kdyby v CSV nebyla cena
                if door_cost == 0: door_cost = 5000 
                surcharges += door_cost
                items.append(f"Dveře: {door_cost:,.0f} Kč")

            if opt_klapka:
                klapka_cost = get_surcharge("klapka")
                if klapka_cost == 0: klapka_cost = 7000
                surcharges += klapka_cost
                items.append(f"Větrací klapka: {klapka_cost:,.0f} Kč")

            if opt_montaz == "Montáž ČR":
                montaz_pct = get_surcharge("Montáž zastřešení v ČR") # v CSV je např. 0.06 nebo 0.08
                if montaz_pct == 0: montaz_pct = 0.08
                montaz_cost = base_price * montaz_pct
                surcharges += montaz_cost
                items.append(f"Montáž ČR ({montaz_pct*100:.0f}%): {montaz_cost:,.0f} Kč")

            # Finální součet
            final_price += surcharges

            # Vizuální výpis účtenky
            st.markdown("---")
            for i in items:
                st.write(i)
            st.markdown("---")
            
            st.markdown(f"### Celkem bez DPH: {final_price:,.0f} Kč")
            st.markdown(f"**Celkem s DPH (21%): {final_price * 1.21:,.0f} Kč**")