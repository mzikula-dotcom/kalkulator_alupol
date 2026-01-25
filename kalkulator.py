import streamlit as st
import pandas as pd
import math
import io
import os
from datetime import date, timedelta
from fpdf import FPDF

# --- KONFIGURACE STRÁNKY ---
st.set_page_config(page_title="Kalkulátor Rentmil", layout="wide", page_icon="🏊‍♂️")

# ==========================================
# 1. DATA
# ==========================================
csv_ceniky_data = """Počet modulů;2;;3;;4;;5;;6;;7;
Cena;910 Kč;;2 729 Kč;;5 459 Kč;;9 098 Kč;;13 647 Kč;;19 106 Kč;
;;;;;;;;;;;;
;;;;;;;;;;;;
Délka zastřešení;4 336;mm;6 446;mm;8 556;mm;10 666;mm;12 776;mm;14 886;mm
;;;;;;;;;;;;
;;;;;;;;;;;;
;;;;;;;;;;;;
PRACTIC;2;;3;;4;;5;;6;;7;
do 3 m;60 461;0,91;84 067;0,96;118 839;1,01;148 254;1,06;179 550;1,11;212 648;1,16
do 3,25 m;63 496;0,98;88 016;1,03;122 330;1,08;152 373;1,13;184 166;1,18;217 770;1,23
do 3,5 m;66 532;1,05;91 965;1,10;126 931;1,15;157 877;1,20;190 459;1,25;224 879;1,30
do 3,75 m;72 106;1,12;99 702;1,17;131 130;1,22;162 726;1,27;195 997;1,32;230 901;1,37
do 4 m;76 766;1,19;106 113;1,24;137 069;1,29;169 747;1,34;204 162;1,39;240 035;1,44
do 4,25 m;78 944;1,26;108 822;1,31;140 340;1,36;173 518;1,41;208 335;1,46;246 388;1,51
do 4,5 m;81 853;1,33;112 543;1,38;144 917;1,43;178 905;1,48;214 452;1,53;255 027;1,58
do 4,75 m;87 470;1,40;119 552;1,45;155 692;1,50;188 648;1,55;225 607;1,60;265 889;1,65
do 5 m;93 087;1,47;126 561;1,52;166 467;1,57;198 391;1,62;236 762;1,67;276 751;1,72
do 5,25 m;97 395;1,54;132 255;1,59;171 111;1,64;206 824;1,69;246 599;1,74;287 925;1,79
do 5,5 m;101 702;1,61;137 949;1,66;175 755;1,71;215 257;1,76;256 437;1,81;299 099;1,86
HARMONY;2;;3;;4;;5;;6;;7;
do 3 m;68 337;0,91;95 241;0,96;133 931;1,01;167 447;1,06;203 762;1,11;240 379;1,16
do 3,25 m;71 372;0,98;99 190;1,03;137 423;1,08;171 566;1,13;208 379;1,18;245 501;1,23
do 3,5 m;74 407;1,05;103 139;1,10;142 024;1,15;177 070;1,20;214 671;1,25;252 611;1,30
DREAM;2;;3;;4;;5;;6;;7;
do 3 m;68 337;0,91;95 241;0,96;133 931;1,01;167 447;1,06;203 762;1,11;240 379;1,16
do 3,25 m;71 372;0,98;99 190;1,03;137 423;1,08;171 566;1,13;208 379;1,18;245 501;1,23
HORIZONT;2;;3;;4;;5;;6;;7;
do 3 m;73 686;0,65;103 133;0,70;146 100;0,75;183 711;0,80;223 533;0,85;263 671;0,90
do 3,25 m;76 721;0,68;107 082;0,73;149 591;0,78;187 830;0,83;228 149;0,88;268 793;0,93
STAR;2;;3;;4;;5;;6;;7;
do 3 m;60 461;0,91;84 067;0,96;118 839;1,01;148 254;1,06;179 550;1,11;212 648;1,16
do 3,25 m;63 496;0,98;88 016;1,03;122 330;1,08;152 373;1,13;184 166;1,18;217 770;1,23
ROCK;2;;3;;4;;5;;6;;7;
do 3 m;68 337;0,91;95 241;0,96;133 931;1,01;167 447;1,06;203 762;1,11;240 379;1,16
TERRACE;2;;3;;4;;5;;6;;7;
do 2 m;81 151;2,20;117 726;2,27;150 820;2,33;185 997;2,40;222 908;2,46;260 527;2,53
do 2,25 m;85 502;2,25;122 482;2,32;155 055;2,38;191 776;2,45;228 691;2,51;268 473;2,58
do 2,5 m;89 852;2,30;127 239;2,37;159 289;2,43;197 554;2,50;234 473;2,56;276 419;2,63
do 2,75 m;92 882;2,34;132 623;2,41;165 615;2,47;204 107;2,54;241 393;2,60;284 343;2,67
do 3 m;95 913;2,38;138 006;2,45;171 941;2,51;210 660;2,58;248 314;2,64;292 268;2,71
"""

