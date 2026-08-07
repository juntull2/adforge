import os
import json

class CreativeMemoryAgent:
    """
    Creative Memory Agent (agents/memory.py) - AdForge Signature Engine
    역할: 광고 성과(CTR, 완독률, 스티커 CVR)를 단순 저장이 아닌 '기억(Memory)'하고,
          고효율 Hook/CTA/해시태그 조합의 우선순위를 동적으로 조정하는 핵심 차별화 엔진.
    """
    def __init__(self, memory_file_path: str = None):
        if memory_file_path is None:
            self.memory_file_path = os.path.join(os.path.dirname(__file__), "creative_memory.json")
        else:
            self.memory_file_path = memory_file_path
        self._load_memory()

    def _load_memory(self):
        if os.path.exists(self.memory_file_path):
            try:
                with open(self.memory_file_path, "r", encoding="utf-8") as f:
                    self.memory_data = json.load(f)
            except Exception:
                self.memory_data = self._get_default_memory()
        else:
            self.memory_data = self._get_default_memory()
            self._save_memory()

    def _get_default_memory(self):
        return {
            "top_performing_hooks": [
                {"hook": "퇴근 후 허리가 아픈 게 아니라 접히는 느낌이 난다", "score_weight": 1.25, "ctr_avg": "4.8%"},
                {"hook": "허리 찜질기 괜히 싼 거 샀다가 돈만 두 번 썼음", "score_weight": 1.20, "ctr_avg": "4.5%"},
                {"hook": "방치하면 척추 속근육 더 굳습니다!", "score_weight": 1.15, "ctr_avg": "4.1%"}
            ],
            "top_performing_ctas": [
                {"cta": "안 맞으면 30일 무료 반품 가능하니 직접 써보고 결정해 보셈!", "cvr_avg": "3.2%"},
                {"cta": "아래 [상품 스티커] 누르시고 30일 무상 환불 혜택을 확인하세요!", "cvr_avg": "2.9%"}
            ],
            "top_performing_hashtags": [
                "#허리통증", "#다피다허리찜질기", "#허리운동", "#운동후", "#30일무상반품"
            ],
            "performance_logs": []
        }

    def _save_memory(self):
        try:
            with open(self.memory_file_path, "w", encoding="utf-8") as f:
                json.dump(self.memory_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Creative Memory Warning] Failed to save memory: {e}")

    def record_performance_log(self, ad_id: str, hook: str, cta: str, tags: str, ctr: float, cvr: float):
        """
        새로운 광고 성과 기록 ➡️ 고효율 훅 및 CTA 기억(Memory) 갱신
        """
        log_entry = {
            "ad_id": ad_id,
            "hook": hook,
            "cta": cta,
            "tags": tags,
            "ctr": ctr,
            "cvr": cvr
        }
        self.memory_data["performance_logs"].append(log_entry)
        
        # 성과 우수(CTR 4.0% 이상 또는 CVR 2.5% 이상) 시 기억 엔진에 우선순위 가중치 갱신
        if ctr >= 4.0:
            self.memory_data["top_performing_hooks"].append({"hook": hook, "score_weight": round(1.0 + (ctr / 20.0), 2), "ctr_avg": f"{ctr}%"})
        if cvr >= 2.5:
            self.memory_data["top_performing_ctas"].append({"cta": cta, "cvr_avg": f"{cvr}%"})

        self._save_memory()
        return log_entry

    def get_memory_insights(self) -> dict:
        """
        AI 생성 에이전트에 우선순위 가중치 공급
        """
        return {
            "top_hooks": self.memory_data.get("top_performing_hooks", []),
            "top_ctas": self.memory_data.get("top_performing_ctas", []),
            "top_hashtags": self.memory_data.get("top_performing_hashtags", []),
            "total_remembered_logs": len(self.memory_data.get("performance_logs", []))
        }
