from agents.base import BaseAgent
from config import config
import json

class PerformanceAgent(BaseAgent):
    """
    PerformanceAgent (agents/performance.py) - Closed-loop Learning Completion Agent
    역할: 네이버 클립 URL 또는 집행 데이터를 받아 조회수, CTR, CVR, 완독률 성과를 추적하고,
          이를 CreativeMemoryAgent로 전달하여 폐쇄형 학습 루프(Closed-loop Learning)를 완성함.
    """
    def __init__(self):
        super().__init__("PerformanceAgent")

    def run(self, context: dict) -> dict:
        clip_url = context.get("clip_url", "")
        perf_data = context.get("performance_data", {})

        # 실제 집행 성과 데이터 추적 (실제 집행 데이터가 입력되지 않았을 시 0)
        views = perf_data.get("views", 0)
        likes = perf_data.get("likes", 0)
        ctr = perf_data.get("ctr", 0.0)
        cvr = perf_data.get("cvr", 0.0)
        completion_rate = perf_data.get("completion_rate", 0.0)

        hook = context.get("script_text", "").split('.')[0] if context.get("script_text") else "퇴근 후 허리가 아픈 게 아니라 접히는 느낌이 난다"
        cta = "안 맞으면 30일 무료 반품 가능하니 직접 써보고 결정해 보셈!"
        tags = context.get("keyword", {}).get("seo_tags", "#허리통증 #다피다허리찜질기")

        performance_report = {
            "clip_url": clip_url,
            "metrics": {
                "views": views,
                "likes": likes,
                "ctr": ctr,
                "cvr": cvr,
                "completion_rate": completion_rate
            },
            "tracked_hook": hook,
            "tracked_cta": cta,
            "is_high_performer": ctr >= 4.0 or cvr >= 2.5
        }

        context["performance"] = performance_report
        return context
