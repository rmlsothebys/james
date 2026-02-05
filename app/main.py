import time
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs
from xml.etree.ElementTree import Element, SubElement, ElementTree

BASE_AUCTIONS = "https://bringatrailer.com/auctions/?sortby=bd"
HEADERS = {"User-Agent": "Mozilla/5.0"}
MAX_PAGES = 200          # safety cap (poți crește)
SLEEP_BETWEEN_REQ = 1.0  # polite throttle
MAX_IMAGES = 7

def clean_url(u: str) -> str:
    # Remove fragments and keep canonical-ish URL
    p = urlparse(u)
    return f"{p.scheme}://{p.netloc}{p.path}"

def is_listing_url(u: str) -> bool:
    return u.startswith("https://bringatrailer.com/listing/")

def extract_listing_links_from_page(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    links = []

    # Listings usually appear as /listing/...
    for a in soup.select("a[href^='/listing/']"):
        href = a.get("href", "").strip()
        if not href:
            continue
        full = clean_url(urljoin("https://bringatrailer.com", href))
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
        r = requests.get(url, headers=HEADERS, timeout=25)
        if r.status_code != 200:
            break

        page_links = extract_listing_links_from_page(r.text)
        new_links = [u for u in page_links if u not in seen]

        # stop when no new listings found
        if not new_links:
            break

        for u in new_links:
            seen.add(u)
            all_links.append(u)

        time.sleep(SLEEP_BETWEEN_REQ)

    return all_links

def first_paragraphs_text(soup: BeautifulSoup, max_paragraphs: int = 2, max_chars: int = 700) -> str:
    # BaT main post content
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
        # keep only BaT-hosted-ish images, and typical image extensions
        if "bringatrailer" not in u:
            return
        if not re.search(r"\.(jpg|jpeg|png|webp)(\?|$)", u, re.IGNORECASE):
            return
        u = clean_url(u)  # dedupe easier
        if u not in imgs:
            imgs.append(u)

    # 1) OG image first (often the hero image)
    og = soup.select_one("meta[property='og:image']")
    if og and og.get("content"):
        add(og["content"])

    # 2) Gallery/attachments often in <a href="...jpg">
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if "bringatrailer" in href and re.search(r"\.(jpg|jpeg|png|webp)(\?|$)", href, re.IGNORECASE):
            add(href)
        if len(imgs) >= max_images:
            return imgs[:max_images]

    # 3) Fallback: <img src / data-src / srcset>
    for img in soup.select("img"):
        for attr in ("src", "data-src"):
            v = img.get(attr, "")
            if v:
                add(v)
                if len(imgs) >= max_images:
                    return imgs[:max_images]

        srcset = img.get("srcset", "")
        if srcset:
            # take the largest candidate (last)
            parts = [p.strip().split(" ")[0] for p in srcset.split(",") if p.strip()]
            if parts:
                add(parts[-1])
                if len(imgs) >= max_images:
                    return imgs[:max_images]

    return imgs[:max_images]

def parse_listing(listing_url: str) -> dict:
    r = requests.get(listing_url, headers=HEADERS, timeout=25)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}")

    soup = BeautifulSoup(r.text, "html.parser")

    h1 = soup.find("h1")
    title = h1.get_text(" ", strip=True) if h1 else listing_url

    # ID stable: slug from URL path
    listing_id = listing_url.rstrip("/").split("/")[-1]  # e.g. 1997-porsche-911-turbo

    description = first_paragraphs_text(soup, max_paragraphs=2, max_chars=900)
    images = pick_image_urls(soup, max_images=MAX_IMAGES)

    return {
        "id": listing_id,
        "title": title,
        "url": listing_url,
        "description": description,
        "images": images,
    }

def build_xml(listings: list[dict]):
    feed = Element("feed", version="3.0")
    header = SubElement(feed, "header")
    SubElement(header, "dealer_id").text = "105029"
    SubElement(header, "dealer_name").text = "RM Sotheby's"

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
    tree.write("JamesEdition_feed_105029.xml", encoding="utf-8", xml_declaration=True)

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
    print(f"Done. Wrote JamesEdition_feed_105029.xml with {len(listings)} listings.")

if __name__ == "__main__":
    main()
