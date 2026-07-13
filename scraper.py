#!/usr/bin/env python3
"""
Spain Solar Leads Database Scraper (Resilient Enterprise Harvester v6)
===================================================================
Features:
- Dual-Engine Harvester: Combines UNEF Associate Directory and DuckDuckGo query loops.
- Apparent Encoding Override: Uses r.apparent_encoding to eliminate double-encoding errors.
- Thread-Safe Real-time Saving: Saves verified leads instantly to CSV.
- Refined Address & Name Cleaners: Filters out JS/CSS/HTML noise.
- Incremental Deduplication: Skips previously harvested websites.
"""
import os
import csv
import re
import time
import urllib3
import logging
import requests
import html
import threading
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Setup Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("leads_harvester")

OUTPUT_CSV = "instaladores_solares_espana.csv"
MAX_WORKERS = 15
FILE_LOCK = threading.Lock()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# Regex definitions
EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PHONE_REGEX = re.compile(r"\b(?:9|6|7)\d{2}[-.\s]?\d{3}[-.\s]?\d{3}\b|\b(?:9|6|7)\d{2}[-.\s]?\d{2}[-.\s]?\d{2}[-.\s]?\d{2}\b")
CIF_REGEX = re.compile(r"\b[A-HJNP-SUVW][- ]?\d{7}[A-J\d]\b", re.IGNORECASE)
POSTAL_CODE_REGEX = re.compile(r"\b(?:0[1-9]|[1-4][0-9]|5[0-2])\d{3}\b")

# Blocked domains (aggregators and spam)
BLOCKED_DOMAINS = [
    "google.com", "duckduckgo.com", "facebook.com", "instagram.com", "linkedin.com",
    "twitter.com", "youtube.com", "selectra.es", "rankia.com", "renovables.blog",
    "eleconomista.es", "empresite", "paginasamarillas.es", "idealista.com", "wikipedia.org",
    "x.com", "pinterest.com", "milanuncios.com", "habitissimo.es", "twenergy.com",
    "solarweb.net", "foro-electricidad.com", "top-conductores.es", "solicitar-presupuesto",
    "comparador", "comparasolar", "guiadeprensa", "soloempresas", "ahorrasolar", "certificados"
]

DUMMY_EMAILS = [
    "tuemail@dominio.com", "info@tudominio.es", "tu@email.com", "email@domain.com",
    "correo@correo.com", "user@example.com", "info@ejemplo.com", "admin@domain.com",
    "test@test.com", "nombre@dominio.com", "ejemplo@ejemplo.com", "mail@example.com",
    "tuemail@empresa.com", "seo.jesusarteaga@gmail.com"
]

PROVINCES = [
    "albacete", "alicante", "almeria", "asturias", "avila", "badajoz", "barcelona",
    "burgos", "caceres", "cadiz", "cantabria", "castellon", "ciudad real", "cordoba",
    "a coruña", "cuenca", "girona", "granada", "guadalajara", "guipuzcoa", "huelva",
    "huesca", "baleares", "jaen", "leon", "lleida", "lugo", "madrid", "malaga",
    "murcia", "navarra", "ourense", "palencia", "las palmas", "pontevedra", "la rioja",
    "salamanca", "segovia", "sevilla", "soria", "tarragona", "tenerife", "teruel",
    "toledo", "valencia", "valladolid", "vizcaya", "zamora", "zaragoza"
]

CITIES = [
    "madrid", "barcelona", "valencia", "sevilla", "zaragoza", "malaga", "murcia", "palma de mallorca",
    "las palmas de gran canaria", "bilbao", "alicante", "cordoba", "valladolid", "vigo", "gijon", "l hospitalet de llobregat",
    "vitoria", "la coruña", "elche", "granada", "badalona", "oviedo", "cartagena", "sabadell",
    "jerez de la frontera", "mostoles", "pamplona", "almeria", "alcala de henares", "fuenlabrada", "leganes",
    "san sebastian", "getafe", "burgos", "albacete", "castellon de la plana", "santander", "alcorcon",
    "logroño", "badajoz", "marbella", "salamanca", "huelva", "lleida", "tarragona", "dos hermanas",
    "parla", "torrejon de ardoz", "leon"
]

