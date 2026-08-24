import os
import json
import re
from typing import Dict, List
import requests

class TouchpointClassifier:
    @staticmethod
    def classify(keyword: str, user_touchpoint: str = None) -> str:
        if user_touchpoint and user_touchpoint != "자동 판별 (키워드 기반)":
            return user_touchpoint
            
        keyword_clean = keyword.replace(" ", "")
        
        if any(x in keyword_clean for x in ["운동", "스트레칭", "자세", "요가", "척추기립근"]):
            return "SEARCH_EXERCISE"
        elif any(x in keyword_clean for x in ["파스", "의자", "베개", "복대", "보호대", "쿠션"]):
            return "SEARCH_ALTERNATIVE_PRODUCT"
        elif any(x in keyword_clean for x in ["조사기", "온열치료", "원적외선", "적외선", "램프"]):
            return "SEARCH_INFORMATION"
        elif any(x in keyword_clean for x in ["찜질기", "온열기", "찜질팩", "마사지기"]):
            return "SEARCH_PRODUCT"
        elif any(x in keyword_clean for x in ["선물", "어버이날", "부모님", "명절", "생신"]):
            return "SEARCH_GIFT"
        elif any(x in keyword_clean for x in ["후기", "리뷰", "사용기", "내돈내산"]):
            return "SEARCH_REVIEW"
        elif any(x in keyword_clean for x in ["추천", "비교", "순위", "어떤"]):
            return "SEARCH_COMPARISON"
        elif any(x in keyword_clean for x in ["증상", "저림", "통증", "뻐근", "아플때", "오래앉으면", "무리했을때"]):
            return "SEARCH_PROBLEM"
            
        return "SEARCH_SYMPTOM" # Default

class USPSelector:
    @staticmethod
    def select_usps(touchpoint: str, intent: str, strategy: str) -> str:
        if touchpoint == "SEARCH_INFORMATION":
            return "한국원적외선협회 인증, 고방사율 원적외선, 3파장 빛"
        elif touchpoint in ["SEARCH_ALTERNATIVE_PRODUCT", "SEARCH_PROBLEM", "SEARCH_SYMPTOM"]:
            return "무선, 허리에 착용 가능, TV/집안일 하면서 사용 가능"
        elif touchpoint == "SEARCH_EXERCISE":
            return "무선, 하루 20분 관리 루틴, 허리에 착용 가능"
        elif touchpoint == "SEARCH_PRODUCT":
            return "한국원적외선협회 인증, 고방사율 원적외선, 3파장 빛, 무선"
        elif touchpoint == "SEARCH_GIFT":
            return "30일 내 반품 가능, 하루 20분 관리 루틴, 무선"
        else:
            return "무선, 고방사율 원적외선, 30일 내 반품 가능"

class ScriptValidator:
    @staticmethod
    def static_validate(script_text: str) -> Dict:
        issues = []
        titles = re.findall(r'제목:\s*(.*)', script_text)
        for t in titles:
            if len(t.strip()) > 30: # 여유있게 30자로 체크
                issues.append(f"제목 길이 초과: '{t.strip()}'")
                
        forbidden = ["치료", "완치", "없어집니다", "신경을 풀어줍니다", "속근육을 치료"]
        for f in forbidden:
            if f in script_text:
                issues.append(f"의료 과대광고 금지어 사용됨: {f}")
                
        if "다피다" not in script_text:
            issues.append("제품명(다피다) 누락됨")
            
        return {
            "passed": len(issues) == 0,
            "issues": issues
        }

