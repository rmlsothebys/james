import re
import time
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
from .config import USER_AGENT, BASE, UNSOLD_URL, MAX_LISTINGS, PAUSE_BETWEEN_REQUESTS

HEADERS = {"User-Agent": USER_AGENT}

def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text

def _extract_listing_links(html):
    soup = BeautifulSoup(html, "lxml")
    links = []
    for a in soup.select('a[href*="/listing/"]'):
        href = a.get("href")
        if href and "/listing/" in href:
            href = href.split("?")[0]
            if href not in links:
                links.append(href)
    return links

def _find_pagination_pages(html):
    soup = BeautifulSoup(html, "lxml")
    pages = set([UNSOLD_URL])
    for a in soup.select("a"):
        href = a.get("href")
        if not href:
            continue
        if "auctions/results/" in href and "result=unsold" in href:
            if href.startswith("http"):
                pages.add(href.split("#")[0])
            else:
                pages.add(urljoin(BASE, href).split("#")[0])
    return sorted(pages)

def parse_unsold_index():
    first = fetch(UNSOLD_URL)
    pages = _find_pagination_pages(first)
    seen = []
    for pg in pages:
        try:
            html = fetch(pg)
            links = _extract_listing_links(html)
            for u in links:
                if u not in seen:
                    seen.append(u)
            if len(seen) >= MAX_LISTINGS:
                break
            time.sleep(PAUSE_BETWEEN_REQUESTS)
        except Exception:
            continue
    return seen[:MAX_LISTINGS]

def parse_listing(url):
    html = fetch(url)
    s = BeautifulSoup(html, "lxml")

    title_el = s.find(["h1","h2"])
    title = title_el.get_text(strip=True) if title_el else "Listing"

    year = None
    m = re.search(r"\b(19|20)\d{2}\b", title)
    if m: year = m.group(0)
    brand = model = ""
    if year and year in title:
        after = title.split(year, 1)[1].strip(" -|")
        parts = after.split()
        if parts:
            brand = parts[0]
            model = " ".join(parts[1:]) or brand
    else:
        parts = title.split()
        if parts:
            brand = parts[0]
            model = " ".join(parts[1:]) if len(parts)>1 else ""

    vin = mileage = transmission = ""
    text_blobs = " ".join(el.get_text(" ", strip=True) for el in s.find_all(["p","li","span","div"]))
    mvin = re.search(r"\b[A-HJ-NPR-Z0-9]{11,17}\b", text_blobs)
    if mvin: vin = mvin.group(0)

    mm = re.search(r"(\d{1,3}(?:,\d{3})+|\d{1,6})\s*(miles|mi\.?|km)\b", text_blobs, re.I)
    if mm: mileage = mm.group(1).replace(",","")

    mt = re.search(r"\b(manual|automatic|semi-automatic|dual-clutch)\b", text_blobs, re.I)
    if mt: transmission = mt.group(1).lower()

        # images: acceptă doar fotografii reale, nu icoane SVG / assets de temă
    imgs = []
    for img in s.select("img"):
        src = img.get("src") or img.get("data-src") or ""
        if not src.startswith("http"):
            continue
        url_no_q = src.split("?", 1)[0].lower()
        # acceptă doar extensii foto
        is_photo = url_no_q.endswith((".jpg", ".jpeg", ".png", ".webp"))
        # exclude icoane / assets de temă
        is_theme_asset = "/themes/" in url_no_q or url_no_q.endswith(".svg")
        if is_photo and not is_theme_asset:
            if src not in imgs:
                imgs.append(src)
    imgs = imgs[:40]


    desc = ""
    body = s.find("article") or s.find("div", class_=re.compile("content|body", re.I))
    if body:
        desc = body.get_text("\n", strip=True)
    if not desc:
        desc = s.get_text("\n", strip=True)
    desc = re.sub(r"\n{3,}", "\n\n", desc)[:3000]

    return {
        "title": title, "brand": brand, "model": model, "year": year or "",
        "vin": vin, "mileage": mileage, "transmission": transmission,
        "images": imgs, "url": url, "description": desc
    }
