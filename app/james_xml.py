from xml.etree.ElementTree import Element, SubElement, tostring
import datetime as dt
import re
import uuid

from .inventory import load_inventory, save_inventory, upsert_bat_cars
from .config import (
    FEED_VERSION,
    FEED_REFERENCE,
    FEED_TITLE,
    JE_DEALER_ID,
    JE_DEALER_NAME,
)

def _txt(v):
    return "" if v is None else str(v).strip()

def _add(parent, tag, value=""):
    el = SubElement(parent, tag)
    el.text = _txt(value)
    return el

# Brand list (poți extinde)
KNOWN_BRANDS = [
    "Aston Martin", "Mercedes-Benz", "Rolls-Royce", "Land Rover",
    "Volkswagen", "Chevrolet", "Porsche", "Ferrari", "Lamborghini",
    "Bentley", "Cadillac", "Studebaker", "Toyota", "Jaguar", "Dodge",
    "BMW", "Ford", "Jeep", "Audi", "Ural", "Honda", "Nissan", "Mazda",
    "Subaru", "Kia", "Hyundai", "Volvo", "Mini", "McLaren", "Lotus",
    "Maserati", "Alfa Romeo", "Fiat", "Peugeot", "Renault", "Saab",
    "Lincoln", "Buick", "GMC", "Pontiac", "Chrysler", "Acura", "Lexus",
    "Infiniti", "Genesis"
]

def _find_year(title: str) -> str:
    m = re.search(r"\b(19\d{2}|20\d{2})\b", title or "")
    return m.group(1) if m else ""

def _find_brand(title: str) -> str:
    t = title or ""
    for b in sorted(KNOWN_BRANDS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(b)}\b", t):
            return b
    return ""

def _extract_brand_model_year(title: str):
    """
    Returnează (year, brand, model) cu model garantat non-empty.
    """
    title = (title or "").strip()
    if not title:
        return "", "", ""

    year = _find_year(title)
    if not year:
        return "", "", ""  # JE cere year, deci fără year nu trimitem

    brand = _find_brand(title)

    # fallback brand: primul cuvânt după year
    if not brand:
        after_year = title.split(year, 1)[1].strip(" -")
        parts = after_year.split()
        brand = parts[0] if parts else "Unknown"

    # model = ce rămâne după "year + brand"
    # încercăm să scoatem partea de început până la brand inclusiv
    model = ""
    if brand in title:
        model = title.split(brand, 1)[1].strip(" -")
    else:
        # dacă brand e fallback și nu apare exact în title (rar), scoatem după year
        model = title.split(year, 1)[1].strip(" -")
        # scoate brand fallback din început
        if model.lower().startswith(brand.lower()):
            model = model[len(brand):].strip(" -")

    # curățare minimală
    model = re.sub(r"\s{2,}", " ", model).strip()

    # FINAL SAFETY NET: model nu are voie să fie gol
    if not model:
        model = "Unknown"

    return year, brand, model

def build_james_xml(items: list) -> bytes:
    if not JE_DEALER_ID or not JE_DEALER_NAME:
        raise SystemExit("JE_DEALER_ID and JE_DEALER_NAME are required env vars.")

    inv = load_inventory()
    inv = upsert_bat_cars(inv, items or [])
    save_inventory(inv)

    items = [x for x in inv.values() if x.get("status") == "active"]

    root = Element("jameslist_feed", {"version": _txt(FEED_VERSION or "3.0")})

    fi = SubElement(root, "feed_information")
    _add(fi, "reference", FEED_REFERENCE or "BAT-unsold")
    _add(fi, "title", FEED_TITLE or "BaT Unsold importer")
    now = dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    _add(fi, "description", "Automated import of unsold Bring a Trailer lots")
    _add(fi, "created", now)
    _add(fi, "updated", now)

    dealer = SubElement(root, "dealer")
    _add(dealer, "id", JE_DEALER_ID)
    _add(dealer, "name", JE_DEALER_NAME)

    adverts = SubElement(root, "adverts")

    for it in items:

        title = _txt(it.get("title"))
        raw = it.get("raw") or {}

        # Preferăm câmpurile extrase din pagină (scraper.py),
        # NU derivări din titlu.
        year = _txt(raw.get("year"))
        brand = _txt(raw.get("brand"))
        model = _txt(raw.get("model"))

        # fallback-uri (rar) – doar dacă pagina nu a livrat câmpurile
        if not year or not brand or not model:
            y2, b2, m2 = _extract_brand_model_year(title)
            year = year or y2
            brand = brand or b2
            model = model or m2

        if not year:
            continue  # nu putem fără year

        # reference stabil: NU schimbăm brusc identitatea
        ref = _txt(it.get("je_reference")) or _txt(it.get("external_id")) or _txt(it.get("url"))
        if not ref:
            ref = f"JE-{uuid.uuid4().hex[:12]}"

        adv = SubElement(adverts, "advert", {"reference": ref, "category": "car"})

        _add(adv, "preowned", "yes")
        _add(adv, "type", "sale")

        _add(adv, "brand", brand)
        _add(adv, "model", model)  # GARANTAT non-empty
        _add(adv, "year", year)

        _add(adv, "price_on_request", "yes")
        SubElement(adv, "price", {"currency": "USD", "vat_included": "VAT Excluded"}).text = ""

        loc_in = it.get("location") or {}
        if not isinstance(loc_in, dict):
            loc_in = {}

        loc = SubElement(adv, "location")
        _add(loc, "country", _txt(loc_in.get("country")) or "United States")
        _add(loc, "region", _txt(loc_in.get("region")))
        _add(loc, "city", _txt(loc_in.get("city")))
        _add(loc, "zip", _txt(loc_in.get("zip")))
        _add(loc, "address", _txt(loc_in.get("address")))

        _add(adv, "headline", title)
        _add(adv, "description", _txt(it.get("description")))
        _add(adv, "url", _txt(it.get("url")))

        media = SubElement(adv, "media")
        for im in (it.get("images") or [])[:40]:
            img = SubElement(media, "image")
            _add(img, "image_url", im)

    xml = tostring(root, encoding="utf-8")
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + xml
