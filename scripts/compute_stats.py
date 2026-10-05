import zipfile
import xml.etree.ElementTree as ET

with zipfile.ZipFile('datalab_longrun.xlsx', 'r') as z:
    shared_strings = []
    if 'xl/sharedStrings.xml' in z.namelist():
        ss_root = ET.fromstring(z.read('xl/sharedStrings.xml'))
        for si in ss_root.findall('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}si'):
            # Some shared strings have multiple <t> inside <r>
            text_val = "".join([t.text for t in si.iter('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t') if t.text])
            shared_strings.append(text_val)
    
    sheet_root = ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
    ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    
    rows = []
    for r in sheet_root.findall('.//s:row', ns):
        row_vals = []
        for c in r.findall('s:c', ns):
            t_attr = c.get('t')
            v = c.find('s:v', ns)
            val = v.text if v is not None else ""
            if t_attr == 's' and val != '':
                val = shared_strings[int(val)]
            row_vals.append(val)
        rows.append(row_vals)

headers = ['날짜', '프롬갓', '날짜', '델리케어', '날짜', '메디옥실', '날짜', '노일리', '날짜', '이옴']
brands = [
    ('프롬갓', 0, 1),
    ('델리케어', 2, 3),
    ('메디옥실', 4, 5),
    ('노일리', 6, 7),
    ('이옴', 8, 9),
]

data_rows = rows[7:] # row 7 onwards is data

results = {}
for brand_name, date_col, val_col in brands:
    series = []
    for r in data_rows:
        if len(r) > val_col and r[date_col] and r[val_col]:
            try:
                date = r[date_col]
                val = float(r[val_col])
                series.append((date, val))
            except ValueError:
                pass
    
    if series:
        max_entry = max(series, key=lambda x: x[1])
        min_entry = min(series, key=lambda x: x[1])
        avg_val = sum(x[1] for x in series) / len(series)
        latest_val = series[-1]
        first_val = series[0]
        # check growth
        recent_30 = series[-30:]
        avg_recent_30 = sum(x[1] for x in recent_30) / len(recent_30)
        first_30 = series[:30]
        avg_first_30 = sum(x[1] for x in first_30) / len(first_30)
        
        results[brand_name] = {
            'count': len(series),
            'max': max_entry,
            'min': min_entry,
            'avg': avg_val,
            'first': first_val,
            'latest': latest_val,
            'first_30_avg': avg_first_30,
            'recent_30_avg': avg_recent_30,
            'growth_rate': (avg_recent_30 / avg_first_30) if avg_first_30 > 0 else 0
        }

with open('brand_stats.txt', 'w', encoding='utf-8') as out:
    for b, s in results.items():
        out.write(f"=== {b} ===\n")
        out.write(f"데이터 수: {s['count']}일 (기간: {s['first'][0]} ~ {s['latest'][0]})\n")
        out.write(f"최고치: {s['max'][1]:.2f} (날짜: {s['max'][0]})\n")
        out.write(f"최저치: {s['min'][1]:.2f} (날짜: {s['min'][0]})\n")
        out.write(f"전체 평균: {s['avg'][2] if False else s['avg']:.2f}\n")
        out.write(f"초기 30일 평균: {s['first_30_avg']:.2f} -> 최근 30일 평균: {s['recent_30_avg']:.2f} (성장률: {s['growth_rate']:.2f}배)\n")
        out.write(f"최근 수치 ({s['latest'][0]}): {s['latest'][1]:.2f}\n\n")

print("Done writing brand_stats.txt")
