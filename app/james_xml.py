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


# Brand-uri comune – ajută să nu ajungă model gol
KNOWN_BRANDS = [
    "Aston Martin", "Mercedes-Benz", "Rolls-Royce", "Land Rover",
    "Volkswagen", "Chevrolet", "Porsche", "Ferrari", "Lamborghini",
    "Bentley", "Cadillac", "Studebaker", "Toyota", "Jaguar", "Dodge",
    "BMW", "Ford", "Jeep", "Audi", "Ural",
]


def extract_brand_model_year(title: str):
    """
    Returnează (year, brand, model) non-empty dacă există titlu.
    Fallback sigur pentru model: titlul complet (ca să nu pice JamesEdition).
    """
    if not title:
        return "", "", ""

    title = title.strip()

    # year
    ym = re.search(r"\b(19\d{2}|20\d{2})\b", title)
    year = ym.group(1) if ym else ""

    # brand: caută un brand cunoscut în titlu
    brand = ""
    for b in sorted(KNOWN_BRANDS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(b)}\b", title):
            brand = b
            break

    # dacă nu găsim brand, luăm primul cuvânt (fallback)
    if not brand:
        brand = title.split()[0] if title.split() else ""

    # model: ce urmează după brand (curățat)
    model = ""
    if brand and brand in title:
        after = title.split(brand, 1)[1].strip(" -")
        after = re.sub(r"\s{2,}", " ", after).strip()

        # taie niște sufixe comune care poluează modelul (dar nu-l lăsa gol)
        cut = re.split(
            r"\b(Automatic|Manual|Dual-Clutch|CVT|Tiptronic|S-Tronic|DSG)\b",
            after,
            1,
            flags=re.I
        )[0].strip(" -")
        model = cut or after

    # fallback: niciodată model gol
    if not model:
        model = title

    # curățare minimă
    model = re.sub(r"\s{2,}", " ", model).strip()

    return year, brand, model


def _safe_reference(it: dict, year: str, brand: str, model: str) -> str:
    """
    Creează un reference INTERN:
    - FARA URL-uri
    - stabil între rulări
    - text simplu (acceptat de JamesEdition)
    """
    # 1) cel mai bun: external_id din inventory (stabil)
    ref = _txt(it.get("external_id"))

    # 2) dacă nu există, folosește url ca sursă doar pentru un ID, nu păstrăm URL-ul
    # ex: .../listing/1992-ford-mustang-54 -> bat-1992-ford-mustang-54
    if not ref:
        url = _txt(it.get("url"))
        m = re.search(r"/listing/([^/]+)/?$", url)
        if m:
            ref = f"JE-{m.group(1)}"
        else:
            ref = f"JE-{year}-{brand}-{model}"

    # 3) curăță orice URL care a ajuns cumva în ref
    ref = re.sub(r"https?://\S+", "", ref)

    # 4) normalizează caractere (fără diacritice/simboluri ciudate)
    ref = re.sub(r"[^A-Za-z0-9 _\-]+", "", ref).strip()

    # 5) limită rezonabilă
    if len(ref) > 80:
        ref = ref[:80].rstrip()

    # fallback final
    if not ref:
        ref = f"JE-{uuid.uuid4().hex[:12]}"

    return ref


def build_james_xml(items: list) -> bytes:
    if not JE_DEALER_ID or not JE_DEALER_NAME:
        raise SystemExit("JE_DEALER_ID and JE_DEALER_NAME are required.")

    # inventory stateful
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

        # year/brand/model robust (niciodată model gol)
        year, brand, model = extract_brand_model_year(title)
        if not (year and brand and model):
            # foarte rar, dar păstrăm strict
            continue

        # reference INTERN curat (fără link BAT)
        ref = _safe_reference(it, year, brand, model)

        adv = SubElement(adverts, "advert", {
            "reference": ref,
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

        loc_in = it.get("location") or {}
        if not isinstance(loc_in, dict):
            loc_in = {}

        # location: JamesEdition nu vrea complet gol
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
