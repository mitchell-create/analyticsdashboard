"""
Fix missing client_slug parameter mapping on Dashboard 131 for unique cards,
and add GA4 web analytics cards to both dashboards 131 and 162.
"""
import requests
import json

MB_URL = "http://localhost:3000"
MB_KEY = "mb_shG81kdEkgdKIR7njalW+w2SIvEk8sAygAPT6vIyze0="
HEADERS = {"x-api-key": MB_KEY, "Content-Type": "application/json"}

# Load GA4 card IDs
with open("scripts/ga4_card_ids.json") as f:
    ga4_ids = json.load(f)


def get_dashboard(dash_id):
    r = requests.get(f"{MB_URL}/api/dashboard/{dash_id}", headers=HEADERS)
    r.raise_for_status()
    return r.json()


def get_dash_params(dash):
    params = dash.get("parameters", [])
    result = {}
    for p in params:
        result[p.get("slug", "")] = p.get("id", "")
    return result


def fix_missing_param_mappings(dash_id, card_ids_to_fix, param_slug, tag_name):
    """Fix cards missing a parameter mapping by updating via PUT /api/dashboard/:id."""
    dash = get_dashboard(dash_id)
    params = get_dash_params(dash)
    param_id = params.get(param_slug)
    if not param_id:
        print(f"  WARNING: No {param_slug} param found on dashboard {dash_id}")
        return

    dashcards = dash.get("dashcards", dash.get("ordered_cards", []))
    updated = False

    for dc in dashcards:
        card = dc.get("card", {})
        card_id = card.get("id", dc.get("card_id"))
        if card_id in card_ids_to_fix:
            pm = dc.get("parameter_mappings", [])
            has_param = any(m.get("parameter_id") == param_id for m in pm)
            if not has_param:
                pm.append({
                    "parameter_id": param_id,
                    "card_id": card_id,
                    "target": ["variable", ["template-tag", tag_name]]
                })
                dc["parameter_mappings"] = pm
                updated = True
                print(f"  [FIX] Card {card_id} on Dashboard {dash_id}: added {param_slug} mapping")
            else:
                print(f"  [OK] Card {card_id} already has {param_slug} mapping")

    if updated:
        # Build the cards array for PUT
        cards_payload = []
        for dc in dashcards:
            card_entry = {
                "id": dc["id"],
                "card_id": dc.get("card", {}).get("id", dc.get("card_id")),
                "row": dc.get("row", 0),
                "col": dc.get("col", 0),
                "size_x": dc.get("size_x", 4),
                "size_y": dc.get("size_y", 4),
                "parameter_mappings": dc.get("parameter_mappings", []),
                "visualization_settings": dc.get("visualization_settings", {})
            }
            cards_payload.append(card_entry)

        r = requests.put(
            f"{MB_URL}/api/dashboard/{dash_id}/cards",
            headers=HEADERS,
            json={"cards": cards_payload}
        )
        if r.status_code == 200:
            print(f"  [OK] Dashboard {dash_id} dashcards updated")
        else:
            print(f"  [WARN] PUT /cards returned {r.status_code}: {r.text[:200]}")
            # Fallback: try updating via PUT /api/dashboard/:id
            r2 = requests.put(
                f"{MB_URL}/api/dashboard/{dash_id}",
                headers=HEADERS,
                json={"dashcards": dashcards}
            )
            if r2.status_code == 200:
                print(f"  [OK] Dashboard {dash_id} updated via PUT /dashboard")
            else:
                print(f"  [ERR] Fallback also failed: {r2.status_code}: {r2.text[:200]}")


def add_cards_to_dashboard(dash_id, new_cards):
    """Add multiple cards to a dashboard."""
    for nc in new_cards:
        payload = {
            "cardId": nc.get("card_id"),
            "row": nc["row"],
            "col": nc["col"],
            "size_x": nc["size_x"],
            "size_y": nc["size_y"],
        }
        if nc.get("parameter_mappings"):
            payload["parameter_mappings"] = nc["parameter_mappings"]
        if nc.get("visualization_settings"):
            payload["visualization_settings"] = nc["visualization_settings"]

        r = requests.post(
            f"{MB_URL}/api/dashboard/{dash_id}/cards",
            headers=HEADERS,
            json=payload
        )
        if r.status_code in [200, 201]:
            result = r.json()
            cid = nc.get("card_id", "heading")
            print(f"  [OK] Added card {cid} to Dashboard {dash_id} (dashcard {result.get('id', '?')})")
        else:
            print(f"  [ERR] Failed adding card {nc.get('card_id')}: {r.status_code}: {r.text[:200]}")


