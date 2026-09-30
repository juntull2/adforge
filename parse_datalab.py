import json
import base64
import zipfile
import xml.etree.ElementTree as ET

step_path = r'C:/Users/5700G/.gemini/antigravity-ide/brain/4fe5841f-1061-41ca-a813-c67222b6e9ca/.system_generated/steps/280/output.txt'
with open(step_path, 'r', encoding='utf-8') as f:
    text = f.read()

lines = text.splitlines()
result_line = None
for i, line in enumerate(lines):
    if line.startswith('### Result'):
        result_line = lines[i+1].strip()
        break

if result_line:
    b64_str = json.loads(result_line)
    binary = base64.b64decode(b64_str)
    with open('datalab_longrun.xlsx', 'wb') as out_f:
        out_f.write(binary)
    print("Successfully wrote datalab_longrun.xlsx, bytes:", len(binary))

    with zipfile.ZipFile('datalab_longrun.xlsx', 'r') as z:
        # shared strings
        shared_strings = []
        if 'xl/sharedStrings.xml' in z.namelist():
            ss_root = ET.fromstring(z.read('xl/sharedStrings.xml'))
            for si in ss_root.findall('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}si'):
                t = si.find('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t')
                shared_strings.append(t.text if t is not None else "")
        
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
        
        print("Total rows:", len(rows))
        for r in rows[:15]:
            print(r)
        
        # Analyze max values and trends for each column
        # Row 7 or so has headers
        header_idx = -1
        for idx, r in enumerate(rows):
            if any('프롬갓' in str(cell) for cell in r):
                header_idx = idx
                print(f"Header found at row {idx}: {r}")
                break
        
        if header_idx != -1:
            headers = rows[header_idx]
            data_rows = rows[header_idx+1:]
            print(f"\nData count: {len(data_rows)} days")
            
            # Print stats
            # headers look like: ['날짜', '프롬갓', '날짜', '델리케어', ...] or ['날짜', '프롬갓', '델리케어', ...]
            # let's inspect structure
            print("Headers:", headers)
            if len(data_rows) > 0:
                print("First data row:", data_rows[0])
                print("Last data row:", data_rows[-1])
