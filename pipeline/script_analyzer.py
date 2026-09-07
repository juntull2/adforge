"""
ScriptAnalyzer — 대본을 semantic beat 단위의 CreativePlan으로 변환

책임 분리:
  ScriptAnalyzer  = "무슨 말을 하는가 + 어떤 beat 단위로 나눌 것인가"
  CreativeDirector = "각 beat를 광고 관점에서 어떻게 보여줄 것인가" (자막 스타일)

이 모듈은 CreativeDirector의 자막 프리셋(ROLE_PRESETS)을 복제하지 않는다.
두 시스템이 공유하는 정보는 role뿐이며, 자막 스타일 결정은 CreativeDirector가 유지한다.

LLM 흐름:
  Script → (LLM: creative_plan.txt 프롬프트) → beats JSON → validate → CreativePlan

Fallback 흐름 (LLM 없음 / 실패):
  Script → 문장 분리 → 규칙 기반 role 추정 → emphasis 추출 → visual_intent 생성 → CreativePlan
"""

import os
import re
import json
import hashlib
import requests
from typing import Optional, List

from models.creative_plan import (
    CreativePlan, SceneBeat, CreativePlanMetadata,
    VALID_ROLES, VALID_EMOTIONS, VALID_PACING,
    VALID_SHOTS, VALID_CAMERA_MOTION, VALID_TRANSITIONS
)
from creative_director import CreativeDirector

CREATIVE_PLAN_PROMPT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "prompts", "creative_plan.txt"
)


