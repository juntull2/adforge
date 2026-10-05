import urllib.request
import re

urls = [
    ("풀리", "https://www.full-y.co.kr/product/detail.html?product_no=463"),
    ("새살", "https://sesal.kr/product/all/107"),
]

lines = []
for name, url in urls:
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
            title = re.search(r'<title>(.*?)</title>', html, re.I)
            t_str = title.group(1).strip() if title else ""
            og_title = re.search(r'<meta property="og:title" content="(.*?)"', html, re.I)
            og_str = og_title.group(1).strip() if og_title else ""
            lines.append(f"=== {name} ===")
            lines.append(f"Title: {t_str}")
            lines.append(f"OG Title: {og_str}\n")
    except Exception as e:
        lines.append(f"=== {name} === Error: {e}\n")

with open('product_info.txt', 'w', encoding='utf-8') as f:
    f.write("\n".join(lines))
