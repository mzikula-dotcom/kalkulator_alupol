import streamlit as st
import pandas as pd
import math
import io
import os
import base64
import json
import re
import altair as alt
from datetime import date, timedelta, datetime
from jinja2 import Template
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, inspect, Boolean
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import func

# --- VERZE APLIKACE ---
APP_VERSION = "72.0 (User Formula: 3k/pcs + Standard Material)"

# --- HESLO ADMINA ---
ADMIN_PASSWORD = "admin123"

# --- KONFIGURACE VÝROBY ---
ROOF_OVERLAP_MM = 100 
FACE_WASTE_COEF = 0.85 
MIN_MODULE_LEN_MM = 1800 
STANDARD_MODULE_LEN_MM = 2190

# --- KATEGORIE MODELŮ (GEOMETRIE) ---
# Modely, které potřebují korekci plochy (nejsou to čisté oblouky)
ANGULAR_MODELS = ["FLASH", "WING", "DREAM", "TERRACE", "ROCK", "HARMONY"]

# --- DEFINICE MODELŮ ---
MODEL_PARAMS = {
    "PRACTIC":  {"step_w": 100, "step_h": 50, "img": "practic.png"},
    "DREAM":    {"step_w": 130, "step_h": 65, "img": "dream.png"},
    "HARMONY":  {"step_w": 130, "step_h": 65, "img": "harmony.png"},
    "ROCK":     {"step_w": 130, "step_h": 65, "img": "rock.png"},
    "TERRACE":  {"step_w": 71,  "step_h": 65, "img": "terrace.png"}, 
    "HORIZONT": {"step_w": 130, "step_h": 65, "img": "horizont.png"}, 
    "STAR":     {"step_w": 130, "step_h": 65, "img": "star.png"},
    "WAVE":     {"step_w": 146, "step_h": 70, "img": "wave.png"},
    "FLASH":    {"step_w": 146, "step_h": 70, "img": "flash.png"},
    "WING":     {"step_w": 130, "step_h": 65, "img": "wing.png"},
    "SUNSET":   {"step_w": 130, "step_h": 65, "img": "sunset.png"},
    "DEFAULT":  {"step_w": 100, "step_h": 50, "img": None}
}

STD_LENGTHS = {2: 4336, 3: 6446, 4: 8556, 5: 10666, 6: 12776, 7: 14886}

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    st.error("Chybí knihovna Playwright. PDF nebude fungovat.")

st.set_page_config(page_title=f"Rentmil v{APP_VERSION}", layout="wide", page_icon="🏊‍♂️")

# CSS Styling
st.markdown("""
    <style>
        .block-container {padding-top: 1rem; padding-bottom: 2rem; padding-left: 2rem; padding-right: 2rem;}
        h1 {padding-top: 0rem;}
        [data-testid="stSidebar"] {min-width: 260px; max-width: 260px;}
        .metric-card {background-color: #f0f2f6; padding: 15px; border-radius: 10px; border-left: 5px solid #004b96;}
        div[data-testid="stExpander"] div[role="button"] p {font-size: 1.1rem; font-weight: bold; color: #004b96;}
        .debug-box {background-color: #ffeebb; padding: 10px; border-radius: 5px; border: 1px solid #eba434; font-family: monospace; font-size: 12px;}
    </style>
""", unsafe_allow_html=True)

if 'form_data' not in st.session_state:
    st.session_state['form_data'] = {}
if 'admin_logged_in' not in st.session_state:
    st.session_state['admin_logged_in'] = False

Base = declarative_base()

class Nabidka(Base):
    __tablename__ = 'nabidky'
    id = Column(Integer, primary_key=True)
    datum_vytvoreni = Column(DateTime, default=datetime.utcnow)
    zakaznik = Column(String)
    model = Column(String)
    cena_celkem = Column(Float)
    data_json = Column(Text)

