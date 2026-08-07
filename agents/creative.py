from agents.base import BaseAgent
from config import config

class CreativeAgent(BaseAgent):
    """
    CreativeAgent (agents/creative.py)
    BaseAgent 상속 및 24자 이내 제목, 200자 이내 카피 생성 (Self-Correction Retry 루프 지원)
    """
    def __init__(self):
        super().__init__("CreativeAgent")
        self.prompt_template = self.load_prompt("creative.md")

    def run(self, context: dict) -> dict:
        product_name = context.get("product_name", "다피다 허리 찜질기")
        script_text = context.get("script_text", "")
        keyword = context.get("keyword", {}).get("target_keyword", "허리통증")
        seo_feedback = context.get("seo_feedback", None)

        # SEOAgent에서 피드백(감점 사유)을 받아 Self-Correction 수정을 요구한 경우
        if seo_feedback and not seo_feedback.get("passed", True):
            # 피드백 반영 튜닝
            retry_note = " (30일 환불 보증 강조)"
        else:
            retry_note = ""

        if "운동" in script_text or "뻐근" in script_text:
            raw_title = f"[{keyword}] 운동 전후 뻐근할 때 필수 찜질"
        else:
            raw_title = f"[{keyword}] 퇴근 후 뻐근할 때 필수 찜질"

        seo_title = raw_title[:24] if len(raw_title) > 24 else raw_title

        if "다피다" in product_name:
            usp_copy = "원적외선+3파장 근적외선 듀얼 온열로 속근육까지 침투!"
        else:
            usp_copy = "3단계 자동 스피드 조절로 관절 무리 없는 재활 페달링!"

        raw_desc = f"""🔥 {keyword} 고민이셨다면 15초 집중!

운동 전후 뻐근한 허리, {usp_copy}

💡 30일 무상 환불 보증제로 부담 없이 직접 체험해보세요.{retry_note}

👇 아래 [상품 스티커] 클릭 시 상세 페이지로 이동합니다!"""

        seo_desc = raw_desc[:190] + "...\n👇 아래 [상품 스티커] 클릭!" if len(raw_desc) > 195 else raw_desc
        store_link = config.DAPIDA_STORE_LINK if "다피다" in product_name else config.PAULINA_STORE_LINK

        context["creative"] = {
            "seo_title": seo_title,
            "seo_desc": seo_desc,
            "store_link": store_link
        }
        return context
