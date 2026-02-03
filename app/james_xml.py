from xml.etree.ElementTree import Element, SubElement, tostring
import datetime as dt
import uuid
import re

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


KNOWN_BRANDS = [
    "Porsche", "Chevrolet", "Aston", "Aston Martin", "Mercedes-Benz",
    "BMW", "Ferrari", "Lamborghini", "Volkswagen", "Land Rover",
    "Toyota", "Ford", "Jeep", "Audi", "Jaguar", "Bentley",
    "Rolls-Royce", "Cadillac", "Dodge", "Studebaker", "Ural"
]


def extract_brand_model_year(title: str):
    """
    Returnează (year, brand, model) GARANTAT non-empty dacă există titlu.
    """
    if not title:
        return "", "", ""

    title = title.strip()

    # year
    ym = re.search(r"\b(19\d{2}|20\d{2})\b", title)
    year = ym.group(1) if ym else ""

    # brand
    brand = ""
    for b in sorted(KNOWN_BRANDS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(b)}\b", title):
            brand = b
            break

    # model
    model = ""

    if brand:
        after = title.split(brand, 1)[1].strip(" -")
        # taie marketing / transmisii
        after = re.split(
            r"\b(Speed|Manual|Automatic|Coupe|Cabriolet|Targa|Sedan|Roadster)\b",
            after,
            1
        )[0]
        model = after.strip(" -")

    # fallback sigur (IMPORTANT pentru JamesEdition)
    if not model:
        model = title

    return year, brand or title.split()[0], model


def build_james_xml(items: list) -> bytes:
    if not JE_DEALER_ID or not JE_DEALER_NAME:
        raise SystemExit("JE_DEALER_ID and JE_DEALER_NAME are required.")

    inv = load_inventory()
    inv = upsert_bat_cars(inv, items or [])
    save_inventory(inv)

    items = [x for x in inv.values() if x.get("status") == "active"]

    root = Element("jameslist_feed", {"version": FEED_VERSION or "3.0"})

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

        year, brand, model = extract_brand_model_year(title)

        # SIGURANȚĂ ABSOLUTĂ (JamesEdition)
        if not (year and brand and model):
            continue

        adv = SubElement(adverts, "advert", {
            "reference": _txt(it.get("external_id") or uuid.uuid4()),
            "category": "car"
        })

        _add(adv, "preowned", "yes")
        _add(adv, "type", "sale")

        _add(adv, "brand", brand)
        _add(adv, "model", model)
        _add(adv, "year", year)

        _add(adv, "price_on_request", "yes")
        SubElement(adv, "price", {
            "currency": "USD",
            "vat_included": "VAT Excluded"
        }).text = ""

        loc = it.get("location") or {}
        l = SubElement(adv, "location")
        _add(l, "country", loc.get("country") or "United States")
        _add(l, "region", loc.get("region", ""))
        _add(l, "city", loc.get("city", ""))
        _add(l, "zip", loc.get("zip", ""))
        _add(l, "address", loc.get("address", ""))

        _add(adv, "headline", title)
        _add(adv, "description", it.get("description", ""))
        _add(adv, "url", it.get("url", ""))

        media = SubElement(adv, "media")
        for img in (it.get("images") or [])[:40]:
            i = SubElement(media, "image")
            _add(i, "image_url", img)

    xml = tostring(root, encoding="utf-8")
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + xml
