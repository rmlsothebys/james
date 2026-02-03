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


def _txt(val) -> str:
    return "" if val is None else str(val)


def _add_text(parent, tag, text=""):
    el = SubElement(parent, tag)
    el.text = _txt(text)
    return el


def _parse_year_brand_model(title: str):
    """
    Derivă (year, brand, model) din titlu.
    Ex: "1969 Chevrolet Camaro ..." -> (1969, Chevrolet, Camaro)
    """
    if not title:
        return ("", "", "")

    m = re.search(r"\b(19\d{2}|20\d{2})\b", title)
    if not m:
        return ("", "", "")
    year = m.group(1)

    after = title[m.end():].strip()
    parts = re.split(r"\s+", after)

    brand = parts[0] if len(parts) >= 1 else ""
    model = parts[1] if len(parts) >= 2 else ""

    brand = re.sub(r"[^A-Za-z0-9\-]+", "", brand)
    model = re.sub(r"[^A-Za-z0-9\-]+", "", model)

    return (year, brand, model)


def _reference_from_title(title: str) -> str:
    """
    Internal Reference = DOAR titlul.
    Curățăm caracterele problematice și limităm lungimea.
    """
    if not title:
        return str(uuid.uuid4())

    ref = title.strip()

    # păstrează litere/cifre/spații/cratimă/apostrof (și apostrof tipografic)
    ref = re.sub(r"[^\w\s\-’']", "", ref)

    # normalizează spațiile
    ref = re.sub(r"\s+", " ", ref).strip()

    # limită safe
    return ref[:120] if ref else str(uuid.uuid4())


def build_james_xml(items: list) -> bytes:
    if not JE_DEALER_ID or not JE_DEALER_NAME:
        raise SystemExit("JE_DEALER_ID and JE_DEALER_NAME are required env vars.")

    # --- STATEFUL INVENTORY ---
    inv = load_inventory()
    inv = upsert_bat_cars(inv, items or [])
    save_inventory(inv)

    # feed din tot inventory activ
    items = [x for x in inv.values() if x.get("status") == "active"]

    # ROOT
    root = Element("jameslist_feed", {"version": _txt(FEED_VERSION or "3.0")})

    # feed_information
    fi = SubElement(root, "feed_information")
    _add_text(fi, "reference", FEED_REFERENCE or "BAT-unsold")
    _add_text(fi, "title", FEED_TITLE or "BaT Unsold importer")
    now = dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    _add_text(fi, "description", "Automated import of unsold Bring a Trailer lots (for our inventory)")
    _add_text(fi, "created", now)
    _add_text(fi, "updated", now)

    # dealer
    dealer = SubElement(root, "dealer")
    _add_text(dealer, "id", JE_DEALER_ID)
    _add_text(dealer, "name", JE_DEALER_NAME)

    # adverts
    adverts = SubElement(root, "adverts")

    for it in (items or []):
        title = it.get("title", "") or ""

        # brand/model/year
        year = _txt(it.get("year", "")).strip()
        brand = _txt(it.get("brand", "")).strip()
        model = _txt(it.get("model", "")).strip()

        # dacă lipsesc, derivă din titlu
        if not (year and brand and model):
            y2, b2, m2 = _parse_year_brand_model(title)
            year = year or y2
            brand = brand or b2
            model = model or m2

        # dacă tot lipsesc, sărim
        if not (year and brand and model):
            continue

        # location
        loc_in = it.get("location") or {}
        if not isinstance(loc_in, dict):
            loc_in = {}

        country = loc_in.get("country") or "United States"
        region = loc_in.get("region") or ""
        city = loc_in.get("city") or ""
        zipc = loc_in.get("zip") or ""
        address = loc_in.get("address") or ""

        # Internal Reference = titlul (fără BAT / fără URL)
        ref = _reference_from_title(title)

        adv = SubElement(adverts, "advert", {"reference": _txt(ref), "category": "car"})

        # required generic
        _add_text(adv, "preowned", "yes")
        _add_text(adv, "type", "sale")

        # required core fields
        _add_text(adv, "brand", brand)
        _add_text(adv, "model", model)
        _add_text(adv, "year", year)

        # price
        _add_text(adv, "price_on_request", "yes")
        price = SubElement(adv, "price", {"currency": "USD", "vat_included": "VAT Excluded"})
        price.text = ""

        # location tags
        loc = SubElement(adv, "location")
        _add_text(loc, "country", country)
        _add_text(loc, "region", region)
        _add_text(loc, "city", city)
        _add_text(loc, "zip", zipc)
        _add_text(loc, "address", address)

        # headline + description
        _add_text(adv, "headline", title)
        _add_text(adv, "description", it.get("description", "") or "")

        # dacă NU vrei link către BAT în listing deloc, spune-mi și îl scot
        _add_text(adv, "url", it.get("url", "") or "")

        # media
        media = SubElement(adv, "media")
        for im in (it.get("images") or [])[:40]:
            img = SubElement(media, "image")
            _add_text(img, "image_url", im)

    xml_body = tostring(root, encoding="utf-8")
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + xml_body
