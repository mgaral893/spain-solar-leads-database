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
    
    # 1. Run scraper with max queries (100, covering provinces and major cities)
    try:
        build_database(max_queries=100)
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

    # 3. Git push database updates
    try:
        import subprocess
        logger.info("Syncing database changes with GitHub...")
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", "chore: auto-sync leads database updates"], check=True)
        subprocess.run(["git", "push"], check=True)
        logger.info("✅ Leads database pushed to GitHub successfully.")
    except Exception as e:
        logger.warning(f"⚠️ Git push skipped/failed: {e}")


if __name__ == "__main__":
    run_pipeline()
