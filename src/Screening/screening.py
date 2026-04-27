# -*- coding: utf-8 -*-
"""
ESG QUICK SCAN — périmètre + process industriel (DOSSIER, mode PATCH)
But: décider si le rapport est exploitable AVANT extraction lourde.
OBJECTIFS FINALS: Granularité Site/Métal, Priorité Prod/Env > Financier, Identification Cu/Ni, CATÉGORISATION DES SITES.
STRATÉGIE: Utilise uniquement l'extraction robuste (tables forcées) pour maximiser la détection de structure.
REPRISE: Retraite les DIAG de taille <= SIZE_THRESHOLD (ex: 2200 octets).
EXCEL: Lit l'ancien Excel, met à jour les nouvelles lignes, et sauvegarde la fusion.
"""

import os, re, sys, json, time
import pdfplumber
import pandas as pd
from typing import List, Dict, Any
from google.cloud import aiplatform
from vertexai.generative_models import GenerativeModel, GenerationConfig

# ===================== CONFIG =====================
# ATTENTION: Vérifiez le chemin du dossier d'entrée
IN_DIR = os.getenv("INPUT_FOLDER", "./input")

# Seuil "diag vide" (octets). 2200 ≈ 2 Ko. Les diagnostics vides (échec) sont souvent de cette taille.
SIZE_THRESHOLD = 2200

# Nombre maximum de tentatives après le premier échec d'analyse vide
MAX_RETRIES = 3

# Métaux d'intérêt pour la décision "GO"
METALS_OF_INTEREST = {
    "Cu": ["copper", "cuivre", "chalcocite", "chalcopyrite", "bornite"],
    "Ni": ["nickel", "laterite", "sulfide", "matte", "ferronickel"],
}
INTEREST_KEYWORDS = set(sum(METALS_OF_INTEREST.values(), []))

# ===================== GOOGLE CLOUD CONFIG =====================
# ⚠️ IMPORTANT:
# Définir la variable d'environnement avant exécution :
# GOOGLE_APPLICATION_CREDENTIALS = chemin/vers/credentials.json

PROJECT_ID = os.getenv("PROJECT_ID", "your-project-id")
LOCATION = os.getenv("VTX_LOCATION", "europe-west4")
MODEL_ID = os.getenv("VTX_MODEL", "gemini-2.5-pro")