class ScriptAnalyzer:
    """대본 → CreativePlan 변환 엔진.

    Args:
        creative_director: 기존 CreativeDirector 인스턴스(선택).
                           None이면 내부에서 기본값으로 생성.
        api_key:  OpenRouter 또는 Nvidia API 키 (없으면 fallback 모드)
        model:    LLM 모델명
        use_llm:  False로 강제하면 항상 fallback 사용 (테스트·오프라인용)
    """

    def __init__(
        self,
        creative_director: Optional[CreativeDirector] = None,
        api_key: str = "",
        model: str = "",
        use_llm: bool = True,
    ):
        # 기존 CreativeDirector를 주입받아 재사용. 중복 로직 없음.
        self.cd = creative_director or CreativeDirector(max_intensity="medium")
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        self.model = model or "nvidia/nemotron-3-super-120b-a12b:free"
        self.use_llm = use_llm

    # ================================================================
    # 메인 API
    # ================================================================

    def analyze(
        self,
        script_text: str,
        product_info: Optional[dict] = None,
        reference_style_id: Optional[str] = None,
    ) -> CreativePlan:
        """대본을 받아 CreativePlan을 반환한다.

        Args:
            script_text:       광고 대본 전문
            product_info:      제품 정보 dict (usp, target 등) — LLM 프롬프트에 맥락 제공용
            reference_style_id: 레퍼런스 스타일 프로필 ID (STEP 6에서 실제 연결)

        Returns:
            검증 완료된 CreativePlan
        """
        script_text = script_text.strip()
        if not script_text:
            return CreativePlan(metadata=CreativePlanMetadata())

        sentences = self._split_sentences(script_text)

        plan: Optional[CreativePlan] = None

        # LLM 경로
        if self.use_llm and self.api_key:
            try:
                plan = self._analyze_with_llm(script_text, sentences, product_info)
            except Exception as e:
                print(f"[ScriptAnalyzer] LLM 실패 → fallback: {e}")

        # Fallback 경로
        if plan is None:
            plan = self._analyze_fallback(sentences)
            plan.metadata.generation_method = "fallback"
        else:
            plan.metadata.generation_method = "llm"

        # 공통 메타데이터 완성
        plan.metadata.total_beats = len(plan.beats)
        plan.metadata.total_sentences = len(sentences)
        plan.metadata.reference_style_id = reference_style_id
        plan.metadata.script_hash = CreativePlan.hash_script(script_text)
        plan.metadata.estimated_duration_sec = self._estimate_duration(sentences)

        return plan

    # ================================================================
    # LLM 경로
    # ================================================================

    def _analyze_with_llm(
        self,
        script_text: str,
        sentences: List[str],
        product_info: Optional[dict],
    ) -> CreativePlan:
        """LLM에 creative_plan.txt 프롬프트를 사용해 CreativePlan JSON 요청."""

        system_prompt = self._load_prompt()
        user_prompt = self._build_user_prompt(script_text, sentences, product_info)

        is_openrouter = self.api_key.startswith("sk-or-")
        base_url = (
            "https://openrouter.ai/api/v1/chat/completions" if is_openrouter
            else "https://integrate.api.nvidia.com/v1/chat/completions"
        )
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 4096,
        }

        resp = requests.post(base_url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]

        return self._parse_llm_response(content, sentences)

    def _load_prompt(self) -> str:
        if os.path.exists(CREATIVE_PLAN_PROMPT_PATH):
            with open(CREATIVE_PLAN_PROMPT_PATH, "r", encoding="utf-8") as f:
                return f.read()
        raise FileNotFoundError(f"프롬프트 파일 없음: {CREATIVE_PLAN_PROMPT_PATH}")

    def _build_user_prompt(
        self,
        script_text: str,
        sentences: List[str],
        product_info: Optional[dict],
    ) -> str:
        lines = ["아래 광고 대본을 분석하여 Creative Plan JSON을 생성하라.\n"]

        if product_info:
            lines.append("# 제품 정보")
            for k, v in product_info.items():
                if v and k in ("target", "usp", "pain_points", "solution"):
                    lines.append(f"- {k}: {v}")
            lines.append("")

        lines.append("# 광고 대본")
        for i, s in enumerate(sentences):
            lines.append(f"[문장 {i}] {s}")
        lines.append("")
        lines.append("대본 원문:\n" + script_text)

        return "\n".join(lines)

    def _parse_llm_response(self, content: str, sentences: List[str]) -> CreativePlan:
        """LLM JSON 응답 파싱 → CreativePlan. 파싱 실패 시 Exception을 raise해서
        상위 호출자가 fallback을 발동하도록 한다."""

        # ```json ... ``` 또는 bare JSON 추출
        json_match = re.search(r'\{[\s\S]*"beats"[\s\S]*\}', content)
        if not json_match:
            raise ValueError("LLM 응답에서 beats JSON을 찾을 수 없음")

        raw = json.loads(json_match.group())
        beats_data = raw.get("beats", [])
        if not beats_data:
            raise ValueError("beats 배열이 비어있음")

        beats = []
        known_fields = set(SceneBeat.__dataclass_fields__.keys())
        for i, b in enumerate(beats_data):
            filtered = {k: v for k, v in b.items() if k in known_fields}
            beat = SceneBeat(**filtered)
            beat.validate()
            beats.append(beat)

        # 모든 문장이 최소 하나의 beat에 포함되는지 검증, 누락 시 보완
        covered = set()
        for b in beats:
            covered.update(b.sentence_indices)

        for i, s in enumerate(sentences):
            if i not in covered:
                fallback_beat = self._make_fallback_beat(s, i, len(sentences), f"b_extra_{i:02d}")
                beats.append(fallback_beat)

        beats.sort(key=lambda b: (b.sentence_indices[0] if b.sentence_indices else 999))

        return CreativePlan(beats=beats)

    # ================================================================
    # Fallback 경로 (LLM 없음)
    # ================================================================

    def _analyze_fallback(self, sentences: List[str]) -> CreativePlan:
        """규칙 기반 fallback — LLM 없이 완전한 CreativePlan 생성.

        기존 CreativeDirector._guess_role_simple()를 재사용하여
        중복 로직 없이 역할 추정.
        """
        beats = []
        n = len(sentences)

        for i, sentence in enumerate(sentences):
            # 기존 CreativeDirector의 역할 추정 로직 재사용
            role = self.cd._guess_role_simple(sentence, i, n)

            # 한 문장이 시각적으로 두 개로 분리될 만한지 판단
            sub_beats = self._try_split_sentence(sentence, i, role, n)
            beats.extend(sub_beats)

        return CreativePlan(beats=beats)

    def _try_split_sentence(
        self, sentence: str, sentence_idx: int, role: str, total: int
    ) -> List[SceneBeat]:
        """문장 내부의 semantic 분기점을 찾아 필요하면 여러 beat로 분리.

        분리 기준:
        - "에 / 이면 / 라면" 등 조건절로 분리되는 문장
        - 숫자/금액 + 행위가 있는 문장 (비용 강조 분리)
        - 7자 이하의 문장은 분리하지 않음

        분리된 경우 각 sub-beat는 같은 sentence_index를 공유한다.
        """
        s = sentence.strip()
        beats_out = []

        # 너무 짧으면 분리 없음
        if len(s) < 8:
            beat = self._make_fallback_beat(s, sentence_idx, total, f"b{len(beats_out):02d}")
            return [beat]

        # 조건절 패턴: A(이)라면 / A(이)면 / A에 → 분리 후보
        split_pattern = re.match(
            r'^(.{4,}?(?:라면|이라면|이면|에서|에게|으로|로서))\s*(.{3,})$', s
        )
        if split_pattern and len(split_pattern.group(1)) >= 4 and len(split_pattern.group(2)) >= 4:
            part_a = split_pattern.group(1).strip()
            part_b = split_pattern.group(2).strip()
            beat_a = self._make_fallback_beat(part_a, sentence_idx, total,
                                               f"b{sentence_idx:02d}a", role)
            beat_b = self._make_fallback_beat(part_b, sentence_idx, total,
                                               f"b{sentence_idx:02d}b")
            # 분리 beat의 전환은 모두 hard_cut
            beat_a.transition = "hard_cut"
            beat_b.transition = "hard_cut"
            return [beat_a, beat_b]

        # 분리 없이 단일 beat
        beat = self._make_fallback_beat(s, sentence_idx, total, f"b{sentence_idx:02d}", role)
        return [beat]

    def _make_fallback_beat(
        self,
        text: str,
        sentence_idx: int,
        total_sentences: int,
        beat_id: str = "",
        role: str = None,
    ) -> SceneBeat:
        """규칙 기반 fallback beat 생성."""
        if role is None:
            role = self.cd._guess_role_simple(text, sentence_idx, total_sentences)

        emotion = self._guess_emotion(text, role)
        visual_intent = self._guess_visual_intent(text, role)
        visual_action = self._guess_visual_action(text, role)
        importance = self._guess_importance(role, sentence_idx, total_sentences)
        pacing = self._guess_pacing(role)
        preferred_shot = self._guess_preferred_shot(role)
        camera_motion = self._guess_camera_motion(role, importance)
        transition = self._guess_transition(role, sentence_idx, total_sentences)
        emphasis = self._extract_emphasis_words(text, role)

        if not beat_id:
            beat_id = f"b{sentence_idx:02d}"

        beat = SceneBeat(
            id=beat_id,
            script=text,
            role=role,
            emotion=emotion,
            visual_intent=visual_intent,
            visual_action=visual_action,
            importance=importance,
            pacing=pacing,
            preferred_shot=preferred_shot,
            emphasis_words=emphasis,
            camera_motion=camera_motion,
            transition=transition,
            sentence_indices=[sentence_idx],
        )
        beat.validate()
        return beat

    # ================================================================
    # 규칙 기반 필드 추정 (fallback용)
    # ================================================================

    def _guess_emotion(self, text: str, role: str) -> str:
        """텍스트와 역할로 감정 추정."""
        role_emotion_map = {
            "hook": "curiosity",
            "empathy": "empathy",
            "agitate": "frustration",
            "evidence": "trust",
            "solution": "relief",
            "usp": "confidence",
            "cta": "urgency",
            "transition": "neutral",
            "normal": "neutral",
        }
        # 텍스트 키워드로 감정 보정
        pain_kw = ["아프", "힘들", "고통", "불편", "계속", "못", "안 풀", "낭비", "돈"]
        relief_kw = ["해결", "편안", "따뜻", "회복", "드디어", "이제"]
        shock_kw = ["!", "?", "엄청", "충격", "놀라"]
        fear_kw = ["위험", "악화", "더 심", "방치"]

        if any(k in text for k in pain_kw) and role in ("empathy", "agitate", "hook"):
            return "frustration"
        if any(k in text for k in relief_kw):
            return "relief"
        if any(k in text for k in shock_kw):
            return "shock"
        if any(k in text for k in fear_kw):
            return "anxiety"

        return role_emotion_map.get(role, "neutral")

    def _guess_visual_intent(self, text: str, role: str) -> str:
        """텍스트에서 시각적 의도 키워드 추출 (영문 snake_case)."""
        # 한국어 시각 의미 → 영문 변환 매핑
        intent_map = [
            (["피부과", "피부 진료", "병원", "클리닉"], "dermatology_clinic"),
            (["영수증", "비용", "돈", "결제", "청구"], "medical_bill_payment"),
            (["여드름", "피부 트러블", "피부 문제", "피부 고민"], "skin_problem_acne"),
            (["허리", "요통", "척추"], "back_pain_spine"),
            (["파스", "찜질", "온열"], "heat_therapy_patch"),
            (["어르신", "노인", "어머니", "부모님"], "elderly_person"),
            (["재활", "운동", "자전거", "페달"], "rehabilitation_exercise"),
            (["수술", "입원", "치료"], "medical_treatment"),
            (["제품", "기기", "장치", "복대"], "product_device"),
            (["구매", "지금", "클릭", "확인", "링크"], "call_to_action"),
            (["후기", "만족", "좋아", "효과"], "customer_testimony"),
            (["가격", "할인", "특가", "원"], "price_promotion"),
            (["근육", "근력", "하체", "다리"], "muscle_strength_legs"),
            (["원적외선", "근적외선", "적외선"], "infrared_therapy"),
            (["무선", "경량", "슬림"], "lightweight_wireless"),
        ]
        for keywords, intent in intent_map:
            if any(k in text for k in keywords):
                return intent

        # 역할 기반 기본값
        role_default = {
            "hook": "attention_grabbing_scene",
            "empathy": "person_in_pain_or_frustration",
            "agitate": "worsening_problem_situation",
            "evidence": "product_result_evidence",
            "solution": "product_in_use_solution",
            "usp": "product_feature_highlight",
            "cta": "call_to_action_screen",
            "normal": "general_lifestyle_scene",
            "transition": "scene_transition",
        }
        return role_default.get(role, "general_lifestyle_scene")

    def _guess_visual_action(self, text: str, role: str) -> str:
        """화면에서 일어나야 하는 동작 (영문 snake_case)."""
        action_map = [
            (["피부과", "병원"], "person_entering_clinic"),
            (["영수증", "비용", "돈", "결제"], "looking_at_expensive_bill"),
            (["여드름", "피부"], "showing_skin_problem_closeup"),
            (["허리", "통증"], "person_holding_back_in_pain"),
            (["파스", "붙이"], "applying_patch_on_back"),
            (["찜질", "온열", "열"], "using_heat_therapy_device"),
            (["어르신", "부모님", "어머니"], "elderly_person_daily_life"),
            (["운동", "자전거", "페달"], "elderly_person_exercising"),
            (["제품", "기기", "착용", "복대"], "product_demonstration_closeup"),
            (["지금", "확인", "구매", "클릭"], "showing_cta_screen_or_app"),
            (["후기", "만족", "좋다", "효과"], "happy_customer_giving_testimony"),
            (["해결", "이제", "드디어"], "person_feeling_relief"),
            (["소리", "조용", "무소음"], "demonstrating_quiet_operation"),
        ]
        for keywords, action in action_map:
            if any(k in text for k in keywords):
                return action

        role_default = {
            "hook": "dynamic_attention_grabbing_shot",
            "empathy": "person_showing_relatable_struggle",
            "agitate": "situation_getting_worse",
            "evidence": "showing_proof_or_certification",
            "solution": "demonstrating_product_solution",
            "usp": "highlighting_key_product_feature",
            "cta": "directing_viewer_to_purchase",
            "normal": "lifestyle_scene",
            "transition": "brief_cutaway",
        }
        return role_default.get(role, "lifestyle_scene")

    def _guess_importance(self, role: str, idx: int, total: int) -> float:
        """역할과 위치로 중요도 추정."""
        role_importance = {
            "hook": 0.95, "cta": 0.90, "agitate": 0.80,
            "usp": 0.75, "solution": 0.70, "evidence": 0.65,
            "empathy": 0.60, "transition": 0.30, "normal": 0.45,
        }
        base = role_importance.get(role, 0.45)
        # 첫 번째 또는 마지막 문장이면 보정
        if idx == 0:
            base = max(base, 0.85)
        elif idx == total - 1:
            base = max(base, 0.80)
        return round(base, 2)

    def _guess_pacing(self, role: str) -> str:
        return {
            "hook": "fast",
            "agitate": "fast",
            "cta": "fast",
            "usp": "medium",
            "empathy": "medium",
            "solution": "medium",
            "evidence": "slow",
            "transition": "fast",
            "normal": "medium",
        }.get(role, "medium")

    def _guess_preferred_shot(self, role: str) -> str:
        return {
            "hook": "closeup",
            "agitate": "closeup",
            "empathy": "medium",
            "solution": "product",
            "usp": "detail",
            "evidence": "detail",
            "cta": "text_overlay",
            "transition": "any",
            "normal": "medium",
        }.get(role, "any")

    def _guess_camera_motion(self, role: str, importance: float) -> str:
        """카메라 모션 — 기본 static, 높은 중요도의 hook/cta만 punch_zoom."""
        if role == "hook" and importance >= 0.9:
            return "punch_zoom"
        if role == "cta" and importance >= 0.85:
            return "subtle_zoom_in"
        if role == "usp" and importance >= 0.75:
            return "subtle_zoom_in"
        return "static"

    def _guess_transition(self, role: str, idx: int, total: int) -> str:
        """전환 — 기본 hard_cut. 파트 전환 지점(agitate→solution)에만 flash."""
        if role in ("solution", "usp") and idx > 1:
            return "flash"
        return "hard_cut"

    def _extract_emphasis_words(self, text: str, role: str) -> list:
        """핵심 강조 단어 추출 — CreativeDirector에 위임."""
        if hasattr(self.cd, "extract_emphasis_words"):
            return self.cd.extract_emphasis_words(text, role)
        return []


    # ================================================================
    # 유틸리티
    # ================================================================

    def _split_sentences(self, script_text: str) -> List[str]:
        """대본을 문장 단위로 분리 (기존 naver_clip_adforge 방식과 동일)."""
        # 구두점 기준 분리 후 개행 기준 보완
        sentences = [s.strip() for s in re.split(r'(?<=[.!?…])\s*', script_text) if s.strip()]
        if not sentences:
            sentences = [s.strip() for s in script_text.split('\n') if s.strip()]
        return sentences

    def _estimate_duration(self, sentences: List[str]) -> float:
        """대본 길이 기반 예상 영상 길이 (초) 추정.
        한국어 평균 발화 속도: 분당 약 300자 → 초당 5자
        """
        total_chars = sum(len(re.sub(r'\s', '', s)) for s in sentences)
        estimated = total_chars / 5.0
        # 최소 10초, 최대 120초로 클램핑
        return round(max(10.0, min(120.0, estimated)), 1)

    # ================================================================
    # Beat ID 재정렬 (LLM 경로 후 ID를 순서대로 재할당)
    # ================================================================

    def _renumber_beats(self, plan: CreativePlan) -> CreativePlan:
        """beat ID를 b01, b02... 순서로 재할당."""
        for i, beat in enumerate(plan.beats):
            beat.id = f"b{i+1:02d}"
        return plan
