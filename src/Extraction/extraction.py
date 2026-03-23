import os, re, json, hashlib, pathlib
import pandas as pd
import pdfplumber
import shutil
from rapidfuzz import fuzz
from rapidfuzz import process 
from google.cloud import aiplatform
from vertexai.generative_models import GenerativeModel, GenerationConfig, Part
from typing import Optional, Tuple
import unicodedata # Import nécessaire pour la normalisation d'Unicode

# =================== CONFIG ===================
INPUT_FOLDER = r"D:\Rapports Vienne - Extraction Charaf\Di_Copper_go_reports"
OUTPUT_FOLDER = INPUT_FOLDER

FLAGS_CSV = os.path.join(OUTPUT_FOLDER, "ALL_FLAGS.csv")
CACHE_DIR = ".llm_cache_v11"
MAPPING_FILE = r"D:\Rapports Vienne - Extraction Charaf\companies_sites_IDs_materials.csv"
# FICHIER RÉCAPITULATIF
SUMMARY_FILE = r"D:\Rapports Vienne - Extraction Charaf\Dia_sum_patch_Cu_Final.csv"

# ⬇️ DPI CONFIGURATION
DEFAULT_DPI = 320
CHART_DPI = 400

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = r"D:\Documents\bejjit\OneDrive - BRGM\Bureau\gen-lang-client-0621439771-7fb242ad8b70.json"

PROJECT_ID = "gen-lang-client-0621439771"
LOCATION = "europe-west4"
MODEL_ID = "gemini-2.5-flash"

TABLE_HINT = """
IMPORTANT:
If the page contains a table with environmental, water, energy, GHG or production metrics:
- You MUST extract ALL rows.
- You MUST extract ALL numeric cells.
- Do NOT skip any column.
- Do NOT summarize or infer.
- Return one JSON entry per (metric_name, value, unit) found in the table.
"""

# =================== PROMPT RENFORCÉ (Contrainte sur les Unités) ===================

PROMPT = """
You are a senior data analyst. Carefully review the PAGE image and extract ONLY:

# ==================== EXTRACTION PAR CATÉGORIE (9 catégories) ====================
1) PRODUCTION metrics: 
    - CATEGORY: "Production"
    - Production (physical), throughput, ore mined/processed, concentrate, refined products, brines, hardrocks. 
    - Any associated volumes, and contained mass/tonnage. 
    - Units may include (but are not limited to): t, kt, Mt, oz, koz, Moz, carats, kg, lb, m³, L, barrels, MWh, GJ, Nm³, Sm³. 
    - Materials may include (but are not limited to): copper, nickel, lithium, iron ore, manganese, coal, diamonds, PGMs, platinum, palladium, gold, silver, cobalt, zinc, lead, bauxite, aluminium.
2) ECONOMICS metrics (segment-level ONLY): 
    - CATEGORY: "Economics"
    - **CRITICAL**: ONLY extract financial metrics that are CLEARLY and EXPLICITLY tied to a specific commodity/product (e.g., Copper, Nickel, Iron ore, etc.).
    - Metrics MUST include a reference to the product name or a product unit cost (e.g., $/t, c/lb, $/oz).
    - Per-product EBITDA, Realised/realized price by product, Unit costs by product (C1, AISC, $/t, $/oz, c/lb, $/PGM ounce). 
    - EXCLUDE **ALL** general accounting entries and inventory movements (Work-in-progress, Finished goods, Spare parts, Recovery, Provision, Reclassification, Purchase of finished goods, Inventories).
    - EXCLUDE: Grants, Subsidies, Allocations, General Financials (unless product-specific).
3) ENERGY metrics:
    - CATEGORY: "Energy"
    - Energy (consumption, intensity), including electricity, fuels (diesel, oil, gasoline, coal), natural gas, and any other energy carriers (e.g., steam, heat, renewables). 
4) WATER metrics:
    - CATEGORY: "Water"
    - Water (withdrawals, consumption, discharge, quality). 
5) GEOLOGY metrics:
    - CATEGORY: "Geology"
    - Mineral or material resource/reserve classifications (e.g., measured, indicated, inferred, proven, probable). 
    - Grades (wt%, ppm, ppb, %).
6) WASTE metrics:
    - CATEGORY: "Waste"
    - Waste, effluents, tailings.
7) EMISSIONS metrics:
    - CATEGORY: "Emissions"
    - GHG (Scopes 1/2/3), air emissions (NOx, SOx, PM).
8) LAND metrics:
    - CATEGORY: "Land"
    - Land (occupied, disturbed, rehabilitated, conserved, managed). 
    - Units typically include (but are not limited to): ha, km², acres, m², hectares.
9) OTHER metrics (process inputs ONLY):
    - CATEGORY: "Other"
    - Extract ONLY industrial/process inputs that have a PHYSICAL unit:
        • mass units (t, kg, kt, Mt)
        • volume units (L, m³, ML)
        • energy units (kWh, MWh, GJ, TJ)
        • concentration units (mg/L, %, ppm)
        • any chemical/reagent consumption with a physical unit.
    - DO NOT extract any metric WITHOUT a physical unit.
    - DO NOT extract:
        • employees / people counts
        • complaints, grievances, incidents (unless environmental and with physical units)
        • social, HR or training information (hours, programs, participation)
        • accident numbers or safety indicators

# ==================== CONTRAINTES DE SORTIE ====================
IGNORE and DO NOT EXTRACT people/workforce/safety data (employees, OEL, LTIFR, TRIFR, accidents, hours worked, medical, etc.). 
IGNORE company-level financials not tied to a specific product.
DO NOT use the word "page" as a unit. If a metric has no value and no unit (e.g., page number), DO NOT extract it.

# 💡 Extraction de l'Entité Locale (SIMPLIFIÉE)
Also return three context fields:
- "category": YOU MUST ASSIGN the metric to its corresponding list CATEGORY (e.g., "Production", "Economics", "Energy", "Water", "Geology", "Waste", "Emissions", or "Other").
- "context": a PRECISE and detailed snippet (≤200 characters) from the SAME panel/row where the value appears. CAPTURE all helpful qualifiers (asset/site/project name, scope, timeframe/years, period). Prioritize local precision; do not return full paragraphs. For items from tables/graphs set "context": "N/A".
- "site": the explicit asset/site/project name if it appears in the SAME panel/section (title, subtitle, bullet, table row header). If none is identifiable, return "N/A".

For each extracted metric, return a JSON object with: 
- "category" 
- "metric_name" 
- "value" 
- "unit" (exactly as written, e.g., t, kt, Mt, oz, koz, Moz, carats, %, mg/L, t CO2e, etc.; otherwise "N/A") 
- "year" (if available, else "N/A") 
- "source_type" ("text", "table", or "graph") 
- "context" 
- "site"

Constraints: 
- Use layout/positioning to correctly associate each label with its value in the SAME panel. 
- Never mix values from different panels. 
- Always capture the unit exactly as written (même si non dans les exemples). 
- Respond STRICTLY with a single JSON array, minified on one line. If nothing relevant: []. 
"""

