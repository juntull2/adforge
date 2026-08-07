from agents.base import BaseAgent
from naver_clip_adforge import NAVER_CLIP_TOP_KEYWORDS
import re

class KeywordAgent(BaseAgent):
    """
    KeywordAgent (agents/keyword.py)
    BaseAgent 상속 및 114개 황금 키워드 & 10개 맞춤 해시태그 파싱
    """
    def __init__(self):
        super().__init__("KeywordAgent")
        self.golden_keywords = NAVER_CLIP_TOP_KEYWORDS

    def run(self, context: dict) -> dict:
        product_name = context.get("product_name", "다피다 허리 찜질기")
        script_text = context.get("script_text", "")

        script_clean = script_text.strip()
        matched_keywords = []

        for item in self.golden_keywords:
            kw = item["keyword"]
            if kw in script_clean:
                matched_keywords.append(kw)

        if not matched_keywords:
            for item in self.golden_keywords:
                kw = item["keyword"]
                for part in [kw[:2], kw[-2:]]:
                    if len(part) >= 2 and part in script_clean:
                        matched_keywords.append(kw)
                        break
                if matched_keywords:
                    break

        auto_keyword = matched_keywords[0] if matched_keywords else ("허리통증" if "다피다" in product_name or "허리" in script_clean else "무릎관절운동")

        # 10개 다이나믹 맞춤 해시태그 생성 (운동, 상충 태그 반영)
        content_tags = [f"#{auto_keyword}"]
        
        if "운동" in script_clean or "뻐근" in script_clean:
            content_tags.extend(["#허리운동", "#운동후", "#스트레칭"])
        if "퇴근" in script_clean:
            content_tags.append("#퇴근후")
        if "부모님" in script_clean or "아빠" in script_clean:
            content_tags.extend(["#부모님선물", "#효도선물"])

        prod_tag = f"#{product_name.replace(' ', '')}"
        if prod_tag not in content_tags:
            content_tags.append(prod_tag)

        brand_tag = "#다피다" if "다피다" in product_name else "#파우리나"
        if brand_tag not in content_tags:
            content_tags.append(brand_tag)

        words = [w.strip() for w in re.findall(r'[가-힣]{2,}', script_clean)]
        for w in words:
            if len(content_tags) >= 10:
                break
            w_tag = f"#{w}"
            if w_tag not in content_tags and len(w) <= 8 and w not in ["사람", "느낌", "모드", "이거"]:
                content_tags.append(w_tag)

        seo_tags = " ".join(content_tags[:10])

        context["keyword"] = {
            "target_keyword": auto_keyword,
            "matched_keywords": matched_keywords[:5],
            "seo_tags": seo_tags
        }
        return context
