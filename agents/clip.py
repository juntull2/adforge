from agents.base import BaseAgent
import re

class ClipIntelligenceAgent(BaseAgent):
    """
    ClipIntelligenceAgent / AdForge Reverse Engineering Engine (agents/clip.py)
    BaseAgent 상속 및 네이버 클립 상위 노출 숏폼 성공 구조 역설계 파싱
    """
    def __init__(self):
        super().__init__("ClipIntelligenceAgent")

    def run(self, context: dict) -> dict:
        script_text = context.get("script_text", "")
        product_name = context.get("product_name", "다피다 허리 찜질기")

        sentences = [s.strip() for s in re.split(r'(?<=[.!?])|\n', script_text.strip()) if s.strip()]
        if not sentences:
            sentences = [script_text.strip()]

        category_labels = ["후킹/공감", "공감/통증", "기술력/효과", "대체재/차별성", "구매유도/CTA"]
        visual_guides = [
            "퇴근/육아하는 일상 모습 ➡️ 통증으로 고통스러워하는 시각적 훅 (흑백 전환)",
            "파스/기존 마사지기 사용하는 모습 ➡️ 한계점 강조 빨간 X 그래픽",
            f"{product_name} 작동 모습 클로즈업 ➡️ 속근육까지 침투하는 모션 그래픽",
            "거대한 안마의자/병원 치료 대비 3초 간편 착용 비교 교차 연출",
            "30일 무상 환불 뱃지 강조 ➡️ 프로필/스마트스토어 스티커 클릭 유도"
        ]

        script_table = []
        for idx, sentence in enumerate(sentences):
            label = category_labels[idx] if idx < len(category_labels) else category_labels[-1]
            visual = visual_guides[idx] if idx < len(visual_guides) else visual_guides[-1]
            on_screen_text = sentence[:22] + "..." if len(sentence) > 22 else sentence
            
            script_table.append({
                "구분": f"**{label}**",
                "음성 (Audio Script)": sentence,
                "화면 (Visual)": visual,
                "자막 (On-Screen Text)": on_screen_text
            })

        first_sentence = sentences[0] if sentences else script_text
        auto_kw = context.get("keyword", {}).get("target_keyword", "허리통증")
        
        marketer_notes = [
            f"**타깃 페르소나 훅 ('{auto_kw}')**: '{first_sentence[:20]}...'라는 직관적 훅으로 극초반 결핍 공감대 100% 형성.",
            f"**대체재 단점 지적**: 파스/저가 마사지기의 한계를 지적하고 {product_name}의 기술적 차별성 전달.",
            f"**자사 제품({product_name}) 트위스트 대입법**: 직장인 퇴근후 통증 ➡️ 부모님 효도선물 프레임 전환 제작 가능."
        ]

        context["clip_intelligence"] = {
            "script_table": script_table,
            "marketer_notes": marketer_notes
        }
        return context
