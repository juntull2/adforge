"""요청한 레퍼런스 표의 표시 열만 변경합니다. 기본은 미리보기, --apply로 적용."""
import argparse
from copy import deepcopy
from datetime import datetime
import json
import os
from pathlib import Path
import sys
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
import notion_references as n
from notion_sync import NotionClient


def configure_fields(view, schema, additions, hidden=()):
    config = deepcopy(view["configuration"])
    properties = config.setdefault("properties", [])
    by_id = {unquote(p["property_id"]): p for p in properties}
    for name, after, width in additions:
        prop_id = unquote(schema[name]["id"])
        prop = by_id.get(prop_id, {"property_id": schema[name]["id"], "width": width})
        prop["visible"] = True
        prop.setdefault("width", width)
        if prop in properties:
            properties.remove(prop)
        anchor = unquote(schema[after]["id"])
        index = next((i + 1 for i, p in enumerate(properties) if unquote(p["property_id"]) == anchor), len(properties))
        properties.insert(index, prop)
        by_id[prop_id] = prop
    for name in hidden:
        prop = by_id.get(unquote(schema[name]["id"]))
        if prop is not None:
            prop["visible"] = False
    for prop in properties:
        prop.pop("property_name", None)
    return config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    ids = n.configured_ids()
    if ids[n.ENV_PAGE].replace("-", "") != "3ebf10190fb181979280ff10cfeb5e58":
        raise RuntimeError("사용자가 지정한 노션 페이지와 설정이 다릅니다.")
    client = NotionClient(os.environ["NOTION_TOKEN"], max_retries=1, timeout=15)
    plans = []
    for db_key, ds_key, additions, hidden in [
        (n.ENV_AD_DB, n.ENV_AD_DS, [(n.A_ACCOUNT, n.A_BRAND, 140), (n.A_STATUS, n.A_ACCOUNT, 95)], [n.A_APPEAL]),
        (n.ENV_BRAND_DB, n.ENV_BRAND_DS, [(n.B_MALL, n.B_PRODUCT, 180)], []),
    ]:
        schema = client.get(f"data_sources/{ids[ds_key]}")["properties"]
        for ref in client.paginate("GET", "views", params={"database_id": ids[db_key]}):
            view = client.get(f"views/{ref['id']}")
            if view["type"] != "table":
                continue
            config = configure_fields(view, schema, additions, hidden)
            plans.append({"before": view, "configuration": config})
    out = ROOT / "outputs" / "notion_layout"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"reference_fields_{datetime.now():%Y%m%d_%H%M%S}.json"
    path.write_text(json.dumps(plans, ensure_ascii=False, indent=2), encoding="utf-8")
    print("SNAPSHOT", path)
    for plan in plans:
        view = plan["before"]
        print("PLAN", view["id"], view["name"].encode("unicode_escape").decode())
        if args.apply:
            client.patch(f"views/{view['id']}", json={"configuration": plan["configuration"]})
            actual = client.get(f"views/{view['id']}")["configuration"]
            expected = [(unquote(p["property_id"]), bool(p.get("visible"))) for p in plan["configuration"]["properties"]]
            got = [(unquote(p["property_id"]), bool(p.get("visible"))) for p in actual["properties"]]
            if got != expected:
                raise RuntimeError("표의 열 표시 설정이 예상과 다릅니다.")
            print("VERIFIED", view["id"])


if __name__ == "__main__":
    main()
