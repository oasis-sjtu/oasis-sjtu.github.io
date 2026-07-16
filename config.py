"""
Configuration for the Oasis Lab website.
"""
import os
from datetime import datetime
from pathlib import Path

DEBUG = os.getenv("FLASK_DEBUG", "").lower() in {"1", "true", "yes", "on"}
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "5000"))

BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = BASE_DIR / "data"

PUBLICATIONS_CSV = STATIC_DIR / "publications.csv"
DATASET_METRICS_JSON = STATIC_DIR / "dataset_metrics.json"
PEOPLE_CSV = DATA_DIR / "people.csv"
RESEARCH_CSV = DATA_DIR / "research.csv"
NEWS_CSV = DATA_DIR / "news.csv"
SPONSORS_CSV = DATA_DIR / "sponsors.csv"
AWARDS_CSV = DATA_DIR / "awards.csv"

SITE_TITLE = "Oasis Lab"
NAVBAR_TITLE = "Oasis Lab"
SITE_DESCRIPTION = (
    "Oasis Lab at Shanghai Jiao Tong University studies Operating And Storage "
    "Infrastructure System research for cloud, storage, and AI infrastructure."
)
COPYRIGHT_YEAR = str(datetime.now().year)
COPYRIGHT_TEXT = "Oasis Lab, Shanghai Jiao Tong University"

GITHUB_URL = "https://github.com/giorgioercixu"
SCHOLAR_URL = "https://scholar.google.com/citations?user=7Yc6A1QAAAAJ"
PI_EMAIL_DISPLAY = "ercixu [at] SJTU [dot] edu [dot] cn"
PERSONAL_SITE_URL = "https://giorgioercixu.github.io/"