FALLBACK_PROMPT = """
You are a senior data analyst. Analyze the following text and image from the FIRST PAGE of a corporate report.
Your sole task is to identify the full, official name of the company/group that published this report. 
Ignore all acronyms unless the full name is not present. 
Identify the name found in the largest font or in the main title/logo area.

Return ONLY the name as a simple string, no JSON, no quotes, no commentary. If you cannot identify the name, return 'UNKNOWN'.
"""

# =================== FONCTIONS UTILITAIRES DE BASE ===================

PEOPLE_EXCLUDE = re.compile(r"\bemployee\b|\bworkforce\b|\blabou?r\b|\bheadcount\b|\boel\b|\binhalable\b|"
                            r"\bltifr\b|\btrifr\b|\bfatal\b|\binjur|\bhours\s*worked\b|\blost\s*time\b|\bmedical\b", re.I)
WASTE_WHITELIST = re.compile(r"\bwaste\b", re.I)
COMMODITIES = re.compile(r"copper|nickel|lithium|iron\s*ore|manganese|coal|diamond|pgm?s?|platinum|palladium|gold|silver|cobalt|zinc|lead|bauxite|aluminiu?m", re.I)
FIN_BY_PRODUCT = re.compile(r"ebitda|real(?:is|iz)ed?\s*price|unit\s*cost|cash\s*cost|c1|aisc|"
                            r"cost\s*/\s*(t|oz|lb|kg)|\$/\s*(t|oz|lb|kg)|c/lb|\$/pgm\s*ounce|\$\/oz|\$\/t", re.I)
GENERIC_FINANCIALS_EXCLUDE = re.compile(r"work-in-progress|finished\s*goods|spare\s*parts|recovery|provision|reclassification|purchase\s*of\s*finished\s*goods|inventories|sale\s*of\s*scrap", re.I)

