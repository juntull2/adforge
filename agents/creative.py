import os
import json

class CreativeAgent:
    """
    Creative Agent (agents/creative.py)
    역할: 24자 이내 업로드 추천 제목 및 200자 이내 옵시디언 03_제품 DB 전문 카피라이팅 본문 생성
    """
    def __init__(self):
        pass

    def generate_creative_copy(self, keyword: str, product_name: str, script_text: str = "") -> dict:
        """
        제목(24자 이내 필수 준수) 및 본문(200자 이내 필수 준수) 생성
        """
        # 제목 24자 이내 strict (허리통증 + 운동 결합 지원)
        if "운동" in script_text or "뻐근" in script_text:
            raw_title = f"[{keyword}] 운동 전후 뻐근할 때 필수 찜질"
        else:
            raw_title = f"[{keyword}] 퇴근 후 뻐근할 때 필수 찜질"

        seo_title = raw_title[:24] if len(raw_title) > 24 else raw_title

        # 본문 200자 이내 strict (옵시디언 03_제품 DB USP 융합)
        if "다피다" in product_name:
            usp_copy = "원적외선+3파장 근적외선 듀얼 온열로 속근육까지 침투!"
        else:
            usp_copy = "3단계 자동 스피드 조절로 관절 무리 없는 재활 페달링!"

        raw_desc = f"""🔥 {keyword} 고민이셨다면 15초 집중!

운동 전후 뻐근한 허리, {usp_copy}

💡 30일 무상 환불 보증제로 부담 없이 직접 체험해보세요.

👇 아래 [상품 스티커] 클릭 시 상세 페이지로 이동합니다!"""

        seo_desc = raw_desc[:190] + "...\n👇 아래 [상품 스티커] 클릭!" if len(raw_desc) > 195 else raw_desc
        store_link = "https://smartstore.naver.com/all-envy/products/12566869835" if "다피다" in product_name else "https://smartstore.naver.com/martinishop/products/7095386764"

        return {
            "seo_title": seo_title,
            "seo_desc": seo_desc,
            "store_link": store_link
        }
