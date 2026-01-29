
import streamlit as st
import pandas as pd
import math
import io
import os
import base64
import json
import re
from datetime import date, timedelta, datetime
from jinja2 import Template
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, inspect, Boolean
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import func

# --- DEFINICE MODELŮ (Dle výpočty.xlsx) ---
# step_width: o kolik je další modul širší (mm)
# step_height: o kolik je další modul vyšší (mm)
MODEL_PARAMS = {
    "PRACTIC": {"step_w": 100, "step_h": 50},
    "DREAM":   {"step_w": 130, "step_h": 65},
    "HARMONY": {"step_w": 130, "step_h": 65},
    "ROCK":    {"step_w": 130, "step_h": 65},
    "TERRACE": {"step_w": 71,  "step_h": 65}, # 70.6 zaokrouhleno
    "HORIZONT":{"step_w": 130, "step_h": 65}, # Odhad (nenalezeno v xls), fallback na standard
    "STAR":    {"step_w": 130, "step_h": 65}, # Odhad
    "DEFAULT": {"step_w": 100, "step_h": 50}
}

# Tabulka standardních délek
STD_LENGTHS = {
    2: 4336,
    3: 6446,
    4: 8556,
    5: 10666,
    6: 12776,
    7: 14886
}

# Zkusíme importovat Playwright
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    st.error("Chybí knihovna Playwright.")

# --- KONFIGURACE STRÁNKY ---
st.set_page_config(page_title="Kalkulátor Rentmil", layout="wide", page_icon="🏊‍♂️")

# ########################################
# 1. DATABÁZE A MODELY
# ########################################

if 'form_data' not in st.session_state:
    st.session_state['form_data'] = {}

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

# ########################################
# 2. POMOCNÉ FUNKCE
# ########################################
def parse_value_clean(val):
    if pd.isna(val) or str(val).strip() == "": return 0
    s = str(val).strip().replace(' ', '').replace('Kč', '').replace('Kc', '').replace('\xa0', '')
    if '%' in s: return float(s.replace('%', '').replace(',', '.')) / 100.0
    try: return float(s.replace(',', '.'))
    except: return 0

# ########################################
# 3. GEOMETRIE (Dle Modelu)
# ########################################
def geometry_segment_area(width_mm, height_mm):
    """Vypočítá plochu kruhové úseče (čela) v m2 a délku oblouku v m."""
    if width_mm <= 0: return 0, 0
    if height_mm <= 0: height_mm = 1
    
    s = width_mm
    v = height_mm
    
    try:
        # Radius R z tětivy a výšky
        R = ((s**2 / 4) + v**2) / (2 * v)
        if R <= 0: return 0, 0
        
        # Úhel alfa
        ratio = s / (2 * R)
        if ratio > 1: ratio = 1
        if ratio < -1: ratio = -1
        alpha_rad = 2 * math.asin(ratio)
        
        # Délka a Plocha
        arc_len = alpha_rad * R
        area = 0.5 * (R**2) * (alpha_rad - math.sin(alpha_rad))
        
        return area / 1_000_000, arc_len / 1000
    except:
        return 0, 0

def calculate_complex_geometry(model_name, width_input_mm, height_input_mm, modules, total_length_mm):
    """
    Počítá geometrii teleskopického zastřešení.
    Předpoklad: width_input je NEJMENŠÍ modul (Vnitřní).
    Každý další modul je větší o step_w a step_h.
    """
    # Načtení parametrů modelu
    params = MODEL_PARAMS.get(model_name.upper(), MODEL_PARAMS["DEFAULT"])
    step_w = params["step_w"]
    step_h = params["step_h"]

    # Modul 1 (Nejmenší/Vnitřní) - Malé čelo
    w_small = width_input_mm
    h_small = height_input_mm
    area_face_small, arc_small = geometry_segment_area(w_small, h_small)
    
    # Modul N (Největší/Vnější) - Velké čelo
    # w_large = w_small + (modules - 1) * step
    w_large = width_input_mm + ((modules - 1) * step_w)
    h_large = height_input_mm + ((modules - 1) * step_h)
    area_face_large, arc_large = geometry_segment_area(w_large, h_large)
    
    # Plocha střechy (Součet všech modulů)
    mod_len_avg = total_length_mm / modules
    total_roof_area = 0
    
    for i in range(modules):
        # Modul i (0..N-1), kde 0 je nejmenší
        w_i = width_input_mm + (i * step_w)
        h_i = height_input_mm + (i * step_h)
        _, arc_i = geometry_segment_area(w_i, h_i)
        
        total_roof_area += (arc_i * (mod_len_avg / 1000.0))
        
    return total_roof_area, area_face_large, area_face_small

