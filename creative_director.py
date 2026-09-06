"""
AI 크리에이티브 디렉터 엔진
- 옵시디언 볼트의 마케팅 지식을 런타임에 로딩
- LLM에게 대본을 분석시켜 연출 지시서(Creative Direction JSON) 생성
- pycapcut의 TextIntro/TextOutro/TextLoopAnim을 통해 캡컷 프로젝트에 적용
- 애니메이션 강도 등급제 (subtle/medium/bold) 로 과도한 효과 자동 차단
- 레퍼런스 영상 학습 프로필을 반영해 스타일 동적 조정
"""

import os
import json
import re
import copy
import requests
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# -------------------------------------------------------------------
# 역할별 기본 프리셋 (전문 편집자 스타일: 절제된 트랜지션, 캡슐 자막 맞춤 외곽선, 루프 애니메이션 배제)
# -------------------------------------------------------------------
ROLE_PRESETS = {
    "hook": {
        "size": 16.5, "color": [1.0, 0.9, 0.0], "bold": True,
        "border_color": [0.0, 0.0, 0.0], "border_width": 22.0,
        "text_intro": "弹出", "text_outro": None, "text_loop_anim": None,
        "video_motion": "punch_in", "transition_out": "White_Flash",
        "source_type": "hailuo_ai", "source_guide": "🤖 Hailuo 영상 권장 (스킵 방지용 시선 강탈 & 절정 동작 클로즈업)",
    },
    "empathy": {
        "size": 14.0, "color": [1.0, 1.0, 1.0], "bold": True,
        "border_color": [0.0, 0.0, 0.0], "border_width": 16.0,
        "text_intro": "渐显", "text_outro": None, "text_loop_anim": None,
        "video_motion": "slow_push", "transition_out": "none",
        "source_type": "hailuo_ai", "source_guide": "🤖 Hailuo 영상 권장 (일상 속 고통/불안/고민 상황 연출)",
    },
    "agitate": {
        "size": 14.5, "color": [1.0, 0.85, 0.7], "bold": True,
        "border_color": [0.0, 0.0, 0.0], "border_width": 18.0,
        "text_intro": "渐显", "text_outro": None, "text_loop_anim": None,
        "video_motion": "slow_push", "transition_out": "none",
        "source_type": "hailuo_ai", "source_guide": "🤖 Hailuo 영상 권장 (해결되지 않는 답답한 상황 연출)",
    },
    "evidence": {
        "size": 13.5, "color": [0.9, 1.0, 0.9], "bold": True,
        "border_color": [0.0, 0.0, 0.0], "border_width": 16.0,
        "text_intro": "渐显", "text_outro": None, "text_loop_anim": None,
        "video_motion": "pan_right", "transition_out": "none",
        "source_type": "local_photo", "source_guide": "📁 보유 사진 권장 (샤오홍슈 B/A 비교 또는 상세페이지 후기)",
    },
    "solution": {
        "size": 15.0, "color": [0.75, 0.95, 1.0], "bold": True,
        "border_color": [0.0, 0.0, 0.0], "border_width": 18.0,
        "text_intro": "弹出", "text_outro": None, "text_loop_anim": None,
        "video_motion": "slow_pull", "transition_out": "Snap_Zoom",
        "source_type": "local_photo", "source_guide": "📁 보유 사진 권장 (실제 제품 실물 누끼/언박싱/제형 컷)",
    },
    "usp": {
        "size": 14.5, "color": [1.0, 1.0, 1.0], "bold": True,
        "border_color": [0.0, 0.0, 0.0], "border_width": 18.0,
        "text_intro": "渐显", "text_outro": None, "text_loop_anim": None,
        "video_motion": "slow_push", "transition_out": "none",
        "source_type": "local_photo", "source_guide": "📁 보유 사진 권장 (상세페이지 특허 성분/원리 그래픽)",
    },
    "cta": {
        "size": 16.0, "color": [1.0, 0.9, 0.0], "bold": True,
        "border_color": [0.0, 0.0, 0.0], "border_width": 22.0,
        "text_intro": "弹出", "text_outro": None, "text_loop_anim": None,
        "video_motion": "pulse", "transition_out": "none",
        "source_type": "hailuo_ai", "source_guide": "🤖 Hailuo 영상 권장 (만족스러운 미소) + 제품 실물 컷",
    },
    "transition": {
        "size": 13.5, "color": [0.85, 0.85, 0.85], "bold": True,
        "border_color": [0.0, 0.0, 0.0], "border_width": 16.0,
        "text_intro": "渐显", "text_outro": None, "text_loop_anim": None,
        "video_motion": "punch_in", "transition_out": "Whip_Tear",
        "source_type": "hailuo_ai", "source_guide": "🤖 Hailuo 영상 권장 (분위기 반전 컷)",
    },
    "normal": {
        "size": 14.0, "color": [1.0, 1.0, 1.0], "bold": True,
        "border_color": [0.0, 0.0, 0.0], "border_width": 16.0,
        "text_intro": "渐显", "text_outro": None, "text_loop_anim": None,
        "video_motion": "slow_push", "transition_out": "none",
        "source_type": "local_photo", "source_guide": "📁 보유 사진/영상 권장",
    },
}