LOCATIONS = sorted(list(set(PROVINCES + CITIES)))

def clean_company_name(name):
    """Clean company name of HTML characters, emojis, years, SEO suffixes and numbers."""
    if not name:
        return ""
    name = html.unescape(name)
    name = re.split(r"\||-|—|::", name)[0].strip()
    name = re.sub(r"<[^>]+>", "", name)
    name = name.strip("※ *•_#-()[]{}▷▶★✔")
    name = re.sub(r"\b202\d\b", "", name).strip()
    name = re.sub(r"^\d+\s*", "", name).strip()
    
    for phrase in ["Directorio de", "Los mejores", "Instaladores de", "Empresas de"]:
        if name.lower().startswith(phrase.lower()):
            name = name[len(phrase):].strip()
            
    # Resolve typical UTF-8 double-encoding glitches
    name = name.replace("Ã³", "ó").replace("ã³", "ó").replace("Â·", "·").replace("ã³", "ó").replace("Ã¡", "á").replace("Ã©", "é").replace("Ã­", "í").replace("Ãº", "ú").replace("Ã±", "ñ").replace("Ã‘", "Ñ").replace("Ã", "á")
    name = " ".join([w.capitalize() for w in name.split()])
    return name

def clean_phone(phone):
    """Normalize phone numbers to international standard +34 6XX XX XX XX."""
    if not phone:
        return ""
    digits = "".join(re.findall(r"\d", phone))
    
    if digits in ["999999999", "123456789", "000000000"]:
        return ""
        
    if digits.startswith("34") and len(digits) > 9:
        digits = digits[2:]
        
    if len(digits) == 9:
        return f"+34 {digits[0:3]} {digits[3:5]} {digits[5:7]} {digits[7:9]}"
    elif len(digits) > 9:
        return f"+34 {digits[-9:-6]} {digits[-6:-4]} {digits[-4:-2]} {digits[-2:]}"
    return phone.strip()

def clean_address(address):
    """Strictly validates address and discards HTML/CSS/JavaScript code leakages."""
    if not address:
        return ""
        
    address = html.unescape(address)
    code_indicators = [
        "{", "}", "[", "]", "class=", "id=", "href=", "src=", "menu-item", 
        "span", "div", "script", "function", "var ", "const ", "let ", "//#", 
        "/*", "*/", "import ", "document.", "window.", "elementor", "wpa_field",
        "margin:", "padding:", "display:", "color:", "z-index", "href"
    ]
    address_lower = address.lower()
    if any(ind in address_lower for ind in code_indicators):
        return ""
        
    address = re.sub(r"<[^>]+>", "", address)
    address = " ".join(address.split())
    address = address.strip(" ,.-:;()[]")
    
    # Clean double-encoding
    address = address.replace("Ã³", "ó").replace("ã³", "ó").replace("Â·", "·").replace("Ã¡", "á").replace("Ã©", "é").replace("Ã­", "í").replace("Ãº", "ú").replace("Ã±", "ñ").replace("Ã‘", "Ñ").replace("Ã", "á")
    address = " ".join([w.capitalize() for w in address.split()])
    return address

def clean_cif(cif):
    """Standardizes Spanish CIF format to uppercase."""
    if not cif:
        return ""
    cif = cif.upper().replace(" ", "").replace("-", "").strip()
    if len(cif) == 9 and cif[0].isalpha():
        return cif
    return ""

def is_valid_email(email):
    """Validates email is not a placeholder template."""
    if not email:
        return False
    email = email.lower().strip()
    if email in DUMMY_EMAILS:
        return False
    if any(email.startswith(dummy.split("@")[0]) for dummy in DUMMY_EMAILS if "@" in dummy):
        if "dominio" in email or "example" in email:
            return False
    if any(email.endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".js", ".css"]):
        return False
    return "@" in email

