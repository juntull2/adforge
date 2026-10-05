"""노션 레퍼런스 표를 좁은 보고용 보기로 정리합니다. 기본은 미리보기, --apply로 적용."""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from notion_sync import NotionClient
import notion_references as n


AD_COLUMNS = [(n.A_TITLE, 200), (n.A_BRAND, 85), (n.A_APPEAL, 90), (n.A_DAYS, 60),
              (n.A_META, 75), (n.H_MATERIAL, 120), (n.H_EDITED, 90), (n.H_FEEDBACK, 160)]
BRAND_COLUMNS = [(n.B_TITLE, 160), (n.B_PRODUCT, 140), (n.B_PEAK, 140), (n.B_RISE, 100),
                 (n.B_MAX_DAYS, 95), (n.B_ACCOUNTS, 95)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--single-page', action='store_true', help='브랜드·소재 기본 보기만 남기고 수동 입력 칸을 정리')
    args = parser.parse_args()
    load_dotenv(ROOT / '.env')
    client = NotionClient(os.environ['NOTION_TOKEN'], max_retries=1, timeout=15)
    ids = n.configured_ids()
    changes, originals, removals = [], [], []
    manual_before = {}
    def manual_values():
        result = {}
        for page in client.query_data_source(ids[n.ENV_AD_DS]):
            for name, prop in page.get('properties', {}).items():
                if name in n.HUMAN_PROTECTED:
                    value = json.dumps(prop.get(prop.get('type')), sort_keys=True, ensure_ascii=True)
                    result[(page['id'], unquote(prop['id']))] = hashlib.sha256(value.encode()).hexdigest()
        return result
    if args.single_page:
        manual_before = manual_values()
        # 속성 ID를 유지한 이름 변경은 기존 사용자 입력값을 그대로 보존합니다.
        schema = client.get(f'data_sources/{ids[n.ENV_AD_DS]}')['properties']
        if args.apply:
            updates = {}
            for old, new in n.HUMAN_ALIASES.items():
                if new not in schema and old in schema:
                    updates[schema[old]['id']] = {'name': new}
                elif new not in schema:
                    updates[new] = n.human_schema({})[new]
            if n.H_FEEDBACK not in schema:
                updates[n.H_FEEDBACK] = n.human_schema({})[n.H_FEEDBACK]
            if updates:
                out = ROOT / 'outputs' / 'notion_layout'
                out.mkdir(parents=True, exist_ok=True)
                (out / f'human_schema_{datetime.now():%Y%m%d_%H%M%S}.json').write_text(
                    json.dumps(schema, ensure_ascii=False, indent=2), encoding='utf-8')
                client.patch(f'data_sources/{ids[n.ENV_AD_DS]}', json={'properties': updates})
    for db_key, ds_key, columns in [(n.ENV_AD_DB, n.ENV_AD_DS, AD_COLUMNS),
                                     (n.ENV_BRAND_DB, n.ENV_BRAND_DS, BRAND_COLUMNS)]:
        schema = client.get(f'data_sources/{ids[ds_key]}')['properties']
        ordered = [(name, width) for name, width in columns if name in schema]
        visible_names = {name for name, _ in ordered}
        refs = client.paginate('GET', 'views', params={'database_id': ids[db_key]})
        for index, ref in enumerate(refs):
            view = client.get(f'views/{ref["id"]}')
            originals.append(view)
            if args.single_page and index > 0:
                removals.append(view['id'])
                continue
            kind = view.get('type')
            if kind not in ('table', 'board', 'list', 'gallery'):
                continue
            config = dict(view.get('configuration') or {})
            config['type'] = kind
            props = []
            for name, width in ordered:
                item = {'property_id': schema[name]['id'], 'visible': True}
                if kind == 'table':
                    item.update(width=width, wrap=name not in (n.A_META, n.H_MATERIAL))
                props.append(item)
            props += [{'property_id': meta['id'], 'visible': False}
                      for name, meta in schema.items() if name not in visible_names]
            config['properties'] = props
            if kind == 'table':
                config.update(wrap_cells=True, frozen_column_index=1)
                if args.single_page:
                    config['group_by'] = None
            body = {'configuration': config}
            if index == 0 and kind == 'table':
                body['name'] = ('소재' if db_key == n.ENV_AD_DB else '브랜드') if args.single_page else \
                    ('📋 대표님 보고' if db_key == n.ENV_AD_DB else '🏢 브랜드 요약')
            changes.append({'id': view['id'], 'before_name': view.get('name'), 'body': body,
                            'visible_columns': [name for name, _ in ordered],
                            'width': sum(width for _, width in ordered) if kind == 'table' else None})
    out = ROOT / 'outputs' / 'notion_layout'
    out.mkdir(parents=True, exist_ok=True)
    snapshot = out / f'layout_{datetime.now():%Y%m%d_%H%M%S}.json'
    snapshot.write_text(json.dumps({'originals': originals, 'changes': changes, 'remove_views': removals}, ensure_ascii=False, indent=2), encoding='utf-8')
    print('SNAPSHOT', snapshot)
    for change in changes:
        print(json.dumps({k: v for k, v in change.items() if k != 'body'}, ensure_ascii=True))
    if not args.apply:
        return
    for change in changes:
        client.patch(f'views/{change["id"]}', json=change['body'])
        actual = client.get(f'views/{change["id"]}')
        expected = change['body']['configuration']['properties']
        actual_props = (actual.get('configuration') or {}).get('properties') or []
        actual_by_id = {unquote(p['property_id']): p for p in actual_props}
        for prop in expected:
            got = actual_by_id.get(unquote(prop['property_id']), {})
            if got.get('visible') != prop['visible']:
                raise RuntimeError(f'열 표시 검증 실패: {change["id"]} {prop["property_id"]}')
            if 'width' in prop and got.get('width') != prop['width']:
                raise RuntimeError(f'열 너비 검증 실패: {change["id"]} {prop["property_id"]}')
        assert [unquote(p['property_id']) for p in actual_props if p.get('visible')] == \
            [unquote(p['property_id']) for p in expected if p.get('visible')]
        print('VERIFIED', json.dumps({'name': actual.get('name'), 'url': actual.get('url')}, ensure_ascii=True))
    for view_id in removals:
        client.delete(f'views/{view_id}')
    if args.single_page:
        manual_after = manual_values()
        assert all(manual_after.get(key) == value for key, value in manual_before.items()), '수동 입력값 보존 검증 실패'
        for block in client.block_children(ids[n.ENV_PAGE]):
            if block.get('type') != 'callout':
                continue
            label = ''.join(t.get('plain_text', '') for t in block['callout'].get('rich_text', []))
            if not label.startswith('누가'):
                continue
            for child in client.block_children(block['id']):
                if child.get('type') != 'bulleted_list_item':
                    continue
                text = ''.join(t.get('plain_text', '') for t in child['bulleted_list_item'].get('rich_text', []))
                if text.startswith('사람 전용:'):
                    note = '사용자 전용: 제작 영상 링크 · 제작 날짜 · 대표님 피드백 — 사용자만 입력하며 adforge는 생성·갱신·이관 시 값을 절대 작성하지 않습니다.'
                    client.patch(f'blocks/{child["id"]}', json={'bulleted_list_item': {
                        'rich_text': [{'type': 'text', 'text': {'content': note}}]}})
        for db_key in (n.ENV_AD_DB, n.ENV_BRAND_DB):
            db = client.get(f'databases/{ids[db_key]}')
            assert db['parent'].get('page_id') == ids[n.ENV_PAGE]
            remaining = client.paginate('GET', 'views', params={'database_id': ids[db_key]})
            assert len(remaining) == 1
        print('VERIFIED: one shared page, one view per database; user-owned column values never written')


if __name__ == '__main__':
    main()
