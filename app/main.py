import time
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from xml.etree.ElementTree import Element, SubElement, ElementTree

from playwright.sync_api import sync_playwright

BASE_AUCTIONS = "https://bringatrailer.com/auctions/?sortby=bd"

DEALER_ID = "105029"
DEALER_NAME = "RM Sotheby's"
OUTPUT_XML = f"JamesEdition_feed_{DEALER_ID}.xml"

MAX_IMAGES = 7
SCROLL_PAUSE = 1.2
SCROLL_MAX_LOOPS = 500         # safety cap
STABLE_LOOPS_TO_STOP = 6       # stop after N loops with no new listings
REQUEST_TIMEOUT_S = 30

def clean_url(u: str) -> str:
    p = urlparse(u)
    return f"{p.scheme}://{p.netloc}{p.path}"

def pick_first_paragraphs(soup: BeautifulSoup, max_paragraphs: int = 2, max_chars: int = 900) -> str:
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

def pick_images(soup: BeautifulSoup, max_images: int = MAX_IMAGES) -> list[str]:
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

    og = soup.select_one("meta[property='og:image']")
    if og and og.get("content"):
        add(og["content"])

    for a in soup.select("a[href]"):
        href = a.get("href") or ""
        if "bringatrailer" in href and re.search(r"\.(jpg|jpeg|png|webp)(\?|$)", href, re.IGNORECASE):
            add(href)
        if len(imgs) >= max_images:
            return imgs[:max_images]

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
                add(parts[-1])
                if len(imgs) >= max_images:
                    return imgs[:max_images]

    return imgs[:max_images]

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
        imgs_el = SubElement(it, "images")
        for u in l["images"][:MAX_IMAGES]:
            SubElement(imgs_el, "image").text = u

    ElementTree(feed).write(OUTPUT_XML, encoding="utf-8", xml_declaration=True)

def collect_listing_urls_with_browser() -> tuple[list[str], dict, str]:
    """
    Returns: (listing_urls, cookies_dict, user_agent)
    Uses a real browser session so BaT JS + protections are satisfied.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # headless=True poate fi blocat
        context = browser.new_context()
        page = context.new_page()

        page.goto(BASE_AUCTIONS, wait_until="domcontentloaded", timeout=120000)

        # încercăm să închidem/acceptăm banner cookies dacă apare
        for txt in ["Accept", "I Agree", "Agree", "OK"]:
            try:
                btn = page.get_by_role("button", name=txt)
                if btn.count() > 0:
                    btn.first.click(timeout=1500)
                    break
            except Exception:
                pass

        seen = set()
        stable = 0

        def grab():
            hrefs = page.eval_on_selector_all(
                "a[href]",
                "els => els.map(e => e.getAttribute('href')).filter(Boolean)"
            )
            out = []
            for h in hrefs:
                if "/listing/" not in h:
                    continue
                full = urljoin("https://bringatrailer.com", h)
                full = clean_url(full)
                if full.startswith("https://bringatrailer.com/") and "/listing/" in full:
                    out.append(full)
            return out

        last_count = 0
        for i in range(SCROLL_MAX_LOOPS):
            links = grab()
            for u in links:
                seen.add(u)

            # scroll down
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(SCROLL_PAUSE)

            now = len(seen)
            if now == last_count:
                stable += 1
            else:
                stable = 0
                last_count = now

            if i % 10 == 0:
                print(f"Scroll loop {i}: collected {now} listing URLs")

            if stable >= STABLE_LOOPS_TO_STOP:
                break

        cookies = context.cookies()
        cookies_dict = {c["name"]: c["value"] for c in cookies}
        user_agent = page.evaluate("() => navigator.userAgent")

        browser.close()

    return sorted(seen), cookies_dict, user_agent

def fetch_listing(session: requests.Session, url: str) -> dict:
    r = session.get(url, timeout=REQUEST_TIMEOUT_S)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}")

    soup = BeautifulSoup(r.text, "html.parser")
    h1 = soup.find("h1")
    title = h1.get_text(" ", strip=True) if h1 else url
    listing_id = url.rstrip("/").split("/")[-1]

    description = pick_first_paragraphs(soup, max_paragraphs=2, max_chars=900)
    images = pick_images(soup, max_images=MAX_IMAGES)

    return {
        "id": listing_id,
        "title": title,
        "url": url,
        "description": description,
        "images": images[:MAX_IMAGES],
    }

def main():
    print("Opening real browser to collect ALL listing URLs…")
    urls, cookies_dict, ua = collect_listing_urls_with_browser()
    print(f"Found {len(urls)} listing URLs")

    sess = requests.Session()
    sess.headers.update({
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
        "Referer": "https://bringatrailer.com/",
    })
    sess.cookies.update(cookies_dict)

    listings = []
    for i, u in enumerate(urls, start=1):
        try:
            item = fetch_listing(sess, u)
            listings.append(item)
            print(f"[{i}/{len(urls)}] OK {item['id']} images={len(item['images'])}")
        except Exception as e:
            print(f"[{i}/{len(urls)}] SKIP {u} ({e})")
        time.sleep(0.5)

    build_xml(listings)
    print(f"Done. Wrote {OUTPUT_XML} with {len(listings)} listings.")

if __name__ == "__main__":
    main()
