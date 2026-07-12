#!/usr/bin/env python3
"""
Spain Solar Leads Database Scraper (Search & Crawl Engine)
===========================================================
Queries DuckDuckGo Lite for solar installers in various Spanish provinces,
gathers unique domains, and crawls them to extract emails, phones, and names.
"""
import os
import csv
import re
import time
import urllib3
import logging
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Setup Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("leads_engine")

OUTPUT_CSV = "instaladores_solares_espana.csv"

# Real User-Agent
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# Queries for various regions in Spain
QUERIES = [
    "instaladores placas solares madrid",
    "empresa autoconsumo solar barcelona",
    "instalacion solar sevilla",
    "placas solares valencia",
    "energia solar zaragoza",
    "empresas instaladoras placas solares malaga",
    "instaladores placas solares murcia",
    "autoconsumo fotovoltaico bilbao",
    "placas solares alicante",
    "instaladores placas solares galicia",
    "placas solares asturias",
    "instalador placas solares valladolid",
    "placas solares toledo",
    "empresa solar mallorca"
]

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PHONE_REGEX = re.compile(r"\b(?:9|6|7)\d{2}[-.\s]?\d{3}[-.\s]?\d{3}\b|\b(?:9|6|7)\d{2}[-.\s]?\d{2}[-.\s]?\d{2}[-.\s]?\d{2}\b")

# Block popular aggregators, blogs, and big directories
BLOCKED_DOMAINS = [
    "google.com", "duckduckgo.com", "facebook.com", "instagram.com", "linkedin.com",
    "twitter.com", "youtube.com", "selectra.es", "rankia.com", "renovables.blog",
    "eleconomista.es", "empresite", "paginasamarillas.es", "idealista.com", "wikipedia.org",
    "x.com", "pinterest.com", "milanuncios.com", "habitissimo.es"
]

def search_ddg_lite(query):
    """Search DuckDuckGo Lite and return external domains."""
    url = "https://lite.duckduckgo.com/lite/"
    data = {"q": query}
    domains = set()
    
    try:
        r = requests.post(url, data=data, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                # Skip internal DDG links
                if "duckduckgo.com" in href or href.startswith("/") or href.startswith("?"):
                    continue
                    
                parsed = urlparse(href)
                domain = parsed.netloc.lower()
                # Clean www.
                if domain.startswith("www."):
                    domain = domain[4:]
                    
                if domain and not any(b in domain for b in BLOCKED_DOMAINS):
                    domains.add((domain, f"{parsed.scheme}://{parsed.netloc}"))
    except Exception as e:
        logger.warning(f"Error searching DuckDuckGo for query {query!r}: {e}")
        
    return domains

def extract_leads_from_website(base_url):
    """Crawls a website homepage and subpages to extract business name, email, and phone."""
    lead_data = {"name": "", "email": "", "phone": "", "web": base_url}
    
    try:
        r = requests.get(base_url, headers=HEADERS, verify=False, timeout=8)
        if r.status_code != 200:
            return None
            
        soup = BeautifulSoup(r.text, "html.parser")
        
        # 1. Company Name from Title
        title_tag = soup.find("title")
        if title_tag:
            # Clean title
            title = title_tag.text.strip()
            # Split common separators
            for sep in ["|", "-", "—"]:
                if sep in title:
                    title = title.split(sep)[0].strip()
            lead_data["name"] = title
            
        # 2. Extract email and phone from homepage text
        html_text = r.text
        emails = EMAIL_REGEX.findall(html_text)
        phones = PHONE_REGEX.findall(html_text)
        
        if emails:
            lead_data["email"] = [e for e in set(emails) if not e.endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg'))][0]
        if phones:
            lead_data["phone"] = phones[0]
            
        # 3. If missing, look for /contacto, /aviso-legal, /politica-de-privacidad links
        if not lead_data["email"] or not lead_data["phone"]:
            subpages = []
            for a in soup.find_all("a", href=True):
                href = a["href"].lower()
                text = a.text.lower()
                if any(k in href or k in text for k in ["contacto", "legal", "privacidad", "sobre-nosotros", "contact"]):
                    sub_url = urljoin(base_url, a["href"])
                    subpages.append(sub_url)
            
            # De-duplicate subpages and scan top 2
            subpages = list(set(subpages))[:2]
            for sub_url in subpages:
                try:
                    logger.info(f"Scanning subpage for details: {sub_url}")
                    sub_r = requests.get(sub_url, headers=HEADERS, verify=False, timeout=5)
                    if sub_r.status_code == 200:
                        sub_text = sub_r.text
                        if not lead_data["email"]:
                            sub_emails = EMAIL_REGEX.findall(sub_text)
                            if sub_emails:
                                lead_data["email"] = [e for e in set(sub_emails) if not e.endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg'))][0]
                        if not lead_data["phone"]:
                            sub_phones = PHONE_REGEX.findall(sub_text)
                            if sub_phones:
                                lead_data["phone"] = sub_phones[0]
                except Exception:
                    pass
                    
    except Exception as e:
        logger.debug(f"Failed to crawl {base_url}: {e}")
        return None
        
    return lead_data

def build_database(max_queries=5):
    """Runs search queries, crawls websites, and saves to CSV."""
    logger.info("Initializing B2B lead generation engine...")
    all_domains = {}
    
    # Phase 1: Search and gather domains
    queries_to_run = QUERIES[:max_queries]
    for q in queries_to_run:
        logger.info(f"Running search query: {q!r}")
        found = search_ddg_lite(q)
        logger.info(f"Found {len(found)} candidate domains.")
        for domain, full_url in found:
            all_domains[domain] = full_url
        time.sleep(2)
        
    logger.info(f"Unique domains collected: {len(all_domains)}")
    
    # Phase 2: Crawl and extract leads
    leads = []
    for domain, full_url in all_domains.items():
        logger.info(f"Crawling company website: {full_url}")
        lead = extract_leads_from_website(full_url)
        if lead and (lead["email"] or lead["phone"]):
            # Normalize company name if empty
            if not lead["name"]:
                lead["name"] = domain.capitalize()
            logger.info(f"Lead Found: {lead['name']} | Email: {lead['email']} | Phone: {lead['phone']}")
            leads.append(lead)
        time.sleep(1.5)
        
    # Phase 3: Export to CSV
    if leads:
        # Sort leads by company name
        leads.sort(key=lambda x: x["name"])
        
        with open(OUTPUT_CSV, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Empresa", "Email", "Teléfono", "Sitio Web"])
            for l in leads:
                writer.writerow([l["name"], l["email"], l["phone"], l["web"]])
                
        logger.info(f"✅ Leads database compiled! {len(leads)} B2B leads written to {OUTPUT_CSV}")
    else:
        logger.warning("No B2B leads could be extracted.")

if __name__ == "__main__":
    # Run a test scan with 4 queries for fast verification
    build_database(max_queries=4)