def keep_item(it: dict) -> bool:
    name = (it.get("metric_name") or "").lower()
    unit = (it.get("unit") or "").lower()
    category = (it.get("category") or "").lower()
    
    value_raw = str(it.get("value") or "").strip() 
    txt = f"{name} {unit}"
    
    if not value_raw:
        if unit.strip() != "%": return False
            
    if PEOPLE_EXCLUDE.search(txt): return False
        
    # Règle CRITIQUE 1: Exclure les données financières génériques
    if category == "economics":
        if GENERIC_FINANCIALS_EXCLUDE.search(name):
             if not COMMODITIES.search(name):
                 return False
        
    if WASTE_WHITELIST.search(txt): return True
        
    # Règle CRITIQUE 2: Logique initiale pour les métriques financières spécifiques au produit
    if FIN_BY_PRODUCT.search(txt):
        return bool(COMMODITIES.search(txt))
        
    return True

CHART_WORDS = re.compile(r"scope|chart|figure|legend|emissions|share|percentage|by\s+source|breakdown", re.I)

def is_charty_page(text: str) -> bool:
    text = text or ""; many_years = len(re.findall(r"\b(201[5-9]|202[0-9]|2030)\b", text)) >= 3
    many_nums = len(re.findall(r"\d", text)) >= 40; has_words = bool(CHART_WORDS.search(text))
    return many_years or many_nums or has_words

def parse_json_robuste(raw: str):
    raw = (raw or "").strip();
    if raw.startswith("```"): raw = re.sub(r"^```(?:json)?\s*", "", raw); raw = re.sub(r"\s*```$", "", raw)
    def _to_list(x):
        if isinstance(x, list): return x
        if isinstance(x, dict):
            for v in x.values():
                if isinstance(v, list): return v
            return [x]
        return []
    try: return _to_list(json.loads(raw))
    except Exception: pass
    start = raw.find("[");
    if start != -1:
        depth = 0; end = None
        for i, ch in enumerate(raw[start:], start):
            if ch == "[": depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0: end = i + 1; break
        if end:
            arr = raw[start:end]; arr = re.sub(r",\s*([}\]])", r"\1", arr); arr = re.sub(r"}\s*{", "},{", arr)
            arr = re.sub(r"]\s*{", "],{", arr); arr = re.sub(r";\s*([{\[])", r",\1", arr); arr = re.sub(r"\bNaN\b", "null", arr, flags=re.IGNORECASE)
            try: return _to_list(json.loads(arr))
            except Exception: pass
    m = re.search(r"\{[\s\S]*\}", raw)
    if m:
        try: return _to_list(json.loads(m.group(0)))
        except Exception: return []
    return []

def render_page_png_bytes(pdf_path: str, page_num: int, dpi: int) -> bytes:
    try: import fitz
    except Exception as e: raise SystemExit("❌ PyMuPDF non installé. Fais: pip install pymupdf") from e
    doc = fitz.open(pdf_path)
    try:
        page = doc.load_page(page_num - 1); mat = fitz.Matrix(dpi / 72.0, dpi / 72.0); pix = page.get_pixmap(matrix=mat, alpha=False)
        return pix.tobytes("png")
    finally: doc.close()

def cache_key(pdf_name: str, page_num: int, prompt: str, img_bytes: bytes) -> str:
    h = hashlib.sha256((pdf_name + str(page_num) + prompt).encode("utf-8") + img_bytes).hexdigest()
    pathlib.Path(CACHE_DIR).mkdir(exist_ok=True)
    return os.path.join(CACHE_DIR, f"{pdf_name}_p{page_num}_{h}.json")

def load_cache(path: str):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f: return json.load(f)
        except Exception: return None
    return None

def save_cache(path: str, data):
    try:
        with open(path, "w", encoding="utf-8") as f: json.dump(data, data, ensure_ascii=False)
    except Exception: pass

def simple_flags(page_text: str, row: dict) -> list[str]:
    reasons = []; name = (row.get("metric_name") or "").lower(); unit = (row.get("unit") or "").lower()
    if "fresh water" in name and re.search(r"employee|workforce|oel", page_text, re.I): reasons.append("water+people_context_mismatch")
    if re.search(r"\b(ml|gj|t\s*co2e|kwh|mwh)\b", unit) and re.search(r"employee|workforce|oel", page_text, re.I): reasons.append("env_unit_in_people_page")
    if unit.strip() == "%" and row.get("value"):
        try:
            v = float(str(row["value"]).replace(",", "").replace(" ", ""))
            if v <= 0 or v > 100: reasons.append("percentage_out_of_range")
        except Exception: pass
    return reasons

def extract_snippet(page_text: str, it: dict, maxlen: int = 200) -> str | None:
    if not page_text: return None
    t = " ".join(str(page_text).split()); name = str(it.get("metric_name") or "").strip()
    if name:
        m = re.search(re.escape(name), t, re.I)
        if m:
            start = max(0, m.start() - 40); end = min(len(t), m.end() + 160)
            return t[start:end][:maxlen]
    val = str(it.get("value") or ""); token = re.sub(r"[^\d.,\-]", "", val)
    if token:
        m = re.search(re.escape(token), t)
        if m:
            start = max(0, m.start() - 60); end = min(len(t), m.end() + 140)
            return t[start:end][:maxlen]
    return None

