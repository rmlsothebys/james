from xml.etree.ElementTree import Element, SubElement, tostring
import datetime as dt
import uuid
from .config import FEED_VERSION, FEED_REFERENCE, FEED_TITLE, JE_DEALER_ID, JE_DEALER_NAME

def _empty(tag, parent):
    el = SubElement(parent, tag)
    el.text = ""
    return el

def build_james_xml(items: list) -> bytes:
    if not JE_DEALER_ID or not JE_DEALER_NAME:
        raise SystemExit("JE_DEALER_ID and JE_DEALER_NAME are required env vars.")

    # 1) root: jameslist_feed (conform ghid)
    root = Element("jameslist_feed", {"version": FEED_VERSION})

    # 2) feed_information
    fi = SubElement(root, "feed_information")
    SubElement(fi, "reference").text = FEED_REFERENCE
    SubElement(fi, "title").text = FEED_TITLE
    now = dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    SubElement(fi, "description").text = "Automated import of unsold Bring a Trailer lots (for our inventory)"
    SubElement(fi, "created").text = now
    SubElement(fi, "updated").text = now

    # 3) dealer (id numeric + name) – exact ca în sample
    dealer = SubElement(root, "dealer")
    SubElement(dealer, "id").text = str(JE_DEALER_ID)
    SubElement(dealer, "name").text = JE_DEALER_NAME

    # 4) adverts / advert (category="car")
    adverts = SubElement(root, "adverts")
    for it in items:
        adv = SubElement(adverts, "advert", {
            "reference": str(uuid.uuid4()),
            "category": "car"
        })

        # câmpuri GENERICE obligatorii (pag. 6–7)
        SubElement(adv, "preowned").text = "yes"
        SubElement(adv, "type").text = "sale"
        SubElement(adv, "brand").text = it.get("brand","") or ""
        SubElement(adv, "model").text = it.get("model","") or ""
        SubElement(adv, "year").text = it.get("year","") or ""