# -------------------------------------------------------------------
# 애니메이션 강도 등급 (subtle ≤ medium ≤ bold)
# 기본값: medium 이하만 허용
# -------------------------------------------------------------------
ANIMATION_INTENSITY = {
    "subtle": {
        "intros": [
            "渐显",      # 페이드인
            "向上滑动",  # 위로 슬라이드
            "向左滑动",  # 왼쪽 슬라이드
            "向右滑动",  # 오른쪽 슬라이드
            "模糊",      # 블러
            "打字机",    # 타자기
            "逐字",      # 글자씩 등장
            "弹出",      # 팝 등장
            "波浪弹入",  # 파도 등장
            "滑动上升",  # 슬라이드+상승
        ],
        "loops": [
            "漂浮",      # 둥둥 떠다니기
            "波浪",      # 파도
            "轻微跳动",  # 가볍게 퉁퉁
        ],
        "outros": [
            "渐隐",      # 페이드아웃
            "向上溶解",  # 위로 페이드
            "模糊",      # 블러
            "向下滑动",  # 아래로 슬라이드
        ],
    },
    "medium": {
        "intros": [
            "放大",      # 확대
            "旋入",      # 회전 진입
            "炫彩弹入",  # 화려한 팝 진입
            "向上弹入",  # 위로 토출
            "弹入跳动",  # 토출 톤톤
            "弹簧",      # 탄성 진입
            "左移弹动",  # 왼쪽 톤톤
        ],
        "loops": [
            "放大缩小",  # 확대축소
            "颤抖_II",   # 진동
            "晃动",      # 흔들림
        ],
        "outros": [
            "缩小",      # 축소
            "展开",      # 펼침
            "拖尾",      # 드래그
        ],
    },
    "bold": {
        "intros": [
            "故障",      # 글리치
            "冲屏位移",  # 화면 충돌
            "投影颤抖",  # 팔로우 흔들림 진입
        ],
        "loops": [
            "心跳",      # 심장박동
            "闪动脉冲",  # 플래시 펄스
            "爆闪",      # 폭발 플래시
        ],
        "outros": [
            "故障打字机", # 글리치 타자기
            "炸开",       # 폭발
            "电光碎裂",   # 번개 분열
        ],
    },
}

STYLE_PROFILES_DIR = os.path.join(os.path.dirname(__file__), "style_profiles")

# 옵시디언에서 읽어올 마케팅 지식 파일 목록
KNOWLEDGE_FILES = [
    "02_마케팅 개념/DA 영상 광고 및 벤치마킹.md",
    "02_마케팅 개념/마케팅축과 스토리라인.md",
    "02_마케팅 개념/설득 및 심리학 기법.md",
    "02_마케팅 개념/오가닉 100만 바이럴 숏폼 공식.md",
    "02_마케팅 개념/숏폼 편집 및 소스 구성.md",
    "02_마케팅 개념/AI 기반 광고 기획 및 대본.md",
    "02_마케팅 개념/키워드 및 타겟팅 기획.md",
]

# 프롬프트 템플릿 경로
PROMPT_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "prompts", "creative_direction.txt")