def normalize_and_constrain_context(it: dict, page_text: str) -> dict:
    for k in ("context", "context_quote", "context-quote", "quote_from_text", "quote"):
        if k in it and it.get(k): it["context"] = it[k]; break
    st = (it.get("source_type") or "").lower()
    if st in ("table", "graph"): it["context"] = "N/A"
    elif st == "text" and not it.get("context"): it["context"] = extract_snippet(page_text, it) or "N/A"
    for k in ("context_quote", "context-quote", "quote_from_text", "quote"): it.pop(k, None)
    it.setdefault("category", "Unclassified")
    return it


# =================== FONCTIONS D'AFFILIATION ET DE SOURCING ===================

def clean_company_name(name: str) -> str:
    """Nettoie le nom de la compagnie en retirant les suffixes légaux, les mots génériques, et NORMALISE les caractères accentués."""
    if pd.isna(name): return ""
    
    name = str(name).strip()
    
    # 1. NORMALISATION CRITIQUE: Suppression des accents et conversion en minuscule
    name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('utf-8')
    name = name.lower()

    # 1a. Suppression des suffixes légaux et mots de liaison
    suffixes = [
        r'\bjoint stock company\b', r'\bjs c\b', r'\bjsac\b', r'\bcorporation\b', r'\bcorp\b', r'\binc\b', 
        r'\bsa\b', r'\bltd\b', r'\bspolka akcyjna\b', r'\bco\b', r'\bgmbh\b', r'\bsarl\b', r'\band co\b',
        r'\band\b', r'\bthe\b', r'\bof\b' 
    ]
    for suffix in suffixes:
        name = re.sub(suffix, ' ', name)

    # 2. FIX CRITIQUE: Suppression des termes génériques des noms (y compris KGHM)
    generic_terms = [
        r'\bmining\b', r'\bmetals\b', r'\bmetallurgical\b', r'\bcomplex\b', 
        r'\bplant\b', r'\bcombine\b', r'\bmine\b', r'\bproducer\b', r'\bgroup\b',
        r'\bpolska\s+miedz\b', 
        r'\bs\s*a\b', 
    ]
    for term in generic_terms:
        name = re.sub(term, ' ', name)

    # 3. Remplacement des caractères non alphanumériques (sauf espaces) par un espace
    name = re.sub(r'[^\w\s]', ' ', name)
    
    # 4. Consolidation des espaces et suppression des espaces de début/fin
    name = re.sub(r'\s+', ' ', name).strip()
    
    return name

def load_summary_company_name(pdf_name: str) -> Optional[str]:
    """
    Charge le nom de la compagnie à partir d'un fichier CSV.
    """
    if not os.path.exists(SUMMARY_FILE): 
        print(f" ⚠️ Fichier Summary introuvable : {SUMMARY_FILE}")
        return None
    
    try:
        # Lecture du CSV avec détection automatique du séparateur (virgule ou point-virgule)
        df_summary = pd.read_csv(SUMMARY_FILE, sep=None, engine='python', encoding='latin-1')
        
        # Nettoyage des noms de colonnes (enlève espaces invisibles)
        df_summary.columns = df_summary.columns.astype(str).str.strip()

        # On définit les colonnes cibles
        col_pdf = 'pdf'
        col_company = 'company'

        if col_pdf not in df_summary.columns or col_company not in df_summary.columns:
            print(f" ❌ Colonnes 'pdf' ou 'company' manquantes dans le CSV. Colonnes lues : {list(df_summary.columns)}")
            return None

        # On cherche la ligne correspondant au PDF
        # On compare sans l'extension pour être plus souple
        pdf_name_no_ext = os.path.splitext(pdf_name)[0]
        
        # On crée une version nettoyée de la colonne pdf pour la comparaison
        df_summary['pdf_clean'] = df_summary[col_pdf].astype(str).str.strip()
        
        match = df_summary[
            (df_summary['pdf_clean'] == pdf_name) | 
            (df_summary['pdf_clean'] == pdf_name_no_ext)
        ]
        
        if not match.empty:
            company_name = match[col_company].iloc[0]
            if pd.notna(company_name) and str(company_name).strip().upper() not in ['N/A', 'UNKNOWN', 'NAN']:
                return str(company_name).strip()
            
    except Exception as e:
        print(f" ❌ ERREUR lors de la lecture du CSV {SUMMARY_FILE}: {e}")
        
    return None

