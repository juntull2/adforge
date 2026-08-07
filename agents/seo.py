from agents.base import BaseAgent
from config import config

class SEOAgent(BaseAgent):
    """
    SEOAgent (agents/seo.py)
    BaseAgent 상속 및 네이버 클립 5대 알고리즘 지표 빡센 자동 심사 (0~100점)
    점수가 미달(score < 80)할 경우 피드백을 전달하여 Retry 자율 교정을 유도함.
    """
    def __init__(self):
        super().__init__("SEOAgent")
        self.prompt_template = self.load_prompt("seo.md")

    def run(self, context: dict) -> dict:
        script_text = context.get("script_text", "")
        product_name = context.get("product_name", "다피다 허리 찜질기")

        score = 0
        details = []

        # Q1. 3초 훅어그로
        q1_keywords = ["퇴근", "육아", "고통", "약", "치료", "아픈", "접히는", "뻐근", "후회", "돈만"]
        q1_pass = any(kw in script_text[:40] for kw in q1_keywords)
        if q1_pass:
            score += 20
            details.append({"criterion": "Q1. 3초 훅 어그로 (타깃/결핍 키워드)", "score": 20, "max": 20, "result": "✅ 합격", "comment": "첫 3초 내 타깃의 결핍 키워드가 선두 배치됨."})
        else:
            details.append({"criterion": "Q1. 3초 훅 어그로 (타깃/결핍 키워드)", "score": 0, "max": 20, "result": "❌ 감점 (-20점)", "comment": "첫 문장에 결핍 키워드를 선두 배치하세요."})

        # Q2. 데드존 UI 가림
        sentences = [s.strip() for s in script_text.split('.') if s.strip()]
        q2_pass = all(len(s) <= 35 for s in sentences) if sentences else True
        if q2_pass:
            score += 20
            details.append({"criterion": "Q2. 화면 하단 데드존 UI 안전성", "score": 20, "max": 20, "result": "✅ 합격", "comment": "모든 자막 문장이 35자 이내로 안전함."})
        else:
            details.append({"criterion": "Q2. 화면 하단 데드존 UI 안전성", "score": 10, "max": 20, "result": "⚠️ 부분 감점 (-10점)", "comment": "35자 이내로 자막 길이를 압축하세요."})

        # Q3. 2~3초 컷 템포
        q3_pass = len(sentences) >= 4
        if q3_pass:
            score += 20
            details.append({"criterion": "Q3. 2~3초 속청 컷 템포 (지루함 방지)", "score": 20, "max": 20, "result": "✅ 합격", "comment": "호흡이 빠른 4개 이상의 컷/문장으로 완독률 최적화."})
        else:
            details.append({"criterion": "Q3. 2~3초 속청 컷 템포 (지루함 방지)", "score": 5, "max": 20, "result": "❌ 감점 (-15점)", "comment": "2.5초마다 호흡이 바뀌도록 문장을 분할하세요."})

        # Q4. 메디컬/기술 USP
        q4_keywords = ["원적외선", "근적외선", "3파장", "방사율", "100W", "무소음", "속근육", "0.902", "스피드"]
        q4_pass = any(kw in script_text for kw in q4_keywords)
        if q4_pass:
            score += 20
            details.append({"criterion": "Q4. 메디컬/기술 USP 명분", "score": 20, "max": 20, "result": "✅ 합격", "comment": "속근육 침투/원적외선 차별성 전달."})
        else:
            details.append({"criterion": "Q4. 메디컬/기술 USP 명분", "score": 0, "max": 20, "result": "❌ 감점 (-20점)", "comment": "원적외선 속근육 침투 등 메디컬 USP를 명시하세요."})

        # Q5. 30일 환불 & CTA
        q5_keywords = ["30일", "무료", "반품", "환불", "스티커", "확인"]
        q5_pass = any(kw in script_text for kw in q5_keywords)
        if q5_pass:
            score += 20
            details.append({"criterion": "Q5. 30일 무상 환불 CTA (위험 소거)", "score": 20, "max": 20, "result": "✅ 합격", "comment": "30일 환불 보증 및 스티커 클릭 유도 포함."})
        else:
            details.append({"criterion": "Q5. 30일 무상 환불 CTA (위험 소거)", "score": 0, "max": 20, "result": "❌ 감점 (-20점)", "comment": "30일 환불 보증 문구를 마지막에 추가하세요."})

        passed = score >= config.SEO_PASS_SCORE_THRESHOLD
        verdict = "🟢 [승인: 네이버 클립 상위 노출 고효율 소재]" if passed else ("🟡 [보완 필요: CVR 개선 권장 소재]" if score >= 60 else "⛔ [경고: CVR 미달 & 노출 실패 위험 소재]")

        context["seo"] = {
            "score": score,
            "verdict": verdict,
            "audits": details
        }

        context["seo_feedback"] = {
            "passed": passed,
            "score": score,
            "correction_needed": [d["criterion"] for d in details if d["score"] < d["max"]]
        }

        return context