# ===================== PROMPT (AJUSTÉ final) =====================
PROMPT = r"""
You are a senior data analyst specialized in responsible mineral resource value chains (ACV, RORR).
From the FULL TEXT below (no guessing), return EXACTLY ONE valid JSON object on ONE line
that helps decide if this report is useful for high-quality, site/product-level metric extraction.

### CONTEXT & GOAL
The extraction system prioritizes **Production** and **Environmental** metrics at site or product level:
- PRODUCTION metrics (ore mined, processed, concentrate, refined, brine, grades, contained metal, etc.)
- ENVIRONMENTAL metrics (water, energy, GHG, air emissions, waste, effluents, tailings, reagents, fuels, utilities)
- FINANCIAL metrics (EBITDA, realized price, unit cost, sold volumes) are strictly secondary and **MUST NOT** be the sole reason for a 'go' or 'maybe' decision.

The final decision must prioritize reports where data is:
1. Relevant to Copper (Cu) or Nickel (Ni) or their by-products.
2. Granular: Separated by site AND by metal/product, ideally presented in tables.
3. Quantitative: Contains production or environmental metrics with units.
Ignore HR/safety/social/governance/standards.

### SITE/ASSET DETECTION — STRICT, OPERATIONAL RULES

A SITE/ASSET must be extracted using the following mandatory rules:

1. A SITE/ASSET is a **proper noun** (capitalized name) referring to a physical industrial location involved in mining or metallurgical processing:
   Accepted categories:
   - Mine / Open Pit / Underground Mine
   - Quarry
   - Concentrator / Mill / Processing Plant
   - Leach Plant / Hydromet Plant / Chemical Plant
   - Smelter
   - Refinery
   - Tailings Storage Facility (TSF) / Tailings Management Facility (TMF)

2. A name qualifies as a SITE ONLY IF:
   - It is a standalone proper noun (e.g., "Cerro Verde", "Onça Puma", "Moa Bay", "Sudbury", "Caserones")
   AND
   - It appears in the same local context (sentence OR table row) as:
        • production metrics (ore mined/processed, concentrate, cathode, matte, grades)
        • environmental metrics (water, energy, GHG, emissions, waste, tailings)
        • metallurgical operations (crushing, milling, flotation, leaching, smelting, refining)

3. **EXCLUSIONS (must NOT be classified as sites):**
   - internal process units: “crusher”, “grinding circuit”, “SX area”, “autoclave 1”
   - departments, projects, business units (e.g., “Mining Division”, “Metals Group”)
   - countries, regions, provinces (e.g., “Chile”, “Ontario”, “Brazil”)
   - ports, logistics hubs, shipping terminals
   - corporate offices, HQ, admin centers

4. **NO DUPLICATION:**
   If the same name appears in multiple roles (e.g., “Caserones Mine” and “Caserones Concentrator”)
   → list the name ONLY ONCE  
   → choose the highest-level category:
       Mine_Quarry > Processing_Plant > Smelter_Refinery

5. **TABLE RULE:**
   In tables, a row header or column header is considered a SITE if:
   - It is a proper noun, AND
   - That row contains at least one numeric value + unit.

6. Output ONLY names of sites (no descriptions, no locations).

### STRICT EXCLUSION RULES (MANDATORY)
The following entities MUST NEVER be classified as industrial sites (Mine_Quarry, Processing_Plant, Smelter_Refinery):

❌ Ports, harbors, marine terminals, shipping terminals  
❌ Logistics hubs, export terminals, transport facilities  
❌ Loading/unloading ports (e.g., “Punta Lobitos Port”, “Puerto Coloso”)  
❌ Corporate offices, HQ, admin centers  
❌ Labs, R&D centers, monitoring stations  
❌ Business units, divisions, regions, countries  
❌ Internal process units (e.g., crushing circuit, flotation line, SX area, autoclave, conveyor)

These MUST ALWAYS be placed under:
"Office_Other"

Additionally:
If a name contains the words:
"port", "terminal", "harbor", "puerto", "punt(a/o)", "muelle", "embarcadero"
→ classify it STRICTLY under "Office_Other".
### KEY LOGIC
- "has_site_level_data" = true only if a **categorized SITE/ASSET** name (excluding Office_Other) appears with a numeric value + UNIT relevant to **production or environment** in the SAME local context (sentence/table row/bullet/panel).
- "has_product_level_data" = true only if a PRODUCT/FORM (copper, nickel, PGMs, etc.) appears with a numeric value + UNIT relevant to **production or environment** in the SAME local context.
- "has_financial_metrics" = true if **product-level financial metrics** (EBITDA, cost, price, sold volume) appear with a numeric value + UNIT ($/t, $M, etc.) in a local context.
- "has_units_present" = true if units appear (t, kt, Mt, m³, L, oz, koz, Moz, GJ, MWh, %, $/t, t CO2e, etc.).
- "total_metric_count_estimate" = Estimate the total number of distinct quantitative metric values (e.g., "15,000 t of Cu" is one value) that appear in tables or clear, structured lists. **Use 0 if none found.**
- "has_tables_with_metrics" = true if structured tables contain production or environmental metrics with units.
- "metrics_separated_by_site" = true if tables or structured data explicitly break down metrics by site/asset name.
- "metrics_separated_by_metal" = true if tables or structured data explicitly break down metrics by specific metal/product name.
- "examples_verbatim" = include 1–3 short EXACT quotes proving the existence of quantitative metrics (must include a unit).
- "table_verbatims" = include 1–3 short EXACT quotes from tables proving the separation by site or metal.
- "table_pages" = Include the page numbers where the main tables or structured lists of production/environmental/financial metrics were found. **Do not infer, list only pages where quotes or counts were derived from.**
- "sites_categorized": Categorize all mentioned sites/assets. **Mine_Quarry** (extraction sites), **Processing_Plant** (concentrators, chemical plants, tailings management facilities), **Smelter_Refinery** (metallurgical processing), **Office_Other** (headquarters, sales offices, non-industrial sites, and logistics/ports). Only list names.
- "site_product_mapping": List the main products associated with each industrial SITE/ASSET.

### OUTPUT SCHEMA
{
  "company_or_group": "string",
  "report_name": "string",
  "year": "int | null",
  "report_type": "**ESG report** | **Annual report (Financial focus)** | **Technical Report (PFS/FS/NI43-101)** | academic/research paper | Corporate report | Country | mixed | unknown",
  
  "sites_categorized": { 
    "Mine_Quarry": ["string", ...],
    "Processing_Plant": ["string", ...],
    "Smelter_Refinery": ["string", ...],
    "Office_Other": ["string", ...] 
  },

  "site_product_mapping": [
    { "site": "string", "products": ["string", ...] },
    ... 
  ],
  
  "products": ["string", ...],
  "metals_or_materials_covered": ["string", ...],

  "data_existence": {
    "has_site_level_data": true|false|null,
    "has_product_level_data": true|false|null,
    "has_financial_metrics": true|false|null,
    "has_units_present": true|false|null,
    "has_time_series": true|false|null,
    "examples_verbatim": ["short exact quotes (with units)"],
    "pages": []
  },

  "data_organization": {
    "primary_axes": "by_site | by_product | by_region | group_total | mixed | unknown",
    "notes": "string"
  },

  "data_structure": {
    "has_tables_with_metrics": true|false|null,
    "metrics_separated_by_site": true|false|null,
    "metrics_separated_by_metal": true|false|null,
    "total_metric_count_estimate": "int | null",
    "table_verbatims": ["short exact quotes from tables or lists"],
    "table_pages": []
  },

  "industrial_process": {
    "flow_summary": "string",
    "key_inputs": ["string", ...],
    "key_outputs": ["string", ...],
    "residues_waste": ["string", ...],
    "process_verbatims": ["exact quotes"],
    "process_pages": []
  },

  "decision_tag": "go | maybe | no",
  "decision_reason": "string"
}

### STRICT RULES
- Use ONLY the provided text; never guess.
- Mark “true” only if the site/product name and numeric value with **unit** appear in the SAME local context.
- **A report with ONLY Financial Metrics and no Production/Environmental Metrics will be classified as 'no'.**
- Ignore HR/governance/safety/community/ethics.
- Do NOT infer page numbers.
- Return ONLY the JSON object, ONE LINE, no code fences, no commentary.
"""

