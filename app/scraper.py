import re
import time
import asyncio
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from .config import USER_AGENT, BASE, MAX_LISTINGS, PAUSE_BETWEEN_REQUESTS

HEADERS = {"User-Agent": USER_AGENT}

# >>> AICI este pagina cerută de tine:
AUCTIONS_URL = "https://bringatrailer.com/auctions/?sortby=bd"


def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text


def _uniq(seq):
    seen = set()
    out = []
    for x in seq:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _normalize_listing_url(h: str) -> str:
    if not h:
        return ""
    h = h.split("#")[0].split("?")[0].rstrip("/")
    if "/listing/" not in h:
        return ""
    if h.startswith("http"):
        return h
    return urljoin(BASE, h)


async def _collect_listing_links_dynamic(target: int) -> list:
    """
    Colectează link-uri de pe /auctions/?sortby=bd (dinamic JS).
    Încercă scroll și butoane tip "Show more" dacă apar.
    Returnează URL-uri absolute către /listing/...
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(extra_http_headers={"User-Agent": USER_AGENT})

        await page.goto(AUCTIONS_URL, wait_until="domcontentloaded", timeout=90000)

        urls = []
        max_steps = 120  # suficient pt 200-300 (depinde de câte încarcă per scroll)
        steps = 0

        while len(urls) < target and steps < max_steps:
            # ia toate linkurile /listing/ din DOM
            hrefs = await page.eval_on_selector_all(
                "a[href*='/listing/']",
                "els => els.map(e => e.getAttribute('href'))"
            )

            cleaned = []
            for h in hrefs or []:
                u = _normalize_listing_url(h)
                if u:
                    cleaned.append(u)

            urls = _uniq(urls + cleaned)
            if len(urls) >= target:
                break

            # încearcă butoane "Show more / Load more" dacă există
            clicked = False
            for sel in [
                "text=Show More",
                "text=Show more",
                "text=Load More",
                "text=Load more",
                "button:has-text('Show More')",
                "button:has-text('Show more')",
                "button:has-text('Load More')",
                "button:has-text('Load more')",
            ]:
                try:
                    btn = page.locator(sel).first
                    if await btn.count():
                        await btn.scroll_into_view_if_needed()
                        await btn.click(timeout=2000)
                        clicked = True
                        break
                except Exception:
                    pass

            # fallback: scroll down (declanșează încărcare)
            if not clicked:
                try:
                    await page.mouse.wheel(0, 3000)
                except Exception:
                    pass

            await page.wait_for_timeout(1200)
            steps += 1

        await browser.close()
        return urls[:target]


def parse_unsold_index():
    """
    Păstrăm numele funcției ca să nu modifici main.py.
    DAR acum ia listările din AUCTIONS_URL (sortby=bd).
    Returnează MAX_LISTINGS linkuri /listing/...
    """
    target = int(MAX_LISTINGS or 300)

    # Playwright (dinamic)
    try:
        links = asyncio.run(_collect_listing_links_dynamic(target=target))
        if links:
            return links[:target]
    except Exception:
        pass

    # Fallback (static) – uneori merge parțial
    try:
        html = fetch(AUCTIONS_URL)
        soup = BeautifulSoup(html, "lxml")
        links = []
        for a in soup.select('a[href*="/listing/"]'):
            href = a.get("href")
            u = _normalize_listing_url(href)
            if u and u not in links:
                links.append(u)
        return links[:target]
    except Exception:
        return []


def parse_listing(url):
    html = fetch(url)
    s = BeautifulSoup(html, "lxml")

    title_el = s.find(["h1", "h2"])
    title = title_el.get_text(strip=True) if title_el else "Listing"

    year = None
    m = re.search(r"\b(19|20)\d{2}\b", title)
    if m:
        year = m.group(0)

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
            model = " ".join(parts[1:]) if len(parts) > 1 else ""

    vin = mileage = transmission = ""
    text_blobs = " ".join(el.get_text(" ", strip=True) for el in s.find_all(["p", "li", "span", "div"]))
    mvin = re.search(r"\b[A-HJ-NPR-Z0-9]{11,17}\b", text_blobs)
    if mvin:
        vin = mvin.group(0)

    mm = re.search(r"(\d{1,3}(?:,\d{3})+|\d{1,6})\s*(miles|mi\.?|km)\b", text_blobs, re.I)
    if mm:
        mileage = mm.group(1).replace(",", "")

    mt = re.search(r"\b(manual|automatic|semi-automatic|dual-clutch)\b", text_blobs, re.I)
    if mt:
        transmission = mt.group(1).lower()

    # location
    location = {"country": "", "region": "", "city": "", "zip": "", "address": ""}
    loc_el = s.find(text=re.compile(r"Location:", re.I))
    if loc_el:
        loc_text = loc_el.strip()
        mloc = re.search(r"Location:\s*(.+)", loc_text)
        if mloc:
            full_loc = mloc.group(1)
            parts = [p.strip() for p in re.split(r",|\n", full_loc) if p.strip()]
            if len(parts) == 1:
                location["city"] = parts[0]
            elif len(parts) >= 2:
                location["city"] = parts[0]
                location["region"] = parts[1]
                if len(parts) >= 3:
                    location["country"] = parts[2]

    imgs = []
    for img in s.select("img"):
        src = img.get("src") or img.get("data-src") or ""
        if not src.startswith("http"):
            continue
        url_no_q = src.split("?", 1)[0].lower()
        is_photo = url_no_q.endswith((".jpg", ".jpeg", ".webp"))
        is_theme_asset = "/themes/" in url_no_q or url_no_q.endswith(".svg")
        if is_photo and not is_theme_asset:
            if "fit=144" in src or "resize=235" in src:
                continue
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

    # respectă pauza între request-uri dacă ai setat
    if PAUSE_BETWEEN_REQUESTS:
        try:
            time.sleep(PAUSE_BETWEEN_REQUESTS)
        except Exception:
            pass

    return {
        "title": title,
        "brand": brand,
        "model": model,
        "year": year or "",
        "vin": vin,
        "mileage": mileage,
        "transmission": transmission,
        "images": imgs,
        "url": url,
        "description": desc,
        "location": location,
    }
