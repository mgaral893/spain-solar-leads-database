#!/usr/bin/env python3
"""
Cron wrapper script to automate the full pipeline:
1. Crawl all Spanish regions for solar installer leads.
2. Synchronize the database with Gumroad.
"""
import os
import sys
import logging

# Ensure project path is in python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from scraper import build_database
import gumroad_export

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("cron_pipeline")

def run_pipeline():
    logger.info("⚡ Starting scheduled Solar Leads Scraping and Gumroad Sync...")
    
    # 1. Run scraper with max queries (14, representing all Spanish regions)
    try:
        build_database(max_queries=14)
    except Exception as e:
        logger.error(f"❌ Error during lead scraping: {e}")
        sys.exit(1)
        
    # 2. Run Gumroad Sync
    try:
        gumroad_export.main()
        logger.info("✅ Scheduled pipeline run completed successfully.")
    except Exception as e:
        logger.error(f"❌ Error during Gumroad synchronization: {e}")
        sys.exit(2)

if __name__ == "__main__":
    run_pipeline()
