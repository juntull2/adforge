import json
import os

def load_data():
    with open("c:/adforge/supplements_investigation_results.json", "r", encoding="utf-8") as f:
        primary = json.load(f)
    extra = []
    if os.path.exists("c:/adforge/supplements_extra_subaccounts.json"):
        with open("c:/adforge/supplements_extra_subaccounts.json", "r", encoding="utf-8") as f:
            extra = json.load(f)
    return primary, extra

primary, extra = load_data()
print(f"Loaded primary: {len(primary)} categories, extra: {len(extra)} ads")
