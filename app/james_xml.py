from xml.etree.ElementTree import Element, SubElement, tostring
import datetime as dt
import re
import uuid
import hashlib

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


def _slug_ref(title: str) -> str:
    """
    JamesEdition: advert@reference trebuie sa fie VarChar (a-z, A-Z, 0-9, _-)
    Deci facem o versiune "ca titlul", dar fara spatii / caractere speciale.
    """
    if not title:
        return "listing"
    t = title.strip()
    t = t.replace("&", "and")
    # spatii -> underscore
    t = re.sub(r"\s+", "_", t)
    # pastreaza doar A-Z a-z 0-9 _ -
    t = re.sub(r"[^A-Za-z0-9_-]+", "", t)
    # evita ref prea scurt
    return t[:120] if t else "listing"


def _unique_suffix(seed: str) -> str:
    if not seed:
        seed = str(uuid.uuid4())
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8]


def _parse_year_brand_model_from_title(title: str):
    """
    Încearcă să derive (year, brand, model) din titlu.
    Ex:
      "1973.5 Porsche 911T Targa 5-Speed" -> year=1973, brand=Porsche, model="911T Targa 5-Speed"
      "Fuel-Injected 1980 Jeep Wagoneer Limited" -> year=1980, brand=Jeep, model="Wagoneer Limited"
    """
    if not title:
        return ("", "", "")

    # year: 4 digits
    m = re.search(r"\b(19\d{2}|20\d{2})\b", title)
    if not m:
        return ("", "", "")

    year = m.group(1)

    after = title[m.end():].strip()

    # scoate prefixe gen ".5" sau "-" imediat dupa an
    after = re.sub(r"^[\.\-_/\\]+", "", after).strip()
    after = re.sub(r"^\d+\b", "", after).strip()  # dacă începe cu "5" etc.

    parts = re.split(r"\s+", after)
    if not parts:
        return (year, "", "")

    brand = parts[0].strip()
    model = " ".join(parts[1:]).strip()

    # curăță brand/model de caractere ciudate la margini
    brand = re.sub(r"^[^A-Za-z0-9]+|[^A-Za-z0-9]+$", "", brand)
    model = re.sub(r"\s{2,}", " ", model)

    # fallback: dacă model e gol, pune brand (ca să nu fie blank)
    if not model:
        model = brand

    return (year, brand, model)


def build_james_xml(items: list) -> bytes:
    if not JE_DEALER_ID or not JE_DEALER_NAME:
        raise SystemExit("JE_DEALER_ID and JE_DEALER_NAME are required env vars.")

    # --- inventory stateful ---
    inv = load_inventory()
    inv = upsert_bat_cars(inv, items or [])
    save_inventory(inv)

    # feed-ul se generează din TOT inventory activ
    inventory_items = [x for x in inv.values() if x.get("status") == "active"]

    # root
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
    # Atenție: în guideline apare <reference> și <name> și <id> (au avut mici inconsistențe în tabel),
    # dar în practică setup-ul tău merge cu id+name. Le păstrăm.
    _add_text(dealer, "id", JE_DEALER_ID)
    _add_text(dealer, "name", JE_DEALER_NAME)

    adverts = SubElement(root, "adverts")

    for rec in inventory_items:
        # datele reale sunt în rec["raw"] (din scraper)
        src = rec.get("raw") if isinstance(rec.get("raw"), dict) else rec

        title = _txt(src.get("title") or rec.get("title") or "").strip()
        if not title:
            # fără titlu = nu merită să riscăm reject
            continue

        # brand/model/year: încearcă din src, altfel din titlu
        year = _txt(src.get("year") or "").strip()
        brand = _txt(src.get("brand") or "").strip()
        model = _txt(src.get("model") or "").strip()

        if not (year and brand and model):
            y2, b2, m2 = _parse_year_brand_model_from_title(title)
            year = year or y2
            brand = brand or b2
            model = model or m2

        # dacă încă lipsesc, oprim (altfel JamesEdition dă fail “Model can’t be blank” / etc.)
        if not (year and brand and model):
            continue

        # imagini: media/image_url e REQUIRED → dacă n-avem imagini, mai bine sărim anunțul
        images = src.get("images") or rec.get("images") or []
        images = [u for u in images if isinstance(u, str) and u.startswith("http")]
        if not images:
            continue
        images = images[:40]

        # location: required tags (pot fi empty-closed, dar e mai bine să avem măcar country)
        loc_in = src.get("location") if isinstance(src.get("location"), dict) else {}
        country = _txt(loc_in.get("country") or "United States")
        region = _txt(loc_in.get("region") or "")
        city = _txt(loc_in.get("city") or "")
        zipc = _txt(loc_in.get("zip") or "")
        address = _txt(loc_in.get("address") or "")

        # reference: “ca titlul”, dar respectă charset + unic
        # IMPORTANT: nu mai punem BAT link.
        seed = _txt(rec.get("external_id") or src.get("url") or title)
        ref = f"{_slug_ref(title)}-{_unique_suffix(seed)}"

        adv = SubElement(adverts, "advert", {"reference": ref, "category": "car"})

        # required generic
        _add_text(adv, "preowned", "yes")
        _add_text(adv, "type", "sale")

        _add_text(adv, "brand", brand)
        _add_text(adv, "model", model)
        _add_text(adv, "year", year)

        # price_on_request=yes => <price ...></price> trebuie prezent chiar dacă gol
        _add_text(adv, "price_on_request", "yes")
        price = SubElement(adv, "price", {"currency": "USD", "vat_included": "VAT Excluded"})
        price.text = ""

        # location (required)
        loc = SubElement(adv, "location")
        _add_text(loc, "country", country)
        _add_text(loc, "region", region)
        _add_text(loc, "city", city)
        _add_text(loc, "zip", zipc)
        _add_text(loc, "address", address)

        _add_text(adv, "headline", title)

        # description optional (dar util)
        desc = _txt(src.get("description") or rec.get("description") or "")
        _add_text(adv, "description", desc)

        # IMPORTANT: scoatem complet <url> ca să nu mai apară link-ul BAT în JamesEdition
        # (tag-ul nu este required în generic fields)

        # media (required)
        media = SubElement(adv, "media")
        for im in images:
            img = SubElement(media, "image")
            _add_text(img, "image_url", im)

        # (opțional cars-specific – dacă vrei, putem adăuga ulterior)
        # if src.get("vin"):
        #     _add_text(adv, "vin", src.get("vin"))
        # if src.get("mileage"):
        #     mileage = SubElement(adv, "mileage", {"unit": "mi"})
        #     mileage.text = _txt(src.get("mileage"))

    xml_body = tostring(root, encoding="utf-8")
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + xml_body