# ===================== UTILS (FONCTIONS D'EXTRACTION MISES À JOUR) =====================

def clean_text(full_text: str) -> str:
    """Applique les nettoyages standards au texte extrait."""
    full_text = re.sub(r"(\w)-\n(\w)", r"\1\2", full_text) # de-hyphen
    full_text = re.sub(r"[ \t]+\n", "\n", full_text)
    full_text = re.sub(r"\n{3,}", "\n\n", full_text)
    return full_text

# MODIFICATION: Suppression de la fonction extract_full_text_simple
# Nous allons forcer l'extraction robuste directement.

def extract_full_text_robust(pdf_path: str, max_chars: int = 140_000) -> str:
    """Méthode d'extraction robuste: Texte + tables structurées mises en évidence."""
    all_content = []
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, p in enumerate(pdf.pages):
                page_content = f"\n\n--- PAGE {i+1} ---\n"
                
                # 1. Extraction des tableaux (priorité aux données structurées)
                tables = p.extract_tables()
                if tables:
                    page_content += "\n[STRUCTURED TABLES FOUND]\n"
                    for table in tables:
                        # Conversion du tableau en format lisible (lignes séparées par tabulations)
                        table_str = "\n".join(["\t".join(cell if cell is not None else "" for cell in row) for row in table])
                        page_content += table_str + "\n---\n"
                
                # 2. Extraction du texte général
                text = p.extract_text(x_tolerance=2) or ""
                
                # Ajouter le texte général APRES les tables
                page_content += text
                
                all_content.append(page_content)

        full_text = "\n".join(all_content)
        return clean_text(full_text)[:max_chars]
        
    except Exception as e:
        print(f"ATTENTION: Échec de l'extraction ROBUSTE de {os.path.basename(pdf_path)}: {e}")
        return "" 


def response_text_safe(resp) -> str:
    txt = getattr(resp, "text", None)
    if isinstance(txt, str) and txt.strip(): return txt.strip()
    try:
        for cand in getattr(resp, "candidates", []) or []:
            content = getattr(cand, "content", None)
            for part in getattr(content, "parts", []) or []:
                t = getattr(part, "text", None)
                if isinstance(t, str) and t.strip(): return t.strip()
    except Exception:
        pass
    return ""

def parse_json_loose(s: str) -> Dict[str, Any]:
    s = (s or "").strip().replace("\ufeff","").replace("\u200b","")
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s); s = re.sub(r"\s*```$", "", s)
    m = re.search(r"\{[\s\S]*\}$", s)
    if m:
        try: return json.loads(m.group(0))
        except Exception: pass
    try: return json.loads(s)
    except Exception: return {}

def is_analysis_empty(data: Dict[str, Any]) -> bool:
    """Vérifie si le résultat de l'analyse Gemini est vide (majorité des champs null)."""
    dx = data.get("data_existence") or {}
    # Considérer comme vide si les 4 booléens principaux de data_existence sont null
    return (dx.get("has_site_level_data") is None) and \
           (dx.get("has_product_level_data") is None) and \
           (dx.get("has_financial_metrics") is None) and \
           (dx.get("has_units_present") is None)


