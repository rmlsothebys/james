from xml.etree.ElementTree import Element, SubElement, tostring
import datetime as dt
import uuid

from .inventory import load_inventory, save_inventory, upsert_bat_cars, INVENTORY_PATH

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


def build_james_xml(items: list) -> bytes:
    if not JE_DEALER_ID or not JE_DEALER_NAME:
        raise SystemExit("JE_DEALER_ID and JE_DEALER_NAME are required env vars.")

    print("DEBUG build_james_xml received items:", len(items or []))

    inv = load_inventory()
    inv = upsert_bat_cars(inv, items or [])
    save_inventory(inv)

    print("DEBUG inventory path:", INVENTORY_PATH)
    print("DEBUG inventory size after upsert:", len(inv))

    items = [x for x in inv.values() if x.get("status") == "active"]

    root = Element("jameslist_feed", {"version": _txt(FEED_VERSION or "3.0")})

    fi = SubElement(root, "feed_information")
    _add_text(fi, "reference", FEED_REFERENCE or "BAT-unsold")
    _add_text(fi, "title", FEED_TITLE or "BaT Unsold importer")
    now = dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    _add_text(fi, "description", "Automated import of unsold Bring a Trailer lots (for our inventory)")
    _add_text(fi, "created", now)
    _add_text(fi, "updated", now)

    dealer = SubElement(root, "dealer")
    _add_text(dealer, "id", JE_DEALER_ID)
    _add_text(dealer, "name", JE_DEALER_NAME)

    adverts = SubElement(root, "adverts")

    for it in (items or []):
        loc_in = it.get("location") or {}
        if not isinstance(loc_in, dict):
            loc_in = {}

        ref = (
            it.get("external_id")
            or (f"BAT-{it.get('id')}" if it.get("id") else None)
            or it.get("url")
            or str(uuid.uuid4())
        )

        adv = SubElement(adverts, "advert", {"reference": _txt(ref), "category": "car"})

        _add_text(adv, "preowned", "yes")
        _add_text(adv, "type", "sale")

        _add_text(adv, "brand", it.get("brand", ""))
        _add_text(adv, "model", it.get("model", ""))
        _add_text(adv, "year", it.get("year", ""))

        _add_text(adv, "price_on_request", "yes")
        price = SubElement(adv, "price", {"currency": "USD", "vat_included": "VAT Excluded"})
        price.text = ""

        loc = SubElement(adv, "location")
        _add_text(loc, "country", loc_in.get("country", ""))
        _add_text(loc, "region", loc_in.get("region", ""))
        _add_text(loc, "city", loc_in.get("city", ""))
        _add_text(loc, "zip", loc_in.get("zip", ""))
        _add_text(loc, "address", loc_in.get("address", ""))

        _add_text(adv, "headline", it.get("title", ""))
        _add_text(adv, "description", it.get("description", ""))

        media = SubElement(adv, "media")
        for im in (it.get("images") or [])[:40]:
            img = SubElement(media, "image")
            _add_text(img, "image_url", im)

    xml_body = tostring(root, encoding="utf-8")
return b'<?xml version="1.0" encoding="UTF-8"?>\n' + xml_body