csv_priplatky_data = """,,Rock,
Jednokřídlé dveře do 1 m,5 000 Kč,5 000 Kč,
Jednokřídlé dveře nad 1 m,7 000 Kč,7 000 Kč,
Dveře pro boční vstup,7 000 Kč,7 000 Kč,
Uzamykání dveří,800 Kč,800 Kč,
Větrací klapka,7 000 Kč,7 000 Kč,
Zkrácení modulu,1 500 Kč,1 500 Kč,
Prodloužení modulu,3 000 Kč,3 000 Kč,
Prodloužení modulu za metr,2 000 Kč,2 000 Kč,
Zvýšení zastřešení,3%,2%,
Změna barvy polykarbonátu,7%,7%,
Zpevnění pro podhorskou oblast,15%,15%,
Plný polykarbonát,1 000 Kč,1 000 Kč,
Montáž zastřešení v ČR,6%,8%,5 500 Kč
Montáž zastřešení v zahraničí,8%,10%,
Jeden metr koleje,220 Kč,330 Kč,
Uzamykání segmentu,1 000 Kč,1 000 Kč,
Pochozí kolejnice,330 Kč,380 Kč,
Plexi,600 Kč,600 Kč,
Příplatek za BR elox,5%,5%,
Příplatek za RAL nástřik,20%,20%,
Příplatek za antracit elox,5%,5%"""

@st.cache_data
def load_data():
    try:
        df_c = pd.read_csv(io.StringIO(csv_ceniky_data), sep=';', header=None)
        df_p = pd.read_csv(io.StringIO(csv_priplatky_data), sep=',', header=None)
        return df_c, df_p
    except Exception as e:
        st.error(f"Chyba dat: {e}")
        return None, None

# ==========================================
# 2. GENERÁTOR PDF (RENTMIL DESIGN)
# ==========================================
class PDF(FPDF):
    def header(self):
        # Barvy
        RENTMIL_BLUE = (0, 75, 150)
        RENTMIL_ORANGE = (240, 120, 0)
        
        # Bezpečné načtení obrázků
        logo_files = ["logo.png", "Logo.png", "LOGO.png", "logo.jpg"]
        mnich_files = ["mnich.png", "Mnich.png", "MNICH.png", "mnich.jpg"]
        
        found_logo = next((f for f in logo_files if os.path.exists(f)), None)
        found_mnich = next((f for f in mnich_files if os.path.exists(f)), None)
        
        if found_logo: self.image(found_logo, 10, 8, 45)
        if found_mnich: self.image(found_mnich, 170, 8, 30)

        # Nadpis
        try:
            self.set_font('DejaVu', 'B', 20)
        except:
            self.set_font('Arial', 'B', 20)
            
        self.set_text_color(*RENTMIL_BLUE)
        self.cell(80) 
        self.cell(30, 10, 'CENOVÁ NABÍDKA', 0, 0, 'C')
        self.ln(12)
        
        # Čára
        self.set_draw_color(*RENTMIL_ORANGE)
        self.set_line_width(0.8)
        self.line(10, 25, 200, 25)
        self.ln(15)

    def footer(self):
        RENTMIL_BLUE = (0, 75, 150)
        self.set_y(-20)
        self.set_draw_color(*RENTMIL_BLUE)
        self.set_line_width(0.5)
        self.line(10, 275, 200, 275)
        
        try:
            self.set_font('DejaVu', '', 8)
        except:
            self.set_font('Arial', '', 8)
            
        self.set_text_color(100, 100, 100)
        self.cell(0, 5, 'Rentmil s.r.o. | www.rentmil.cz | bazeny@rentmil.cz', 0, 1, 'C')
        self.cell(0, 5, f'Strana {self.page_no()}', 0, 0, 'C')

