import time
from .config import output_filename
from .scraper import parse_unsold_index, parse_listing
from .james_xml import build_james_xml
from .storage import upload_to_s3

def run():
    print("Discovering unsold listings...")
    urls = parse_unsold_index()
    print(f"Found {len(urls)} listings candidates")

    items = []
    for i,u in enumerate(urls, start=1):
        try:
            data = parse_listing(u if u.startswith("http") else f"https://bringatrailer.com{u}")
            items.append(data)
            print(f"[{i}/{len(urls)}] Parsed: {data.get('title','')}")
            time.sleep(0.5)
        except Exception as e:
            print("Skip", u, e)

    xml_bytes = build_james_xml(items)
    outfile = output_filename()
    with open(outfile, "wb") as f:
        f.write(xml_bytes)
    print("Wrote feed:", outfile)
    print(open(outfile, "rb").read(300))

    s3_url = upload_to_s3(outfile, object_name=outfile)
    if s3_url:
        print("Uploaded to:", s3_url)

if __name__ == "__main__":
    run()