def search_ddg_lite(query):
    """Query DuckDuckGo Lite HTML search and return unique full URLs."""
    url = "https://lite.duckduckgo.com/lite/"
    data = {"q": query}
    links = set()
    
    retries = 3
    delay = 6
    
    for attempt in range(retries):
        try:
            r = requests.post(url, data=data, headers=HEADERS, timeout=12)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                result_elements = soup.find_all("a", class_="result-link")
                if not result_elements:
                    time.sleep(delay)
                    delay *= 2
                    continue
                    
                for a in result_elements:
                    href = a["href"]
                    parsed = urlparse(href)
                    domain = parsed.netloc.lower()
                    if domain.startswith("www."):
                        domain = domain[4:]
                        
                    if domain and not any(b in domain for b in BLOCKED_DOMAINS):
                        links.add(f"{parsed.scheme}://{parsed.netloc}")
                if links:
                    break
            else:
                time.sleep(delay)
                delay *= 2
        except Exception:
            time.sleep(delay)
            delay *= 2
            
    return links

def harvest_unef_profiles():
    """Loops through all pages of the UNEF associate directory and gathers all profile links."""
    logger.info("Harvesting associate profiles from UNEF directory...")
    profile_urls = set()
    
    # 1. Fetch Page 1 links
    try:
        r = requests.get("https://www.unef.es/es/asociados", headers=HEADERS, verify=False, timeout=10)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.find_all("a", href=True):
                if "/es/asociado/" in a["href"]:
                    profile_urls.add(a["href"])
    except Exception as e:
        logger.error(f"UNEF Page 1 error: {e}")
        
    logger.info(f"Page 1 fetched: {len(profile_urls)} profiles.")
    
    # 2. Fetch remaining pages dynamically via AJAX pagination
    url = "https://www.unef.es/es/asociadosFront/ajaxCargarMasAsociados"
    unef_headers = HEADERS.copy()
    unef_headers["X-Requested-With"] = "XMLHttpRequest"
    
    page = 2
    while True:
        data = {
            "pagina": page,
            "busqueda": "",
            "idComunidadActividad": "",
            "idTipoActividad": "",
            "idSeccion": ""
        }
        try:
            r = requests.post(url, headers=unef_headers, data=data, verify=False, timeout=12)
            if r.status_code == 200:
                res = r.json()
                html_content = res.get("data", {}).get("html", "")
                soup = BeautifulSoup(html_content, "html.parser")
                cards = soup.find_all("a", href=True)
                page_links = 0
                for a in cards:
                    if "/es/asociado/" in a["href"]:
                        profile_urls.add(a["href"])
                        page_links += 1
                        
                logger.info(f"UNEF Page {page} read: added {page_links} profiles. Cumulative unique: {len(profile_urls)}")
                
                if res.get("data", {}).get("hayMas", 0) <= 0 or page_links == 0:
                    break
                    
                page += 1
                time.sleep(1.0) # Safe delay
            else:
                logger.warning(f"UNEF AJAX HTTP error {r.status_code} at page {page}.")
                break
        except Exception as e:
            logger.error(f"UNEF AJAX error on page {page}: {e}. Retrying with extra sleep...")
            time.sleep(4.0)
            continue
            
    return list(profile_urls)

def extract_corporate_website_from_unef(profile_url):
    """Parses a UNEF associate profile page and extracts its official corporate website and region."""
    company_info = {"website": "", "province": ""}
    try:
        r = requests.get(profile_url, headers=HEADERS, verify=False, timeout=8)
        if r.status_code == 200:
            r.encoding = r.apparent_encoding or "utf-8"
            soup = BeautifulSoup(r.text, "html.parser")
            
            # Extract province
            text_blocks = soup.get_text()
            province_match = re.search(r"Provincia:\s*([^\n,.;]+)", text_blocks, re.IGNORECASE)
            if province_match:
                company_info["province"] = clean_company_name(province_match.group(1)).capitalize()
            
            # Extract corporate website
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                href_lower = href.lower()
                if (href_lower.startswith("http") and 
                    "unef.es" not in href_lower and 
                    "linkedin.com" not in href_lower and 
                    "facebook.com" not in href_lower and 
                    "twitter.com" not in href_lower and 
                    "youtube.com" not in href_lower and 
                    "eepurl.com" not in href_lower and 
                    "globalsolarcouncil.org" not in href_lower and 
                    "solarpowereurope.org" not in href_lower and 
                    "alianzaautoconsumo.org" not in href_lower and 
                    "observatorirenovables.cat" not in href_lower):
                    company_info["website"] = href
                    break
    except Exception:
        pass
    return company_info