class Cenik(Base):
    __tablename__ = 'cenik'
    id = Column(Integer, primary_key=True)
    model = Column(String)
    sirka_mm = Column(Integer)
    moduly = Column(Integer)
    cena = Column(Float)
    vyska = Column(Float)
    delka_fix = Column(Float)

class Priplatek(Base):
    __tablename__ = 'priplatky'
    id = Column(Integer, primary_key=True)
    nazev = Column(String)
    cena_fix = Column(Float)
    cena_pct = Column(Float)
    kategorie = Column(String)

db_url = os.environ.get("DATABASE_URL")
engine = None
SessionLocal = None

if db_url:
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    try:
        engine = create_engine(db_url)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        st.error(f"Chyba DB: {e}")

# --- POMOCNÉ FUNKCE ---
def parse_value_clean(val):
    if pd.isna(val) or str(val).strip() == "": return 0
    s = str(val).strip().replace(' ', '').replace('Kč', '').replace('Kc', '').replace('\xa0', '')
    if '%' in s: return float(s.replace('%', '').replace(',', '.')) / 100.0
    try: return float(s.replace(',', '.'))
    except: return 0

def geometry_segment_values(width_mm, height_mm):
    if width_mm <= 0: return 0, 0, 0
    if height_mm <= 0: height_mm = 1
    s = width_mm
    v = height_mm
    try:
        R = ((s**2 / 4) + v**2) / (2 * v)
        if R <= 0: arc_len = s
        else:
            ratio = s / (2 * R)
            if ratio > 1: ratio = 1
            if ratio < -1: ratio = -1
            alpha_rad = 2 * math.asin(ratio)
            arc_len = alpha_rad * R
    except: arc_len = s

    raw_rect_area = (s * v) / 1_000_000 
    production_area = raw_rect_area * FACE_WASTE_COEF 
    return production_area, arc_len, raw_rect_area

def calculate_complex_geometry_v2(model_name, width_input_mm, height_input_mm, modules, total_length_mm):
    params = MODEL_PARAMS.get(model_name.upper(), MODEL_PARAMS["DEFAULT"])
    step_w = params["step_w"]
    step_h = params["step_h"]

    w_small = width_input_mm
    h_small = height_input_mm
    area_face_small, _, _ = geometry_segment_values(w_small, h_small)
    
    w_large = width_input_mm + ((modules - 1) * step_w)
    h_large = height_input_mm + ((modules - 1) * step_h)
    area_face_large, _, _ = geometry_segment_values(w_large, h_large)
    
    mod_len_mm = total_length_mm / modules
    sheet_len_m = (mod_len_mm + ROOF_OVERLAP_MM) / 1000.0
    total_roof_area_geometric = 0
    total_arc_len_mm = 0
    
    for i in range(modules):
        w_i = width_input_mm + (i * step_w)
        h_i = height_input_mm + (i * step_h)
        _, arc_len_i_mm, _ = geometry_segment_values(w_i, h_i)
        total_roof_area_geometric += (arc_len_i_mm / 1000.0) * sheet_len_m
        total_arc_len_mm += arc_len_i_mm
        
    return total_roof_area_geometric, area_face_large, area_face_small, total_arc_len_mm

def get_surcharge_db(search_term, is_rock=False):
    if not SessionLocal: return {"fix": 0, "pct": 0}
    session = SessionLocal()
    cat = "Rock" if is_rock else "Standard"
    try:
        item = session.query(Priplatek).filter(Priplatek.kategorie == cat, Priplatek.nazev.ilike(f"%{search_term}%")).first()
        if not item and is_rock: 
             item = session.query(Priplatek).filter(Priplatek.kategorie == "Standard", Priplatek.nazev.ilike(f"%{search_term}%")).first()
        if item:
            return {"fix": item.cena_fix or 0, "pct": item.cena_pct or 0}
        return {"fix": 0, "pct": 0}
    finally: session.close()