# ########################################
# 4. DB FUNKCE
# ########################################

def get_surcharge_db(search_term, is_rock=False):
    if not SessionLocal: return {"fix": 0, "pct": 0}
    session = SessionLocal()
    cat = "Rock" if is_rock else "Standard"
    try:
        item = session.query(Priplatek).filter(Priplatek.kategorie == cat, Priplatek.nazev.ilike(f"%{search_term}%")).first()
        if not item and is_rock: 
             item = session.query(Priplatek).filter(Priplatek.kategorie == "Standard", Priplatek.nazev.ilike(f"%{search_term}%")).first()
        if item:
            return {"fix": item.cena_fix, "pct": item.cena_pct}
        return {"fix": 0, "pct": 0}
    finally:
        session.close()

def calculate_base_price_db(model, width_mm, modules):
    if not SessionLocal: return 0,0, "DB Error"
    session = SessionLocal()
    try:
        count = session.query(Cenik).filter(Cenik.model == model).count()
        if count == 0: 
            if model == "PRACTIC": return 0,0, "Ceník je prázdný!"
        
        row = session.query(Cenik).filter(
            Cenik.model == model,
            Cenik.moduly == modules,
            Cenik.sirka_mm >= width_mm
        ).order_by(Cenik.sirka_mm.asc()).first()

        if row:
            return row.cena, row.vyska * 1000, None
        else:
            max_row = session.query(Cenik).filter(Cenik.model == model, Cenik.moduly == modules).order_by(Cenik.sirka_mm.desc()).first()
            if max_row:
                return 0, 0, f"Mimo rozsah (Max pro {model} je {max_row.sirka_mm} mm)"
            return 0, 0, "Rozměr nebo počet modulů nenalezen"
    except Exception as e:
        return 0,0, str(e)
    finally:
        session.close()

def save_offer_to_db(data_dict, total_price):
    if not SessionLocal: return False, "DB Error"
    session = SessionLocal()
    try:
        json_str = json.dumps(data_dict, default=str)
        nova_nabidka = Nabidka(zakaznik=data_dict.get('zak_jmeno', 'Neznámý'), model=data_dict.get('model', '-'), cena_celkem=total_price, data_json=json_str, datum_vytvoreni=datetime.now())
        session.add(nova_nabidka)
        session.commit()
        return True, "Uloženo."
    except Exception as e:
        return False, str(e)
    finally:
        session.close()

def get_all_offers():
    if not SessionLocal: return []
    session = SessionLocal()
    try:
        return session.query(Nabidka).order_by(Nabidka.datum_vytvoreni.desc()).all()
    finally:
        session.close()

def delete_offer(offer_id):
    if not SessionLocal: return
    session = SessionLocal()
    try:
        offer = session.query(Nabidka).filter(Nabidka.id == offer_id).first()
        if offer:
            session.delete(offer)
            session.commit()
    finally:
        session.close()

