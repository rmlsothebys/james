from xml.etree.ElementTree import Element, SubElement, tostring
import datetime as dt
import uuid

from .inventory import load_inventory, save_inventory, upsert_bat_cars  # <-- ADAUGĂ ASTA

# importă din config valorile necesare
from .config import (
    FEED_VERSION,
    FEED_REFERENCE,
    FEED_TITLE,
    JE_DEALER_ID,
    JE_DEALER_NAME,
)

def _txt(val) -> str:
    """Convertește în string și elimină None."""
    return "" if val is None else str(val)

def _add_text(parent, tag, text=""):
    el = SubElement(parent, tag)
    el.text = _txt(text)
    return el

def build_james_xml(items: list) -> bytes:
    """
    Construcție feed JamesEdition (Cars) conform ghidului:
    - Rădăcină: <jameslist_feed version="3.0">
    - Secțiuni: feed_information, dealer, adverts/advert(category="car")
    - Câmpuri required într-un <advert> (cel puțin): preowned, type, brand, model, year,
      price_on_request, price (prezent chiar dacă gol), location (country/region/city/zip/address),
      headline, media/image/image_url.
    """
    if not JE_DEALER_ID or not JE_DEALER_NAME:
        raise SystemExit("JE_DEALER_ID and JE_DEALER_NAME are required env vars.")

    # --- STATEFUL INVENTORY (nu mai pierdem masinile intre rulări) ---
    inv = load_inventory()
    inv = upsert_bat_cars(inv, items or [])
    save_inventory(inv)

    # Generăm feed-ul din TOT inventory-ul activ, nu doar din ce am găsit azi
    items = [x for x in inv.values() if x.get("status") == "active"]

    # 1) root
    root = Element("jameslist_feed", {"version": _txt(FEED_VERSION or "3.0")})

    # 2) feed_information
    fi = SubElement(root, "feed_information")
    _add_text(fi, "reference", FEED_REFERENCE or "BAT-unsold")
    _add_text(fi, "title", FEED_TITLE or "BaT Unsold importer")
    now = dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    _add_text(fi, "description", "Automated import of unsold Bring a Trailer lots (for our inventory)")
    _add_text(fi, "created", now)
    _add_text(fi, "updated", now)

    # 3) dealer
    dealer = SubElement(root, "dealer")
    _add_text(dealer, "id", JE_DEALER_ID)
    _add_text(dealer, "name", JE_DEALER_NAME)

    # 4) adverts
    adverts = SubElement(root, "adverts")

    for it in (items or []):
        # asigură-te că avem dict pentru location
        loc_in = it.get("location") or {}
        if not isinstance(loc_in, dict):
            loc_in = {}

        # reference STABIL (altfel JamesEdition vede anunturi noi la fiecare run)
        ref = (
            it.get("external_id")  # cel mai bun (din inventory)
            or (f"BAT-{it.get('id')}" if it.get("id") else None)  # dacă ai id BAT
            or it.get("url")  # fallback stabil dacă ai URL
            or str(uuid.uuid4())  # ultim fallback
        )

        adv = SubElement(adverts, "advert", {
            "reference": _txt(ref),
            "category": "car",
        })


        # required generic
        _add_text(adv, "preowned", "yes")
        _add_text(adv, "type", "sale")

        # required core vehicle fields
        _add_text(adv, "brand", it.get("brand", ""))
        _add_text(adv, "model", it.get("model", ""))
        _add_text(adv, "year", it.get("year", ""))

        # price block: POR=yes + <price .../> prezent chiar dacă gol
        _add_text(adv, "price_on_request", "yes")
        price = SubElement(adv, "price", {"currency": "USD", "vat_included": "VAT Excluded"})
        price.text = ""  # empty-closed

        # required location: toate cele 5 tag-uri trebuie să existe
        loc = SubElement(adv, "location")
        _add_text(loc, "country", loc_in.get("country", ""))
        _add_text(loc, "region",  loc_in.get("region", ""))
        _add_text(loc, "city",    loc_in.get("city", ""))
        _add_text(loc, "zip",     loc_in.get("zip", ""))
        _add_text(loc, "address", loc_in.get("address", ""))

        # headline (required) + description
        _add_text(adv, "headline", it.get("title", ""))
        _add_text(adv, "description", it.get("description", ""))

        # media: image/image_url (doar URL-urile deja filtrate în scraper)
        media = SubElement(adv, "media")
        for im in (it.get("images") or [])[:40]:
            img = SubElement(media, "image")
            _add_text(img, "image_url", im)

        # (opțional) câmpuri cars-specific se pot adăuga ulterior:
        # if it.get("vin"): _add_text(adv, "vin", it["vin"])
        # if it.get("mileage"): _add_text(adv, "mileage", it["mileage"])
        # if it.get("transmission"): _add_text(adv, "gearbox", it["transmission"])

    return tostring(root, encoding="utf-8")