def extract_razon_social(text):
    """Tries to extract Spanish corporate names (Razón Social) containing S.L., S.A., etc."""
    matches = re.findall(r"\b([A-Z0-9\s,.-]{4,45}\s(?:S\.?L\.?|S\.?A\.?|S\.?L\.?U\.?|S\.?A\.?U\.?))\b", text)
    if matches:
        cleaned = []
        for m in matches:
            c = m.strip().replace("\n", " ")
            c = re.sub(r"\s+", " ", c)
            if len(c) > 6 and not any(k in c.lower() for k in ["de s.l", "en s.l", "para s.l"]):
                cleaned.append(c)
        if cleaned:
            val = " ".join([w.capitalize() if not w.isupper() else w for w in cleaned[0].split()])
            return val.replace("Ã³", "ó").replace("ã³", "ó").replace("Â·", "·").replace("Ã¡", "á").replace("Ã©", "é").replace("Ã­", "í").replace("Ãº", "ú").replace("Ã±", "ñ").replace("Ã‘", "Ñ").replace("Ã", "á")
            
    label_match = re.search(r"(?:razón|denominación)\s+social:?\s*([^\n.,;]{3,45})", text, re.IGNORECASE)
    if label_match:
        val = label_match.group(1).strip()
        return val.replace("Ã³", "ó").replace("ã³", "ó").replace("Â·", "·").replace("Ã¡", "á").replace("Ã©", "é").replace("Ã­", "í").replace("Ãº", "ú").replace("Ã±", "ñ").replace("Ã‘", "Ñ").replace("Ã", "á")
    return ""

def extract_social_links(soup, base_url):
    """Finds links to LinkedIn and Facebook."""
    socials = {"linkedin": "", "facebook": ""}
    for a in soup.find_all("a", href=True):
        href = a["href"].lower()
        if "linkedin.com/company/" in href or "linkedin.com/in/" in href:
            socials["linkedin"] = a["href"]
        elif "facebook.com/" in href and not any(k in href for k in ["sharer", "share", "plugins"]):
            socials["facebook"] = a["href"]
    return socials

