from xml.etree.ElementTree import Element, SubElement, tostring
import datetime as dt
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
    "Aston Martin", "Mercedes-Benz", "Rolls-Royce", "Land Rover",
    "Volkswagen", "Chevrolet", "Porsche", "Ferrari", "Lamborghini",
    "Bentley", "Cadillac", "Studebaker", "Toyota", "Jaguar", "Dodge",
    "BMW", "Ford", "Jeep", "Audi", "Ural",
]


def extract_year(title: str) -> str:
    m = re.search(r"\b(19\d{2}|20\d{2})\b", title or "")
    return m.group(1) if m else ""


def extract_brand_model(title: str):
    """
    Brand/model robuste: niciodată model gol.
    """
    title = (title or "").strip()
    if not title:
        return "", ""

    brand = ""
    for b in sorted(KNOWN_BRANDS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(b)}\b", title):
            brand = b
            break
    if not brand:
        brand = title.split()[0] if title.split() else "Unknown"

    model = ""
    if brand and brand in title:
        after = title.split(brand, 1)[1].strip(" -")
        after = re.sub(r"\s{2,}", " ", after).strip()
        model = after

    # fallback final: model = titlu
    if not model:
        model = title

    model = re.sub(r"\s{2,}", " ", model).strip()
    return brand, model


def build_james_xml(items: list) -> bytes:
    if not JE_DEALER_ID or not JE_DEALER_NAME:
        raise SystemExit("JE_DEALER_ID and JE_DEALER_NAME are required env vars.")

    # stateful inventory
    inv = load_inventory()
    inv = upsert_bat_cars(inv, items or [])
    save_inventory(inv)

    # feed din tot inventory activ
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
        year = _txt(it.get("year")) or extract_year(title)
        brand = _txt(it.get("brand"))
        model = _txt(it.get("model"))

        if not brand or not model:
            b2, m2 = extract_brand_model(title)
            brand = brand or b2
            model = model or m2

        # JamesEdition cere year -> dacă nu avem deloc year, nu putem trimite listingul
        if not year:
            # nu-l ștergem din inventory; doar nu-l trimitem până când apare year în titlu
            continue

        # reference stabil (NU schimbăm, altfel dispar listings)
        # je_reference e doar slug, fără URL.
        ref = _txt(it.get("je_reference")) or _txt(it.get("external_id"))
        if not ref:
            continue

        adv = SubElement(adverts, "advert", {"reference": ref, "category": "car"})

        _add(adv, "preowned", "yes")
        _add(adv, "type", "sale")

        _add(adv, "brand", brand)
        _add(adv, "model", model)  # garantat non-empty
        _add(adv, "year", year)

        _add(adv, "price_on_request", "yes")
        SubElement(adv, "price", {"currency": "USD", "vat_included": "VAT Excluded"}).text = ""

        loc_in = it.get("location") or {}
        if not isinstance(loc_in, dict):
            loc_in = {}

        country = _txt(loc_in.get("country")) or "United States"
        region = _txt(loc_in.get("region"))
        city = _txt(loc_in.get("city"))
        zipc = _txt(loc_in.get("zip"))
        address = _txt(loc_in.get("address"))

        loc = SubElement(adv, "location")
        _add(loc, "country", country)
        _add(loc, "region", region)
        _add(loc, "city", city)
        _add(loc, "zip", zipc)
        _add(loc, "address", address)

        _add(adv, "headline", title)
        _add(adv, "description", _txt(it.get("description")))
        _add(adv, "url", _txt(it.get("url")))

        media = SubElement(adv, "media")
        for im in (it.get("images") or [])[:40]:
            img = SubElement(media, "image")
            _add(img, "image_url", im)

    xml = tostring(root, encoding="utf-8")
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + xml
