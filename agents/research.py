import os
import json

class ResearchAgent:
    """
    Research Agent (agents/research.py)
    역할: 4단계 심층 리서치 파이프라인 (상품 분석 ➡️ 고객 분석 ➡️ 경쟁사 분석 ➡️ 시장 분석)
    """
    def __init__(self):
        pass

    def analyze_product_and_market(self, product_name: str, target_script: str = "") -> dict:
        """
        대상 제품 및 시장 페르소나 분석
        """
        is_dapida = "다피다" in product_name
        
        # 1. 상품 분석 (Product Analysis)
        product_info = {
            "name": product_name,
            "core_usp": "원적외선+3파장 근적외선 듀얼 온열 속근육 침투" if is_dapida else "3단계 자동 스피드 조절 관절 무리 없는 재활 페달링",
            "guarantee": "30일 무상 환불 100% 보증",
            "smartstore_url": "https://smartstore.naver.com/all-envy/products/12566869835" if is_dapida else "https://smartstore.naver.com/martinishop/products/7095386764"
        }

        # 2. 고객 페르소나 및 결핍 분석 (Customer Painpoint Analysis)
        customer_painpoints = [
            "하루 종일 앉아있는 직장인/주부의 퇴근 후 뻐근한 허리 접힘 통증",
            "일반 찜질기로 피부 겉만 데워지고 속근육 고통은 그대로인 이중지출 후회",
            "병원 재활 치료비 부담 및 거대 안마의자의 공간 차지 부담"
        ]

        # 3. 경쟁사 대체재 비교 (Competitor Analysis)
        competitor_flaws = [
            "단순 핫팩/파스: 일시적 임시방편이며 속근육 침투 불가능",
            "일반 저가 찜질기: 온열 전달 깊이 미흡 및 원적외선 미방출",
            "거대 안마의자: 집안 공간 차지 및 높은 구매 가격 부담"
        ]

        # 4. 시장 트렌드 (Market Insight)
        market_trends = {
            "trend_keyword": "홈 헬스케어 메디컬 찜질",
            "target_demographics": "3040 직장인 퇴근후 선물 / 5060 부모님 효도선물"
        }

        return {
            "product_info": product_info,
            "customer_painpoints": customer_painpoints,
            "competitor_flaws": competitor_flaws,
            "market_trends": market_trends
        }