def get_company_name_from_front_page(pdf_path: str, model: GenerativeModel, cfg: GenerationConfig) -> Optional[str]:
    """
    Tente d'extraire le nom de la compagnie uniquement de la Page 1 (image + texte)
    en priorisant le nom complet plutôt que les acronymes.
    """
    pdf_name = os.path.basename(pdf_path)
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if not pdf.pages: return None
            page_text = (pdf.pages[0].extract_text(x_tolerance=2) or "")
    except Exception as e:
        print(f" ❌ Erreur lecture Page 1 pour Fallback: {e}"); return None

    try:
        img_bytes = render_page_png_bytes(pdf_path, 1, DEFAULT_DPI)
    except Exception as e:
        print(f" ❌ Erreur image Page 1 pour Fallback: {e}"); return None

    print("     -> Appel Fallback sur Page 1 pour le nom de compagnie...")
    
    fallback_cache_key = cache_key(pdf_name, 0, FALLBACK_PROMPT, img_bytes) 
    cached_name = load_cache(fallback_cache_key)

    if cached_name is not None: return cached_name

    try:
        resp = model.generate_content(
            [FALLBACK_PROMPT, f"PAGE 1 TEXT:\n{page_text[:4000]}", Part.from_data(mime_type="image/png", data=img_bytes)],
            generation_config=cfg
        )
        name = (getattr(resp, "text", "") or "").strip()
        if name.upper() == 'UNKNOWN' or not name: name = None
        else:
            name = name.strip('\'"').strip()
            save_cache(fallback_cache_key, name)
        return name

    except Exception as e:
        print(f"     ❌ Erreur API Fallback: {e}")
        return None

def attempt_fuzzy_match(name_raw: Optional[str], mapping_df: pd.DataFrame, threshold: int, attempt_name: str, use_clean: bool) -> Tuple[Optional[str], Optional[str]]:
    """Tente un matching flou sur le nom fourni (brut ou nettoyé) et renvoie l'ID et le nom court en cas de succès."""
    
    if not name_raw: return None, None
    
    if use_clean:
        name_for_match = clean_company_name(name_raw)
        log_name = f"'{name_raw}' (nettoyé: '{name_for_match}')"
    else:
        # Version 'brute' : Normalisation Unicode, minuscule et retrait des symboles (sans les suppressions agressives de mots)
        name_for_match = unicodedata.normalize('NFKD', name_raw).encode('ascii', 'ignore').decode('utf-8').lower().strip()
        name_for_match = re.sub(r'[^\w\s]', ' ', name_for_match)
        name_for_match = re.sub(r'\s+', ' ', name_for_match).strip()
        log_name = f"'{name_raw}' (brut/norm.)"

    # TENTATIVE D'EXACT MATCH (sur la clé de recherche)
    exact_match_df = mapping_df[mapping_df['company_name_key'] == name_for_match]
    
    if not exact_match_df.empty:
        dominant_id = exact_match_df['ID_operator_SP'].iloc[0]
        dominant_name = exact_match_df['company_name_short'].iloc[0]
        print(f"→ {attempt_name}: ID trouvé (Exact Match). Nom utilisé: {name_for_match} ({dominant_id})")
        return dominant_id, dominant_name
    
    # FUZZY MATCH AVEC TokenSetRatio
    mapping_company_choices = mapping_df['company_name_key'].tolist()
    
    best_match_info = process.extractOne(
        name_for_match, 
        mapping_company_choices, 
        scorer=fuzz.token_set_ratio, 
        score_cutoff=threshold
    )
    
    if best_match_info:
        matched_key, score, index = best_match_info
        original_index = mapping_df[mapping_df['company_name_key'] == matched_key].index[0]

        dominant_id = mapping_df.loc[original_index, 'ID_operator_SP']
        dominant_name = mapping_df.loc[original_index, 'company_name_short']
        print(f"→ {attempt_name}: ID trouvé (TokenSet Match {score:.1f}%). Nom utilisé: {name_for_match} ({dominant_id})") 
        return dominant_id, dominant_name
    else:
        print(f"→ {attempt_name}: Échec match ID. Nom de recherche: {name_for_match}. Seuil: {threshold}%.")
        return None, None


