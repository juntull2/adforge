"""기존 노션 안내와 보고용 검색량 열을 60일 기준으로 전환합니다 (--apply로 적용)."""
import argparse
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    load_dotenv(ROOT / '.env')
    c = NotionClient(os.environ['NOTION_TOKEN'], max_retries=1, timeout=15)
    ids = n.configured_ids()
    schema = c.get(f'data_sources/{ids[n.ENV_BRAND_DS]}')
    guides = []
    rise_callouts = []
    for block in c.block_children(ids[n.ENV_PAGE]):
        if block.get('type') != 'callout':
            continue
        label = ''.join(t.get('plain_text') or t.get('text', {}).get('content', '')
                        for t in block['callout'].get('rich_text', []))
        if label == 'A급 기준' or label.startswith('급상승'):
            if label.startswith('급상승'):
                rise_callouts.append(block['id'])
            for child in c.block_children(block['id']):
                if child.get('type') != 'bulleted_list_item':
                    continue
                text = ''.join(t.get('plain_text') or t.get('text', {}).get('content', '')
                               for t in child['bulleted_list_item'].get('rich_text', []))
                if text.startswith('①') or text.startswith('🚀 급상승:'):
                    guides.append(child)
    refs = c.paginate('GET', 'views', params={'database_id': ids[n.ENV_BRAND_DB]})
    views = [c.get(f'views/{ref["id"]}') for ref in refs]
    out = ROOT / 'outputs' / 'notion_layout'
    out.mkdir(parents=True, exist_ok=True)
    snapshot = out / f'volume_60d_{datetime.now():%Y%m%d_%H%M%S}.json'
    snapshot.write_text(json.dumps({'schema': schema, 'guides': guides, 'views': views},
                                   ensure_ascii=False, indent=2), encoding='utf-8')
    print('SNAPSHOT', snapshot)
    print('PLAN: use 60-day volume and rise columns; retain historical 30-day values; update guides and report views')
    if not args.apply:
        return
    replacements = {'최고 60일 검색량': n.B_PEAK, '급상승': n.B_RISE, '급상승 구간': n.B_RISE_RANGE,
                    '30일 증가폭': n.B_JUMP, '증가 배수': n.B_RATIO, '평소 수준': n.B_BASELINE}
    desired = n.brand_schema()
    additions = {name: desired[name] for name in replacements.values() if name not in schema['properties']}
    if additions:
        c.patch(f'data_sources/{ids[n.ENV_BRAND_DS]}', json={'properties': additions})
    properties = c.get(f'data_sources/{ids[n.ENV_BRAND_DS]}')['properties']
    by_old_id = {unquote(properties[old]['id']): properties[new]['id']
                 for old, new in replacements.items() if old in properties}
    for view in views:
        config = dict(view.get('configuration') or {})
        if config.get('type') != 'table':
            continue
        props = []
        present = {unquote(p['property_id']) for p in config.get('properties') or []}
        inherited = {unquote(by_old_id[unquote(p['property_id'])]): p
                     for p in config.get('properties') or [] if unquote(p['property_id']) in by_old_id}
        for prop in config.get('properties') or []:
            pid = unquote(prop['property_id'])
            if pid in by_old_id:
                new_id = by_old_id[pid]
                if unquote(new_id) not in present:
                    props.append({'property_id': new_id, 'visible': prop.get('visible', False),
                                  'width': prop.get('width', 140), 'wrap': True})
                props.append(dict(prop, visible=False))
            else:
                if pid in inherited:
                    source = inherited[pid]
                    prop = dict(prop, visible=source.get('visible', False), width=source.get('width', 140), wrap=True)
                props.append(prop)
        configured = {unquote(p['property_id']) for p in props}
        for name in replacements.values():
            if unquote(properties[name]['id']) not in configured:
                props.append({'property_id': properties[name]['id'], 'visible': name in (n.B_PEAK, n.B_RISE),
                              'width': 140 if name == n.B_PEAK else 100, 'wrap': True})
        config['properties'] = props
        for prop in props:
            if unquote(prop['property_id']) in {unquote(properties[n.B_PEAK]['id']), unquote(properties[n.B_RISE]['id'])}:
                prop['visible'] = True
        group = config.get('group_by')
        if group and unquote(group.get('property_id', '')) in by_old_id:
            group = dict(group)
            group['property_id'] = by_old_id[unquote(group['property_id'])]
            group.pop('property_name', None)
            config['group_by'] = group
        body = {'configuration': config}
        if view.get('sorts'):
            sorts = []
            for item in view['sorts']:
                item = dict(item)
                value = item.get('property', '')
                if value in replacements:
                    item['property'] = replacements[value]
                elif unquote(value) in by_old_id:
                    item['property'] = by_old_id[unquote(value)]
                sorts.append(item)
            body['sorts'] = sorts
        c.patch(f'views/{view["id"]}', json=body)
        actual = c.get(f'views/{view["id"]}')
        shown = {unquote(p['property_id']) for p in actual['configuration']['properties'] if p.get('visible')}
        assert unquote(properties[n.B_PEAK]['id']) in shown
        assert unquote(properties[n.B_RISE]['id']) in shown
        assert not shown.intersection(by_old_id)
    text = '① 최근 1년 안에 동일한 브랜드·제품 키워드의 30일 검색량이 1만 건 이상인 이력과, 직전 60일 대비 60일 검색량 증가폭이 7,000건 이상인 이력 (네이버 최근 30일 실측 검색수로 데이터랩 일간 추이를 환산)'
    for guide in guides:
        old_text = ''.join(t.get('plain_text', '') for t in guide['bulleted_list_item']['rich_text'])
        guide_text = text if old_text.startswith('①') else '🚀 급상승: 30일 검색량 1만 건 이상 + 직전 60일 대비 60일 증가폭 7,000건 이상. 배수는 참고용'
        c.patch(f'blocks/{guide["id"]}', json={'bulleted_list_item': {'rich_text': [{'type': 'text', 'text': {'content': guide_text}}]}})
        actual = c.get(f'blocks/{guide["id"]}')
        assert ''.join(t.get('plain_text', '') for t in actual['bulleted_list_item']['rich_text']) == guide_text
    for block_id in rise_callouts:
        label = '급상승 판정 (A급 필수 조건)'
        c.patch(f'blocks/{block_id}', json={'callout': {'rich_text': [{'type': 'text', 'text': {'content': label}}]}})
        actual = c.get(f'blocks/{block_id}')
        assert ''.join(t.get('plain_text', '') for t in actual['callout']['rich_text']) == label
    print('VERIFIED: 60-day column and report views updated; criterion guides updated:', len(guides))


if __name__ == '__main__':
    main()
