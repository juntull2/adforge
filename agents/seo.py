import os
import json

class SEOAgent:
    """
    SEO Agent (agents/seo.py)
    역할: 옵시디언 GUIDE-DA-01 기준 네이버 클립 5대 알고리즘 지표 빡센 자동 심사 채점 엔진 (0~100점)
    """
    def __init__(self):
        pass

    def audit_marketing_quality_strictly(self, script_text: str, target_product: str) -> dict:
        """
        자동 채점 엔진 (5개 항목 각 20점 만점)
        """
        score = 0
        details = []
        
        # Q1. 3초 훅어그로
        q1_keywords = ["퇴근", "육아", "고통", "약", "치료", "아픈", "접히는", "뻐근", "후회", "돈만"]
        q1_pass = any(kw in script_text[:40] for kw in q1_keywords)
        if q1_pass:
            score += 20
            details.append({"criterion": "Q1. 3초 훅 어그로 (타깃/결핍 키워드)", "score": 20, "max": 20, "result": "✅ 합격", "comment": "첫 3초 내 타깃의 극심한 통증/결핍 키워드가 명확히 배치됨."})
        else:
            details.append({"criterion": "Q1. 3초 훅 어그로 (타깃/결핍 키워드)", "score": 0, "max": 20, "result": "❌ 감점 (-20점)", "comment": "첫 문장이 지루합니다! '퇴근 후 허리 접히는 통증' 등 결핍 키워드를 3초 내에 선두 배치하세요."})

        # Q2. 데드존 UI 가림 (자막 길이)
        sentences = [s.strip() for s in script_text.split('.') if s.strip()]
        q2_pass = all(len(s) <= 35 for s in sentences) if sentences else True
        if q2_pass:
            score += 20
            details.append({"criterion": "Q2. 화면 하단 데드존 UI 안전성", "score": 20, "max": 20, "result": "✅ 합격", "comment": "모든 자막 문장이 35자 이내로 하단 좋아요/댓글 버튼에 가려지지 않음."})
        else:
            details.append({"criterion": "Q2. 화면 하단 데드존 UI 안전성", "score": 10, "max": 20, "result": "⚠️ 부분 감점 (-10점)", "comment": "35자가 넘는 긴 자막 문장이 존재합니다. 화면 하단 네이버 클립 UI에 가려집니다."})

        # Q3. 2~3초 속청 컷 템포
        sentence_count = len(sentences)
        q3_pass = sentence_count >= 4
        if q3_pass:
            score += 20
            details.append({"criterion": "Q3. 2~3초 속청 컷 템포 (지루함 방지)", "score": 20, "max": 20, "result": "✅ 합격", "comment": "호흡이 빠른 4개 이상의 컷/문장으로 시청 지속률(완독률) 최적화."})
        else:
            details.append({"criterion": "Q3. 2~3초 속청 컷 템포 (지루함 방지)", "score": 5, "max": 20, "result": "❌ 감점 (-15점)", "comment": "문장 길이가 길어 루즈합니다. 15초 숏폼은 2.5초마다 호흡(컷 전환)이 바뀌어야 합니다."})

        # Q4. 과한 데이터/메디컬 USP
        q4_keywords = ["원적외선", " 근적외선", "3파장", "방사율", "100W", "무소음", "속근육", "0.902", "스피드"]
        q4_pass = any(kw in script_text for kw in q4_keywords)
        if q4_pass:
            score += 20
            details.append({"criterion": "Q4. 메디컬/기술 USP 명분 (구매 명분)", "score": 20, "max": 20, "result": "✅ 합격", "comment": "단순 온열이 아닌 물리적 메디컬 차별성(원적외선/속근육 침투) 전달."})
        else:
            details.append({"criterion": "Q4. 메디컬/기술 USP 명분 (구매 명분)", "score": 0, "max": 20, "result": "❌ 감점 (-20점)", "comment": "제품의 이성적 구매 명분이 약합니다! '방사율 0.902 원적외선 속근육 침투' 등 USP를 명시하세요."})

        # Q5. 30일 환불 & CTA
        q5_keywords = ["30일", "무료", "반품", "환불", "스티커", "확인"]
        q5_pass = any(kw in script_text for kw in q5_keywords)
        if q5_pass:
            score += 20
            details.append({"criterion": "Q5. 30일 무상 환불 CTA (위험 소거)", "score": 20, "max": 20, "result": "✅ 합격", "comment": "구매 장벽을 낮추는 30일 환불 보증 및 스마트스토어 스티커 클릭 유도 포함."})
        else:
            details.append({"criterion": "Q5. 30일 무상 환불 CTA (위험 소거)", "score": 0, "max": 20, "result": "❌ 감점 (-20점)", "comment": "구매 위험 소구가 빠졌습니다! '안 맞으면 30일 100% 무상 환불 가능' 문구를 마지막에 넣으세요."})

        verdict = "🟢 [승인: 네이버 클립 상위 노출 고효율 소재]" if score >= 80 else ("🟡 [보완 필요: CVR 개선 권장 소재]" if score >= 60 else "⛔ [경고: CVR 미달 & 노출 실패 위험 소재]")

        return {
            "score": score,
            "verdict": verdict,
            "details": details
        }
