from abc import ABC, abstractmethod
import os

class BaseAgent(ABC):
    """
    AdForge BaseAgent (agents/base.py)
    모든 에이전트가 따르는 표준 공통 인터페이스:
    BaseAgent.run(context: dict) -> dict
    """
    def __init__(self, agent_name: str):
        self.agent_name = agent_name

    def load_prompt(self, prompt_filename: str) -> str:
        """
        prompts/ 디렉토리에서 프롬프트 파일 로드
        """
        try:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            prompt_path = os.path.join(base_dir, "prompts", prompt_filename)
            if os.path.exists(prompt_path):
                with open(prompt_path, "r", encoding="utf-8") as f:
                    return f.read()
        except Exception:
            pass
        return ""

    @abstractmethod
    def run(self, context: dict) -> dict:
        """
        모든 에이전트가 공통으로 구현해야 하는 파이프라인 실행 메서드.
        context 파이프라인 객체를 받아 분석/생성 후 축적(enrich)하여 반환함.
        """
        pass