def create_pdf(zak_udaje, items, totals):
    pdf = PDF()
    
    # Fonty - Fallback
    font_path = "font.ttf"
    has_font = os.path.exists(font_path)
    
    if has_font:
        pdf.add_font('DejaVu', '', font_path, uni=True)
        pdf.add_font('DejaVu', 'B', font_path, uni=True)
        pdf.set_font('DejaVu', '', 10)
    else:
        pdf.set_font('Arial', '', 10)

    pdf.add_page()
    
    RENTMIL_BLUE = (0, 75, 150)
    RENTMIL_ORANGE = (240, 120, 0)
    DARK_GREY = (50, 50, 50)
    
    pdf.set_text_color(*DARK_GREY)
    
    # --- DODAVATEL / ODBĚRATEL ---
    x_start = 10
    y_start = 35
    pdf.set_xy(x_start, y_start)
    
    pdf.set_font('', 'B', 11)
    pdf.set_text_color(*RENTMIL_BLUE)
    pdf.cell(90, 6, "DODAVATEL:", 0, 1)
    pdf.set_text_color(*DARK_GREY)
    
    pdf.set_font('', 'B', 10)
    pdf.cell(90, 5, "Rentmil s.r.o.", 0, 1)
    pdf.set_font('', '', 9)
    pdf.cell(90, 5, "Lidická 1233/26, 323 00 Plzeň", 0, 1)
    pdf.cell(90, 5, "IČO: 26342910, DIČ: CZ26342910", 0, 1)
    pdf.cell(90, 5, "Tel: 737 222 004, 377 530 806", 0, 1)
    pdf.cell(90, 5, "Email: bazeny@rentmil.cz", 0, 1)
    pdf.cell(90, 5, "Web: www.rentmil.cz", 0, 1)
    
    pdf.ln(3)
    pdf.set_font('', 'B', 9)
    
    # Ošetření češtiny pokud chybí font
    vypracoval_txt = zak_udaje['vypracoval'] if has_font else "Vypracoval"
    pdf.cell(90, 5, f"Vypracoval: {vypracoval_txt}", 0, 1)
    
    # Odběratel
    pdf.set_xy(110, y_start)
    pdf.set_font('', 'B', 11)
    pdf.set_text_color(*RENTMIL_BLUE)
    pdf.cell(90, 6, "ODBĚRATEL:", 0, 1)
    pdf.set_text_color(*DARK_GREY)
    
    pdf.set_font('', 'B', 11)
    pdf.set_x(110)
    
    # Fallback pro jméno bez diakritiky
    jmeno_txt = zak_udaje['jmeno'] if has_font else "Zakaznik"
    pdf.cell(90, 6, jmeno_txt, 0, 1)
    
    pdf.set_font('', '', 10)
    pdf.set_x(110)
    
    adr_txt = zak_udaje['adresa'] if has_font else ""
    pdf.multi_cell(80, 5, f"{adr_txt}\n\nTel: {zak_udaje['tel']}\nEmail: {zak_udaje['email']}")
    
    pdf.set_xy(110, y_start + 40)
    pdf.set_font('', 'B', 9)
    pdf.cell(40, 5, "Datum vystavení:", 0, 0)
    pdf.set_font('', '', 9)
    pdf.cell(40, 5, f"{zak_udaje['datum']}", 0, 1)
    
    pdf.set_x(110)
    pdf.set_font('', 'B', 9)
    pdf.cell(40, 5, "Platnost nabídky:", 0, 0)
    pdf.set_font('', '', 9)
    pdf.cell(40, 5, f"{zak_udaje['platnost']}", 0, 1)
    
    pdf.ln(10)
    
    # --- TABULKA ---
    pdf.set_fill_color(*RENTMIL_BLUE)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font('', 'B', 10)
    pdf.cell(90, 8, " Položka", 0, 0, 'L', True)
    pdf.cell(60, 8, " Detail", 0, 0, 'L', True)
    pdf.cell(40, 8, "Cena (Kč) ", 0, 1, 'R', True)
    
    pdf.set_text_color(*DARK_GREY)
    pdf.set_font('', '', 10)
    
    fill = False
    for item in items:
        if fill: pdf.set_fill_color(245, 245, 245)
        else: pdf.set_fill_color(255, 255, 255)
        
        # Odstranění diakritiky pokud chybí font
        pol_txt = item['pol'] if has_font else item['pol'].encode('ascii', 'ignore').decode()
        det_txt = item['det'] if has_font else item['det'].encode('ascii', 'ignore').decode()
        
        pdf.cell(90, 7, " " + pol_txt, 0, 0, 'L', True)
        pdf.cell(60, 7, " " + det_txt, 0, 0, 'L', True)
        pdf.cell(40, 7, f"{item['cen']:,.0f} ".replace(',', ' '), 0, 1, 'R', True)
        
        pdf.set_draw_color(230, 230, 230)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        fill = not fill

    pdf.ln(5)
    
    # --- SOUČTY ---
    pdf.set_x(110)
    pdf.set_font('', '', 10)
    pdf.cell(50, 6, "Cena bez DPH:", 0, 0, 'R')
    pdf.cell(30, 6, f"{totals['bez_dph']:,.0f} Kč".replace(',', ' '), 0, 1, 'R')
    
    pdf.set_x(110)
    pdf.cell(50, 6, f"DPH ({totals['sazba_dph']}%):", 0, 0, 'R')
    pdf.cell(30, 6, f"{totals['dph']:,.0f} Kč".replace(',', ' '), 0, 1, 'R')
    
    pdf.ln(3)
    pdf.set_x(110)
    pdf.set_font('', 'B', 14)
    pdf.set_text_color(*RENTMIL_ORANGE)
    pdf.cell(50, 10, "CELKEM K ÚHRADĚ:", 0, 0, 'R')
    pdf.cell(30, 10, f"{totals['s_dph']:,.0f} Kč".replace(',', ' '), 0, 1, 'R')
    
    pdf.set_text_color(*DARK_GREY)
    
    # --- PATIČKA DODÁNÍ ---
    pdf.ln(15)
    pdf.set_fill_color(240, 248, 255)
    pdf.set_draw_color(*RENTMIL_BLUE)
    pdf.rect(10, pdf.get_y(), 190, 20, 'DF')
    
    pdf.set_xy(12, pdf.get_y() + 2)
    pdf.set_font('', 'B', 10)
    txt_termin = "Termín dodání:" if has_font else "Termin dodani:"
    pdf.cell(40, 6, txt_termin, 0, 1)
    
    pdf.set_font('', '', 10) # <-- ZMĚNA: Použito obyčejné písmo, ne kurzíva 'I'
    pdf.set_x(12)
    term_val = zak_udaje['termin'] if has_font else "Dle dohody"
    pdf.cell(0, 6, term_val, 0, 1)
    
    pdf.set_x(12)
    # Poznámka dole - také obyčejné písmo (nebo Bold 'B', ale ne 'I')
    pdf.set_font('', '', 8) 
    note = "Poznámka: Tato nabídka je nezávazná. Pro potvrzení kontaktujte svého obchodního zástupce." if has_font else "Poznamka: Tato nabidka je nezavazna."
    pdf.cell(0, 6, note, 0, 1)
    
    return pdf.output(dest='S').encode('latin-1')