# ########################################
# 5. PDF GENERATOR
# ########################################
def img_to_base64(img_path):
    if not os.path.exists(img_path):
        for f in os.listdir('.'):
            if f.lower() == img_path.lower():
                img_path = f
                break
    if os.path.exists(img_path):
        with open(img_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode('utf-8')
    return None

def generate_pdf_html(zak_udaje, items, totals):
    logo_b64 = img_to_base64("logo.png")
    mnich_b64 = img_to_base64("mnich.png")
    html_template = """
    <!DOCTYPE html>
    <html lang="cs">
    <head>
        <meta charset="UTF-8">
        <style>
            @page { margin: 2cm; size: A4; }
            body { font-family: 'Helvetica', 'Arial', sans-serif; color: #333; font-size: 14px; line-height: 1.4; }
            .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
            .logo { max-width: 250px; height: auto; }
            .mnich { max-width: 100px; height: auto; }
            .title { text-align: center; color: #004b96; font-size: 28px; font-weight: bold; margin-top: 10px; margin-bottom: 10px; }
            .divider { border-bottom: 3px solid #f07800; margin-bottom: 30px; }
            .info-grid { display: flex; justify-content: space-between; margin-bottom: 30px; }
            .col { width: 48%; }
            .col-header { color: #004b96; font-weight: bold; font-size: 16px; margin-bottom: 5px; border-bottom: 1px solid #ddd; padding-bottom: 5px; }
            .info-text { margin: 2px 0; }
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
            <div>{% if mnich_b64 %}<img src="data:image/png;base64,{{ mnich_b64 }}" class="mnich">{% endif %}</div>
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
    template = Template(html_template)
    html_content = template.render(data=zak_udaje, items=items, totals=totals, logo_b64=logo_b64, mnich_b64=mnich_b64)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(html_content)
        pdf_bytes = page.pdf(format="A4", print_background=True, margin={"top": "0cm", "right": "0cm", "bottom": "0cm", "left": "0cm"})
        browser.close()
    return pdf_bytes

# ########################################
# 6. UI (STREAMLIT)
# ########################################
st.sidebar.title("Navigace")
page_mode = st.sidebar.radio("Režim:", ["Kalkulátor", "Historie Nabídek"])

# --- SERVISNÍ ZÓNA ---
with st.sidebar.expander("🔐 Servisní zóna (Admin)"):
    tab_modely, tab_priplatky = st.tabs(["🏠 Ceníky Modelů", "➕ Příplatky"])
    
    with tab_modely:
        st.caption("Formát: 'Model;...\\n do 3m;...'")
        import_data_models = st.text_area("CSV Modely", height=150, key="imp_models")
        if st.button("⚠️ Nahrát Modely"):
            if not import_data_models.strip():
                st.error("Vlož data!")
            elif SessionLocal:
                session = SessionLocal()
                try:
                    session.query(Cenik).delete()
                    df_c = pd.read_csv(io.StringIO(import_data_models), sep=';', header=None)
                    current_model = None
                    counter = 0
                    for idx, row in df_c.iterrows():
                        first_col = str(row[0]).strip()
                        if first_col.upper() in ["PRACTIC", "HARMONY", "DREAM", "HORIZONT", "STAR", "ROCK", "TERRACE"]:
                            current_model = first_col.upper()
                            continue
                        if current_model and first_col.startswith("do "):
                            try:
                                sirka_mm = int(float(first_col.replace("do ", "").replace(" m", "").replace(",", ".")) * 1000)
                            except: continue
                            for mod_i in range(2, 8):
                                col_p = 1 + (mod_i - 2) * 2
                                col_h = col_p + 1
                                if col_p < len(row):
                                    cena = parse_value_clean(row[col_p])
                                    vyska = parse_value_clean(row[col_h] if col_h < len(row) else 0)
                                    if cena > 0:
                                        session.add(Cenik(model=current_model, sirka_mm=sirka_mm, moduly=mod_i, cena=cena, vyska=vyska, delka_fix=0))
                                        counter += 1
                    session.commit()
                    st.success(f"Nahráno {counter} cen modelů.")
                except Exception as e:
                    session.rollback()
                    st.error(f"Chyba: {e}")
                finally:
                    session.close()

    with tab_priplatky:
        st.caption("Formát: 'Název; Cena Standard; Cena Rock'")
        import_data_extras = st.text_area("CSV Příplatky", height=150, key="imp_extras")
        if st.button("⚠️ Nahrát Příplatky"):
            if not import_data_extras.strip():
                st.error("Vlož data!")
            elif SessionLocal:
                session = SessionLocal()
                try:
                    session.query(Priplatek).delete()
                    df_p = pd.read_csv(io.StringIO(import_data_extras), sep=';', header=None)
                    counter = 0
                    for _, row in df_p.iterrows():
                        nazev = str(row[0]).strip()
                        if not nazev or pd.isna(nazev): continue
                        
                        val_std = row[1]
                        val_std_clean = parse_value_clean(val_std)
                        is_pct_std = isinstance(val_std, str) and '%' in val_std
                        
                        p_std = Priplatek(nazev=nazev, cena_pct=val_std_clean if is_pct_std else 0, cena_fix=val_std_clean if not is_pct_std else 0, kategorie="Standard")
                        session.add(p_std)
                        counter += 1

                        if len(row) > 2:
                            val_rock = row[2]
                            if pd.isna(val_rock) or str(val_rock).strip() == "": val_rock = val_std
                            val_rock_clean = parse_value_clean(val_rock)
                            is_pct_rock = isinstance(val_rock, str) and '%' in val_rock
                            
                            p_rock = Priplatek(nazev=nazev, cena_pct=val_rock_clean if is_pct_rock else 0, cena_fix=val_rock_clean if not is_pct_rock else 0, kategorie="Rock")
                            session.add(p_rock)
                            counter += 1
                    
                    session.commit()
                    st.success(f"Nahráno {counter} položek příplatků.")
                except Exception as e:
                    session.rollback()
                    st.error(f"Chyba: {e}")
                finally:
                    session.close()

if page_mode == "Historie Nabídek":
    st.title("🗄️ Historie Nabídek")
    nabidky = get_all_offers()
    if not nabidky:
        st.info("Zatím žádné uložené nabídky.")
    else:
        data_table = []
        for n in nabidky:
            data_table.append({
                "ID": n.id,
                "Datum": n.datum_vytvoreni.strftime("%d.%m.%Y %H:%M"),
                "Zákazník": n.zakaznik,
                "Model": n.model,
                "Cena": f"{n.cena_celkem:,.0f} Kč"
            })
        st.dataframe(pd.DataFrame(data_table), use_container_width=True, hide_index=True)
        st.divider()
        col_hist1, col_hist2 = st.columns(2)
        with col_hist1:
            selected_id = st.selectbox("Vyber ID nabídky:", [n.id for n in nabidky])
        with col_hist2:
            st.write("")
            st.write("")
            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                if st.button("📂 Načíst do kalkulátoru"):
                    offer_to_load = next((n for n in nabidky if n.id == selected_id), None)
                    if offer_to_load:
                        st.session_state['form_data'] = json.loads(offer_to_load.data_json)
                        st.success(f"Načteno ID {selected_id}.")
            with col_btn2:
                if st.button("🗑️ Smazat"):
                    delete_offer(selected_id)
                    st.rerun()

else:
    # REŽIM KALKULÁTOR
    st.title("🛠 Konfigurátor Zastřešení")
    def get_val(key, default):
        if 'form_data' in st.session_state and key in st.session_state['form_data']:
            return st.session_state['form_data'][key]
        return default

    with st.expander("👤 Údaje o zákazníkovi a nabídce", expanded=True):
        col_cust1, col_cust2 = st.columns(2)
        with col_cust1:
            zak_jmeno = st.text_input("Jméno a příjmení", value=get_val('zak_jmeno', ""))
            zak_adresa = st.text_input("Adresa", value=get_val('zak_adresa', ""))
            zak_tel = st.text_input("Telefon", value=get_val('zak_tel', ""))
            zak_email = st.text_input("Email", value=get_val('zak_email', ""))
        with col_cust2:
            def_vypracoval = get_val('vypracoval', "Martin Zikula")
            list_vypracoval = ["Martin Zikula", "Zuzana Zikulová", "Drahoslav Houška", "Ivan Reif", "Lenka Finklarová"]
            if def_vypracoval not in list_vypracoval: list_vypracoval.append(def_vypracoval)
            vypracoval = st.selectbox("Vypracoval:", list_vypracoval, index=list_vypracoval.index(def_vypracoval))
            col_d1, col_d2 = st.columns(2)
            with col_d1: platnost_dny = st.number_input("Platnost (dní)", value=get_val('platnost_dny', 10), min_value=1)
            with col_d2: 
                datum_vystaveni = date.today()
                platnost_do = datum_vystaveni + timedelta(days=platnost_dny)
                st.date_input("Platnost do:", value=platnost_do, disabled=True)
            termin_dodani = st.text_input("Termín dodání", value=get_val('termin_dodani', "dle dohody (cca 6-8 týdnů)"))

    with st.sidebar:
        st.header("1. Parametry")
        def_model = get_val('model', "PRACTIC")
        models_list = ["PRACTIC", "HARMONY", "DREAM", "HORIZONT", "STAR", "ROCK", "TERRACE"]
        model = st.selectbox("Model", models_list, index=models_list.index(def_model) if def_model in models_list else 0)
        is_rock = (model.upper() == "ROCK")
        sirka = st.number_input("Šířka (mm)", 2000, 8000, get_val('sirka', 3500), step=10)
        moduly = st.slider("Počet modulů", 2, 7, get_val('moduly', 3))
        
        # --- DÉLKA Z TABULKY ---
        std_len = STD_LENGTHS.get(moduly, moduly * 2190)
        st.caption(f"Standardní délka pro {moduly} moduly: {std_len} mm")
        celkova_delka = st.number_input("Celková délka (mm)", 2000, 20000, get_val('celkova_delka', std_len), step=10)
        diff_len = celkova_delka - std_len

        st.markdown("---")
        st.header("2. Barvy a Polykarbonát")
        barvy_opts = ["Stříbrný Elox (Bonus -10 000 Kč)", "Bronzový Elox", "Antracitový Elox", "RAL Nástřik"]
        def_barva = get_val('barva_typ', barvy_opts[0])
        barva_typ = st.selectbox("Barva konstrukce", barvy_opts, index=barvy_opts.index(def_barva) if def_barva in barvy_opts else 0)
        poly_strecha = st.checkbox("Plný polykarbonát - STŘECHA", value=get_val('poly_strecha', False))
        
        col_poly1, col_poly2 = st.columns(2)
        with col_poly1:
             poly_celo_male = st.checkbox("Plný poly - MALÉ čelo", value=get_val('poly_celo_male', False))
        with col_poly2:
             poly_celo_velke = st.checkbox("Plný poly - VELKÉ čelo", value=get_val('poly_celo_velke', False))
             
        change_color_poly = st.checkbox("Změna barvy polykarbonátu", value=get_val('change_color_poly', False))

        st.markdown("---")
        st.header("3. Doplňky")
        pocet_dvere_vc = st.number_input("Dveře v čele (ks)", 0, 2, get_val('pocet_dvere_vc', 0))
        pocet_dvere_bok = st.number_input("Boční vstup (ks)", 0, 4, get_val('pocet_dvere_bok', 0))
        zamykaci_klika = st.checkbox("Zamykací klika", value=get_val('zamykaci_klika', False))
        klapka = st.checkbox("Větrací klapka", value=get_val('klapka', False))
        pochozi_koleje = st.checkbox("Pochozí koleje", value=get_val('pochozi_koleje', False))
        pochozi_koleje_zdarma = st.checkbox("➡️ Akce: Koleje ZDARMA", value=get_val('pochozi_koleje_zdarma', False))
        ext_draha_m = st.number_input("Prodloužení dráhy (m)", 0.0, 20.0, get_val('ext_draha_m', 0.0), step=0.5)
        podhori = st.checkbox("Zpevnění Podhoří", value=get_val('podhori', False))

        st.markdown("---")
        st.header("4. Ostatní")
        col_km1, col_km2 = st.columns(2)
        with col_km1:
            km = st.number_input("Doprava (km)", 0, 5000, get_val('km', 0))
        with col_km2:
            cena_za_km = st.number_input("Cena za km", 0, 100, get_val('cena_za_km', 18))
            
        montaz = st.checkbox("Montáž", value=get_val('montaz', True))
        sleva_pct = st.number_input("Sleva (%)", 0, 100, get_val('sleva_pct', 0))
        dph_sazba = st.selectbox("DPH", [21, 12, 0], index=0)

    # --- VÝPOČET ---
    base_price, height, err = calculate_base_price_db(model, sirka, moduly)

    if err:
        st.error(f"⚠️ {err}")
    else:
        items = []
        avg_mod_len = int(celkova_delka / moduly)
        items.append({"pol": f"Zastřešení {model}", "det": f"{moduly} seg., Š: {sirka}mm ({avg_mod_len} mm/mod)", "cen": base_price})
        
        # PRODLOUŽENÍ / ZKRÁCENÍ
        if diff_len > 10:
            p_data = get_surcharge_db("Prodloužení modulu", is_rock)
            p_meter_data = get_surcharge_db("za metr", is_rock)
            
            fix_prod = p_data['fix'] if p_data['fix'] > 0 else 3000
            per_m = p_meter_data['fix'] if p_meter_data['fix'] > 0 else 2000
            
            price_len = (diff_len / 1000.0) * per_m
            cost = fix_prod + price_len
            items.append({"pol": "Atypická délka (Prodloužení)", "det": f"+{diff_len} mm", "cen": cost})

        elif diff_len < -10:
            p_data = get_surcharge_db("Zkrácení modulu", is_rock)
            val = p_data['fix'] if p_data['fix'] > 0 else 1500
            items.append({"pol": "Atypická délka (Zkrácení)", "det": f"{diff_len} mm", "cen": val})

        # Barvy
        if "Stříbrný" in barva_typ:
            val = base_price * -0.10
            items.append({"pol": "BONUS: Stříbrný Elox", "det": "Sleva 10% ze základu", "cen": val})
        elif "RAL" in barva_typ:
            p_data = get_surcharge_db("RAL", is_rock)
            val = p_data['pct'] if p_data['pct'] > 0 else 0.20
            c = base_price * val
            items.append({"pol": "Příplatek RAL", "det": f"{val*100:.0f}%", "cen": c})
        elif "Bronz" in barva_typ:
            p_data = get_surcharge_db("BR elox", is_rock)
            val = p_data['pct'] if p_data['pct'] > 0 else 0.05
            c = base_price * val
            items.append({"pol": "Příplatek Bronz", "det": f"{val*100:.0f}%", "cen": c})
        elif "Antracit" in barva_typ:
            p_data = get_surcharge_db("antracit elox", is_rock)
            val = p_data['pct'] if p_data['pct'] > 0 else 0.05
            c = base_price * val
            items.append({"pol": "Příplatek Antracit", "det": f"{val*100:.0f}%", "cen": c})

        # GEOMETRIE A POLY (S modelem)
        roof_a, face_a_large, face_a_small = calculate_complex_geometry(model, sirka, height, moduly, celkova_delka)
        p_data = get_surcharge_db("Plný polykarbonát", is_rock)
        
        # Ochrana: Cena poly musí být číslo (např. 1000), ne procento
        poly_p = p_data['fix']
        if poly_p < 10: poly_p = 1000 # Fallback
        
        if poly_strecha:
            c = roof_a * poly_p
            items.append({"pol": "Plný poly (Střecha)", "det": f"{roof_a:.1f} m²", "cen": c})
        if poly_celo_male:
            c = face_a_small * poly_p
            items.append({"pol": "Plný poly (Malé čelo)", "det": f"{face_a_small:.1f} m²", "cen": c})
        if poly_celo_velke:
            c = face_a_large * poly_p
            items.append({"pol": "Plný poly (Velké čelo)", "det": f"{face_a_large:.1f} m²", "cen": c})

        if change_color_poly:
            p_data = get_surcharge_db("barvy poly", is_rock)
            val = p_data['pct'] if p_data['pct'] > 0 else 0.07
            c = base_price * val
            items.append({"pol": "Změna barvy poly", "det": f"{val*100:.0f}%", "cen": c})

        if podhori:
            p_data = get_surcharge_db("podhorskou", is_rock)
            val = p_data['pct'] if p_data['pct'] > 0 else 0.15
            c = base_price * val
            items.append({"pol": "Zpevnění Podhoří", "det": f"{val*100:.0f}%", "cen": c})

        doors = []
        p_vc = get_surcharge_db("Jednokřídlé dveře", is_rock)['fix'] or 5000
        p_bok = get_surcharge_db("boční vstup", is_rock)['fix'] or 7000
        for _ in range(pocet_dvere_vc): doors.append(("Dveře v čele", p_vc))
        for _ in range(pocet_dvere_bok): doors.append(("Boční vstup", p_bok))
        if doors:
            doors.sort(key=lambda x: x[1], reverse=True)
            free = doors.pop(0)
            items.append({"pol": f"{free[0]} (1. ks)", "det": "ZDARMA", "cen": 0})
            for n, p in doors:
                items.append({"pol": n, "det": "Další kus", "cen": p})

        if zamykaci_klika and (pocet_dvere_vc + pocet_dvere_bok) > 0:
            cnt = pocet_dvere_vc + pocet_dvere_bok
            val = get_surcharge_db("Uzamykání dveří", is_rock)['fix'] or 800
            c = cnt * val
            items.append({"pol": "Zamykací klika", "det": f"{cnt} ks", "cen": c})

        if klapka:
            val = get_surcharge_db("klapka", is_rock)['fix'] or 7000
            items.append({"pol": "Větrací klapka", "det": "", "cen": val})

        if pochozi_koleje:
            m_rail = (celkova_delka / 1000.0) * 2
            if pochozi_koleje_zdarma:
                items.append({"pol": "Pochozí koleje", "det": f"{m_rail:.1f} m (AKCE)", "cen": 0})
            else:
                val = get_surcharge_db("Pochozí kolejnice", is_rock)['fix'] or 330
                c = m_rail * val
                items.append({"pol": "Pochozí koleje", "det": f"{m_rail:.1f} m", "cen": c})

        if ext_draha_m > 0:
            val = get_surcharge_db("Jeden metr koleje", is_rock)['fix'] or 220
            c = ext_draha_m * val
            items.append({"pol": "Prodloužení dráhy", "det": f"+{ext_draha_m} m", "cen": c})

        # MONTÁŽ
        mat_sum = sum(x['cen'] for x in items)
        
        c_montaz = 0
        if montaz:
            p_data = get_surcharge_db("Montáž zastřešení v ČR", is_rock)
            val = p_data['pct'] if p_data['pct'] > 0 else 0.08
            c_montaz = mat_sum * val
            items.append({"pol": "Montáž (ČR)", "det": f"{val*100:.0f}% z materiálu", "cen": c_montaz})
        
        # SLEVA
        sum_before_discount = sum(x['cen'] for x in items)
        
        discount_val = 0
        if sleva_pct > 0:
            discount_val = sum_before_discount * (sleva_pct / 100.0)
            items.append({"pol": "SLEVA", "det": f"-{sleva_pct}% (bez dopravy)", "cen": -discount_val})
        
        # DOPRAVA
        c_doprava = 0 if km == 0 else km * cena_za_km
        if km > 0:
            items.append({"pol": "Doprava", "det": f"{km} km x {cena_za_km} Kč", "cen": c_doprava})

        # FINÁLNÍ SOUČET
        total_no_vat = sum(item['cen'] for item in items)
        dph_val = total_no_vat * (dph_sazba / 100.0)
        total_with_vat = total_no_vat + dph_val

        st.divider()
        col1, col2 = st.columns([1.5, 1])
        with col1:
            st.subheader("Rozpočet")
            st.dataframe(pd.DataFrame(items), hide_index=True, use_container_width=True)
            # Debug info pro tebe, Martina:
            st.caption(f"ℹ️ {model}: odskok šířky {MODEL_PARAMS.get(model, MODEL_PARAMS['DEFAULT'])['step_w']}mm")
        with col2:
            st.subheader("Celkem")
            st.metric("Bez DPH", f"{total_no_vat:,.0f} Kč")
            st.metric(f"S DPH ({dph_sazba}%)", f"{total_with_vat:,.0f} Kč")
            
            c_a1, c_a2 = st.columns(2)
            with c_a1:
                if zak_jmeno:
                    zak_udaje = {'jmeno': zak_jmeno, 'adresa': zak_adresa, 'tel': zak_tel, 'email': zak_email, 'vypracoval': vypracoval, 'datum': datum_vystaveni.strftime("%d.%m.%Y"), 'platnost': platnost_do.strftime("%d.%m.%Y"), 'termin': termin_dodani}
                    totals = {'bez_dph': total_no_vat, 'dph': dph_val, 's_dph': total_with_vat, 'sazba_dph': dph_sazba}
                    pdf_data = generate_pdf_html(zak_udaje, items, totals)
                    st.download_button("📄 PDF Nabídka", data=pdf_data, file_name=f"Nabidka_{zak_jmeno}.pdf", mime="application/pdf", type="primary")
            with c_a2:
                if zak_jmeno:
                    if st.button("💾 Uložit do systému"):
                        save_data = {
                            'zak_jmeno': zak_jmeno, 'zak_adresa': zak_adresa, 'zak_tel': zak_tel, 'zak_email': zak_email,
                            'vypracoval': vypracoval, 'platnost_dny': platnost_dny, 'termin_dodani': termin_dodani,
                            'model': model, 'sirka': sirka, 'moduly': moduly, 'celkova_delka': celkova_delka,
                            'barva_typ': barva_typ,
                            'poly_strecha': poly_strecha, 'poly_celo_male': poly_celo_male, 'poly_celo_velke': poly_celo_velke,
                            'change_color_poly': change_color_poly,
                            'pocet_dvere_vc': pocet_dvere_vc, 'pocet_dvere_bok': pocet_dvere_bok,
                            'zamykaci_klika': zamykaci_klika, 'klapka': klapka, 
                            'pochozi_koleje': pochozi_koleje, 'pochozi_koleje_zdarma': pochozi_koleje_zdarma,
                            'ext_draha_m': ext_draha_m, 'podhori': podhori, 'km': km, 'cena_za_km': cena_za_km, 
                            'montaz': montaz, 'sleva_pct': sleva_pct,
                            'dph_sazba': dph_sazba
                        }
                        success, msg = save_offer_to_db(save_data, total_with_vat)
                        if success: st.success("Uloženo!")
                        else: st.error(msg)
