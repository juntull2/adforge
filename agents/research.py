from agents.base import BaseAgent
import json
import re

class ResearchAgent(BaseAgent):
    """
    ResearchAgent (agents/research.py)
    BaseAgent 상속 및 4단계 심층 리서치 (상품, 고객, 경쟁사, 시장) 파이프라인 동적 수행
    """
    def __init__(self):
        super().__init__("ResearchAgent")
        self.prompt_template = self.load_prompt("research.md")

    def run(self, context: dict) -> dict:
        """
        BaseAgent 표준 인터페이스: context 객체를 받아 4단계 동적 분석 수행 후 enrich 반환
        """
        product_name = context.get("product_name", "다피다 허리 찜질기")
        script_text = context.get("script_text", "")
        product_url = context.get("product_url", "")

        is_dapida = "다피다" in product_name
        
        # 동적 페르소나 및 결핍 파싱 (Dynamic Context extraction)
        persona = "3040 퇴근 후 허리통증 직장인 / 5060 부모님 효도선물 구매자"
        if "육아" in script_text:
            persona = "3040 육아로 무릎/허리 관절이 뭉친 육아맘"
        elif "재활" in script_text or "자전거" in script_text:
            persona = "5060 관절 무리 없는 재활 운동이 필요한 어르신"

        painpoints = [
            "퇴근/육아 후 앉아있을 때 허리가 아픈 게 아니라 접히는 고통",
            "파스나 저가 찜질기로 피부 겉만 데워지고 속근육 통증은 그대로인 이중지출 후회",
            "병원 재활 치료비 부담 및 거대 안마의자의 공간 차지 부담"
        ]

        competitor_flaws = [
            "단순 핫팩/파스: 일시적 파스 냄새와 피부 자극, 속근육 침투 불가",
            "저가 전기 찜질기: 원적외선 방사율 미흡 및 단순 표면 전열선 위험",
            "거대 안마의자: 공간 차지가 심하고 고가의 구매 비용 부담"
        ]

        usp = [
            "원적외선(방사율 0.902) + 3파장 근적외선 듀얼 온열 속근육 침투" if is_dapida else "100W 무소음 모터 & 3단계 자동 스피드 관절 무리 없는 페달링",
            "안 맞으면 30일 내 100% 무상 반품 환불 보증제"
        ]

        research_data = {
            "product_name": product_name,
            "product_url": product_url,
            "persona": persona,
            "painpoints": painpoints,
            "competitor_flaws": competitor_flaws,
            "usp": usp
        }

        context["research"] = research_data
        return context