def get_rail_price_from_db(modules):
    if not SessionLocal: return DEFAULT_RAIL_PRICES.get(modules, 0)
    session = SessionLocal()
    try:
        search_name = f"Koleje prodloužení {modules} mod"
        item = session.query(Priplatek).filter(Priplatek.nazev.ilike(f"%{search_name}%")).first()
        if item and item.cena_fix > 0: return item.cena_fix
        else: return DEFAULT_RAIL_PRICES.get(modules, 0)
    finally: session.close()

def get_poly_factor_from_db():
    if not SessionLocal: return DEFAULT_POLY_FACTOR
    session = SessionLocal()
    try:
        item = session.query(Priplatek).filter(Priplatek.nazev.ilike("Koeficient plochy")).first()
        if item and item.cena_fix > 0: return item.cena_fix
        else: return DEFAULT_POLY_FACTOR
    finally: session.close()

def calculate_base_price_db(model, width_mm, modules):
    if not SessionLocal: return 0,0, "DB Error"
    session = SessionLocal()
    try:
        count = session.query(Cenik).filter(Cenik.model == model).count()
        if count == 0: return 0, 0, f"Ceník pro {model} je prázdný!"
        row = session.query(Cenik).filter(
            Cenik.model == model,
            Cenik.moduly == modules,
            Cenik.sirka_mm >= width_mm
        ).order_by(Cenik.sirka_mm.asc()).first()
        if row: return row.cena, row.vyska * 1000, None
        else:
            max_row = session.query(Cenik).filter(Cenik.model == model, Cenik.moduly == modules).order_by(Cenik.sirka_mm.desc()).first()
            if max_row: return 0, 0, f"Mimo rozsah (Max pro {model} je {max_row.sirka_mm} mm)"
            return 0, 0, "Rozměr nebo počet modulů nenalezen"
    except Exception as e: return 0,0, str(e)
    finally: session.close()

def save_offer_to_db(data_dict, total_price):
    if not SessionLocal: return False, "DB Error"
    session = SessionLocal()
    try:
        json_str = json.dumps(data_dict, default=str)
        obchodnik = data_dict.get('vypracoval', 'Neznámý')
        nova_nabidka = Nabidka(
            zakaznik=data_dict.get('zak_jmeno', 'Neznámý'), 
            model=data_dict.get('model', '-'), 
            cena_celkem=total_price, 
            data_json=json_str, 
            datum_vytvoreni=datetime.now()
        )
        session.add(nova_nabidka)
        session.commit()
        return True, "Uloženo."
    except Exception as e: return False, str(e)
    finally: session.close()

def get_all_offers():
    if not SessionLocal: return []
    session = SessionLocal()
    try: return session.query(Nabidka).order_by(Nabidka.datum_vytvoreni.desc()).all()
    finally: session.close()

def delete_offer(offer_id):
    if not SessionLocal: return
    session = SessionLocal()
    try:
        offer = session.query(Nabidka).filter(Nabidka.id == offer_id).first()
        if offer:
            session.delete(offer)
            session.commit()
    finally: session.close()

def update_priplatek_db(edited_df):
    if not SessionLocal: return
    session = SessionLocal()
    try:
        records = edited_df.to_dict('records')
        for row in records:
            item = session.query(Priplatek).filter(Priplatek.id == row['id']).first()
            if item:
                item.nazev = row['nazev']
                item.cena_fix = float(row['cena_fix']) if row['cena_fix'] is not None else 0.0
                item.cena_pct = float(row['cena_pct']) if row['cena_pct'] is not None else 0.0
                item.kategorie = row['kategorie']
        session.commit()
        st.toast("Ceny uloženy! ✅")
    except Exception as e:
        st.error(f"Chyba při ukládání: {e}")
    finally:
        session.close()