# ==========================================
# 3. POMOCNÉ FUNKCE
# ==========================================
def parse_value(raw_value):
    if pd.isna(raw_value): return 0
    s = str(raw_value).strip().replace(' ', '').replace('Kč', '').replace('Kc', '')
    if '%' in s:
        try: return float(s.replace('%', '').replace(',', '.')) / 100.0
        except: return 0
    try: return float(s.replace(',', '.'))
    except: return 0

def get_surcharge(df, search_term, is_rock=False):
    if df is None: return 0
    mask = df[0].astype(str).str.contains(search_term, case=False, na=False)
    row = df[mask]
    if row.empty: return 0
    col_idx = 2 if (is_rock and row.shape[1] > 2) else 1
    try:
        val = row.iloc[0, col_idx]
        if pd.isna(val) or str(val).strip() == "": val = row.iloc[0, 1]
        return parse_value(val)
    except:
        return parse_value(row.iloc[0, 1])

def calculate_geometry(width_mm, height_mm, length_mm):
    w, h, l = width_mm/1000.0, height_mm/1000.0, length_mm/1000.0
    a, b = w/2, h
    perimeter = math.pi * (3*(a+b) - math.sqrt((3*a + b) * (a + 3*b)))
    arc_length = perimeter / 2
    roof_area = arc_length * l
    face_area = (math.pi * a * b) / 2
    return roof_area, face_area