def build_ga4_cards(dash_id):
    """Build GA4 card list for a dashboard."""
    dash = get_dashboard(dash_id)
    params = get_dash_params(dash)
    dashcards = dash.get("dashcards", dash.get("ordered_cards", []))

    sid = params.get("start_date")
    eid = params.get("end_date")
    cid = params.get("compare_period")
    csid = params.get("client_slug")

    def scalar_map(card_id):
        m = [
            {"parameter_id": sid, "card_id": card_id, "target": ["variable", ["template-tag", "report_date_start"]]},
            {"parameter_id": eid, "card_id": card_id, "target": ["variable", ["template-tag", "report_date_end"]]},
        ]
        if cid:
            m.append({"parameter_id": cid, "card_id": card_id, "target": ["variable", ["template-tag", "compare_mode"]]})
        if csid:
            m.append({"parameter_id": csid, "card_id": card_id, "target": ["variable", ["template-tag", "client_slug"]]})
        return m

    def chart_map(card_id):
        m = [
            {"parameter_id": sid, "card_id": card_id, "target": ["variable", ["template-tag", "report_date_start"]]},
            {"parameter_id": eid, "card_id": card_id, "target": ["variable", ["template-tag", "report_date_end"]]},
        ]
        if csid:
            m.append({"parameter_id": csid, "card_id": card_id, "target": ["variable", ["template-tag", "client_slug"]]})
        return m

    max_row = max((dc.get("row", 0) + dc.get("size_y", 0)) for dc in dashcards) if dashcards else 0
    sr = max_row + 2  # start row

    return [
        # Heading
        {"card_id": None, "row": sr - 1, "col": 0, "size_x": 24, "size_y": 1,
         "visualization_settings": {"virtual_card": {"name": None, "display": "heading", "visualization_settings": {}, "dataset_query": {}, "archived": False}, "text": "Web Analytics (GA4)"}},
        # Smart scalars
        {"card_id": ga4_ids["sessions"], "row": sr, "col": 0, "size_x": 5, "size_y": 4, "parameter_mappings": scalar_map(ga4_ids["sessions"])},
        {"card_id": ga4_ids["atc"], "row": sr, "col": 5, "size_x": 5, "size_y": 4, "parameter_mappings": scalar_map(ga4_ids["atc"])},
        {"card_id": ga4_ids["checkout"], "row": sr, "col": 10, "size_x": 5, "size_y": 4, "parameter_mappings": scalar_map(ga4_ids["checkout"])},
        {"card_id": ga4_ids["web_cvr"], "row": sr, "col": 15, "size_x": 5, "size_y": 4, "parameter_mappings": scalar_map(ga4_ids["web_cvr"])},
        {"card_id": ga4_ids["bounce_rate"], "row": sr, "col": 20, "size_x": 4, "size_y": 4, "parameter_mappings": scalar_map(ga4_ids["bounce_rate"])},
        # Charts
        {"card_id": ga4_ids["web_funnel"], "row": sr + 4, "col": 0, "size_x": 12, "size_y": 8, "parameter_mappings": chart_map(ga4_ids["web_funnel"])},
        {"card_id": ga4_ids["sessions_trend"], "row": sr + 4, "col": 12, "size_x": 12, "size_y": 8, "parameter_mappings": chart_map(ga4_ids["sessions_trend"])},
        {"card_id": ga4_ids["funnel_rates"], "row": sr + 12, "col": 0, "size_x": 24, "size_y": 4, "parameter_mappings": chart_map(ga4_ids["funnel_rates"])},
    ]


# =====================================================
# Step 1: Fix parameter mappings for cards 421, 422, 423
# =====================================================
print("=== Step 1: Fix client_slug mappings on Dashboard 131 ===")
fix_missing_param_mappings(131, [421, 422, 423], "client_slug", "client_slug")

# =====================================================
# Step 2: Add GA4 cards to Dashboard 131
# =====================================================
print("\n=== Step 2: Add GA4 cards to Dashboard 131 ===")
ga4_cards_131 = build_ga4_cards(131)
add_cards_to_dashboard(131, ga4_cards_131)

# =====================================================
# Step 3: Add GA4 cards to Dashboard 162 (Chubble)
# =====================================================
print("\n=== Step 3: Add GA4 cards to Dashboard 162 ===")
ga4_cards_162 = build_ga4_cards(162)
add_cards_to_dashboard(162, ga4_cards_162)

print("\n[OK] All done!")