def crawl_company_site(base_url, province_name=""):
    """Crawls website and returns complete cleaned B2B lead info."""
    lead = {
        "name": "",
        "razon_social": "",
        "cif": "",
        "email": "",
        "phone": "",
        "website": base_url,
        "address": "",
        "province": province_name.capitalize(),
        "linkedin": "",
        "facebook": ""
    }
    
    try:
        r = requests.get(base_url, headers=HEADERS, verify=False, timeout=8)
        if r.status_code != 200:
            return None
            
        r.encoding = r.apparent_encoding or "utf-8"
        soup = BeautifulSoup(r.text, "html.parser")
        
        # Company Name
        title_tag = soup.find("title")
        if title_tag:
            lead["name"] = clean_company_name(title_tag.text)
            
        html_text = r.text
        
        # Social links
        socials = extract_social_links(soup, base_url)
        lead.update(socials)
        
        # Emails & phones
        emails = EMAIL_REGEX.findall(html_text)
        phones = PHONE_REGEX.findall(html_text)
        
        valid_emails = [e for e in set(emails) if is_valid_email(e)]
        if valid_emails:
            lead["email"] = valid_emails[0].lower().strip()
            
        if phones:
            lead["phone"] = clean_phone(phones[0])
            
        # Deep scan legal pages
        subpages = []
        for a in soup.find_all("a", href=True):
            href = a["href"].lower()
            text = a.text.lower()
            if any(k in href or k in text for k in ["contacto", "legal", "privacidad", "sobre", "contact", "condiciones"]):
                sub_url = urljoin(base_url, a["href"])
                subpages.append(sub_url)
                
        subpages = list(set(subpages))[:3]
        
        for sub_url in subpages:
            try:
                sub_r = requests.get(sub_url, headers=HEADERS, verify=False, timeout=5)
                if sub_r.status_code == 200:
                    sub_r.encoding = sub_r.apparent_encoding or "utf-8"
                    sub_text = sub_r.text
                    
                    if not lead["email"]:
                        sub_emails = EMAIL_REGEX.findall(sub_text)
                        valid_sub_emails = [e for e in set(sub_emails) if is_valid_email(e)]
                        if valid_sub_emails:
                            lead["email"] = valid_sub_emails[0].lower().strip()
                    if not lead["phone"]:
                        sub_phones = PHONE_REGEX.findall(sub_text)
                        if sub_phones:
                            lead["phone"] = clean_phone(sub_phones[0])
                            
                    if not lead["cif"]:
                        cif_match = CIF_REGEX.search(sub_text)
                        if cif_match:
                            lead["cif"] = clean_cif(cif_match.group(0))
                            
                    if not lead["razon_social"]:
                        rs = extract_razon_social(sub_text)
                        if rs:
                            lead["razon_social"] = rs
                            
                    if not lead["address"]:
                        zip_match = POSTAL_CODE_REGEX.search(sub_text)
                        if zip_match:
                            zip_idx = sub_text.find(zip_match.group(0))
                            start = max(0, zip_idx - 65)
                            end = min(len(sub_text), zip_idx + 65)
                            snippet = sub_text[start:end].replace("\n", " ").strip()
                            lead["address"] = clean_address(snippet)
            except Exception:
                pass
                
    except Exception:
        return None
        
    if not lead["name"]:
        parsed = urlparse(base_url)
        domain = parsed.netloc.lower().replace("www.", "").split(".")[0]
        lead["name"] = domain.capitalize()
        
    return lead

def load_existing_leads():
    """Loads existing leads from CSV to skip redundant crawls."""
    seen_websites = set()
    seen_contacts = set()
    
    if os.path.exists(OUTPUT_CSV):
        try:
            with open(OUTPUT_CSV, mode="r", encoding="utf-8") as f:
                reader = csv.reader(f)
                header = next(reader, None)
                if header:
                    for row in reader:
                        if len(row) >= 6:
                            email = row[3].lower().strip()
                            phone = row[4].strip()
                            web = row[5].lower().strip()
                            
                            seen_websites.add(web)
                            if email:
                                seen_contacts.add(email)
                            if phone:
                                seen_contacts.add(phone)
            logger.info(f"Loaded {len(seen_websites)} existing lead websites from {OUTPUT_CSV}")
        except Exception as e:
            logger.warning(f"Could not parse existing CSV: {e}")
            
    return seen_websites, seen_contacts

