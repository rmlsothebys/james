import time
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from xml.etree.ElementTree import Element, SubElement, ElementTree

# SOURCE
BASE_AUCTIONS = "https://bringatrailer.com/auctions/?sortby=bd"

# TUNING
MAX_PAGES = 300          # safety cap; creste daca vrei
MAX_IMAGES = 7
SLEEP_BETWEEN_REQ = 1.0  # polite throttle
TIMEOUT_S = 30

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}

DEALER_ID = "105029"
DEALER_NAME = "RM Sotheby's"
OUTPUT_XML = f"JamesEdition_feed_{DEALER_ID}.xml"


def clean_url(u: str) -> str:
    """Drop query/fragment for stable dedupe."""
    p = urlparse(u)
    return f"{p.scheme}://{p.netloc}{p.path}"


def is_listing_url(u: str) -> bool:
    u = u.lower()
    return u.startswith("https://bringatrailer.com/") and "/listing/" in u


def looks_like_bot_block(html: str) -> bool:
    """Detect common bot/cookie challenge pages."""
    h = html.lower()
    signals = [
        "just a moment",
        "checking your browser",
        "enable cookies",
        "cloudflare",
        "cf-browser-verification",
        "attention required",
        "captcha",
        "verify you are human",
    ]
    return any(s in h for s in signals)


def extract_listing_links_from_page(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    links = []

    for a in soup.select("a[href]"):
        href = (a.get("href") or "").strip()
        if not href:
            continue

        if href.startswith("http"):
            full = href
        else:
            full = urljoin("https://bringatrailer.com", href)

        full = clean_url(full)

        if is_listing_url(full):
            links.append(full)

    # de-dup preserve order
    out, seen = [], set()
    for u in links:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def get_all_listing_links() -> list[str]:
    all_links: list[str] = []
    seen: set[str] = set()

    for page in range(1, MAX_PAGES + 1):
        url = f"{BASE_AUCTIONS}&page={page}"
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT_S)

        if page == 1:
            print("Index page status:", r.status_code)
            if looks_like_bot_block(r.text):
                print("\n⚠️ BaT returned a bot/cookie challenge page.")
                print("Open the URL in a browser and confirm it loads normally:")
                print(BASE_AUCTIONS)
                print("Then re-run. If it still blocks, we need a cookies-based approach.\n")
                # continue anyway to show 0 links rather than crashing

        if r.status_code != 200:
            print(f"Stop: HTTP {r.status_code} at page {page}")
            break

        page_links = extract_listing_links_from_page(r.text)
        new_links = [u for u in page_links if u not in seen]

        # stop condition: no new listings found
        if not new_links:
            break

        for u in new_links:
            seen.add(u)
            all_links.append(u)

        if page % 5 == 0:
            print(f"Collected {len(all_links)} listing URLs so far (page {page})")

        time.sleep(SLEEP_BETWEEN_REQ)

    return all_links


def first_paragraphs_text(soup: BeautifulSoup, max_paragraphs: int = 2, max_chars: int = 900) -> str:
    container = soup.select_one(".post-content") or soup.select_one("article") or soup.body
    if not container:
        return ""

    ps = container.find_all("p")
    chunks = []
    for p in ps[:max_paragraphs]:
        t = p.get_text(" ", strip=True)
        if t:
            chunks.append(t)

    text = " ".join(chunks).strip()
    if len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0].strip() + "…"
    return text


def pick_image_urls(soup: BeautifulSoup, max_images: int = MAX_IMAGES) -> list[str]:
    imgs: list[str] = []

    def add(u: str):
        if not u:
            return
        u = u.strip()
        if u.startswith("//"):
            u = "https:" + u
        if not u.startswith("http"):
            return
        if "bringatrailer" not in u:
            return
        if not re.search(r"\.(jpg|jpeg|png|webp)(\?|$)", u, re.IGNORECASE):
            return
        u = clean_url(u)
        if u not in imgs:
            imgs.append(u)

    # 1) OG image
    og = soup.select_one("meta[property='og:image']")
    if og and og.get("content"):
        add(og["content"])

    # 2) direct links to images
    for a in soup.select("a[href]"):
        href = a.get("href") or ""
        if "bringatrailer" in href and re.search(r"\.(jpg|jpeg|png|webp)(\?|$)", href, re.IGNORECASE):
            add(href)
        if len(imgs) >= max_images:
            return imgs[:max_images]

    # 3) img tags + srcset
    for img in soup.select("img"):
        for attr in ("src", "data-src"):
            v = img.get(attr, "")
            if v:
                add(v)
                if len(imgs) >= max_images:
                    return imgs[:max_images]

        srcset = img.get("srcset", "")
        if srcset:
            parts = [p.strip().split(" ")[0] for p in srcset.split(",") if p.strip()]
            if parts:
                add(parts[-1])  # usually largest
                if len(imgs) >= max_images:
                    return imgs[:max_images]

    return imgs[:max_images]


def parse_listing(listing_url: str) -> dict:
    r = requests.get(listing_url, headers=HEADERS, timeout=TIMEOUT_S)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}")

    if looks_like_bot_block(r.text):
        raise RuntimeError("Bot/cookie challenge on listing page")

    soup = BeautifulSoup(r.text, "html.parser")

    h1 = soup.find("h1")
    title = h1.get_text(" ", strip=True) if h1 else listing_url

    # Stable ID: slug part after /listing/
    # Example: https://bringatrailer.com/listing/1997-porsche-911-turbo/
    listing_id = listing_url.rstrip("/").split("/")[-1]

    description = first_paragraphs_text(soup, max_paragraphs=2, max_chars=900)
    images = pick_image_urls(soup, max_images=MAX_IMAGES)

    return {
        "id": listing_id,
        "title": title,
        "url": listing_url,
        "description": description,
        "images": images[:MAX_IMAGES],
    }


def build_xml(listings: list[dict]):
    feed = Element("feed", version="3.0")
    header = SubElement(feed, "header")
    SubElement(header, "dealer_id").text = DEALER_ID
    SubElement(header, "dealer_name").text = DEALER_NAME

    items = SubElement(feed, "listings")

    for l in listings:
        it = SubElement(items, "listing")
        SubElement(it, "id").text = l["id"]
        SubElement(it, "title").text = l["title"]
        SubElement(it, "url").text = l["url"]
        SubElement(it, "description").text = l["description"]
        SubElement(it, "price_on_request").text = "yes"

        imgs = SubElement(it, "images")
        for img in l["images"][:MAX_IMAGES]:
            SubElement(imgs, "image").text = img

    tree = ElementTree(feed)
    tree.write(OUTPUT_XML, encoding="utf-8", xml_declaration=True)


def main():
    print("Collecting all auction listing URLs…")
    links = get_all_listing_links()
    print(f"Found {len(links)} listing URLs")

    listings = []
    for i, link in enumerate(links, start=1):
        try:
            l = parse_listing(link)
            listings.append(l)
            print(f"[{i}/{len(links)}] OK: {l['id']} images={len(l['images'])}")
        except Exception as e:
            print(f"[{i}/{len(links)}] SKIP: {link} ({e})")

        time.sleep(SLEEP_BETWEEN_REQ)

    build_xml(listings)
    print(f"Done. Wrote {OUTPUT_XML} with {len(listings)} listings.")


if __name__ == "__main__":
    main()
