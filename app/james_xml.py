from xml.etree.ElementTree import Element, SubElement, tostring
import datetime as dt
import uuid
from .config import FEED_VERSION, FEED_REFERENCE, FEED_TITLE, JE_DEALER_ID, JE_DEALER_NAME

def build_james_xml(items:list) -> bytes:
    if not JE_DEALER_ID or not JE_DEALER_NAME:
        raise SystemExit("JE_DEALER_ID and JE_DEALER_NAME are required env vars.")

    root = Element("jamesedition_feed", {"version": FEED_VERSION})
    fi = SubElement(root, "feed_information")
    SubElement(fi, "reference").text = FEED_REFERENCE
    SubElement(fi, "title").text = FEED_TITLE
    now = dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    SubElement(fi, "description").text = "Automated import of unsold Bring a Trailer lots (for our inventory)"
    SubElement(fi, "created").text = now
    SubElement(fi, "updated").text = now

    dealer = SubElement(root, "dealer")
    SubElement(dealer, "name").text = JE_DEALER_NAME
    SubElement(dealer, "id").text = str(JE_DEALER_ID)

    listings = SubElement(root, "listings")

    for it in items:
        auto = SubElement(listings, "automobile")
        SubElement(auto, "reference").text = str(uuid.uuid4()))
        SubElement(auto, "title").text = it.get("title","")
        SubElement(auto, "url").text = it.get("url","")
        SubElement(auto, "price_on_request").text = "yes"
        SubElement(auto, "price")

        SubElement(auto, "make").text = it.get("brand","")
        SubElement(auto, "model").text = it.get("model","")
        SubElement(auto, "year").text = it.get("year","")
        SubElement(auto, "mileage").text = it.get("mileage","")
        if it.get("transmission"):
            SubElement(auto, "transmission").text = it["transmission"]
        if it.get("vin"):
            SubElement(auto, "vin").text = it["vin"]

        SubElement(auto, "description").text = it.get("description","")

        media = SubElement(auto, "media")
        for im in it.get("images", [])[:40]:
            img = SubElement(media, "image")
            img.text = im

    return tostring(root, encoding="utf-8")
