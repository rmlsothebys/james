# app/inventory.py
import json
import os
from datetime import datetime, timezone

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
INVENTORY_PATH = os.path.join(BASE_DIR, "data", "inventory.json")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_inventory() -> dict:
    """
    Încarcă inventory.json (dict: external_id -> record).
    Dacă nu există sau e corupt, întoarce {}.
    """
    if not os.path.exists(INVENTORY_PATH):
        return {}

    try:
        with open(INVENTORY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_inventory(inv: dict) -> None:
    """
    Salvează inventory.json într-un format stabil.
    """
    os.makedirs(os.path.dirname(INVENTORY_PATH), exist_ok=True)
    with open(INVENTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(inv, f, indent=2, ensure_ascii=False, sort_keys=True)


def _choose_best(old_val, new_val):
    """
    Preferă new_val dacă există (non-empty).
    Altfel păstrează old_val.
    """
    if new_val is None:
        return old_val
    if isinstance(new_val, str) and new_val.strip() == "":
        return old_val
    if isinstance(new_val, list) and len(new_val) == 0:
        return old_val
    if isinstance(new_val, dict) and len(new_val) == 0:
        return old_val
    return new_val


def _merge_images(old_imgs, new_imgs, limit=40):
    """
    Păstrează imaginile vechi + adaugă imagini noi.
    IMPORTANT: dacă azi scraperul nu găsește imagini, nu le pierdem.
    """
    old_imgs = old_imgs or []
    new_imgs = new_imgs or []
    seen = []
    for u in old_imgs + new_imgs:
        if isinstance(u, str) and u.startswith("http") and u not in seen:
            seen.append(u)
        if len(seen) >= limit:
            break
    return seen


def _merge_location(old_loc, new_loc):
    """
    Location are chei fixe; păstrează ce e bun din vechi dacă noul e gol.
    """
    old_loc = old_loc if isinstance(old_loc, dict) else {}
    new_loc = new_loc if isinstance(new_loc, dict) else {}

    out = {
        "country": _choose_best(old_loc.get("country", ""), new_loc.get("country", "")) or "",
        "region":  _choose_best(old_loc.get("region", ""),  new_loc.get("region", ""))  or "",
        "city":    _choose_best(old_loc.get("city", ""),    new_loc.get("city", ""))    or "",
        "zip":     _choose_best(old_loc.get("zip", ""),     new_loc.get("zip", ""))     or "",
        "address": _choose_best(old_loc.get("address", ""), new_loc.get("address", "")) or "",
    }
    return out


def _make_external_id(car: dict) -> str:
    """
    ID stabil pentru inventory.
    Ideal: un ID numeric BAT, dacă există.
    Fallback: URL complet.
    """
    if not isinstance(car, dict):
        return ""

    if car.get("id"):
        return f"JE-{car['id']}"  # nu mai apare BAT în internal reference (e doar pentru inventory)
    url = (car.get("url") or "").strip()
    if url:
        return f"JE-{url.rstrip('/')}"
    # ultim fallback
    return f"JE-{_now_iso()}"


def upsert_bat_cars(inv: dict, cars: list) -> dict:
    """
    Upsert „cars” în inventory.
    - NU șterge nimic automat.
    - Dacă azi lipsesc câmpuri, păstrează valorile vechi.
    - Dacă azi lipsesc imagini, păstrează imaginile vechi.
    - Dacă azi lipsesc brand/model/year, păstrează vechi.
    - Marchează recordurile văzute azi ca active + last_seen.
    - Pentru cele nevăzute azi, NU le dezactivează (doar increment missing_runs).
    """
    inv = inv if isinstance(inv, dict) else {}
    cars = cars or []

    now = _now_iso()
    seen_today = set()

    # 1) upsert pentru ce am găsit azi
    for car in cars:
        if not isinstance(car, dict):
            continue

        ext_id = _make_external_id(car)
        if not ext_id:
            continue

        seen_today.add(ext_id)

        rec = inv.get(ext_id) or {
            "external_id": ext_id,
            "first_seen": now,
            "missing_runs": 0,
        }

        # menține statutul activ
        rec["status"] = "active"
        rec["last_seen"] = now
        rec["missing_runs"] = 0

        # câmpuri de top-level "bune"
        rec["title"] = _choose_best(rec.get("title"), car.get("title"))
        rec["url"] = _choose_best(rec.get("url"), car.get("url"))
        rec["price"] = _choose_best(rec.get("price"), car.get("price"))

        # brand/model/year — păstrează vechi dacă noul e gol
        rec["brand"] = _choose_best(rec.get("brand", ""), car.get("brand", "")) or ""
        rec["model"] = _choose_best(rec.get("model", ""), car.get("model", "")) or ""
        rec["year"] = _choose_best(rec.get("year", ""), car.get("year", "")) or ""

        # location merge
        rec["location"] = _merge_location(rec.get("location"), car.get("location"))

        # images merge (NU pierdem)
        rec["images"] = _merge_images(rec.get("images"), car.get("images"), limit=40)

        # păstrează raw complet (dar fără să omori vechiul dacă noul e gol)
        old_raw = rec.get("raw") if isinstance(rec.get("raw"), dict) else {}
        new_raw = car
        merged_raw = dict(old_raw)
        for k, v in new_raw.items():
            merged_raw[k] = _choose_best(merged_raw.get(k), v)
        # imagini + location coerente în raw
        merged_raw["images"] = rec["images"]
        merged_raw["location"] = rec["location"]
        merged_raw["brand"] = rec["brand"]
        merged_raw["model"] = rec["model"]
        merged_raw["year"] = rec["year"]
        merged_raw["title"] = rec.get("title") or merged_raw.get("title")
        merged_raw["url"] = rec.get("url") or merged_raw.get("url")

        rec["raw"] = merged_raw

        inv[ext_id] = rec

    # 2) pentru cele nevăzute azi: nu dezactivăm, doar contorizăm
    for ext_id, rec in inv.items():
        if ext_id in seen_today:
            continue
        if not isinstance(rec, dict):
            continue
        rec["missing_runs"] = int(rec.get("missing_runs", 0) or 0) + 1
        # NU schimbăm status; rămâne active până decizi tu altceva

    return inv
