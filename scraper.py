#!/usr/bin/env python3
"""
Spain Solar Leads Database Scraper (Enterprise-Grade Engine)
============================================================
Queries DuckDuckGo Lite programmatically for all 50 Spanish provinces.
Crawls installer domains concurrently, parsing Home, Contact, Legal, and Privacy pages.
Extracts: Name, Razón Social, CIF, Email, Phone, Website, Address, and Social Media links.
"""
import os
import csv
import re
import time
import urllib3
import logging
import requests
import html
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Setup Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("enterprise_leads_engine")

OUTPUT_CSV = "instaladores_solares_espana.csv"
MAX_WORKERS = 10  # Speed up crawling with 10 threads concurrently

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# Regex definitions
EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PHONE_REGEX = re.compile(r"\b(?:9|6|7)\d{2}[-.\s]?\d{3}[-.\s]?\d{3}\b|\b(?:9|6|7)\d{2}[-.\s]?\d{2}[-.\s]?\d{2}[-.\s]?\d{2}\b")
CIF_REGEX = re.compile(r"\b[A-HJNP-SUVW][- ]?\d{7}[A-J\d]\b", re.IGNORECASE)
POSTAL_CODE_REGEX = re.compile(r"\b(?:0[1-9]|[1-4][0-9]|5[0-2])\d{3}\b")  # Spanish ZIP codes (01000 - 52999)

# Exclude popular aggregators, directory scrapers, and large media domains
BLOCKED_DOMAINS = [
    "google.com", "duckduckgo.com", "facebook.com", "instagram.com", "linkedin.com",
    "twitter.com", "youtube.com", "selectra.es", "rankia.com", "renovables.blog",
    "eleconomista.es", "empresite", "paginasamarillas.es", "idealista.com", "wikipedia.org",
    "x.com", "pinterest.com", "milanuncios.com", "habitissimo.es", "twenergy.com",
    "solarweb.net", "foro-electricidad.com", "top-conductores.es"
]

# 50 Spanish Provinces
PROVINCES = [
    "albacete", "alicante", "almeria", "asturias", "avila", "badajoz", "barcelona",
    "burgos", "caceres", "cadiz", "cantabria", "castellon", "ciudad real", "cordoba",
    "a coruña", "cuenca", "girona", "granada", "guadalajara", "guipuzcoa", "huelva",
    "huesca", "baleares", "jaen", "leon", "lleida", "lugo", "madrid", "malaga",
    "murcia", "navarra", "ourense", "palencia", "las palmas", "pontevedra", "la rioja",
    "salamanca", "segovia", "sevilla", "soria", "tarragona", "tenerife", "teruel",
    "toledo", "valencia", "valladolid", "vizcaya", "zamora", "zaragoza"
]

def search_ddg_lite(query):
    """Query DuckDuckGo Lite HTML search and return unique full URLs with retry logic."""
    url = "https://lite.duckduckgo.com/lite/"
    data = {"q": query}
    links = set()
    
    # Retry configuration for anti-bot resilience
    retries = 3
    delay = 8
    
    for attempt in range(retries):
        try:
            logger.info(f"Sending search request (attempt {attempt + 1}/{retries})...")
            r = requests.post(url, data=data, headers=HEADERS, timeout=12)
            
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                
                # Verify if actual search results are returned
                result_elements = soup.find_all("a", class_="result-link")
                if not result_elements:
                    logger.warning(f"No result-link elements found (possible challenge page). Retrying in {delay}s...")
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
                
                # If we successfully parsed results, break the retry loop
                if links:
                    break
            else:
                logger.warning(f"Search endpoint returned HTTP {r.status_code}. Retrying in {delay}s...")
                time.sleep(delay)
                delay *= 2
        except Exception as e:
            logger.warning(f"Error during search request: {e}. Retrying in {delay}s...")
            time.sleep(delay)
            delay *= 2
            
    return links


