import os

BASE = "https://bringatrailer.com"
UNSOLD_URL = f"{BASE}/auctions/results/?result=unsold"
PAUSE_BETWEEN_REQUESTS = float(os.getenv("PAUSE_BETWEEN_REQUESTS", "0.9"))
MAX_LISTINGS = int(os.getenv("MAX_LISTINGS", "120"))
USER_AGENT = os.getenv("USER_AGENT", "Mozilla/5.0 (+je-feed; contact: you@example.com)")

FEED_VERSION = os.getenv("FEED_VERSION", "3.0")
FEED_REFERENCE = os.getenv("FEED_REFERENCE", "BAT-unsold")
FEED_TITLE = os.getenv("FEED_TITLE", "BaT Unsold importer")
JE_DEALER_ID = os.getenv("JE_DEALER_ID", "").strip()
JE_DEALER_NAME = os.getenv("JE_DEALER_NAME", "").strip()

IMAGE_HOST_BASE = os.getenv("IMAGE_HOST_BASE", "").rstrip("/")

def output_filename():
    if not JE_DEALER_ID:
        raise SystemExit("Environment JE_DEALER_ID is required")
    return f"JamesEdition_feed_{JE_DEALER_ID}.xml"

AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "")
AWS_DEFAULT_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
S3_BUCKET = os.getenv("S3_BUCKET", "")
S3_PREFIX = os.getenv("S3_PREFIX", "").lstrip("/")
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "")
