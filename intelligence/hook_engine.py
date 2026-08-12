import json
from typing import List, Dict, Any
from core.schemas import ProductInfo, AudienceProfile, HookCandidate
from openai import OpenAI
from core.config import config
from core.logging import logger

class HookStrategyLibrary:
    STRATEGIES = {
        "LOSS_AVERSION": {
            "name": "손실회피 전략",
            "psychological_mechanism": "얻는 것보다 잃는 것을 더 크게 느끼는 심리 활용",
            "best_for": "가격 대비 효용, 놓치고 있는 혜택, 시간/비용 낭비 상황",
            "avoid_when": "단순 감성 위주의 브랜드 캠페인",
            "required_evidence": "구체적인 손실 내용(금액, 시간, 기회)",
            "example_patterns": ["이걸 몰라서 당신은 돈을 잃고 있을지도 모릅니다.", "올해도 똑같이 피부과에 돈을 버리실 건가요?"],
            "risk_flags": ["과장된 허위 손실 금지"]
        },
        "CURIOSITY_GAP": {
            "name": "정보 격차(Curiosity Gap)",
            "psychological_mechanism": "일부 정보를 의도적으로 숨겨 결말을 확인하고 싶게 만듦",
            "best_for": "새로운 방식, 남들이 모르는 꿀팁",
            "avoid_when": "해결책이 너무 뻔하거나 이미 다 아는 내용일 때",
            "required_evidence": "흥미로운 정보와 그에 대한 논리적 이유",
            "example_patterns": ["이 방법에는 3가지가 있는데, 대부분 마지막 1가지를 놓칩니다.", "마사지기를 샀는데 오히려 더 아픈 진짜 이유"],
            "risk_flags": ["알맹이 없는 낚시성 제목 금지"]
        },
        "PATTERN_INTERRUPT": {
            "name": "상식 파괴(Pattern Interrupt)",
            "psychological_mechanism": "기존 상식이나 통념과 반대되는 의견으로 주의를 끔",
            "best_for": "기존 제품의 문제를 해결한 혁신 제품",
            "avoid_when": "반박 근거가 빈약할 때",
            "required_evidence": "왜 기존 통념이 틀렸는지 설명할 수 있는 명확한 근거",
            "example_patterns": ["비싸야 좋은 제품이라는 생각, 꼭 맞는 건 아닙니다.", "매일 폼롤러를 하는데도 몸이 뻐근한 이유, 방식이 틀렸기 때문입니다."],
            "risk_flags": ["근거 없이 무조건 남을 깎아내리기 금지"]
        },
        "SPECIFIC_EMPATHY": {
            "name": "초정밀 타겟 공감",
            "psychological_mechanism": "'내 이야기'라고 느끼게 만드는 구체적 페르소나 설정",
            "best_for": "특정 직업군, 나이대, 상황에 맞는 맞춤형 제품",
            "avoid_when": "불특정 다수를 위한 일상 용품",
            "required_evidence": "실제 상황에서 겪는 매우 구체적인 고충",
            "example_patterns": ["아침마다 아이 깨우는 것부터 전쟁인 초등학생 부모님이라면...", "하루 8시간 앉아 일하면서 허리가 끊어질 듯 아픈 직장인 주목"],
            "risk_flags": ["너무 포괄적인 타겟팅(예: 현대인이라면 누구나) 금지"]
        },
        "AUTHORITY": {
            "name": "전문가/권위 활용",
            "psychological_mechanism": "전문성 있는 화자의 의견을 더 신뢰하는 심리",
            "best_for": "건강, 미용, 고관여 제품",
            "avoid_when": "입증 불가능한 권위",
            "required_evidence": "실제 확인 가능한 전문성 또는 경력",
            "example_patterns": ["10년차 피부과 실장이 본인 돈 주고 사는 유일한 제품", "자세 교정 전문가들이 제일 먼저 추천하는 스트레칭"],
            "risk_flags": ["실존하지 않는 허위 스펙, 거짓 경력 절대로 생성 금지"]
        },
        "SOCIAL_PROOF_FOMO": {
            "name": "사회적 증거 및 FOMO",
            "psychological_mechanism": "남들이 다 아는 것을 나만 모른다는 두려움 활용",
            "best_for": "베스트셀러, 리뷰가 많은 제품, 바이럴 제품",
            "avoid_when": "판매량이 적거나 증거가 없는 신제품",
            "required_evidence": "진짜 리뷰, 판매량, 랭킹 정보",
            "example_patterns": ["이미 10만 명이 바꾸고 있는데 아직도 옛날 방식을 쓰시나요?", "출시하자마자 품절대란 났던 그 꿀템"],
            "risk_flags": ["허위 숫자, 가짜 리뷰 생성 절대 금지"]
        },
        "SIMPLE_LIST": {
            "name": "간단한 리스트/숫자",
            "psychological_mechanism": "복잡한 정보를 간단하게 요약하여 인지적 부담을 낮춤",
            "best_for": "특장점이 여러 개인 다기능 제품",
            "avoid_when": "정보가 너무 적을 때",
            "required_evidence": "3~5개의 핵심 포인트",
            "example_patterns": ["이 선풍기 살 때 딱 3가지만 확인하세요.", "여름철 삶의 질을 수직 상승시키는 필수템 3대장"],
            "risk_flags": ["정보량을 억지로 부풀리기 금지"]
        },
        "EXPERIENCE_STORY": {
            "name": "개인 경험담 기반",
            "psychological_mechanism": "사용자의 Before & After 실제 변화 스토리에 몰입",
            "best_for": "체감 효과가 큰 일상템, 미용 기기",
            "avoid_when": "스토리가 허술하거나 제품과 무관할 때",
            "required_evidence": "실제 제품의 Before -> After 특징",
            "example_patterns": ["저도 처음엔 반신반의했는데, 딱 3일 써보고 완전히 생각이 바뀌었습니다.", "솔직히 돈 낭비일 줄 알았거든요? 근데 제 피부가 증명하네요."],
            "risk_flags": ["허구의 인위적인 감동 스토리 금지"]
        },
        "MICRO_COMMITMENT": {
            "name": "마이크로 커밋먼트 (작은 실행 단위)",
            "psychological_mechanism": "'딱 1분', '하루 5번'처럼 아주 작은 실행 단위를 제시하여 시작 저항을 제거",
            "best_for": "운동, 스트레칭, 건강 습관, 자기계발",
            "avoid_when": "제품에 반복 사용 개념이 없을 때",
            "required_evidence": "실제로 해당 시간/횟수 안에 효과를 체감할 수 있는 근거",
            "example_patterns": ["딱 5번만 해보세요. 허리가 확 달라집니다.", "1분이면 됩니다. 아침에 일어나자마자 이것만 하세요."],
            "risk_flags": ["근거 없는 숫자 임의 생성 금지"]
        }
    }