def append_lead_to_csv(lead):
    """Appends a single lead row to the CSV file in a thread-safe manner."""
    with FILE_LOCK:
        file_exists = os.path.exists(OUTPUT_CSV)
        with open(OUTPUT_CSV, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow([
                    "Empresa", "Razón Social", "CIF", "Email", "Teléfono", 
                    "Sitio Web", "Dirección", "Provincia", "LinkedIn", "Facebook"
                ])
            writer.writerow([
                lead["name"], lead["razon_social"], lead["cif"], lead["email"], lead["phone"],
                lead["website"], lead["address"], lead["province"], lead["linkedin"], lead["facebook"]
            ])

def build_database(max_queries=15):
    """Dual-Engine B2B leads harvester."""
    logger.info("Initializing Resilient B2B Leads Harvester v6...")
    
    seen_websites, seen_contacts = load_existing_leads()
    all_domains = {}
    
    # --- ENGINE 1: UNEF Associate Directory Harvester (High-Quality Targets) ---
    try:
        profile_urls = harvest_unef_profiles()
        logger.info(f"UNEF directory yielded {len(profile_urls)} associate profile links. Starting parallel profile extraction...")
        
        extracted_count = 0
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_prof = {
                executor.submit(extract_corporate_website_from_unef, url): url 
                for url in profile_urls
            }
            for future in as_completed(future_to_prof):
                prof_url = future_to_prof[future]
                try:
                    info = future.result()
                    web = info.get("website")
                    prov = info.get("province") or "Spain"
                    if web:
                        parsed = urlparse(web)
                        domain = parsed.netloc.lower()
                        if domain.startswith("www."):
                            domain = domain[4:]
                        
                        clean_url = f"{parsed.scheme}://{parsed.netloc}"
                        if clean_url.lower().strip() not in seen_websites and domain not in all_domains:
                            all_domains[domain] = (clean_url, prov)
                            extracted_count += 1
                except Exception as e:
                    logger.debug(f"Failed extracting website from profile {prof_url}: {e}")
                    
        logger.info(f"UNEF harvesting complete! Collected {extracted_count} new installer corporate sites.")
    except Exception as err:
        logger.error(f"UNEF Engine error: {err} (falling back entirely to DuckDuckGo)")
        
    # --- ENGINE 2: DuckDuckGo Search Engine Fallback & Expansion ---
    if len(all_domains) < 100:
        logger.info("Expanding lead scope with DuckDuckGo search engine...")
        # Query first max_queries locations
        queries_to_run = LOCATIONS[:max_queries]
        for idx, loc in enumerate(queries_to_run):
            for query_type in ["instaladores placas solares", "empresas energia solar"]:
                q = f"{query_type} {loc}"
                logger.info(f"[{idx+1}/{len(queries_to_run)}] Querying DuckDuckGo: {q!r}")
                found_urls = search_ddg_lite(q)
                for url in found_urls:
                    parsed = urlparse(url)
                    domain = parsed.netloc.lower()
                    if domain.startswith("www."):
                        domain = domain[4:]
                    
                    clean_url = f"{parsed.scheme}://{parsed.netloc}"
                    if clean_url.lower().strip() not in seen_websites and domain not in all_domains:
                        all_domains[domain] = (clean_url, loc)
                time.sleep(6.0)
                
    logger.info(f"Total NEW unique installer domains collected for deep crawl: {len(all_domains)}")
    if not all_domains:
        logger.info("No new domains to crawl. Database is up to date!")
        return
        
    # --- ENGINE 3: Deep Crawler (Concurrent Website Scraping) ---
    logger.info(f"Launching deep concurrent crawler with {MAX_WORKERS} workers...")
    new_leads_count = 0
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_url = {
            executor.submit(crawl_company_site, url, prov): url
            for domain, (url, prov) in all_domains.items()
        }
        
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                lead = future.result()
                if lead and (is_valid_email(lead["email"]) or lead["phone"]):
                    lead["name"] = clean_company_name(lead["name"])
                    
                    if len(lead["name"]) > 2:
                        contact_key = lead["email"] if lead["email"] else lead["phone"]
                        
                        if contact_key not in seen_contacts:
                            seen_contacts.add(contact_key)
                            
                            # Append to CSV in real-time
                            append_lead_to_csv(lead)
                            new_leads_count += 1
                            logger.info(f"✅ Clean Lead saved ({new_leads_count} new): {lead['name']} | CIF: {lead['cif']} | Email: {lead['email']} | Tel: {lead['phone']}")
            except Exception as e:
                logger.error(f"Error crawling website {url}: {e}")
                
    logger.info(f"🥇 PREMIUM HARVEST COMPLETE! Added {new_leads_count} clean leads directly to {OUTPUT_CSV}")

if __name__ == "__main__":
    build_database(max_queries=15)
