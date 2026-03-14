"""Fix missing client_slug parameter mapping for cards 421, 422, 423 on Dashboard 131."""
import requests
import json

MB_URL = "http://localhost:3000"
MB_KEY = "mb_shG81kdEkgdKIR7njalW+w2SIvEk8sAygAPT6vIyze0="
HEADERS = {"x-api-key": MB_KEY, "Content-Type": "application/json"}

DASH_ID = 131

r = requests.get(f"{MB_URL}/api/dashboard/{DASH_ID}", headers=HEADERS)
r.raise_for_status()
dash = r.json()

# Find client_slug param ID
params = dash.get("parameters", [])
client_slug_param_id = None
for p in params:
    if p.get("slug") == "client_slug":
        client_slug_param_id = p.get("id")
        break

print(f"client_slug param ID: {client_slug_param_id}")

dashcards = dash.get("dashcards", dash.get("ordered_cards", []))

# Serialize existing dashcard
def serialize_dashcard(dc):
    return {
        "id": dc["id"],
        "card_id": dc.get("card", {}).get("id", dc.get("card_id")),
        "row": dc.get("row", 0),
        "col": dc.get("col", 0),
        "size_x": dc.get("size_x", 4),
        "size_y": dc.get("size_y", 4),
        "parameter_mappings": dc.get("parameter_mappings", []),
        "visualization_settings": dc.get("visualization_settings", {}),
        "series": dc.get("series", [])
    }

cards_payload = []
fixed = []

for dc in dashcards:
    entry = serialize_dashcard(dc)
    card = dc.get("card", {})
    card_id = card.get("id", dc.get("card_id"))

    if card_id in [421, 422, 423]:
        pm = entry["parameter_mappings"]
        has_client_slug = any(m.get("parameter_id") == client_slug_param_id for m in pm)
        if not has_client_slug:
            pm.append({
                "parameter_id": client_slug_param_id,
                "card_id": card_id,
                "target": ["variable", ["template-tag", "client_slug"]]
            })
            entry["parameter_mappings"] = pm
            fixed.append(card_id)

    cards_payload.append(entry)

if fixed:
    r = requests.put(f"{MB_URL}/api/dashboard/{DASH_ID}",
                     headers=HEADERS,
                     json={"dashcards": cards_payload})
    r.raise_for_status()
    print(f"[OK] Fixed client_slug mapping for cards: {fixed}")
else:
    print("[OK] All cards already have client_slug mapping")

# Verify
r = requests.get(f"{MB_URL}/api/dashboard/{DASH_ID}", headers=HEADERS)
r.raise_for_status()
dash = r.json()
for dc in dash.get("dashcards", []):
    card = dc.get("card", {})
    cid = card.get("id")
    if cid in [421, 422, 423]:
        pm = dc.get("parameter_mappings", [])
        has_cs = any(m.get("parameter_id") == client_slug_param_id for m in pm)
        print(f"  Card {cid} ({card.get('name')}): client_slug={has_cs}, total_mappings={len(pm)}")
