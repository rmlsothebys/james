import time
import requests
from bs4 import BeautifulSoup
from xml.etree.ElementTree import Element, SubElement, ElementTree

BASE_RESULTS = "https://bringatrailer.com/auctions/results/?result=unsold"
HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

def get_listing_links():
    links = []
    seen = set()

    for page in range(1, 50):
        url = f"{BASE_RESULTS}&page={page}"
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            break

        soup = BeautifulSoup(r.text, "html.parser")
        found = 0

        for a in soup.select("a[href^='/listing/']"):
            link = "https://bringatrailer.com" + a["href"]
            if link not in seen:
                seen.add(link)
                links.append(link)
                found += 1

        if found == 0:
            break

        time.sleep(1)

    return links


def parse_listing(url):
    r = requests.get(url, headers=HEADERS, timeout=20)
    soup = BeautifulSoup(r.text, "html.parser")

    title = soup.find("h1").get_text(strip=True)

    # descriere – primele 2 paragrafe
    desc = ""
    content = soup.select_one(".post-content")
    if content:
        ps = content.find_all("p")
        desc = " ".join(p.get_text(strip=True) for p in ps[:2])

    # imagini – maxim 5
    images = []
    for img in soup.select("img"):
        src = img.get("src", "")
        if "bringatrailer" in src and src.endswith(".jpg"):
            images.append(src)
        if len(images) == 5:
            break

    return {
        "id": url.split("/")[-2],
        "title": title,
        "url": url,
        "description": desc,
        "images": images
    }


def build_xml(listings):
    feed = Element("feed", version="3.0")
    header = SubElement(feed, "header")
    SubElement(header, "dealer_id").text = "105029"
    SubElement(header, "dealer_name").text = "RM Sotheby's"

    items = SubElement(feed, "listings")

    for l in listings:
        it = SubElement(items, "listing")
        SubElement(it, "id").text = l["id"]
        SubElement(it, "title").text = l["title"]
        SubElement(it, "url").text = l["url"]
        SubElement(it, "description").text = l["description"]
        SubElement(it, "price_on_request").text = "yes"

        imgs = SubElement(it, "images")
        for img in l["images"]:
            SubElement(imgs, "image").text = img

    tree = ElementTree(feed)
    tree.write("JamesEdition_feed_105029.xml", encoding="utf-8", xml_declaration=True)


def main():
    print("Fetching listings…")
    links = get_listing_links()
    print(f"Found {len(links)} listings")

    listings = []
    for link in links:
        try:
            listings.append(parse_listing(link))
            time.sleep(1)
        except Exception as e:
            print("Skip:", link, e)

    build_xml(listings)
    print("Feed generated.")


if __name__ == "__main__":
    main()