def img_to_base64(img_path):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    full_path = os.path.join(current_dir, img_path)
    if os.path.exists(full_path):
        with open(full_path, "rb") as img_file: return base64.b64encode(img_file.read()).decode('utf-8')
    files = os.listdir(current_dir)
    for f in files:
        if f.lower() == img_path.lower():
            full_path = os.path.join(current_dir, f)
            with open(full_path, "rb") as img_file: return base64.b64encode(img_file.read()).decode('utf-8')
    return None

def generate_pdf_html(zak_udaje, items, totals, model_name):
    logo_b64 = img_to_base64("logo.png")
    mnich_b64 = img_to_base64("mnich.png")
    params = MODEL_PARAMS.get(model_name.upper(), MODEL_PARAMS["DEFAULT"])
    img_filename = params.get("img")
    model_img_b64 = img_to_base64(img_filename) if img_filename else None

    html_template = """
    <!DOCTYPE html>
    <html lang="cs">
    <head>
        <meta charset="UTF-8">
        <style>
            @page { margin: 2cm; size: A4; }
            body { font-family: 'Helvetica', 'Arial', sans-serif; color: #333; font-size: 14px; line-height: 1.4; }
            .header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px; }
            .logo { max-width: 180px; height: auto; }
            .right-header { text-align: center; display: flex; flex-direction: column; align-items: center; }
            .mnich { max-width: 100px; height: auto; margin-bottom: 5px; }
            .slogan { font-size: 12px; font-weight: bold; color: #555; font-style: italic; }
            .title { text-align: center; color: #004b96; font-size: 28px; font-weight: bold; margin-top: 10px; margin-bottom: 10px; }
            .divider { border-bottom: 3px solid #f07800; margin-bottom: 30px; }
            .info-grid { display: flex; justify-content: space-between; margin-bottom: 30px; }
            .col { width: 48%; }
            .col-header { color: #004b96; font-weight: bold; font-size: 16px; margin-bottom: 5px; border-bottom: 1px solid #ddd; padding-bottom: 5px; }
            .info-text { margin: 2px 0; }
            .model-section { text-align: center; margin: 30px 0; }
            .model-intro { font-size: 14px; color: #333; margin-bottom: 5px; }
            .model-name-highlight { font-size: 22px; font-weight: bold; color: #004b96; text-transform: uppercase; margin-bottom: 15px; display: block; }
            .model-img { max-width: 60%; height: auto; border-radius: 5px; }
            .items-table { width: 100%; border-collapse: collapse; margin-bottom: 20px; }
            .items-table th { background-color: #004b96; color: white; padding: 10px; text-align: left; }
            .items-table td { padding: 10px; border-bottom: 1px solid #eee; }
            .items-table tr:nth-child(even) { background-color: #f9f9f9; }
            .price-col { text-align: right; white-space: nowrap; }
            .totals { float: right; width: 40%; text-align: right; }
            .total-row { display: flex; justify-content: space-between; margin: 5px 0; }
            .grand-total { font-size: 24px; color: #f07800; font-weight: bold; margin-top: 10px; border-top: 2px solid #f07800; padding-top: 5px; }
            .footer { clear: both; margin-top: 50px; padding-top: 20px; border-top: 1px solid #004b96; font-size: 12px; color: #666; text-align: center; }
            .note { background-color: #e6f2ff; padding: 15px; border-left: 5px solid #004b96; margin-top: 20px; margin-bottom: 20px; font-style: italic; }
        </style>
    </head>
    <body>
        <div class="header">
            <div>{% if logo_b64 %}<img src="data:image/png;base64,{{ logo_b64 }}" class="logo">{% else %}<h1>Rentmil s.r.o.</h1>{% endif %}</div>
            <div class="right-header">
                {% if mnich_b64 %}<img src="data:image/png;base64,{{ mnich_b64 }}" class="mnich">{% endif %}
                <div class="slogan">Zastřešení v klidu</div>
            </div>
        </div>
        <div class="title">CENOVÁ NABÍDKA</div>
        <div class="divider"></div>
        <div class="info-grid">
            <div class="col">
                <div class="col-header">DODAVATEL</div>
                <div class="info-text"><strong>Rentmil s.r.o.</strong></div>
                <div class="info-text">Lidická 1233/26, 323 00 Plzeň</div>
                <div class="info-text">IČO: 26342910, DIČ: CZ26342910</div>
                <div class="info-text">Tel: 737 222 004, 377 530 806</div>
                <div class="info-text">Email: bazeny@rentmil.cz</div>
                <div class="info-text">Web: www.rentmil.cz</div>
                <br>
                <div class="info-text">Vypracoval: <strong>{{ data.vypracoval }}</strong></div>
            </div>
            <div class="col">
                <div class="col-header">ODBĚRATEL</div>
                <div class="info-text"><strong>{{ data.jmeno }}</strong></div>
                <div class="info-text">{{ data.adresa }}</div>
                <div class="info-text">Tel: {{ data.tel }}</div>
                <div class="info-text">Email: {{ data.email }}</div>
                <br>
                <div class="info-text">Datum vystavení: <strong>{{ data.datum }}</strong></div>
                <div class="info-text">Platnost do: <strong>{{ data.platnost }}</strong></div>
            </div>
        </div>
        {% if model_img_b64 %}
        <div class="model-section">
            <div class="model-intro">Připravili jsme pro vás nabídku zastřešení:</div>
            <span class="model-name-highlight">{{ data.model }}</span>
            <img src="data:image/png;base64,{{ model_img_b64 }}" class="model-img">
        </div>
        {% endif %}
        <table class="items-table">
            <thead>
                <tr>
                    <th width="50%">Položka</th>
                    <th width="30%">Detail</th>
                    <th width="20%" class="price-col">Cena</th>
                </tr>
            </thead>
            <tbody>
                {% for item in items %}
                <tr>
                    <td><strong>{{ item.pol }}</strong></td>
                    <td>{{ item.det }}</td>
                    <td class="price-col">{{ "{:,.0f}".format(item.cen).replace(',', ' ') }} Kč</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        <div class="totals">
            <div class="total-row">
                <span>Cena bez DPH:</span>
                <span><strong>{{ "{:,.0f}".format(totals.bez_dph).replace(',', ' ') }} Kč</strong></span>
            </div>
            <div class="total-row">
                <span>DPH ({{ totals.sazba_dph }}%):</span>
                <span>{{ "{:,.0f}".format(totals.dph).replace(',', ' ') }} Kč</span>
            </div>
            <div class="total-row grand-total">
                <span>CELKEM:</span>
                <span>{{ "{:,.0f}".format(totals.s_dph).replace(',', ' ') }} Kč</span>
            </div>
        </div>
        <div style="clear: both;"></div>
        <div class="note">
            <strong>Termín dodání:</strong> {{ data.termin }}<br>
            Poznámka: Tato nabídka je nezávazná. Pro potvrzení objednávky prosím kontaktujte svého obchodního zástupce.
        </div>
        <div class="footer">
            Rentmil s.r.o. | www.rentmil.cz | bazeny@rentmil.cz
        </div>
    </body>
    </html>
    """
    data_w_model = zak_udaje.copy()
    data_w_model['model'] = model_name
    template = Template(html_template)
    html_content = template.render(data=data_w_model, items=items, totals=totals, logo_b64=logo_b64, mnich_b64=mnich_b64, model_img_b64=model_img_b64)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(html_content)
        pdf_bytes = page.pdf(format="A4", print_background=True, margin={"top": "0cm", "right": "0cm", "bottom": "0cm", "left": "0cm"})
        browser.close()
    return pdf_bytes

