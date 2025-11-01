from xml.etree.ElementTree import Element, SubElement, tostring
import datetime as dt
import uuid
from .config import FEED_VERSION, FEED_REFERENCE, FEED_TITLE, JE_DEALER_ID, JE_DEALER_NAME

def _empty(tag, parent):
    el = SubElement(parent, tag)
    el.text = ""
    return el

def _txt(val: str) -> str:
    return "" if val is None else str(val)

def build_james_xml(items: list) -> bytes:
    if not JE_DEALER_ID or not JE_DEALER_NAME:
        raise SystemExit("JE_DEALER_ID and JE_DEALER_NAME are required env vars.")

    # Root must be jameslist_feed (per JamesEdition guidelines)
    root = Element("jameslist_feed", {"version": _txt(FEED_VERSION)})

    # feed_information
    fi = SubElement(root, "feed_information")
    SubElement(fi, "reference").text = _txt(FEED_REFERENCE)
    SubElement(fi, "title").text = _txt(FEED_TITLE)
    now = dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    SubElement(fi, "description").text = "Automated import of unsold Bring a Trailer lots (for our inventory)"
    SubElement(fi, "created").text = now
    SubElement(fi, "updated").text = now

    # dealer
    dealer = SubElement(root, "dealer")
    SubElement(dealer, "id").text = _txt(JE_DEALER_ID)
    SubElement(dealer, "name").text = _txt(JE_DEALER_NAME)

    # adverts
    adverts = SubElement(root, "adverts")
    for it in items or []:
        adv = SubElement(adverts, "advert", {
            "reference": str(uuid.uuid4()),
            "category": "car"
        })

        # required, generic
        SubElement(adv, "preowned").text = "yes"
        SubElement(adv, "type").text = "sale"

        # core vehicle fields (required)
        SubElement(adv, "brand").text = _txt(it.get("brand", ""))
        SubElement(adv, "model").text = _txt(it.get("model", ""))
        SubElement(adv, "year").text = _txt(it.get("year", ""))

        # price: POR=yes + present <price .../> (empty)
        SubElement(adv, "price_on_request").text = "yes"
        price = SubElement(adv, "price", {"currency": "USD", "vat_included": "VAT Excluded"})
        price.text = ""

        # location 
loc_data = it.get("location", {}) or {}
loc = SubElement(adv, "location")
SubElement(loc, "country").text = loc_data.get("country", "")
SubElement(loc, "region").text = loc_data.get("region", "")
SubElement(loc, "city").text = loc_data.get("city", "")
SubElement(loc, "zip").text = loc_data.get("zip", "")
SubElement(loc, "address").text = loc_data.get("address", "")


        # headline (required) + description
        SubElement(adv, "headline").text = _txt(it.get("title", ""))
        SubElement(adv, "description").text = _txt(it.get("description", ""))

        # media structure: media/image/image_url
        media = SubElement(adv, "media")
        for im in (it.get("images") or [])[:40]:
            img = SubElement(media, "image")
            SubElement(img, "image_url").text = _txt(im)

        # optional extras (cars-specific) can be added later:
        # if it.get("vin"): SubElement(adv, "vin").text = _txt(it["vin"])
        # if it.get("mileage"): SubElement(adv, "mileage").text = _txt(it["mileage"])

    return tostring(root, encoding="utf-8")
