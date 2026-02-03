# app/inventory.py
import json
import os
import re
from datetime import datetime, timezone

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
INVENTORY_PATH = os.path.join(BASE_DIR, "data", "inventory.json")


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_inventory() -> dict:
    if not os.path.exists(INVENTORY_PATH):
        return {}
    with open(INVENTORY_PATH, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}


def save_inventory(inv: dict) -> None:
    os.makedirs(os.path.dirname(INVENTORY_PATH), exist_ok=True)
    with open(INVENTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(inv, f, indent=2, ensure_ascii=False)


def _slugify(s: str, max_len: int = 80) -> str:
    s = (s or "").strip()
    s = s.lower()
    s = re.sub(r"https?://\S+", "", s)       # elimină URL-uri
    s = re.sub(r"[^a-z0-9]+", "-", s)        # non-alnum -> -
    s = re.sub(r"-{2,}", "-", s).strip("-")  # dubluri
    if not s:
        s = "listing"
    return s[:max_len].rstrip("-")


def _extract_bat_listing_slug(url: str) -> str:
    """
    https://bringatrailer.com/listing/1992-ford-mustang-54/
      -> 1992-ford-mustang-54
    """
    url = (url or "").strip()
    m = re.search(r"/listing/([^/]+)/?$", url)
    if m:
        return m.group(1)
    return ""


def _external_id_for_car(car: dict) -> str:
    """
    ID stabil intern pt inventory (NU neapărat cel din XML).
    Important: să fie stabil ca key în inventory.
    """
    # dacă ai id numeric real de la BAT, folosește-l
    if car.get("id"):
        return f"BAT-{car['id']}"
    # altfel folosește slug din URL (nu url complet)
    slug = _extract_bat_listing_slug(car.get("url", ""))
    if slug:
        return f"BAT-{slug}"
    # fallback
    return f"BAT-{_slugify(car.get('title', 'listing'))}"


def ensure_je_reference(rec: dict) -> dict:
    """
    Regula de aur:
    - dacă deja există je_reference în inventory -> NU îl schimbăm (altfel dispar listings)
    - dacă nu există -> îl generăm curat (fără URL)
    """
    if rec.get("je_reference"):
        return rec

    ext = rec.get("external_id", "")
    url = rec.get("url", "")

    # dacă ext_id deja e curat (ex: BAT-1992-ford-mustang-54), îl folosim
    # dacă ar conține URL (BAT-https://...), NU vrem să-l punem, dar poate ai avut deja așa în trecut.
    # Ca să nu-ți dispară listings, dacă ai avut deja așa, probabil există în inventory vechi.
    # Aici generăm DOAR pentru anunțurile care nu existau înainte.
    slug = ""
    if ext and not ext.lower().startswith("bat-http"):
        slug = ext.replace("BAT-", "").strip()
    if not slug:
        slug = _extract_bat_listing_slug(url) or _slugify(rec.get("title", ""))

    rec["je_reference"] = slug  # doar slug, fără BAT și fără URL
    return rec


def upsert_bat_cars(inv: dict, cars: list) -> dict:
    now = _now_iso()

    for car in cars or []:
        ext_id = _external_id_for_car(car)

        rec = inv.get(ext_id)
        if not rec:
            # first time seen
            rec = {
                "external_id": ext_id,
                "first_seen": now,
                "status": "active",
            }

        # update common fields
        rec["last_seen"] = now
        rec["status"] = "active"
        rec["title"] = car.get("title")
        rec["url"] = car.get("url")
        rec["price"] = car.get("price")
        rec["images"] = car.get("images", []) or []
        rec["location"] = car.get("location") or {}
        rec["description"] = car.get("description") or ""
        rec["raw"] = car

        # IMPORTANT: setăm je_reference doar dacă nu există deja (nu schimbăm niciodată)
        rec = ensure_je_reference(rec)

        inv[ext_id] = rec

    # NU ștergem nimic automat
    return inv