def normalize(d: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise la sortie JSON pour s'assurer que tous les champs existent."""
    schema = {
        "company_or_group": None,
        "report_name": None,
        "year": None,
        "report_type": None,
        
        "sites_categorized": { 
            "Mine_Quarry": [],
            "Processing_Plant": [],
            "Smelter_Refinery": [],
            "Office_Other": []
        },
        
        "products": [],
        "metals_or_materials_covered": [],
        "site_product_mapping": [], 
        "data_existence": {
            "has_site_level_data": None,
            "has_product_level_data": None,
            "has_financial_metrics": None,
            "has_units_present": None,
            "has_time_series": None,
            "examples_verbatim": [],
            "pages": []
        },
        "data_organization": {"primary_axes":"unknown","notes":""},
        "data_structure": {
            "has_tables_with_metrics": None,
            "metrics_separated_by_site": None,
            "metrics_separated_by_metal": None,
            "total_metric_count_estimate": None,
            "table_verbatims": [],
            "table_pages": []
        },
        "industrial_process": {
            "flow_summary": "",
            "key_inputs": [],
            "key_outputs": [],
            "residues_waste": [],
            "process_verbatims": [],
            "process_pages": []
        },
        "decision_tag": "maybe",
        "decision_reason": ""
    }
    out = {**schema, **(d or {})}
    
    # Cleaning des listes de métaux/produits
    out["products"] = [p for p in (out.get("products") or []) if isinstance(p,str) and p.strip()]
    out["metals_or_materials_covered"] = [m for m in (out.get("metals_or_materials_covered") or []) if isinstance(m,str) and m.strip()]
    
    # Cleaning des sites catégorisés
    sc = out.get("sites_categorized") or {}
    for key in sc.keys():
        sc[key] = [s for s in (sc.get(key) or []) if isinstance(s,str) and s.strip()]
    out["sites_categorized"] = sc
    
    # Cleaning du site_product_mapping
    spm = out.get("site_product_mapping") or []
    cleaned_spm = []
    for item in spm:
        if isinstance(item, dict) and 'site' in item and 'products' in item:
            item['products'] = [p for p in (item.get('products') or []) if isinstance(p, str) and p.strip()]
            if item['site'] and item['site'].strip():
                cleaned_spm.append(item)
    out["site_product_mapping"] = cleaned_spm 
    
    def uniq(xs):
        u=[]; seen=set()
        for x in xs or []:
            k=str(x)
            if k not in seen: seen.add(k); u.append(x)
        return u
    
    dx = out.get("data_existence", {}) or {}
    dx["examples_verbatim"] = uniq(dx.get("examples_verbatim"))
    out["data_existence"]=dx
    
    ds = out.get("data_structure", {}) or {}
    ds["table_verbatims"] = uniq(ds.get("table_verbatims"))
    ds["table_pages"] = uniq([str(p) for p in (ds.get("table_pages") or []) if isinstance(p, (int, str)) and str(p).strip()])
    out["data_structure"] = ds

    ip = out.get("industrial_process", {}) or {}
    ip["process_verbatims"] = uniq(ip.get("process_verbatims"))
    out["industrial_process"]=ip
    
    return out

def fmt(v):
    if v is True: return "Oui"
    if v is False: return "Non"
    return "Inconnu"

def human_diag(d: Dict[str, Any]) -> str:
    """Version lisible SANS troncature et SANS '+N'."""
    def join_all(lst):
        lst = [x for x in (lst or []) if isinstance(x,str) and x.strip()]
        return "—" if not lst else ", ".join(lst)

    sc = d.get("sites_categorized") or {}
    
    # Calcul du nombre total de sites industriels (dédupliqué) pour le diagnostic
    industrial_sites_set = set(sc.get("Mine_Quarry", [])) | \
                           set(sc.get("Processing_Plant", [])) | \
                           set(sc.get("Smelter_Refinery", []))
                           
    industrial_sites = sorted([s for s in list(industrial_sites_set) if s and s.strip()])
    total_sites_count = len(industrial_sites)
    
    lines=[]
    lines.append("=== QUICK SCAN (Périmètre + Process industriel) ===")
    lines.append(f"Entreprise : {d.get('company_or_group') or 'Inconnue'}")
    lines.append(f"Nom du rapport : {d.get('report_name') or '—'} ({d.get('year') or 'N/A'})")
    lines.append(f"Type de rapport : {d.get('report_type') or 'unknown'}")
    lines.append("---")
    
    # Affichage des sites catégorisés
    lines.append(f"Sites industriels (Total unique: {total_sites_count}) :") # Modifié
    lines.append(f"    • Mines/Carrières : {join_all(sc.get('Mine_Quarry'))}")
    lines.append(f"    • Usines/Traitement : {join_all(sc.get('Processing_Plant'))}")
    lines.append(f"    • Fonderies/Raffineries : {join_all(sc.get('Smelter_Refinery'))}")
    
    if sc.get("Office_Other"):
        lines.append(f"    • Bureaux/Autres/Ports (Ignorés) : {join_all(sc.get('Office_Other'))}") # Modifié
    
    lines.append(f"Produits/Métaux : {join_all(d.get('metals_or_materials_covered'))} ({len(d.get('metals_or_materials_covered') or [])} trouvés)")
    
    if d.get("site_product_mapping"):
        lines.append("Mapping site → produits :")
        for sp in d["site_product_mapping"]:
            products = [p for p in (sp.get('products') or []) if p and p.strip()]
            lines.append(f"    - {sp.get('site') or '—'}: {', '.join(products) or '—'}")
    
    dx = d.get("data_existence") or {}
    lines.append("")
    lines.append("Données disponibles ?")
    lines.append(f"    • Par site (Prod/Env): {fmt(dx.get('has_site_level_data'))}")
    lines.append(f"    • Par produit (Prod/Env): {fmt(dx.get('has_product_level_data'))}")
    lines.append(f"    • Données Financières (granulaires): {fmt(dx.get('has_financial_metrics'))}")
    lines.append(f"    • Unités présentes: {fmt(dx.get('has_units_present'))}")
    lines.append(f"    • Série temporelle: {fmt(dx.get('has_time_series'))}")
    if dx.get("pages"):
        lines.append(f"    • Pages repérées : {', '.join(map(str, dx['pages']))}")
    if dx.get("examples_verbatim"):
        lines.append("    • Exemples (verbatim) :")
        for q in dx["examples_verbatim"]:
            q=" ".join(str(q).split())
            lines.append(f"    “{q}”")
    
    ds = d.get("data_structure") or {}
    lines.append("")
    lines.append("Structure des Données :")
    lines.append(f"    • Tables avec métriques: {fmt(ds.get('has_tables_with_metrics'))}")
    lines.append(f"    • Séparé par site       : {fmt(ds.get('metrics_separated_by_site'))}")
    lines.append(f"    • Séparé par métal      : {fmt(ds.get('metrics_separated_by_metal'))}")
    lines.append(f"    • Nb métriques (est.): {ds.get('total_metric_count_estimate') or '0'}")
    if ds.get("table_pages"):
        lines.append(f"    • Pages des tables    : {', '.join(map(str, ds['table_pages']))}")
    if ds.get("table_verbatims"):
        lines.append("    • Citations de Tables :")
        for q in ds["table_verbatims"]:
            q=" ".join(str(q).split())
            lines.append(f"    “{q}”")
    
    lines.append("")
    do = d.get("data_organization") or {}
    lines.append(f"Organisation des chiffres : {do.get('primary_axes') or 'unknown'}")
    if do.get("notes"):
        lines.append(f"Notes : {do['notes']}")
        
    ip = d.get("industrial_process") or {}
    lines.append("")
    lines.append("Process industriel :")
    lines.append(f"    • Résumé : {ip.get('flow_summary') or '—'}")
    if ip.get("key_inputs"): lines.append(f"    • Intrants : {', '.join(ip['key_inputs'])}")
    if ip.get("key_outputs"): lines.append(f"    • Outputs  : {', '.join(ip['key_outputs'])}")
    if ip.get("residues_waste"):lines.append(f"    • Résidus  : {', '.join(ip['residues_waste'])}")
    if ip.get("process_pages"):
        lines.append(f"    • Pages (process) : {', '.join(map(str, ip['process_pages']))}")
    if ip.get("process_verbatims"):
        lines.append("    • Citations :")
        for q in ip["process_verbatims"]:
            lines.append(f"    “{' '.join(str(q).split())}”")
            
    lines.append("")
    lines.append(f"Décision : {d.get('decision_tag') or 'maybe'} — {d.get('decision_reason') or ''}")
    return "\n".join(lines)


# ===================== PROCESS UN PDF (Logique de décision CORRIGÉE) =====================
def process_pdf(pdf_path: str, model, cfg) -> Dict[str, Any]:
    base = os.path.splitext(os.path.basename(pdf_path))[0]
    out_dir = os.path.dirname(pdf_path)
    out_json = os.path.join(out_dir, f"{base}__SCAN.json")
    out_txt = os.path.join(out_dir, f"{base}__DIAG.txt")

    print(f"\n=== {base} ===")
    
    # MODIFICATION: Suppression de la logique SIMPLE. Forcer l'extraction robuste.
    txt_robust = extract_full_text_robust(pdf_path)

    
    # --- Première tentative d'analyse Gemini (ROBUSTE) ---
    data = {}
    analysis_successful = False
    
    if txt_robust.strip():
        last_error = "Extraction Robuste Réussie."
        for attempt in range(MAX_RETRIES):
            print(f"    → Essai robuste n° {attempt + 1}...")
            try:
                resp = model.generate_content("--- FULL REPORT TEXT ---\n" + txt_robust, generation_config=cfg)
                raw = response_text_safe(resp)
                data = normalize(parse_json_loose(raw))
                
                if not is_analysis_empty(data):
                    analysis_successful = True
                    print("    ✅ Analyse robuste réussie.")
                    break # Sortir de la boucle de réessai
                
                # Si l'analyse n'est pas vide mais manque d'informations (réessayer)
                print("    ⚠️ Résultat incomplet. Nouvelle tentative...")
                
            except Exception as e:
                last_error = str(e)
                print(f"    ❌ Erreur Gemini (Essai n° {attempt + 1}) : {last_error}")
            
            # Attendre un peu avant de réessayer (simple backoff pour éviter les timeouts API)
            if not analysis_successful and attempt < MAX_RETRIES - 1:
                time.sleep(2) 

        if not analysis_successful:
            # Si tous les essais robustes ont échoué
            data = normalize({"company_or_group": "Analysis Failed", "decision_tag": "no", "decision_reason": f"AI Analysis Failed after {MAX_RETRIES} robust attempts. Last Error: {last_error}"})
    else:
        # Si même l'extraction robuste échoue (PDF illisible/corrompu/RAM)
        data = normalize({"company_or_group": "Extraction Failed", "decision_tag": "no", "decision_reason": "PDF Extraction Failed (corrupted or resource intensive)."})


    # ----------------------------------------------------
    # LOGIQUE DE DÉCISION (Appliquée seulement si l'analyse a réussi)
    # ----------------------------------------------------
    
    # Initialiser les variables pour le cas d'échec
    num_sites = 0
    num_metals = 0
    sites_sample = ""
    metals = []
    has_financial_metrics = False
    has_prod_env_metrics = False
    cu_present = False
    ni_present = False

    if analysis_successful:
        sc = data.get("sites_categorized") or {}
        metals = data.get("metals_or_materials_covered") or []
        dx = data.get("data_existence") or {}
        ds = data.get("data_structure") or {}
        
        # Calcul des variables pour la décision et l'Excel (compte unique)
        industrial_sites_set = set(sc.get("Mine_Quarry", [])) | \
                               set(sc.get("Processing_Plant", [])) | \
                               set(sc.get("Smelter_Refinery", []))
                               
        industrial_sites = sorted([s for s in list(industrial_sites_set) if s and s.strip()])
        
        sites_sample = ", ".join(industrial_sites[:12])
        num_sites = len(industrial_sites)
        num_metals = len(metals)
        
        relevant_metals = []
        for metal in metals:
            # Recherche des mots-clés dans les métaux trouvés par Gemini
            if any(kw in metal.lower() for kw in INTEREST_KEYWORDS):
                relevant_metals.append(metal)
                
        is_relevant_metal_present = bool(relevant_metals)
        
        decision_tag = "no"
        decision_reason = "No relevant industrial metrics (site/product/units) or no Cu/Ni material found."
        
        # Booléens pour la décision
        has_prod_env_metrics = (dx.get("has_site_level_data") is True) or (dx.get("has_product_level_data") is True)
        has_financial_metrics = (dx.get("has_financial_metrics") is True)
        has_units = (dx.get("has_units_present") is True)

        # RÈGLES ÉLIMINATOIRES 
        if not has_units:
            decision_tag = "no"
            decision_reason = "Only narrative/aggregated totals; no quantified industrial metrics with units."
            
        elif not is_relevant_metal_present:
            decision_tag = "no"
            decision_reason = "Quantified metrics found, but none of the metals/products are related to Cu or Ni."

        # CAS OÙ IL Y A DES UNITÉS ET CU/NI PERTINENT
        else:
            
            # Define Key Separation Booleans
            sep_site_in_table = (ds.get("metrics_separated_by_site") is True)
            has_site_specific_data_in_text = (dx.get("has_site_level_data") is True)
            sep_metal_in_table = (ds.get("metrics_separated_by_metal") is True)
            
            # *** FILTRE 1: Exclusion des rapports Purement Financiers (Financial Data ONLY = NO-GO) ***
            if not has_prod_env_metrics:
                decision_tag = "no"
                decision_reason = "Only granular FINANCIAL metrics found (EBITDA, cost, price). PRODUCTION/ENVIRONMENTAL data is missing/aggregated. (NO-GO for ACV)."
                
            # CAS GO/MAYBE/NO pour les données Production/Environnement (Priorité)
            elif has_prod_env_metrics:
                
                # *** FILTRE 2: Correction de l'erreur d'inférence (Séparation impossible sans Site) ***
                if num_sites == 0:
                    # Si on a des métriques Prod/Env (has_prod_env_metrics=True) mais AUCUN site identifié, c'est NO.
                    decision_tag = "no"
                    primary_axes = data.get("data_organization", {}).get("primary_axes", "group_total")
                    data["decision_reason"] = f"Prod/Env metrics found, but NO industrial sites identified. Data is aggregated (Company-Wide / {primary_axes.replace('group_total', 'Group-Total')}) and unusable for site-specific ACV."
                
                # *** FILTRE 3: La Logique GO (Structure) vs. MAYBE (Texte) ***
                
                # 1. GO DIRECT: La séparation structurelle par site est prouvée (Tables)
                # Cette condition est VRAIE si l'IA a trouvé une structure explicite (colonne site dans un tableau).
                elif sep_site_in_table:
                    
                    if num_sites > 1 and num_metals > 1 and not sep_metal_in_table:
                         # Si c'est séparé par Site mais pas par Métal, on dégrade en MAYBE si num_sites > 1
                         decision_tag = "maybe"
                         reason = "GO demoted to MAYBE: Data separated by Site in tables, but not by Metal (partial structural granularity). Needs manual check."
                    else:
                         # Si c'est un GO simple (un seul site) OU si c'est parfaitement séparé (Site ET Métal)
                         decision_tag = "go"
                         reason = "Structural data separation confirmed by Site (in tables). Easy extraction."
                    
                    if has_financial_metrics: reason += " (Financial metrics also present, but secondary)."
                    data["decision_reason"] = reason

                # 2. MAYBE: La séparation structurale échoue (sep_site_in_table=False), mais on a des données site-spécifiques dans le texte
                elif has_site_specific_data_in_text:
                    
                    # Si structural separation failed, but we still have site-level data, it's text-based = MAYBE
                    decision_tag = "maybe"
                    reason = "Specific site-level Prod/Env metrics found (in text/sentences) but are NOT structured in tables. Needs manual data extraction."
                    if has_financial_metrics: reason += " (Financial metrics also present, but secondary)."
                    data["decision_reason"] = reason
                
                # 3. NO: Lacks all required granularity
                else:
                    decision_tag = "no"
                    data["decision_reason"] = "Relevant material found, but data is aggregated (Company-Wide/Group-Total) without any separation by Site or Metal in tables, AND lacks explicit site-level metrics in text."

            
            # Finalisation des données
            data["decision_tag"] = decision_tag
            
        # Colonnes pour l'Excel
        cu_present = any(kw in m.lower() for kw in METALS_OF_INTEREST["Cu"] for m in metals)
        ni_present = any(kw in m.lower() for kw in METALS_OF_INTEREST["Ni"] for m in metals)
    
    
    # Sauvegardes par PDF
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

    report = human_diag(data)
    with open(out_txt, "w", encoding="utf-8") as f:
        # diagnostic lisible complet
        f.write(report + "\n\n")
        # JSON complet (non tronqué)
        f.write("--- RAW JSON (complete) ---\n")
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"    ✅ {out_txt}")

    # Ligne pour l’Excel PATCH
    row = {
        "pdf": os.path.basename(pdf_path),
        "company": data.get("company_or_group"),
        "report_name": data.get("report_name"), 
        "year": data.get("year"),             
        "report_type": data.get("report_type"), 
        "sites_count": num_sites,
        "products_count": len(metals),
        "Cu_present": cu_present,      
        "Ni_present": ni_present,      
        "has_financial_data": has_financial_metrics if analysis_successful else False,
        "has_prod_env_data": has_prod_env_metrics if analysis_successful else False,
        "metrics_count_est": data.get("data_structure", {}).get("total_metric_count_estimate"),
        "sep_by_site": fmt(data.get("data_structure", {}).get("metrics_separated_by_site")),
        "sep_by_metal": fmt(data.get("data_structure", {}).get("metrics_separated_by_metal")),
        "decision": data.get("decision_tag"),
        "reason": data.get("decision_reason"),
        "sites_sample": sites_sample,
        "products_sample": ", ".join(metals[:12]), 
        "model_ok": analysis_successful
    }
    return row

