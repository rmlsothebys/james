import re
import time
import asyncio
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from .config import USER_AGENT, BASE, UNSOLD_URL, MAX_LISTINGS, PAUSE_BETWEEN_REQUESTS

HEADERS = {"User-Agent": USER_AGENT}


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


async def _collect_listing_links_dynamic(target: int) -> list:
    """
    Colectează link-uri din "All Completed Auctions" prin "Show more"/scroll.
    Folosește Playwright doar pentru results page (dinamic).
    Returnează o listă de URL-uri absolute către /listing/...
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(
            extra_http_headers={"User-Agent": USER_AGENT}
        )

        await page.goto(UNSOLD_URL, wait_until="domcontentloaded", timeout=45000)

        urls = []
        clicks = 0
        max_clicks = 80  # suficient pentru 200-300 rezultate

        while len(urls) < target and clicks < max_clicks:
            hrefs = await page.eval_on_selector_all(
                "a[href*='/listing/']",
                "els => els.map(e => e.href)"
            )

            cleaned = []
            for h in hrefs or []:
                if not h:
                    continue
                h = h.split("#")[0].split("?")[0].rstrip("/")
                if "/listing/" in h:
                    cleaned.append(h)

            urls = _uniq(urls + cleaned)

            if len(urls) >= target:
                break

            # încearcă să apese butonul "Show More" (dacă există)
            clicked = False
            for sel in [
                "text=Show More",
                "text=Show more",
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

            # fallback: scroll (declanșează loading)
            if not clicked:
                try:
                    await page.mouse.wheel(0, 2500)
                except Exception:
                    pass

            await page.wait_for_timeout(1200)
            clicks += 1

        await browser.close()

        # uneori page dă relative; normalizează pe BASE
        out = []
        for u in urls[:target]:
            if u.startswith("http"):
                out.append(u)
            else:
                out.append(urljoin(BASE, u))
        return out


def parse_unsold_index():
    """
    Returnează MAX_LISTINGS link-uri (200-300) din All Completed Auctions.
    """
    target = int(MAX_LISTINGS or 300)
    try:
        links = asyncio.run(_collect_listing_links_dynamic(target=target))
        return links[:target]
    except Exception:
        # fallback: vechiul comportament (doar ce e în HTML static)
        first = fetch(UNSOLD_URL)
        soup = BeautifulSoup(first, "lxml")
        links = []
        for a in soup.select('a[href*="/listing/"]'):
            href = a.get("href")
            if href and "/listing/" in href:
                href = href.split("?")[0]
                href = urljoin(BASE, href)
                if href not in links:
                    links.append(href)
        return links[:target]


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