# =================== FONCTION DE TRAITEMENT UNIQUE (HYBRIDE DÉCISIF) ===================
def process_one_pdf(pdf_path, model, cfg, mapping_df):
    pdf_name = os.path.basename(pdf_path)
    print(f"\n{'='*40}\n🚀 TRAITEMENT (Ciblé Page 1 + Stabilité) : {pdf_name}\n{'='*40}")

    base_name = os.path.splitext(pdf_name)[0]
    out_xlsx = os.path.join(OUTPUT_FOLDER, f"{base_name}_EXTRACT.xlsx")
    flags_csv = os.path.join(OUTPUT_FOLDER, f"{base_name}_FLAGS.csv")

    if os.path.exists(out_xlsx):
        print(f"⚠️ Fichier déjà existant, on passe : {out_xlsx}")
        return

    # =========================================================================
    # ⬇️ SOURCING ET DOUBLE TENTATIVE DE MATCHING ⬇️
    # =========================================================================
    
    COMPANY_FUZZY_THRESHOLD = 90  # Seuil de sécurité élevé
    SITE_FUZZY_THRESHOLD = 70 

    # 1. SOURCING DES NOMS
    dominant_name_raw_llm = get_company_name_from_front_page(pdf_path, model, GenerationConfig(temperature=0.0, max_output_tokens=256))
    dominant_name_raw_summary = load_summary_company_name(pdf_name)
    
    dominant_id = None
    dominant_name = None
    
    dominant_name_raw = dominant_name_raw_llm if dominant_name_raw_llm else dominant_name_raw_summary

    # 2. TENTATIVES SUR LE NOM DU LLM (PRIORITÉ MAXIMALE)
    if dominant_name_raw_llm:
        dominant_id, dominant_name = attempt_fuzzy_match(
            dominant_name_raw_llm, mapping_df, COMPANY_FUZZY_THRESHOLD, "Tentative 1A (LLM Brut)", use_clean=False
        )
        
        if dominant_id is None:
             dominant_id, dominant_name = attempt_fuzzy_match(
                dominant_name_raw_llm, mapping_df, COMPANY_FUZZY_THRESHOLD, "Tentative 1B (LLM Nettoyé)", use_clean=True
            )

    # 3. TENTATIVES SUR LE NOM DU SUMMARY (SI LE LLM A TOTALEMENT ÉCHOUÉ)
    if dominant_id is None and dominant_name_raw_summary:
        print("→ Échec LLM. Début des tentatives sur le nom du Summary.")
        
        dominant_id, dominant_name = attempt_fuzzy_match(
            dominant_name_raw_summary, mapping_df, COMPANY_FUZZY_THRESHOLD, "Tentative 2A (Summary Brut)", use_clean=False
        )
        
        if dominant_id is None:
            dominant_id, dominant_name = attempt_fuzzy_match(
                dominant_name_raw_summary, mapping_df, COMPANY_FUZZY_THRESHOLD, "Tentative 2B (Summary Nettoyé)", use_clean=True
            )
            if dominant_id is not None:
                dominant_name_raw = dominant_name_raw_summary

        
    # LOG FINAL DU SOURCING
    if dominant_id is None:
        print("→ Échec total du Sourcing de Nom ID. Poursuite sans ID de compagnie.")
    # =========================================================================


    try:
        with pdfplumber.open(pdf_path) as pdf:
            total_pages = len(pdf.pages)
            # FIX CRITIQUE DE LA VARIABLE 'p' non définie
            page_texts = [(page.extract_text(x_tolerance=2) or "") for page in pdf.pages]
    except Exception as e:
        print(f"❌ Erreur lecture PDF {pdf_name} : {e}")
        return

    print(f"→ {total_pages} pages")
    all_rows, flag_rows = [], []
    

    for page_num in range(1, total_pages + 1):
        txt = page_texts[page_num-1]
        dpi = CHART_DPI if is_charty_page(txt) else DEFAULT_DPI
        print(f"→ Page {page_num}/{total_pages} | DPI={dpi}")

        try:
            img_bytes = render_page_png_bytes(pdf_path, page_num, dpi)
        except Exception as e:
            print(f" ❌ Erreur image page {page_num}: {e}"); continue

        # AJOUT DU NOM DU FICHIER DANS LA CLÉ DE CACHE
        unique_prompt = PROMPT + f" [FILE: {pdf_name}]"
        ck = cache_key(pdf_name, page_num, unique_prompt, img_bytes)
        data = load_cache(ck)

        if data is None:
            print("     Appel Gemini Vision…")
            try:
                resp = model.generate_content(
                    [
                        TABLE_HINT, 
                        PROMPT,
                        f"PAGE_TEXT (context only):\n{txt[:4000]}",
                        Part.from_data(mime_type="image/png", data=img_bytes)
                    ],
                    generation_config=cfg
                )

                data = parse_json_robuste((getattr(resp, "text", "") or "").strip())
                save_cache(ck, data)
            except Exception as e:
                print(f"     ❌ Erreur API : {e}"); data = []
        else:
            print("     ↻ cache")

        if not data: continue

        for it in data:
            if isinstance(it, dict) and keep_item(it): 
                it.setdefault("metric_name", None)
                it.setdefault("value", None)
                it.setdefault("unit", None)
                it.setdefault("year", None)
                
                it.setdefault("entity_name", dominant_name_raw if dominant_name_raw else "N/A") 
                
                it["source_page"] = page_num
                it["source_pdf"] = pdf_name 
                
                it = normalize_and_constrain_context(it, txt)
                all_rows.append(it)

                for reason in simple_flags(txt, it):
                    flag_rows.append({**it, "reason": reason, "source_pdf": pdf_name})

    if not all_rows:
        print(f"ℹ️ Rien trouvé pour {pdf_name}."); return

    df = pd.DataFrame(all_rows)
    
    # ⬇️ LOGIQUE D'AFFILIATION FINALISÉE (Rattachement ID) ⬇️
    
    SITE_FUZZY_THRESHOLD = 70 
    
    df_merged = df.copy() 
    df_merged['ID_operator_SP'] = None
    df_merged['company_name_short'] = None
    df_merged['external_site_ID'] = None
    df_merged['primary_commodity_site'] = None 
    
    if dominant_id is not None:
         df_merged['ID_operator_SP'] = df_merged['ID_operator_SP'].fillna(dominant_id)
         df_merged['company_name_short'] = df_merged['company_name_short'].fillna(dominant_name)
    
    if mapping_df is not None:
        
        # 2. LOGIQUE DE MATCHING DES SITES (PAUSE/JUMP SI ID MANQUANT)
        
        if "site" in df.columns and "site_name_key" in mapping_df.columns:
            
            df_merged['site_key'] = df_merged['site'].astype(str).str.lower().str.replace('n/a', '').str.strip()
            df_merged['site_key'] = df_merged['site_key'].apply(clean_company_name) 
            
            unique_sites_to_match = df_merged[df_merged['site_key'] != '']['site_key'].unique()
            site_to_id_map = {} 
            
            # --- PREMIÈRE PASSE (Rattrapage de l'ID Cie si besoin) ---
            # FIX: Ce bloc est désormais désactivé dans le code que je vous ai fourni, 
            # mais nous le conservons ici pour le contexte du log.
            if dominant_id is None and unique_sites_to_match.size > 0:
                print(f"   ∟ ID Compagnie Inconnu. Tentative de RATTRAPAGE via Sites DÉSACTIVÉE (Trop risqué).")
            
            # --- DEUXIÈME PASSE (Matching de TOUS les sites valides avec le FILTRE) ---
            
            # ⚠️ LE BLOC CRITIQUE QUI NE DOIT S'EXÉCUTER QUE SI L'ID EST CONNU ⚠️
            if dominant_id is not None and unique_sites_to_match.size > 0:
                
                mapping_site_df = mapping_df[mapping_df['ID_operator_SP'] == dominant_id].copy() 
                mapping_site_choices = mapping_site_df['site_name_key'].tolist()
                print(f"   ∟ Reprise de matching de TOUS les sites (Seuil {SITE_FUZZY_THRESHOLD}%) pour ID {dominant_id}.")

                for site_key in unique_sites_to_match:
                    best_match_info = process.extractOne(
                        site_key, 
                        mapping_site_choices, 
                        scorer=fuzz.WRatio, 
                        score_cutoff=SITE_FUZZY_THRESHOLD
                    )
                    
                    if best_match_info:
                        matched_key, score, index = best_match_info
                        original_index = mapping_site_df[mapping_site_df['site_name_key'] == matched_key].index[0]
                        
                        site_match_data = {
                            'ID_operator_SP_site': mapping_df.loc[original_index, 'ID_operator_SP'],
                            'company_name_short_site': mapping_df.loc[original_index, 'company_name_short'],
                            'external_site_ID_site': mapping_df.loc[original_index, 'site_ID'],
                            'primary_commodity_site_site': mapping_df.loc[original_index, 'primary_commodity_site']
                        }
                        site_to_id_map[site_key] = site_match_data
                        print(f"   ∟ Site matché (Fuzzy {score:.1f}%): '{site_key}' -> '{mapping_df.loc[original_index, 'site_name']}'")

                if site_to_id_map:
                    temp_site_map_df = pd.DataFrame.from_dict(site_to_id_map, orient='index')
                    
                    df_merged = pd.merge(
                        df_merged, 
                        temp_site_map_df, 
                        left_on='site_key', 
                        right_index=True, 
                        how='left'
                    )
                    
                    df_merged['ID_operator_SP'] = df_merged['ID_operator_SP_site'].combine_first(df_merged['ID_operator_SP'])
                    df_merged['company_name_short'] = df_merged['company_name_short_site'].combine_first(df_merged['company_name_short'])
                    df_merged['external_site_ID'] = df_merged['external_site_ID_site'].combine_first(df_merged['external_site_ID'])
                    df_merged['primary_commodity_site'] = df_merged['primary_commodity_site_site'].combine_first(df_merged['primary_commodity_site'])
                    
                    cols_to_drop = [c for c in df_merged.columns if c.endswith('_site')]
                    df_merged = df_merged.drop(columns=cols_to_drop, errors='ignore')
                
        if dominant_id is None:
            print("     ∟ Filtrage final: Aucune affiliation ID trouvée, les colonnes ID/short_name/site resteront vides ou 'N/A'.")
    
    # ⬆️ FIN DE LA LOGIQUE D'AFFILIATION FINALISÉE ⬆️
    
    df = df_merged.copy() 
    
    df['entity_name'] = df['company_name_short'].combine_first(df['entity_name']) 
    df = df.drop(columns=['primary_commodity_site', 'site_key', 'entity_key'], errors='ignore')

    for col in ['entity_name', 'site', 'metric_name', 'value', 'unit']:
        if col in df.columns:
            df[col] = df[col].astype(str).str.replace(r'\s+', ' ', regex=True).str.strip()
            df[col] = df[col].str.replace(',', '', regex=False)
    
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    
    final_cols = ["source_pdf", "ID_operator_SP", "company_name_short", "entity_name", "external_site_ID", "site", "category", "metric_name", "value", "unit", "year", "source_type", "source_page", "context"]
    
    existing_cols = df.columns.tolist()
    ordered_cols = [c for c in final_cols if c in existing_cols]
    remaining_cols = [c for c in existing_cols if c not in ordered_cols]
    
    df = df[ordered_cols + remaining_cols]
    
    df.to_excel(out_xlsx, index=False)
    print(f"✅ OK : {os.path.basename(out_xlsx)} ({len(df)} lignes)")

    if flag_rows:
        pd.DataFrame(flag_rows).to_csv(FLAGS_CSV, index=False, encoding="utf-8-sig")

    return 


