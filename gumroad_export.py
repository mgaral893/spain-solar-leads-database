#!/usr/bin/env python3
"""
Gumroad Database Sync Engine
=============================
Automates product creation and file uploads to Gumroad using the Gumroad API v2.
Reads token from GUMROAD_TOKEN environment variable.
"""
import os
import json
import logging
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("gumroad_sync")

CONFIG_FILE = "gumroad_config.json"
CSV_FILE = "instaladores_solares_espana.csv"

def get_gumroad_token():
    """Retrieve the Gumroad API token from environment."""
    token = os.environ.get("GUMROAD_TOKEN")
    if not token:
        logger.error("❌ GUMROAD_TOKEN environment variable not set. Please export it before running.")
        return None
    return token.strip()

def load_config():
    """Load cached Gumroad product configuration."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load config file: {e}")
    return {}

def save_config(config):
    """Save Gumroad product configuration."""
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=4)
        logger.info(f"Config cached to {CONFIG_FILE}")
    except Exception as e:
        logger.error(f"Failed to save config: {e}")

def create_product(token):
    """Create a new product on Gumroad and return the product ID."""
    url = "https://api.gumroad.com/v2/products"
    headers = {"Authorization": f"Bearer {token}"}
    
    payload = {
        "name": "Base de Datos de Instaladores de Placas Solares en España (Leads B2B)",
        "price": "2900",  # $29.00 in cents
        "description": (
            "Directorio comercial verificado de empresas de energía solar y autoconsumo en España.\n\n"
            "Incluye:\n"
            "• Nombre de la Empresa\n"
            "• Correo electrónico corporativo verificado\n"
            "• Teléfono de contacto directo\n"
            "• Enlace a su sitio web oficial\n\n"
            "Ideal para proveedores de material fotovoltaico, agencias de marketing y empresas B2B."
        ),
        "summary": "Directorio verificado de instaladores de placas solares en España.",
        "shown_on_profile": "true"
    }
    
    logger.info("Registering new product on Gumroad...")
    try:
        r = requests.post(url, data=payload, headers=headers, timeout=15)
        if r.status_code in [200, 201]:
            res = r.json()
            product = res.get("product", {})
            product_id = product.get("id")
            short_url = product.get("short_url")
            logger.info(f"✅ Product created successfully! ID: {product_id} | Link: {short_url}")
            return product_id
        else:
            logger.error(f"❌ Failed to create product: HTTP {r.status_code} - {r.text}")
    except Exception as e:
        logger.error(f"Error during product registration: {e}")
    return None

def upload_product_file(token, product_id, filepath):
    """Uploads the B2B CSV file to the Gumroad product as the main deliverable."""
    if not os.path.exists(filepath):
        logger.error(f"❌ Target database file not found: {filepath}")
        return False
        
    # Gumroad API v2 allows attaching files by sending multi-part form data to
    # PUT /v2/products/:product_id
    url = f"https://api.gumroad.com/v2/products/{product_id}"
    headers = {"Authorization": f"Bearer {token}"}
    
    logger.info(f"Uploading database file {filepath} to product {product_id}...")
    try:
        with open(filepath, "rb") as f:
            files = {"file": f}
            r = requests.put(url, headers=headers, files=files, timeout=30)
            if r.status_code == 200:
                logger.info("✅ Database file uploaded and synchronized successfully to Gumroad!")
                return True
            else:
                logger.error(f"❌ Upload failed: HTTP {r.status_code} - {r.text}")
    except Exception as e:
        logger.error(f"Error uploading file to Gumroad: {e}")
    return False

def publish_product(token, product_id):
    """Publishes (enables) the product on Gumroad so it is live for buyers."""
    url = f"https://api.gumroad.com/v2/products/{product_id}/enable"
    headers = {"Authorization": f"Bearer {token}"}
    
    logger.info(f"Publishing product {product_id} to make it live...")
    try:
        r = requests.put(url, headers=headers, timeout=15)
        if r.status_code == 200:
            logger.info("✅ Product published successfully and is now live on Gumroad!")
            return True
        else:
            logger.error(f"❌ Failed to publish product: HTTP {r.status_code} - {r.text}")
    except Exception as e:
        logger.error(f"Error publishing product on Gumroad: {e}")
    return False

def main():
    token = get_gumroad_token()
    if not token:
        return
        
    if not os.path.exists(CSV_FILE):
        logger.error(f"❌ Scraped database file {CSV_FILE} not found. Run scraper.py first.")
        return
        
    config = load_config()
    product_id = config.get("product_id")
    
    if not product_id:
        product_id = create_product(token)
        if product_id:
            config["product_id"] = product_id
            save_config(config)
        else:
            return
            
    # Upload/Update the CSV file
    uploaded = upload_product_file(token, product_id, CSV_FILE)
    if uploaded:
        # Publish/Enable the product
        publish_product(token, product_id)

if __name__ == "__main__":
    main()