def extract_razon_social(text):
    """Tries to extract Spanish corporate names (Razón Social) containing S.L., S.A., etc."""
    # Find lines or sentences matching standard Spanish corporate suffix structures
    matches = re.findall(r"\b([A-Z0-9\s,.-]+?\s(?:S\.?L\.?|S\.?A\.?|S\.?L\.?U\.?|S\.?A\.?U\.?))\b", text)
    if matches:
        # Return first matches cleaned of extra whitespace
        cleaned = [m.strip().replace("\n", " ") for m in matches if len(m.strip()) > 3]
        if cleaned:
            return cleaned[0]
            
    # Fallback to look for labels
    label_match = re.search(r"(?:razón|denominación)\s+social:?\s*([^\n.,;]+)", text, re.IGNORECASE)
    if label_match:
        return label_match.group(1).strip()
        
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
    """Crawls website and returns complete structured B2B lead info."""
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
            
        soup = BeautifulSoup(r.text, "html.parser")
        
        # 1. Company Name from Title
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.text.strip()
            for sep in ["|", "-", "—"]:
                if sep in title:
                    title = title.split(sep)[0].strip()
            lead["name"] = title
            
        # Extract metadata from homepage
        html_text = r.text
        
        # Parse basic social links from homepage
        socials = extract_social_links(soup, base_url)
        lead.update(socials)
        
        # Extract emails & phones
        emails = EMAIL_REGEX.findall(html_text)
        phones = PHONE_REGEX.findall(html_text)
        
        if emails:
            lead["email"] = [e for e in set(emails) if not e.endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.js', '.css'))][0]
        if phones:
            lead["phone"] = phones[0]
            
        # 2. Scan internal legal and contact links for deep harvesting (CIF, Razón Social)
        subpages = []
        for a in soup.find_all("a", href=True):
            href = a["href"].lower()
            text = a.text.lower()
            if any(k in href or k in text for k in ["contacto", "legal", "privacidad", "sobre", "contact", "condiciones"]):
                sub_url = urljoin(base_url, a["href"])
                subpages.append(sub_url)
                
        subpages = list(set(subpages))[:3]  # Scan up to 3 legal/contact subpages
        
        for sub_url in subpages:
            try:
                sub_r = requests.get(sub_url, headers=HEADERS, verify=False, timeout=5)
                if sub_r.status_code == 200:
                    sub_soup = BeautifulSoup(sub_r.text, "html.parser")
                    sub_text = sub_r.text
                    
                    # Deep harvest emails & phones if missing
                    if not lead["email"]:
                        sub_emails = EMAIL_REGEX.findall(sub_text)
                        if sub_emails:
                            lead["email"] = [e for e in set(sub_emails) if not e.endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.js', '.css'))][0]
                    if not lead["phone"]:
                        sub_phones = PHONE_REGEX.findall(sub_text)
                        if sub_phones:
                            lead["phone"] = sub_phones[0]
                            
                    # Harvest CIF/Tax ID
                    if not lead["cif"]:
                        cif_match = CIF_REGEX.search(sub_text)
                        if cif_match:
                            lead["cif"] = cif_match.group(0).upper().replace(" ", "").replace("-", "")
                            
                    # Harvest Razón Social (Legal Entity Name)
                    if not lead["razon_social"]:
                        rs = extract_razon_social(sub_text)
                        if rs:
                            lead["razon_social"] = rs
                            
                    # Harvest Address / Zip code
                    if not lead["address"]:
                        zip_match = POSTAL_CODE_REGEX.search(sub_text)
                        if zip_match:
                            # Try to extract the line surrounding the zip code as address snippet
                            zip_idx = sub_text.find(zip_match.group(0))
                            start = max(0, zip_idx - 60)
                            end = min(len(sub_text), zip_idx + 60)
                            snippet = sub_text[start:end].replace("\n", " ").strip()
                            # Strip HTML tags
                            snippet = re.sub(r"<[^>]+>", "", snippet)
                            lead["address"] = " ".join(snippet.split()[:8])
            except Exception:
                pass
                
    except Exception as e:
        logger.debug(f"Failed to crawl website {base_url}: {e}")
        return None
        
    return lead

def build_database(max_queries=14):
    """Gathers B2B leads from search engine and crawls them concurrently."""
    logger.info("Initializing High-Performance B2B Leads Engine...")
    all_domains = {}
    
    # 1. Gather domains by province query
    queries_to_run = PROVINCES[:max_queries]
    for idx, prov in enumerate(queries_to_run):
        q = f"instaladores placas solares {prov}"
        logger.info(f"[{idx+1}/{len(queries_to_run)}] Querying DuckDuckGo: {q!r}")
        found_urls = search_ddg_lite(q)
        for url in found_urls:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            if domain.startswith("www."):
                domain = domain[4:]
            if domain not in all_domains:
                all_domains[domain] = (url, prov)
        time.sleep(7.0)
        
    logger.info(f"Target installer domains collected: {len(all_domains)}")
    
    # 2. Crawl domains concurrently using ThreadPoolExecutor
    leads = []
    logger.info(f"Launching parallel crawler with {MAX_WORKERS} workers...")
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_url = {
            executor.submit(crawl_company_site, url, prov): url
            for domain, (url, prov) in all_domains.items()
        }
        
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                lead = future.result()
                if lead and (lead["email"] or lead["phone"]):
                    # Strip any HTML entity characters
                    for k in lead:
                        if isinstance(lead[k], str):
                            lead[k] = html.unescape(lead[k]).strip()
                            
                    # Skip garbage capture results
                    if "@" in lead["email"] and not any(ext in lead["email"].lower() for ext in [".webp", ".png", ".jpg", ".js", ".css"]):
                        logger.info(f"✅ Lead Found: {lead['name']} | CIF: {lead['cif']} | Email: {lead['email']}")
                        leads.append(lead)
            except Exception as e:
                logger.error(f"Error crawling worker result for {url}: {e}")
                
    # 3. Write structured database to CSV
    if leads:
        # Sort leads alphabetically
        leads.sort(key=lambda x: x["name"])
        
        with open(OUTPUT_CSV, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Empresa", "Razón Social", "CIF", "Email", "Teléfono", 
                "Sitio Web", "Dirección", "Provincia", "LinkedIn", "Facebook"
            ])
            for l in leads:
                writer.writerow([
                    l["name"], l["razon_social"], l["cif"], l["email"], l["phone"],
                    l["website"], l["address"], l["province"], l["linkedin"], l["facebook"]
                ])
                
        logger.info(f"🥇 HIGH-POWERED SCRAPING COMPLETE! {len(leads)} B2B leads written to {OUTPUT_CSV}")
    else:
        logger.warning("No B2B leads could be extracted.")

if __name__ == "__main__":
    # Cover 14 regions for standard runs (can run all 50 in cron jobs!)
    build_database(max_queries=14)
