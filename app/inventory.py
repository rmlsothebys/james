# app/inventory.py
import json
import os
from datetime import datetime, timezone

INVENTORY_PATH = "data/inventory.json"

def _now_iso():
    return datetime.now(timezone.utc).isoformat()

def load_inventory() -> dict:
    if not os.path.exists(INVENTORY_PATH):
        return {}
    with open(INVENTORY_PATH, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

def save_inventory(inv: dict) -> None:
    os.makedirs(os.path.dirname(INVENTORY_PATH), exist_ok=True)
    with open(INVENTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(inv, f, indent=2, ensure_ascii=False)

def upsert_bat_cars(inv: dict, cars: list) -> dict:
    now = _now_iso()
    for car in cars:
        # ID stabil: ideal BAT listing id
        if car.get("id"):
            ext_id = f"BAT-{car['id']}"
        else:
            ext_id = f"BAT-{car.get('url','').rstrip('/')}"

        rec = inv.get(ext_id) or {"external_id": ext_id, "first_seen": now}
        rec.update({
            "status": "active",
            "last_seen": now,
            "title": car.get("title"),
            "url": car.get("url"),
            "price": car.get("price"),
            "images": car.get("images", []),
            "raw": car,
        })
        inv[ext_id] = rec

    # IMPORTANT: nu stergem nimic automat
    return inv
