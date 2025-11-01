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

    # root
    root = Element("jamesedition_feed", {"version": FEED_VERSION})

    # feed_information
    fi = SubElement(root, "feed_information")
    SubElement(fi, "reference").text = FEED_REFERENCE
    SubElement(fi, "title").text = FEED_TITLE
    now = dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    SubElement(fi, "description").text = "Automated import of unsold Bring a Trailer lots (for our inventory)"
    SubElement(fi, "created").text = now
    SubElement(fi, "updated").text = now

    # dealer  (ID numeric + nume)
    dealer = SubElement(root, "dealer")
    SubElement(dealer, "id").text = str(JE_DEALER_ID)     # ← ID numeric JE
    SubElement(dealer, "name").text = JE_DEALER_NAME      # ← nume dealer

    # adverts (Cars schema)
    adverts = SubElement(root, "adverts")
    for it in items:
        adv = SubElement(adverts, "advert", {
            "reference": str(uuid.uuid4()),   # referință unică per anunț
            "category": "car"
        })

        # Required generice
        SubElement(adv, "preowned").text = "yes"     # mașini folosite
        SubElement(adv, "type").text = "sale"        # vânzare

        # detalii auto
        SubElement(adv, "brand").text = it.get("brand","") or ""
        SubElement(adv, "model").text = it.get("model","") or ""
        SubElement(adv, "year").text = it.get("year","") or ""

        # preț
        SubElement(adv, "price_on_request").text = "yes"
        # când POR=yes, <price> trebuie să existe; îl lăsăm empty-closed cu atributele cerute
        price = SubElement(adv, "price", {"currency":"USD", "vat_included":"VAT Excluded"})
        price.text = ""  # empty

        # location — toate 5 taguri trebuie să existe (pot rămâne goale -> JE folosește locația dealerului)
        loc = SubElement(adv, "location")
        _empty("country", loc)
        _empty("region", loc)
        _empty("city", loc)
        _empty("zip", loc)
        _empty("address", loc)

        # headline (obligatoriu) + description (opțional)
        SubElement(adv, "headline").text = it.get("title","") or ""
        SubElement(adv, "description").text = it.get("description","") or ""

        # media — structură corectă: <media><image><image_url>...</image_url></image>...</media>
        media = SubElement(adv, "media")
        for im in it.get("images", [])[:40]:
            img = SubElement(media, "image")
            SubElement(img, "image_url").text = im

        # URL listing (pentru referință)
        # JE nu are un tag standard "url" în schema Cars; dacă vrei să-l păstrezi, îl punem în <description> deja.

    return tostring(root, encoding="utf-8")