class HookEngine:
    def __init__(self, api_key: str = None, base_url: str = "https://integrate.api.nvidia.com/v1", model: str = "meta/llama-3.1-70b-instruct"):
        key = api_key or config.NVIDIA_API_KEY
        self.client = OpenAI(api_key=key, base_url=base_url)
        self.model = model

    def select_strategies(self, product: ProductInfo, audience: AudienceProfile, benchmark_patterns: List[str] = None) -> List[str]:
        """Select 2-3 most appropriate hook strategies based on product, audience, and benchmark patterns."""
        strategies_info = json.dumps(HookStrategyLibrary.STRATEGIES, ensure_ascii=False, indent=2)
        
        benchmark_hint = ""
        if benchmark_patterns:
            benchmark_hint = f"""
Benchmark Intelligence (observed patterns from successful videos in this domain):
{', '.join(benchmark_patterns)}

Consider these observed patterns when selecting strategies. These are structural patterns, not content to copy."""

        prompt = f"""You are a Hook Strategy Expert for Naver Clip short-form ads.
Given the product and audience, select the 2-3 BEST hook strategies from the library.
Do NOT write the hooks yet. Just pick the strategy IDs and explain why.

Product: {product.name} ({product.category})
Description: {product.description}
Audience: {audience.age_group} ({audience.gender}), Core Problem: {audience.core_problem}
{benchmark_hint}

Strategies Library:
{strategies_info}

Return ONLY valid JSON matching this schema:
{{
  "selected_strategies": ["STRATEGY_ID_1", "STRATEGY_ID_2"],
  "reason": "explanation here"
}}
"""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.3
        )
        try:
            result = json.loads(response.choices[0].message.content)
            strategies = result.get("selected_strategies", [])
            valid_strategies = [s for s in strategies if s in HookStrategyLibrary.STRATEGIES]
            if not valid_strategies:
                return ["SPECIFIC_EMPATHY", "MICRO_COMMITMENT"]
            return valid_strategies[:3]
        except Exception as e:
            logger.error(f"Failed to select strategies: {e}")
            return ["SPECIFIC_EMPATHY", "MICRO_COMMITMENT"]

    def generate_hook_candidates(self, product: ProductInfo, audience: AudienceProfile, strategies: List[str], benchmark_patterns: List[str] = None) -> List[HookCandidate]:
        """Generate 1 hook candidate per strategy, informed by benchmark patterns."""
        candidates = []
        
        benchmark_hint = ""
        if benchmark_patterns:
            benchmark_hint = f"""
Benchmark Intelligence (observed structural patterns from successful videos in this domain):
{', '.join(benchmark_patterns)}
Use these as structural inspiration. Do NOT copy any specific content. Create original content."""

        for strategy_id in strategies:
            strat_info = HookStrategyLibrary.STRATEGIES[strategy_id]
            prompt = f"""You are a Naver Clip short-form ad copywriter.
Write exactly ONE hook sentence (the first 3 seconds of the video) using the following strategy.

Product: {product.name} ({product.category})
Audience: {audience.age_group} ({audience.gender}), Core Problem: {audience.core_problem}
{benchmark_hint}

Strategy: {strat_info['name']}
Mechanism: {strat_info['psychological_mechanism']}
Risk to avoid: {', '.join(strat_info['risk_flags'])}
Example style: {strat_info['example_patterns'][0]}

Requirements:
- Keep it under 2 sentences, punchy and highly engaging.
- Use natural spoken Korean (~해요, ~습니다).
- Do NOT invent fake reviews, fake numbers, or fake data.
- Return ONLY valid JSON:
{{
  "hook": "The actual hook sentence",
  "reason": "Why this fits the strategy and audience"
}}
"""
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    temperature=0.7
                )
                result = json.loads(response.choices[0].message.content)
                candidates.append(HookCandidate(
                    strategy_id=strategy_id,
                    content=result.get("hook", ""),
                    reason=result.get("reason", "")
                ))
            except Exception as e:
                logger.error(f"Failed to generate hook for {strategy_id}: {e}")
        return candidates