class CreativeDirector:
    """옵시디언 마케팅 지식을 기반으로 대본을 분석하고 연출 지시서를 생성하는 AI 엔진

    Args:
        vault_path: 옵시디언 볼트 경로
        max_intensity: 애니메이션 최대 강도 ("subtle" | "medium" | "bold"). 기본값 "medium"
        style_profile: 레퍼런스 학습으로 만들어진 스타일 프로필 dict
    """

    def __init__(self, vault_path: Optional[str] = None,
                 max_intensity: str = "medium",
                 style_profile: Optional[dict] = None):
        self.vault_path = vault_path or os.environ.get(
            "OBSIDIAN_VAULT_PATH",
            r"C:\Users\임준모\Documents\노리몰_가이드\Obsidian Vault"
        )
        self.max_intensity = max_intensity  # "subtle" | "medium" | "bold"
        self.style_profile = style_profile  # 레퍼런스 학습 프로필

    # -------------------------------------------------------------------
    # 애니메이션 강도 필터
    # -------------------------------------------------------------------
    def get_allowed_animations(self, category: str) -> list:
        """최대 강도(max_intensity) 이하의 허용 애니메이션 목록 반환

        Args:
            category: "intros" | "loops" | "outros"
        """
        levels = ["subtle", "medium", "bold"]
        max_idx = levels.index(self.max_intensity)
        allowed = []
        for level in levels[:max_idx + 1]:
            allowed.extend(ANIMATION_INTENSITY[level].get(category, []))
        return allowed

    def _filter_animation(self, anim_name: Optional[str], category: str) -> Optional[str]:
        """애니메이션이 허용 강도 범위 내에 있으면 그대로, 아니면 subtle 대안으로 대체"""
        if not anim_name:
            return None
        allowed = self.get_allowed_animations(category)
        if anim_name in allowed:
            return anim_name
        # 허용 안 되면 subtle 등급에서 첫 번째를 반환 (폴백)
        subtle_list = ANIMATION_INTENSITY["subtle"].get(category, [])
        return subtle_list[0] if subtle_list else None

    # -------------------------------------------------------------------
    # 레퍼런스 프로필 적용
    # -------------------------------------------------------------------
    def _apply_style_profile_to_presets(self) -> dict:
        """레퍼런스 학습 프로필이 있으면 ROLE_PRESETS를 동적으로 조정"""
        presets = copy.deepcopy(ROLE_PRESETS)

        if not self.style_profile:
            return presets

        role_styles = self.style_profile.get("role_styles", {})

        # 색상 맵핑 (Vision 분석 결과 → RGB float)
        color_map = {
            "yellow": [1.0, 0.9, 0.0],
            "white":  [1.0, 1.0, 1.0],
            "red":    [1.0, 0.25, 0.25],
            "orange": [1.0, 0.6, 0.2],
            "green":  [0.7, 1.0, 0.7],
            "blue":   [0.6, 0.85, 1.0],
            "gray":   [0.8, 0.8, 0.8],
        }
        size_map = {
            "small":  13.0,
            "medium": 14.5,
            "large":  16.0,
            "xlarge": 17.5,
        }

        for role, style in role_styles.items():
            if role not in presets:
                continue
            dom_color = style.get("dominant_color", "")
            dom_size  = style.get("dominant_size", "")
            if dom_color in color_map:
                presets[role]["color"] = color_map[dom_color]
            if dom_size in size_map:
                presets[role]["size"] = size_map[dom_size]

        return presets

    # -------------------------------------------------------------------
    # 옵시디언 마케팅 지식 로더
    # -------------------------------------------------------------------
    def load_marketing_knowledge(self) -> str:
        """옵시디언 볼트에서 마케팅 지식 .md 파일들을 읽어 하나의 컨텍스트 문자열로 반환"""
        knowledge_parts = []

        for relative_path in KNOWLEDGE_FILES:
            full_path = os.path.join(self.vault_path, relative_path)
            if os.path.exists(full_path):
                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    # YAML frontmatter 제거
                    content = re.sub(r'^---\n.*?\n---\n', '', content, flags=re.DOTALL)
                    knowledge_parts.append(f"### 📄 {os.path.basename(relative_path)}\n{content.strip()}")
                except Exception as e:
                    print(f"[CreativeDirector] 마케팅 지식 로딩 경고: {relative_path} - {e}")
            else:
                print(f"[CreativeDirector] 파일 미발견: {full_path}")

        return "\n\n---\n\n".join(knowledge_parts)

    def _load_prompt_template(self) -> str:
        """prompts/creative_direction.txt 파일에서 시스템 프롬프트 템플릿을 로드"""
        if os.path.exists(PROMPT_TEMPLATE_PATH):
            with open(PROMPT_TEMPLATE_PATH, "r", encoding="utf-8") as f:
                return f.read()
        raise FileNotFoundError(f"프롬프트 템플릿을 찾을 수 없습니다: {PROMPT_TEMPLATE_PATH}")

    def build_system_prompt(self) -> str:
        """마케팅 지식을 주입한 시스템 프롬프트 생성"""
        template = self._load_prompt_template()
        knowledge = self.load_marketing_knowledge()
        return template.replace("{marketing_knowledge}", knowledge)

    # -------------------------------------------------------------------
    # LLM 대본 분석 (OpenRouter → Nvidia 폴백)
    # -------------------------------------------------------------------
    def analyze_script(self, script_text: str, api_key: str = "", model: str = "") -> dict:
        """LLM에 대본을 보내 연출 지시서 JSON을 받아옴.

        Args:
            script_text: 광고 대본 텍스트
            api_key: OpenRouter 또는 Nvidia API 키
            model: 사용할 LLM 모델명

        Returns:
            연출 지시서 dict {"sentences": [...]}
        """
        if not api_key:
            api_key = os.environ.get("OPENROUTER_API_KEY", "")
        if not model:
            model = "nvidia/nemotron-3-super-120b-a12b:free"
        if not api_key:
            print("[CreativeDirector] API 키 없음 — 프리셋 기반 폴백 모드")
            return self._fallback_analysis(script_text)

        system_prompt = self.build_system_prompt()

        # 문장 분리 (구두점 기준)
        sentences = [s.strip() for s in re.split(r'(?<=[.!?…])', script_text) if s.strip()]
        if not sentences:
            sentences = [s.strip() for s in script_text.split('\n') if s.strip()]

        user_prompt = f"아래 광고 대본을 분석하여 연출 지시서를 JSON으로 작성해주세요.\n\n대본 ({len(sentences)}개 문장):\n"
        for i, s in enumerate(sentences):
            user_prompt += f"[{i}] {s}\n"

        # API 엔드포인트 결정 (OpenRouter vs Nvidia)
        is_openrouter = api_key.startswith("sk-or-")
        base_url = (
            "https://openrouter.ai/api/v1/chat/completions" if is_openrouter
            else "https://integrate.api.nvidia.com/v1/chat/completions"
        )
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 4096,
        }

        try:
            response = requests.post(base_url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            result = response.json()

            content = result["choices"][0]["message"]["content"]

            # JSON 블록 추출 (LLM이 ```json ... ``` 로 감쌀 수 있으므로)
            json_match = re.search(r'\{[\s\S]*"sentences"[\s\S]*\}', content)
            if json_match:
                direction = json.loads(json_match.group())
            else:
                direction = json.loads(content)

            # 유효성 검증 및 보정 + 강도 필터
            direction = self._validate_and_fix(direction, sentences)
            return direction

        except requests.exceptions.RequestException as e:
            print(f"[CreativeDirector] API 호출 실패: {e}")
            return self._fallback_analysis(script_text)
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            print(f"[CreativeDirector] JSON 파싱 실패: {e}")
            return self._fallback_analysis(script_text)

    # -------------------------------------------------------------------
    # 검증 및 보정
    # -------------------------------------------------------------------
    def _validate_and_fix(self, direction: dict, sentences: list) -> dict:
        """LLM 출력을 검증하고 누락/잘못된 부분을 프리셋으로 보정 + 강도 필터 적용"""
        valid_roles = set(ROLE_PRESETS.keys())
        presets = self._apply_style_profile_to_presets()  # 레퍼런스 프로필 반영

        if "sentences" not in direction:
            direction = {"sentences": []}

        # 문장 수가 부족하면 채우기
        existing_indices = {item.get("index", -1) for item in direction["sentences"]}
        for i, sentence in enumerate(sentences):
            if i not in existing_indices:
                role = self._guess_role_simple(sentence, i, len(sentences))
                preset = presets[role]
                src_type, src_guide, h_prompt, h_vars = self.generate_hailuo_prompt(sentence, role)
                direction["sentences"].append({
                    "index": i,
                    "text": sentence,
                    "role": role,
                    "reasoning": "자동 폴백 (LLM 분석 누락)",
                    "psychology": None,
                    "video_motion": preset.get("video_motion", "slow_push"),
                    "transition_out": "none" if i == len(sentences) - 1 else preset.get("transition_out", "none"),
                    "source_type": src_type,
                    "source_guide": src_guide,
                    "hailuo_prompt": h_prompt,
                    "hook_variations": h_vars,
                    "subtitle_style": {
                        "size": preset["size"],
                        "color": preset["color"],
                        "bold": preset["bold"],
                        "border_color": preset["border_color"],
                        "border_width": preset["border_width"],
                    },
                    "text_intro": self._filter_animation(preset["text_intro"], "intros"),
                    "text_outro": self._filter_animation(preset["text_outro"], "outros"),
                    "text_loop_anim": self._filter_animation(preset["text_loop_anim"], "loops"),
                })

        # 인덱스 순 정렬
        direction["sentences"].sort(key=lambda x: x.get("index", 0))

        # 각 항목 유효성 보정 + 강도 필터
        total_s = len(direction["sentences"])
        for idx, item in enumerate(direction["sentences"]):
            role = item.get("role", "normal")
            if role not in valid_roles:
                item["role"] = "normal"
                role = "normal"

            preset = presets[role]

            # 비디오 모션 및 트랜지션 보정
            if "video_motion" not in item or not item["video_motion"]:
                item["video_motion"] = preset.get("video_motion", "slow_push")

            if idx == total_s - 1:
                item["transition_out"] = "none"
            elif "transition_out" not in item or not item["transition_out"]:
                item["transition_out"] = preset.get("transition_out", "none")

            # 소스 추천 및 Hailuo 프롬프트 누락 시 자동 보충
            if "source_type" not in item or not item["source_type"] or "hailuo_prompt" not in item or not item["hailuo_prompt"]:
                src_type, src_guide, h_prompt, h_vars = self.generate_hailuo_prompt(item.get("text", ""), role)
                item["source_type"] = item.get("source_type") or src_type
                item["source_guide"] = item.get("source_guide") or src_guide
                item["hailuo_prompt"] = item.get("hailuo_prompt") or h_prompt
                if role == "hook" and not item.get("hook_variations"):
                    item["hook_variations"] = h_vars

            # subtitle_style 누락 시 프리셋 적용
            if "subtitle_style" not in item or not item["subtitle_style"]:
                item["subtitle_style"] = {
                    "size": preset["size"],
                    "color": preset["color"],
                    "bold": preset["bold"],
                    "border_color": preset["border_color"],
                    "border_width": preset["border_width"],
                }
            else:
                # LLM이 과도하게 두꺼운 외곽선 지정 시 캡슐 배경에 맞춰 정제
                if "border_width" in item["subtitle_style"]:
                    item["subtitle_style"]["border_width"] = min(float(item["subtitle_style"]["border_width"]), 22.0)

            # 애니메이션 강도 필터 적용
            item["text_intro"] = self._filter_animation(item.get("text_intro"), "intros")
            item["text_outro"] = self._filter_animation(item.get("text_outro"), "outros")
            # 전문 편집자 원칙: 자막 떨림/루프 애니메이션 전면 배제 (가독성 및 모던 룩 보장)
            item["text_loop_anim"] = None

        return direction

    @staticmethod
    def generate_hailuo_prompt(sentence: str, role: str) -> tuple:
        """Hailuo AI 공식 6-Block 공식 및 마케팅 인사이트(인버티드 프롬프트/렌즈 명시/피부 질감) 기반 프롬프트 생성

        Returns:
            (source_type, source_guide, hailuo_prompt, hook_variations)
        """
        s = sentence.lower()

        # 도메인 감지 (뷰티/피부 vs 허리/통증 vs 다이어트/체형 vs 일반)
        is_skin = any(kw in s for kw in ["여드름", "트러블", "피부", "모공", "흉터", "각질", "세안", "붉은", "진정", "시카", "화장", "기초", "세럼", "크림", "톤"])
        is_pain = any(kw in s for kw in ["허리", "파스", "속근육", "통증", "찜질", "결림", "어깨", "목", "근육", "쑤시", "아프", "뻐근"])
        is_diet = any(kw in s for kw in ["붓기", "살", "다이어트", "체중", "뱃살", "라인", "감량", "식단", "부종"])

        hook_variations = None

        if role == "hook":
            source_type = "hailuo_ai"
            source_guide = "🤖 Hailuo 영상 권장 (스킵 방지용 시선 강탈 & 절정 동작 클로즈업)"
            if is_skin:
                if any(kw in s for kw in ["의사", "전문의", "피부과", "싫어", "폐업"]):
                    # 6869 레퍼런스 스타일: 피부과 전문의 정면 클로즈업 훅
                    hailuo_prompt = (
                        "Shot on 85mm at f/2.8, eye level, subtle handheld sway, starting mid-action: "
                        "an authentic 30s East Asian male dermatologist wearing white doctor gown, surgical cap and light blue medical mask looking serious directly into camera, "
                        "bright modern dermatology clinic examination room background, visible skin texture, authentic clinical atmosphere, cinematic 9:16 vertical video"
                    )
                elif any(kw in s for kw in ["남자", "남성", "곰보", "패인", "연애", "살렸"]):
                    # 6868 레퍼런스 스타일: 20대 남성 패인 흉터 리얼 스토리 훅
                    hailuo_prompt = (
                        "Shot on 85mm at f/2.8, subtle handheld camera sway, starting mid-action: "
                        "a distressed 20s East Asian young man with visible red pitted acne scars on cheek touching face in mirror with genuine frustration, "
                        "warm modern bathroom interior, soft morning daylight, visible skin pores, natural flyaway hair, cinematic 9:16 vertical video"
                    )
                else:
                    hailuo_prompt = (
                        "Shot on 85mm at f/2.8, subtle handheld camera sway, starting mid-action: "
                        "a distressed 20s East Asian woman looking into bathroom vanity mirror and gently pressing a red blemish on cheek with a frustrated grimace, "
                        "warm modern bathroom interior, soft morning window daylight mixed with vanity mirror lights, "
                        "visible skin pores, authentic skin texture, natural flyaway hair, cinematic 9:16 vertical video"
                    )

                hook_variations = {
                    "var_a": "Shot on 85mm at f/2.8, eye level, subtle sway: an authentic 30s East Asian male dermatologist in white gown, surgical cap and mask looking serious directly at camera, modern clinic background, visible skin texture, 9:16 vertical video",
                    "var_b": "Shot on 85mm at f/2.8, subtle handheld, starting mid-action: a 20s East Asian young man with visible red pitted acne scars on cheek looking into bathroom mirror with genuine emotional distress, visible skin pores, 9:16 vertical video",
                    "var_c": "Shot on 85mm at f/2.8, subtle handheld sway: a worried 20s East Asian woman touching red blemish on cheek looking into bathroom mirror, soft morning light, visible skin pores, authentic skin texture, 9:16 vertical video"
                }
            elif is_pain:
                hailuo_prompt = (
                    "Shot on 85mm at f/2.8, subtle handheld camera sway, starting mid-action: "
                    "a tired 30s East Asian person standing in living room clutching lower back with a painful grimace, "
                    "cozy home interior, warm afternoon window light, "
                    "authentic micro-expression of physical tension, natural documentary movement, cinematic 9:16 vertical video"
                )
                hook_variations = {
                    "var_a": "Shot on 85mm at f/2.8, handheld sway, starting mid-action: a 30s East Asian person suddenly grimacing and holding lower back while standing up from chair, warm living room light, authentic expression, 9:16 vertical video",
                    "var_b": "Shot on 50mm lens, close-up, starting mid-action: hands awkwardly trying to slap a pain relief patch onto lower back with a groan of frustration, realistic home setting, 9:16 vertical video",
                    "var_c": "Shot on 85mm at f/2.8, direct address, starting mid-action: a person looking into camera rubbing lower back with an exhausted look, asking an honest question, natural room light, 9:16 vertical video"
                }
            elif is_diet:
                hailuo_prompt = (
                    "Shot on 50mm lens, subtle handheld camera sway, starting mid-action: "
                    "a 20s East Asian woman looking in a full-length mirror gently pinching her waist with a troubled sigh, "
                    "bright morning bedroom, soft sunlight through sheer curtains, "
                    "authentic expression, natural body motion, cinematic 9:16 vertical video"
                )
                hook_variations = {
                    "var_a": "Shot on 50mm lens, subtle handheld, starting mid-action: a woman checking morning face swelling in mirror with a concerned frown, bright natural morning light, 9:16 vertical video",
                    "var_b": "Shot on 50mm lens, close-up, starting mid-action: trying to button tight jeans and exhaling with frustration, authentic lifestyle setting, 9:16 vertical video",
                    "var_c": "Shot on 85mm at f/2.8, direct address, starting mid-action: a relatable young woman looking directly into camera with an exasperated smile, natural room light, 9:16 vertical video"
                }
            else:
                hailuo_prompt = (
                    "Shot on 85mm at f/2.8, subtle handheld camera sway, starting mid-action: "
                    "a relatable 20s East Asian person reacting with surprise and intense curiosity, looking into camera, "
                    "modern lifestyle interior, warm cinematic lighting, authentic micro-expressions, cinematic 9:16 vertical video"
                )
                hook_variations = {
                    "var_a": "Shot on 85mm at f/2.8, subtle handheld, starting mid-action: a person reacting with eyes widening in disbelief, authentic indoor lighting, 9:16 vertical video",
                    "var_b": "Shot on 50mm lens, close-up, starting mid-action: an everyday person shaking head in frustration over a common problem, natural home setting, 9:16 vertical video",
                    "var_c": "Shot on 85mm at f/2.8, direct address, starting mid-action: person looking into camera gesturing eagerly to ask a direct question, warm soft light, 9:16 vertical video"
                }
        elif role in ["empathy", "agitate"]:
            source_type = "hailuo_ai"
            source_guide = "🤖 Hailuo 영상 권장 (일상 속 고통/불안/고민 상황 연출)"
            if is_skin:
                hailuo_prompt = (
                    "Shot on 50mm lens, subtle handheld camera sway, starting mid-action: "
                    "an everyday 20s East Asian woman touching irritated facial skin with a worried sigh, "
                    "cozy bedroom vanity setting, soft warm ambient lighting, "
                    "visible skin pores, authentic skin texture, cinematic 9:16 vertical video"
                )
            elif is_pain:
                hailuo_prompt = (
                    "Shot on 50mm lens, subtle handheld camera sway, starting mid-action: "
                    "a middle-aged person working at desk repeatedly massaging neck and lower back with stiff motion, "
                    "soft home office lighting, natural exhaustion expression, cinematic 9:16 vertical video"
                )
            else:
                hailuo_prompt = (
                    "Shot on 50mm lens, subtle handheld camera sway, starting mid-action: "
                    "a relatable East Asian person looking tired and exasperated with routine problems, "
                    "realistic everyday home interior, soft natural room lighting, cinematic 9:16 vertical video"
                )
        elif role in ["solution", "usp"]:
            source_type = "local_photo"
            source_guide = "📁 보유 사진 권장 (실제 제품 실물 누끼/언박싱/제형 컷 — 켄번스 줌인 적용)"
            if is_skin:
                hailuo_prompt = (
                    "Shot on 85mm macro lens at f/2.8, slow push-in, "
                    "a clean glass dropper dispensing a soothing skincare serum droplet falling onto glowing clear surface, "
                    "bright clean studio lighting, soft light refraction, shallow depth of field, 4k texture, cinematic 9:16 vertical video"
                )
            elif is_pain:
                hailuo_prompt = (
                    "Shot on 85mm macro lens at f/2.8, slow push-in, "
                    "a sleek modern heating therapy device emitting soothing warm red infrared light glow, "
                    "high-end studio presentation, soft gradient background, cinematic 9:16 vertical video"
                )
            else:
                hailuo_prompt = (
                    "Shot on 85mm macro lens at f/2.8, slow push-in, "
                    "cinematic product presentation with elegant lighting sweep across surface, "
                    "clean minimalist studio backdrop, shallow depth of field, cinematic 9:16 vertical video"
                )
        elif role == "evidence":
            source_type = "local_photo"
            source_guide = "📁 보유 사진 권장 (샤오홍슈 B/A 비교 또는 상세페이지 시험 성적서/후기)"
            if is_skin:
                hailuo_prompt = (
                    "Shot on 50mm lens, locked-off shot, clean clinical laboratory background, "
                    "macro scientific side-by-side skin inspection, bright diffused lighting, authentic skin pores, cinematic 9:16 vertical video"
                )
            else:
                hailuo_prompt = (
                    "Shot on 50mm lens, locked-off shot, clean professional aesthetic, "
                    "clear documentary proof and test result demonstration, bright diffused laboratory lighting, cinematic 9:16 vertical video"
                )
        elif role == "cta":
            source_type = "hailuo_ai"
            source_guide = "🤖 Hailuo 영상 권장 (만족스러운 미소/개선된 일상) + 제품 실물 컷"
            if is_skin:
                hailuo_prompt = (
                    "Shot on 85mm at f/2.8, slow push-in, "
                    "a radiant 20s East Asian woman smiling with glowing clear skin, touching smooth cheek with pure joy, "
                    "warm golden hour sunlight streaming in, genuine cheerful smile, authentic skin texture, cinematic 9:16 vertical video"
                )
            elif is_pain:
                hailuo_prompt = (
                    "Shot on 85mm at f/2.8, slow push-in, "
                    "a relieved 30s East Asian person stretching comfortably with a happy relaxed smile, "
                    "bright morning sunlit living room, genuine feeling of relief and energy, cinematic 9:16 vertical video"
                )
            else:
                hailuo_prompt = (
                    "Shot on 85mm at f/2.8, slow push-in, "
                    "a confident happy person smiling warmly into camera with satisfaction, "
                    "bright inviting lifestyle interior, golden hour backlight, cinematic 9:16 vertical video"
                )
        else:  # transition / normal
            source_type = "hailuo_ai" if role == "transition" else "local_photo"
            source_guide = "🤖 Hailuo 영상 권장 (분위기 반전 컷)" if role == "transition" else "📁 보유 사진/영상 권장"
            hailuo_prompt = (
                "Shot on 50mm lens, subtle handheld camera sway, starting mid-action: "
                "an everyday East Asian person paused thoughtfully with a sudden realization, "
                "warm natural room lighting, authentic micro-expression, cinematic 9:16 vertical video"
            )

        return source_type, source_guide, hailuo_prompt, hook_variations

    def _guess_role_simple(self, sentence: str, index: int, total: int) -> str:
        """LLM 없이 간단한 규칙으로 역할 추정 (폴백용)"""
        s = sentence.strip()

        if index == 0:
            return "hook"
        if index >= total - 1:
            return "cta"

        cta_keywords = ["지금", "확인", "링크", "클릭", "바로", "검색", "구매", "주문"]
        if any(kw in s for kw in cta_keywords):
            return "cta"

        question_endings = ["?", "세요?", "까요?", "나요?", "죠?"]
        if any(s.endswith(q) for q in question_endings):
            if index <= 1:
                return "hook"
            return "empathy"

        evidence_keywords = ["실제", "후기", "만족", "%", "인증", "특허", "시험", "데이터"]
        if any(kw in s for kw in evidence_keywords):
            return "evidence"

        agitate_keywords = ["아깝", "낭비", "계속", "또", "여전히", "안 풀", "못"]
        if any(kw in s for kw in agitate_keywords):
            return "agitate"

        usp_keywords = ["유일", "최초", "특허", "인증", "듀얼", "3파장", "무선"]
        if any(kw in s for kw in usp_keywords):
            return "usp"

        solution_keywords = ["해결", "덕분", "이제", "드디어", "가능"]
        if any(kw in s for kw in solution_keywords):
            return "solution"

        return "normal"

    def _fallback_analysis(self, script_text: str) -> dict:
        """LLM 호출 없이 규칙 기반으로 연출 지시서 생성 + 강도 필터 + 레퍼런스 프로필 반영"""
        sentences = [s.strip() for s in re.split(r'(?<=[.!?…])', script_text) if s.strip()]
        if not sentences:
            sentences = [s.strip() for s in script_text.split('\n') if s.strip()]

        presets = self._apply_style_profile_to_presets()
        result = {"sentences": []}
        for i, sentence in enumerate(sentences):
            role = self._guess_role_simple(sentence, i, len(sentences))
            preset = presets[role]
            is_last = (i == len(sentences) - 1)
            src_type, src_guide, h_prompt, h_vars = self.generate_hailuo_prompt(sentence, role)
            result["sentences"].append({
                "index": i,
                "text": sentence,
                "role": role,
                "reasoning": f"규칙 기반 자동 분류 ({role})",
                "psychology": None,
                "video_motion": preset.get("video_motion", "slow_push"),
                "transition_out": "none" if is_last else preset.get("transition_out", "none"),
                "source_type": src_type,
                "source_guide": src_guide,
                "hailuo_prompt": h_prompt,
                "hook_variations": h_vars,
                "subtitle_style": {
                    "size": preset["size"],
                    "color": preset["color"],
                    "bold": preset["bold"],
                    "border_color": preset["border_color"],
                    "border_width": preset["border_width"],
                },
                # 강도 필터 적용
                "text_intro": self._filter_animation(preset["text_intro"], "intros"),
                "text_outro": self._filter_animation(preset["text_outro"], "outros"),
                "text_loop_anim": self._filter_animation(preset["text_loop_anim"], "loops"),
            })
        return result

    def get_preset(self, role: str) -> dict:
        """특정 역할의 프리셋 반환"""
        return ROLE_PRESETS.get(role, ROLE_PRESETS["normal"])


# -------------------------------------------------------------------
# CLI 테스트용
# -------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    cd = CreativeDirector(max_intensity="medium")

    knowledge = cd.load_marketing_knowledge()
    print(f"[테스트] 마케팅 지식 로딩: {len(knowledge):,}자")
    print(f"[테스트] medium 이하 허용 인트로: {cd.get_allowed_animations('intros')}")

    test_script = "아직도 여드름을 손으로 짜고 계신가요?\n손톱 세균 때문에 흉터만 더 붉어집니다.\n특허받은 시카 성분이 피부 속 깊이 진정시킵니다.\n3일 만에 가라앉은 실제 피부 변화를 확인하세요.\n지금 프로필 링크에서 만나보세요!"
    result = cd._fallback_analysis(test_script)
    for item in result["sentences"]:
        print(f"  [{item['role']:>10}] {item['text'][:35]} | 소스: {item['source_type']} | 가이드: {item['source_guide']}")
        print(f"     🎬 Hailuo: {item['hailuo_prompt'][:70]}...")
        if item.get("hook_variations"):
            print(f"     🎯 Hook Variations: {list(item['hook_variations'].keys())}")
    print("[ALL TESTS PASSED]")