class ScriptEngine:
    def __init__(self):
        self.api_key = os.environ.get("OPENROUTER_API_KEY", "")
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://adforge.ai", # OpenRouter requires referer
            "X-Title": "Adforge Script Engine",
            "Content-Type": "application/json"
        }
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
        self.model = "anthropic/claude-sonnet-5"
        
    def read_prompt(self, filename: str) -> str:
        with open(os.path.join(self.base_dir, "prompts", filename), "r", encoding="utf-8") as f:
            return f.read()

    def _call_openrouter(self, prompt_text: str, json_mode: bool = False, temperature: float = 0.7, max_tokens: int = 2500):
        # Anthropic 프롬프트 캐싱을 위해 system/user 메시지에 cache_control 명시
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt_text,
                            "cache_control": {"type": "ephemeral"} # 프롬프트 캐싱 활성화 (비용 90% 절감)
                        }
                    ]
                },
                {
                    "role": "user",
                    "content": "위 지시사항을 바탕으로 작업을 수행해주세요."
                }
            ],
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
            
        response = requests.post(self.api_url, headers=self.headers, json=payload, timeout=60)
        if response.status_code != 200:
            raise Exception(f"OpenRouter API 에러 ({response.status_code}): {response.text}")
        
        result = response.json()
        content = result["choices"][0]["message"].get("content")
        if content is None:
            raise Exception(f"OpenRouter 응답에 내용(content)이 없습니다. 전체 응답: {json.dumps(result, ensure_ascii=False)}")
        return content
        
    def _parse_json(self, content: str):
        content = content.strip()
        if content.startswith("```"):
            match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
            if match:
                content = match.group(1).strip()
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            raise Exception(f"JSON 파싱 에러. 모델 원본 텍스트:\n{content}") from e

    def analyze_intent(self, keyword, product, target, touchpoint, content_goal):
        prompt = self.read_prompt("intent_prompt.md")
        prompt = prompt.replace("{keyword}", keyword)
        prompt = prompt.replace("{product}", product)
        prompt = prompt.replace("{target}", target)
        prompt = prompt.replace("{touchpoint}", touchpoint)
        prompt = prompt.replace("{content_goal}", content_goal)
        
        content = self._call_openrouter(prompt, json_mode=True, temperature=0.7, max_tokens=1000)
        return self._parse_json(content)

    def generate_scripts(self, keyword, touchpoint, intent_data, usps, target, duration):
        prompt = self.read_prompt("generation_prompt.md")
        prompt = prompt.replace("{keyword}", keyword)
        prompt = prompt.replace("{touchpoint}", touchpoint)
        prompt = prompt.replace("{content_strategy}", intent_data.get("content_strategy", ""))
        prompt = prompt.replace("{search_intent}", intent_data.get("search_intent", ""))
        prompt = prompt.replace("{pain_point}", intent_data.get("pain_point", ""))
        prompt = prompt.replace("{usps}", usps)
        prompt = prompt.replace("{target}", target)
        prompt = prompt.replace("{duration}", str(duration))
        
        return self._call_openrouter(prompt, json_mode=False, temperature=0.8, max_tokens=2500)

    def validate_with_llm(self, script_text, static_issues):
        prompt = self.read_prompt("validation_prompt.md")
        prompt = prompt.replace("{script_text}", script_text)
        prompt = prompt.replace("{static_issues}", "\n".join(static_issues))
        
        content = self._call_openrouter(prompt, json_mode=True, temperature=0.3, max_tokens=1000)
        return self._parse_json(content)

def run_script_pipeline(keyword: str, user_touchpoint: str, product: str, target: str, content_goal: str, duration: int):
    engine = ScriptEngine()
    
    # 1. Touchpoint
    touchpoint = TouchpointClassifier.classify(keyword, user_touchpoint)
    yield {"step": "Touchpoint 분류 완료", "detail": f"[{touchpoint}]로 분류되었습니다."}
    
    # 2. Search Intent
    yield {"step": "검색 의도 분석 중...", "detail": ""}
    intent_data = engine.analyze_intent(keyword, product, target, touchpoint, content_goal)
    yield {"step": "검색 의도 분석 완료", "detail": f"핵심 고민: {intent_data.get('pain_point')}\n전략: {intent_data.get('content_strategy')}"}
    
    # 3. USP
    usps = USPSelector.select_usps(touchpoint, intent_data.get('search_intent', ''), intent_data.get('content_strategy', ''))
    
    # 4. Generate
    yield {"step": "A/B/C 대본 작성 중...", "detail": "Humanize Processor 및 전략 기반 작성 중..."}
    script_text = engine.generate_scripts(keyword, touchpoint, intent_data, usps, target, duration)
    
    # 5. Static Validation
    yield {"step": "Python 정적 검증 중...", "detail": ""}
    static_val = ScriptValidator.static_validate(script_text)
    
    if not static_val["passed"]:
        yield {"step": "LLM 재검증 및 수정 여부 판단 중...", "detail": f"사유: {', '.join(static_val['issues'])}"}
        llm_val = engine.validate_with_llm(script_text, static_val["issues"])
        
        if llm_val.get("rewrite_required", False):
            yield {"step": "대본 재작성 중...", "detail": f"수정 대상: {', '.join(llm_val.get('rewrite_targets', []))}"}
            # Regenerate simplified
            script_text = engine.generate_scripts(keyword, touchpoint, intent_data, usps, target, duration)
            
    yield {"step": "완료", "result": script_text, "intent_data": intent_data, "touchpoint": touchpoint}