def get_length_from_ceniky(df_c, modules):
    try:
        col_idx = 1 + (modules - 2) * 2
        val = df_c.iloc[4, col_idx]
        return parse_value(val)
    except:
        return modules * 2150

def calculate_base_price(model, width, modules, df_c):
    if df_c is None: return 0,0,0, "Chyba dat"
    try:
        mask = df_c[0].astype(str).str.lower() == model.lower()
        if not mask.any(): 
            mask = df_c[0].astype(str).str.lower() == "practic"
        start_index = df_c.index[mask].tolist()[0]
    except: return 0,0,0, "Model nenalezen"

    offset = 1750 if model.upper() == "TERRACE" else 2750
    row_shift = math.ceil((width - (offset + 250)) / 250) if width >= (offset + 250) else 0
    target_row = start_index + 1 + row_shift
    col_price = 1 + (modules - 2) * 2
    col_height = col_price + 1

    try:
        price = parse_value(df_c.iloc[target_row, col_price])
        height = parse_value(df_c.iloc[target_row, col_height]) * 1000
        length = get_length_from_ceniky(df_c, modules)
        if price == 0: return 0,0,0, "Cena 0 nebo mimo rozsah"
        return price, height, length, None
    except: return 0,0,0, "Mimo rozsah"

# ==========================================
# 4. HLAVNÍ APLIKACE
# ==========================================
st.title("🛠 Konfigurátor Zastřešení")
df_c, df_p = load_data()

# --- ZÁKAZNÍK ---
with st.expander("👤 Údaje o zákazníkovi a nabídce", expanded=True):
    col_cust1, col_cust2 = st.columns(2)
    with col_cust1:
        st.subheader("Zákazník")
        zak_jmeno = st.text_input("Jméno a příjmení")
        zak_adresa = st.text_input("Adresa")
        zak_tel = st.text_input("Telefon")
        zak_email = st.text_input("Email")
    with col_cust2:
        st.subheader("Nabídka")
        vypracoval = st.selectbox("Vypracoval:", ["Martin Zikula", "Zuzana Zikulová", "Drahoslav Houška", "Ivan Reif", "Lenka Finklarová"])
        col_d1, col_d2 = st.columns(2)
        with col_d1: platnost_dny = st.number_input("Platnost (dní)", value=10, min_value=1)
        with col_d2: 
            datum_vystaveni = date.today()
            platnost_do = datum_vystaveni + timedelta(days=platnost_dny)
            st.date_input("Platnost do:", value=platnost_do, disabled=True)
        termin_dodani = st.text_input("Termín dodání", value="dle dohody (cca 6-8 týdnů)")

