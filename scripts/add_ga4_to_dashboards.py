"""Add GA4 web analytics cards to dashboards 131 and 162 using PUT with full dashcards array."""
import requests
import json

MB_URL = "http://localhost:3000"
MB_KEY = "mb_shG81kdEkgdKIR7njalW+w2SIvEk8sAygAPT6vIyze0="
HEADERS = {"x-api-key": MB_KEY, "Content-Type": "application/json"}

with open("scripts/ga4_card_ids.json") as f:
    ga4_ids = json.load(f)


def get_dashboard(dash_id):
    r = requests.get(f"{MB_URL}/api/dashboard/{dash_id}", headers=HEADERS)
    r.raise_for_status()
    return r.json()


def get_dash_params(dash):
    return {p.get("slug", ""): p.get("id", "") for p in dash.get("parameters", [])}


def serialize_dashcard(dc):
    """Serialize an existing dashcard for the PUT payload."""
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


def add_ga4_cards(dash_id):
    """Add GA4 cards to a dashboard."""
    dash = get_dashboard(dash_id)
    params = get_dash_params(dash)
    dashcards = dash.get("dashcards", dash.get("ordered_cards", []))

    sid = params.get("start_date")
    eid = params.get("end_date")
    cid = params.get("compare_period")
    csid = params.get("client_slug")

    print(f"Dashboard {dash_id}: {len(dashcards)} existing cards")
    print(f"  Params: start={sid}, end={eid}, cmp={cid}, client={csid}")

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

    # Check if GA4 cards already exist on this dashboard
    existing_card_ids = set()
    for dc in dashcards:
        card = dc.get("card", {})
        cid_val = card.get("id", dc.get("card_id"))
        if cid_val:
            existing_card_ids.add(cid_val)

    ga4_card_ids_set = set(ga4_ids.values())
    already_added = ga4_card_ids_set & existing_card_ids
    if already_added:
        print(f"  GA4 cards already on dashboard: {already_added}")
        return

    # Serialize existing dashcards
    cards_payload = [serialize_dashcard(dc) for dc in dashcards]

    # Find max row
    max_row = max((dc.get("row", 0) + dc.get("size_y", 0)) for dc in dashcards) if dashcards else 0
    sr = max_row + 2  # start row with gap

    # New card counter (negative IDs for new cards)
    new_id = -1

    # Add heading
    cards_payload.append({
        "id": new_id,
        "card_id": None,
        "row": sr - 1,
        "col": 0,
        "size_x": 24,
        "size_y": 1,
        "parameter_mappings": [],
        "visualization_settings": {
            "virtual_card": {
                "name": None,
                "display": "heading",
                "visualization_settings": {},
                "dataset_query": {},
                "archived": False
            },
            "text": "Web Analytics (GA4)"
        },
        "series": []
    })
    new_id -= 1

    # Smart scalar cards
    scalars = [
        ("sessions", 0), ("atc", 5), ("checkout", 10),
        ("web_cvr", 15), ("bounce_rate", 20)
    ]
    for key, col in scalars:
        card_id = ga4_ids[key]
        size_x = 4 if key == "bounce_rate" else 5
        cards_payload.append({
            "id": new_id,
            "card_id": card_id,
            "row": sr,
            "col": col,
            "size_x": size_x,
            "size_y": 4,
            "parameter_mappings": scalar_map(card_id),
            "visualization_settings": {},
            "series": []
        })
        new_id -= 1

    # Chart cards
    charts = [
        ("web_funnel", sr + 4, 0, 12, 8),
        ("sessions_trend", sr + 4, 12, 12, 8),
        ("funnel_rates", sr + 12, 0, 24, 4),
    ]
    for key, row, col, sx, sy in charts:
        card_id = ga4_ids[key]
        cards_payload.append({
            "id": new_id,
            "card_id": card_id,
            "row": row,
            "col": col,
            "size_x": sx,
            "size_y": sy,
            "parameter_mappings": chart_map(card_id),
            "visualization_settings": {},
            "series": []
        })
        new_id -= 1

    print(f"  Total cards after adding GA4: {len(cards_payload)}")

    # PUT the full dashboard update
    r = requests.put(
        f"{MB_URL}/api/dashboard/{dash_id}",
        headers=HEADERS,
        json={"dashcards": cards_payload}
    )
    if r.status_code == 200:
        result = r.json()
        new_count = len(result.get("dashcards", result.get("ordered_cards", [])))
        print(f"  [OK] Dashboard {dash_id} updated: {new_count} cards")
    else:
        print(f"  [ERR] {r.status_code}: {r.text[:500]}")


# Process both dashboards
print("=== Adding GA4 cards to Dashboard 131 ===")
add_ga4_cards(131)

print("\n=== Adding GA4 cards to Dashboard 162 ===")
add_ga4_cards(162)

print("\n[OK] Done!")