def get_val(key, default):
    if 'form_data' in st.session_state and key in st.session_state['form_data']: return st.session_state['form_data'][key]
    return default

# =======================
# HLAVNÍ LOGIKA APLIKACE
# =======================

with st.sidebar:
    st.title(f"Rentmil v{APP_VERSION.split(' ')[0]}")
    app_mode = st.radio("Sekce:", ["Kalkulátor", "🔧 Admin Mód"])
    if app_mode == "🔧 Admin Mód":
        st.markdown("---")
        if not st.session_state['admin_logged_in']:
            pwd = st.text_input("Heslo administrátora", type="password")
            if st.button("Přihlásit"):
                if pwd == ADMIN_PASSWORD:
                    st.session_state['admin_logged_in'] = True
                    st.rerun()
                else:
                    st.error("Chybné heslo")
        else:
            st.success("Přihlášen jako Admin")
            if st.button("Odhlásit"):
                st.session_state['admin_logged_in'] = False
                st.rerun()

if app_mode == "Kalkulátor":
    st.title("🛠 Kalkulátor Zastřešení")
    with st.container():
        c_n1, c_n2, c_n3, c_n4 = st.columns(4)
        with c_n1: zak_jmeno = st.text_input("Jméno a příjmení", value=get_val('zak_jmeno', ""))
        with c_n2: zak_adresa = st.text_input("Adresa", value=get_val('zak_adresa', ""))
        with c_n3: zak_tel = st.text_input("Telefon", value=get_val('zak_tel', ""))
        with c_n4: zak_email = st.text_input("Email", value=get_val('zak_email', ""))
        c_d1, c_d2, c_d3, c_d4 = st.columns(4)
        with c_d1: 
            def_vypracoval = get_val('vypracoval', "Martin Zikula")
            list_vypracoval = ["Martin Zikula", "Zuzana Zikulová", "Drahoslav Houška", "Ivan Reif", "Lenka Finklarová"]
            if def_vypracoval not in list_vypracoval: list_vypracoval.append(def_vypracoval)
            vypracoval = st.selectbox("Vypracoval", list_vypracoval, index=list_vypracoval.index(def_vypracoval))
        with c_d2: termin_dodani = st.text_input("Termín", value=get_val('termin_dodani', "dle dohody (cca 6-8 týdnů)"))
        with c_d3: platnost_dny = st.number_input("Platnost (dní)", value=get_val('platnost_dny', 10), min_value=1)
        with c_d4: 
            datum_vystaveni = date.today()
            platnost_do = datum_vystaveni + timedelta(days=platnost_dny)
            st.text_input("Platnost do", value=platnost_do.strftime("%d.%m.%Y"), disabled=True)

    st.divider()
    col_input, col_result = st.columns([1, 1], gap="large")

    with col_input:
        st.subheader("1. Parametry")
        models_list = list(MODEL_PARAMS.keys()); models_list.sort()
        if "DEFAULT" in models_list: models_list.remove("DEFAULT")
        def_model = get_val('model', "PRACTIC")
        c_p1, c_p2 = st.columns([1, 1])
        with c_p1: 
            model = st.selectbox("Model", models_list, index=models_list.index(def_model) if def_model in models_list else 0)
        with c_p2:
            is_rock = (model.upper() == "ROCK")
            moduly = st.slider("Počet modulů", 2, 7, get_val('moduly', 3))
        c_p3, c_p4 = st.columns(2)
        with c_p3: sirka = st.number_input("Šířka (mm)", 2000, 8000, get_val('sirka', 3500), step=10)
        with c_p4: 
            std_len = STD_LENGTHS.get(moduly, moduly * 2190)
            celkova_delka = st.number_input(f"Délka (std {std_len})", 2000, 20000, get_val('celkova_delka', std_len), step=10)
        
        diff_len = celkova_delka - std_len
        if diff_len > 10:
            pocet_prod_modulu = st.number_input("Počet prodloužených modulů", 1, moduly, get_val('pocet_prod_modulu', 1))
        else: pocet_prod_modulu = 1
        zvyseni_cm = st.number_input("Zvýšení zastřešení (po 10 cm)", 0, 50, get_val('zvyseni_cm', 0), step=10)
        avg_mod_len = celkova_delka / moduly
        if avg_mod_len < MIN_MODULE_LEN_MM: st.warning(f"⚠️ Pozor! Průměrná délka segmentu {avg_mod_len:.0f} mm je pod limitem {MIN_MODULE_LEN_MM} mm.")

        st.subheader("2. Barvy a Polykarbonát")
        c_b1, c_b2 = st.columns(2)
        with c_b1:
            barvy_opts = ["Stříbrný Elox (Bonus -10 000 Kč)", "Bronzový Elox", "Antracitový Elox", "RAL Nástřik"]
            def_barva = get_val('barva_typ', barvy_opts[0])
            barva_typ = st.selectbox("Barva", barvy_opts, index=barvy_opts.index(def_barva) if def_barva in barvy_opts else 0)
        with c_b2: ral_kod = st.text_input("RAL Kód", value=get_val('ral_kod', ""), disabled=("RAL" not in barva_typ))
        poly_strecha = st.checkbox("Plný poly - STŘECHA", value=get_val('poly_strecha', False))
        c_poly1, c_poly2 = st.columns(2)
        with c_poly1: poly_celo_male = st.checkbox("Plný poly - MALÉ čelo", value=get_val('poly_celo_male', False))
        with c_poly2: poly_celo_velke = st.checkbox("Plný poly - VELKÉ čelo", value=get_val('poly_celo_velke', False))
        change_color_poly = st.checkbox("Změna barvy polykarbonátu", value=get_val('change_color_poly', False))

        st.subheader("3. Doplňky")
        with st.expander("Dveře a vstupy", expanded=True):
            c_dv1, c_dv2 = st.columns(2)
            with c_dv1:
                pocet_dvere_vc = st.number_input("Ks VČ", 0, 2, get_val('pocet_dvere_vc', 0))
                if pocet_dvere_vc > 0:
                    dvere_vc_sirka = st.number_input("Šířka VČ", 600, 1200, get_val('dvere_vc_sirka', 800))
                    dvere_vc_typ = st.selectbox("Typ VČ", ["Panty", "Posuvné"])
            with c_dv2:
                pocet_dvere_bok = st.number_input("Ks Bok", 0, 4, get_val('pocet_dvere_bok', 0))
                if pocet_dvere_bok > 0: dvere_bok_umisteni = st.selectbox("Umístění", ["Vlevo", "Vpravo", "Oboustranně"])

        with st.expander("Ostatní doplňky", expanded=True):
            c_x1, c_x2 = st.columns(2)
            with c_x1:
                zamykaci_klika = st.checkbox("Zamykací klika", value=get_val('zamykaci_klika', False))
                uzamykani_segmentu = st.checkbox("Uzamykání segmentů", value=get_val('uzamykani_segmentu', False))
                klapka = st.checkbox("Větrací klapka", value=get_val('klapka', False))
            with c_x2:
                bez_maleho_cela = st.checkbox("BEZ malého čela", value=get_val('bez_maleho_cela', False))
                bez_velkeho_cela = st.checkbox("BEZ velkého čela", value=get_val('bez_velkeho_cela', False))
                vyklopne_celo = st.checkbox("Výklopné čelo", value=get_val('vyklopne_celo', False))

        with st.expander("4. Koleje", expanded=True):
            c_k1, c_k2 = st.columns(2)
            with c_k1:
                pochozi_koleje = st.checkbox("Pochozí koleje", value=get_val('pochozi_koleje', False))
                pochozi_koleje_zdarma = st.checkbox("➡️ Akce: Koleje ZDARMA", value=get_val('pochozi_koleje_zdarma', False))
                obousmerne_koleje = st.checkbox("Obous
