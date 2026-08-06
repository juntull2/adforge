import csv
import json

csv_file = r"C:\Users\5700G\.gemini\antigravity-ide\brain\da1f9f6e-aff8-48b9-91a4-988a6393bcf3\.system_generated\steps\88\content.md"

keywords_data = []

with open(csv_file, "r", encoding="utf-8") as f:
    lines = f.readlines()

data_lines = lines[19:]
raw_csv = "".join(data_lines)

reader = csv.reader(raw_csv.splitlines())

for row in reader:
    if not row or len(row) < 15:
        continue
    
    idx = row[0].strip()
    kw = row[1].strip()
    if not idx.isdigit() or not kw:
        continue

    total_vol = row[4].strip()

    # Check 1탭 to 10탭 (col 10 to col 19)
    clip_rank = None
    matched_tab = ""
    for tab_idx in range(10, min(20, len(row))):
        tab_name = row[tab_idx].strip()
        if "네이버 클립" in tab_name or "클립" in tab_name:
            clip_rank = tab_idx - 9  # 10=1탭, 11=2탭...
            matched_tab = tab_name
            break

    if clip_rank is not None and clip_rank <= 6:
        keywords_data.append({
            "keyword": kw,
            "volume": total_vol,
            "clip_tab_rank": clip_rank,
            "main_tab": matched_tab
        })

print(f"Total Naver Clip Keywords Extracted: {len(keywords_data)}\n")
with open("extracted_keywords.json", "w", encoding="utf-8") as f_out:
    json.dump(keywords_data, f_out, ensure_ascii=False, indent=2)

print("Saved to extracted_keywords.json successfully!")