# ===================== MAIN (mode PATCH: ne traite que les __DIAG petits) =====================
def main():
    os.makedirs(IN_DIR, exist_ok=True)
    # NOUVELLES COLONNES POUR LE DATAFRAME FINAL
    EXCEL_COLUMNS = [
        "pdf","company","report_name","year","report_type",
        "sites_count","products_count",
        "Cu_present","Ni_present",
        "has_financial_data","has_prod_env_data",
        "metrics_count_est", 
        "sep_by_site","sep_by_metal", 
        "decision","reason","sites_sample","products_sample","model_ok"
    ]
    
    if not os.path.isdir(IN_DIR):
        print(f"❌ Dossier introuvable : {IN_DIR}")
        sys.exit(1)

    # liste des PDF (non récursif)
    pdfs = [os.path.join(IN_DIR, f) for f in os.listdir(IN_DIR) if f.lower().endswith(".pdf")]
    pdfs.sort()
    if not pdfs:
        print("⚠️ Aucun PDF trouvé."); sys.exit(0)

    print(f"🗂️ {len(pdfs)} PDF trouvés dans : {IN_DIR}")

    # init modèle une seule fois
    aiplatform.init(project=PROJECT_ID, location=LOCATION)
    model = GenerativeModel(MODEL_ID, system_instruction=PROMPT)
    cfg = GenerationConfig(response_mime_type="application/json", temperature=0.0, max_output_tokens=8192)

    summary_rows = []
    for pdf in pdfs:
        base = os.path.splitext(os.path.basename(pdf))[0]
        diag_path = os.path.join(IN_DIR, f"{base}__DIAG.txt")

        # LOGIQUE DE REPASSE (Retraitement si DIAG existe mais est "vide" ou trop petit)
        if os.path.exists(diag_path):
            try:
                size = os.path.getsize(diag_path)
            except Exception:
                size = 0
            if size > SIZE_THRESHOLD:
                print(f"⏭️     Skip {base} (diag existant {size} o > {SIZE_THRESHOLD} o)")
                continue

        # Sinon, (re)traite ce PDF
        try:
            row = process_pdf(pdf, model, cfg)
            if row: summary_rows.append(row)
        except Exception as e:
            print(f"    ❌ Erreur sur {os.path.basename(pdf)} : {e}")

    # ====== Export Excel PATCH à la racine du dossier (Fusion) ======
    if summary_rows:
        
        # 1. Créer le DataFrame à partir des NOUVELLES lignes traitées
        df_new = pd.DataFrame(summary_rows, columns=EXCEL_COLUMNS)
        
        out_xlsx = os.path.join(IN_DIR, "__SUMMARY_PATCH.xlsx")
        
        # 2. Vérifier si le fichier EXISTE et charger les anciennes données (Fusion)
        df_final = df_new
        if os.path.exists(out_xlsx):
            print(f"    → Fichier existant trouvé. Fusion des {len(df_new)} nouvelles lignes...")
            try:
                df_old = pd.read_excel(out_xlsx, engine="openpyxl")
                
                # S'assurer que les colonnes sont cohérentes
                df_old = df_old.reindex(columns=EXCEL_COLUMNS)
                
                # Filtrer les anciennes lignes pour ne pas dupliquer ou mélanger le PATCH
                pdfs_to_exclude = df_new['pdf'].tolist()
                df_old_filtered = df_old[~df_old['pdf'].isin(pdfs_to_exclude)]
                
                # Concaténer l'ancien contenu non-retraité et le nouveau contenu
                df_final = pd.concat([df_old_filtered, df_new], ignore_index=True)
                
            except Exception as e:
                print(f"❌ Erreur lors de la lecture/fusion du fichier Excel existant: {e}. Écriture des nouvelles lignes SEULEMENT.")
                # df_final reste df_new dans ce cas
        
        # 3. Écrire le DataFrame final (qui contient l'ancien + le nouveau)
        df_final.to_excel(out_xlsx, index=False, engine="openpyxl")
        print(f"\n📊 Patch résumé écrit : {out_xlsx} (Total: {len(df_final)} lignes)")
    else:
        print("\n👌 Rien à retraiter (aucun diag ≤ seuil).")

    print("\n🎉 Terminé.")

if __name__ == "__main__":
    main()