# =================== MAIN LOOP ===================
def main():
    import glob
    aiplatform.init(project=PROJECT_ID, location=LOCATION)
    model = GenerativeModel(MODEL_ID)
    
    # ⬇️ LOGIQUE DE CHARGEMENT DU MAPPING CSV ⬇️
    mapping_df = None
    try:
        print(f"Chargement du fichier de mapping: {MAPPING_FILE}")
        if MAPPING_FILE.endswith(".xlsx"): # Supporte le CSV même si le nom est .xlsx
            mapping_df = pd.read_excel(MAPPING_FILE, engine='openpyxl')
        else:
            mapping_df = pd.read_csv(MAPPING_FILE, sep=';', encoding='utf-8') 

        mapping_df = mapping_df.dropna(subset=['site_name'])
        
        mapping_df['company_name_short'] = mapping_df['company_name_short'].astype(str) 
        mapping_df['company_name_key'] = mapping_df['company_name_short'].apply(clean_company_name) 
        mapping_df['site_name_key'] = mapping_df['site_name'].apply(clean_company_name) 
        
        mapping_df['site_ID'] = mapping_df['site_ID'].astype(str)
        mapping_df['primary_commodity_site'] = mapping_df['primary_commodity_site'].astype(str)
        
        print(f"✅ Mapping chargé: {len(mapping_df)} entrées.")
    except Exception as e:
        print(f"❌ ERREUR: Impossible de charger le fichier de mapping {MAPPING_FILE}. Les IDs ne seront pas ajoutés. Détail: {e}")
    # ⬆️ FIN DE LA LOGIQUE DE CHARGEMENT ⬆️

    # ⬇️ CONFIG GENERATION ⬇️
    cfg = GenerationConfig(
        response_mime_type="application/json",
        temperature=0.0,
        top_p=0.1
    )

    pdf_files = glob.glob(os.path.join(INPUT_FOLDER, "*.pdf"))
    if not pdf_files:
        print(f"❌ Aucun PDF trouvé dans {INPUT_FOLDER}")
        return

    print(f"📂 {len(pdf_files)} PDFs à traiter dans {INPUT_FOLDER}")

    for pdf_path in pdf_files:
        # 🔥 Purge le cache avant chaque PDF
        shutil.rmtree(CACHE_DIR, ignore_errors=True)
        pathlib.Path(CACHE_DIR).mkdir(exist_ok=True)
        
        # ⚠️ Appel de la fonction avec le DataFrame de mapping (mapping_df)
        process_one_pdf(pdf_path, model, cfg, mapping_df) 


    print("\n🏁 TRAITEMENT TERMINÉ POUR TOUS LES FICHIERS.")


if __name__ == "__main__":
    main()