# --- SIDEBAR ---
with st.sidebar:
    st.header("1. Parametry")
    model = st.selectbox("Model", ["PRACTIC", "HARMONY", "DREAM", "HORIZONT", "STAR", "ROCK", "TERRACE"])
    is_rock = (model.upper() == "ROCK")
    sirka = st.number_input("Šířka (mm)", 2000, 8000, 3500, step=10)
    moduly = st.slider("Počet modulů", 2, 7, 3)

    st.markdown("---")
    st.header("2. Barvy a Polykarbonát")
    barva_typ = st.selectbox("Barva konstrukce", ["Stříbrný Elox (Bonus -10 000 Kč)", "Bronzový Elox", "Antracitový Elox", "RAL Nástřik"])
    poly_strecha = st.checkbox("Plný polykarbonát - STŘECHA")
    poly_cela = st.checkbox("Plný polykarbonát - ČELA")
    change_color_poly = st.checkbox("Změna barvy polykarbonátu")

    st.markdown("---")
    st.header("3. Úpravy modulů")
    zkraceni_ks = st.number_input("Zkrácení (ks)", 0, moduly, 0)
    prodlouzeni_ks = st.number_input("Prodloužení (ks)", 0, moduly, 0)
    prodlouzeni_mm = st.number_input("Délka prodloužení (mm)", 0, 2000, 0, step=10)

    st.markdown("---")
    st.header("4. Doplňky")
    pocet_dvere_vc = st.number_input("Dveře v čele (ks)", 0, 2, 0)
    pocet_dvere_bok = st.number_input("Boční vstup (ks)", 0, 4, 0)
    zamykaci_klika = st.checkbox("Zamykací klika")
    klapka = st.checkbox("Větrací klapka")
    pochozi_koleje = st.checkbox("Pochozí koleje")
    ext_draha_m = st.number_input("Prodloužení dráhy (m)", 0.0, 20.0, 0.0, step=0.5)
    podhori = st.checkbox("Zpevnění Podhoří")

    st.markdown("---")
    st.header("5. Ostatní")
    km = st.number_input("Doprava (km)", 0, 5000, 0)
    montaz = st.checkbox("Montáž", value=True)
    sleva_pct = st.number_input("Sleva (%)", 0, 100, 0)
    dph_sazba = st.selectbox("DPH", [21, 12, 0])

# --- VÝPOČET ---
base_price, height, length, err = calculate_base_price(model, sirka, moduly, df_c)

if err:
    st.error(f"⚠️ Nelze vypočítat: {err}")
else:
    items = []
    items.append({"pol": f"Zastřešení {model}", "det": f"{moduly} seg., Š: {sirka}mm", "cen": base_price})
    running = base_price

    # Úpravy délky
    if zkraceni_ks > 0:
        val = get_surcharge(df_p, "Zkrácení modulu", is_rock) or 1500
        cost = zkraceni_ks * val
        items.append({"pol": "Zkrácení modulů", "det": f"{zkraceni_ks} ks x {val} Kč", "cen": cost})
        running += cost
    if prodlouzeni_ks > 0 and prodlouzeni_mm > 0:
        fix = get_surcharge(df_p, "Prodloužení modulu", is_rock) or 3000
        per_m = get_surcharge(df_p, "za metr", is_rock) or 2000
        c = prodlouzeni_ks * (fix + (prodlouzeni_mm/1000.0 * per_m))
        items.append({"pol": "Prodloužení modulů", "det": f"{prodlouzeni_ks} ks á {prodlouzeni_mm}mm", "cen": c})
        running += c

    # Barvy
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
        items.append({"pol": "Příplatek Bronz", "det": f"{val*100:.0f}%", "cen": c})
        running += c
    elif "Antracit" in barva_typ:
        val = get_surcharge(df_p, "antracit elox", is_rock) or 0.05
        c = base_price * val
        items.append({"pol": "Příplatek Antracit", "det": f"{val*100:.0f}%", "cen": c})
        running += c

    # Poly
    roof_a, face_a = calculate_geometry(sirka, height, length)
    poly_p = get_surcharge(df_p, "Plný polykarbonát", is_rock) or 1000
    if poly_strecha:
        c = roof_a * poly_p
        items.append({"pol": "Plný poly (Střecha)", "det": f"{roof_a:.1f} m²", "cen": c})
        running += c
    if poly_cela:
        c = (face_a * 2) * poly_p
        items.append({"pol": "Plný poly (Čela)", "det": f"{face_a*2:.1f} m²", "cen": c})
        running += c
    if change_color_poly:
        val = get_surcharge(df_p, "barvy poly", is_rock) or 0.07
        c = base_price * val
        items.append({"pol": "Změna barvy poly", "det": f"{val*100:.0f}%", "cen": c})
        running += c

    # Podhoří
    if podhori:
        val = get_surcharge(df_p, "podhorskou", is_rock) or 0.15
        c = base_price * val
        items.append({"pol": "Zpevnění Podhoří", "det": f"{val*100:.0f}%", "cen": c})
        running += c

    # Dveře
    doors = []
    p_vc = get_surcharge(df_p, "Jednokřídlé dveře", is_rock) or 5000
    p_bok = get_surcharge(df_p, "boční vstup", is_rock) or 7000
    for _ in range(pocet_dvere_vc): doors.append(("Dveře v čele", p_vc))
    for _ in range(pocet_dvere_bok): doors.append(("Boční vstup", p_bok))
    
    if doors:
        doors.sort(key=lambda x: x[1], reverse=True)
        free = doors.pop(0)
        items.append({"pol": f"{free[0]} (1. ks)", "det": "ZDARMA", "cen": 0})
        for n, p in doors:
            items.append({"pol": n, "det": "Další kus", "cen": p})
            running += p
            
    if zamykaci_klika and (pocet_dvere_vc + pocet_dvere_bok) > 0:
        cnt = pocet_dvere_vc + pocet_dvere_bok
        val = get_surcharge(df_p, "Uzamykání dveří", is_rock) or 800
        c = cnt * val
        items.append({"pol": "Zamykací klika", "det": f"{cnt} ks", "cen": c})
        running += c
        
    if klapka:
        val = get_surcharge(df_p, "klapka", is_rock) or 7000
        items.append({"pol": "Větrací klapka", "det": "", "cen": val})
        running += val

    # Koleje
    if pochozi_koleje:
        m_rail = (length / 1000.0) * 2
        val = get_surcharge(df_p, "Pochozí kolejnice", is_rock) or 330
        c = m_rail * val
        items.append({"pol": "Pochozí koleje", "det": f"{m_rail:.1f} m", "cen": c})
        running += c
    if ext_draha_m > 0:
        m_rail_ext = ext_draha_m * 2
        val = get_surcharge(df_p, "Jeden metr koleje", is_rock) or 220
        c = m_rail_ext * val
        items.append({"pol": "Prodloužení dráhy", "det": f"+{ext_draha_m} m", "cen": c})
        running += c

    # Montáž
    c_montaz = 0
    if montaz:
        val = get_surcharge(df_p, "Montáž zastřešení v ČR", is_rock) or 0.08
        c_montaz = running * val
        items.append({"pol": "Montáž (ČR)", "det": f"{val*100:.0f}% z materiálu", "cen": c_montaz})
    subtotal = running + c_montaz
    
    # Doprava
    c_doprava = 0
    if km > 0:
        c_doprava = km * 18
        items.append({"pol": "Doprava", "det": f"{km} km", "cen": c_doprava})
    total_no_vat = subtotal + c_doprava
    
    # Sleva
    if sleva_pct > 0:
        disc = total_no_vat * (sleva_pct / 100.0)
        items.append({"pol": "SLEVA", "det": f"-{sleva_pct}%", "cen": -disc})
        total_no_vat -= disc

    # --- ZOBRAZENÍ ---
    st.divider()
    col1, col2 = st.columns([1.5, 1])
    with col1:
        st.subheader("Rozpočet")
        df_show = pd.DataFrame(items)
        if not df_show.empty:
            st.dataframe(df_show, hide_index=True, use_container_width=True)
    with col2:
        st.subheader("Celkem")
        dph_val = total_no_vat * (dph_sazba / 100.0)
        total_with_vat = total_no_vat + dph_val
        st.metric("Bez DPH", f"{total_no_vat:,.0f} Kč")
        st.metric(f"S DPH ({dph_sazba}%)", f"{total_with_vat:,.0f} Kč")
        
        # PDF tlačítko
        if zak_jmeno:
            zak_udaje = {
                'jmeno': zak_jmeno, 'adresa': zak_adresa, 'tel': zak_tel, 'email': zak_email,
                'vypracoval': vypracoval, 'datum': datum_vystaveni.strftime("%d.%m.%Y"),
                'platnost': platnost_do.strftime("%d.%m.%Y"), 'termin': termin_dodani
            }
            totals = {'bez_dph': total_no_vat, 'dph': dph_val, 's_dph': total_with_vat, 'sazba_dph': dph_sazba}
            try:
                pdf_data = create_pdf(zak_udaje, items, totals)
                st.download_button("📄 Stáhnout Nabídku (PDF)", data=pdf_data, file_name=f"Nabidka_{zak_jmeno.replace(' ','_')}.pdf", mime="application/pdf", type="primary")
            except Exception as e:
                st.error(f"Chyba PDF: {e}")
                st.write(str(e))
        else:
            st.info("Pro stažení PDF vyplňte jméno zákazníka.")
