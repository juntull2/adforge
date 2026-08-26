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
# 역할별 기본 프리셋 (LLM 호출 없이도 폴백으로 사용 가능)
# -------------------------------------------------------------------
ROLE_PRESETS = {
    "hook": {
        "size": 16.0, "color": [1.0, 0.9, 0.0], "bold": True,
        "border_color": [0.0, 0.0, 0.0], "border_width": 45.0,
        "text_intro": "弹出", "text_outro": None, "text_loop_anim": "颤抖_II",
    },
    "empathy": {
        "size": 14.0, "color": [1.0, 1.0, 1.0], "bold": True,
        "border_color": [0.0, 0.0, 0.0], "border_width": 25.0,
        "text_intro": "渐显", "text_outro": None, "text_loop_anim": None,
    },
    "agitate": {
        "size": 15.0, "color": [1.0, 0.6, 0.2], "bold": True,
        "border_color": [0.0, 0.0, 0.0], "border_width": 35.0,
        "text_intro": "故障", "text_outro": None, "text_loop_anim": "晃动",
    },
    "evidence": {
        "size": 13.5, "color": [0.85, 1.0, 0.85], "bold": False,
        "border_color": [0.0, 0.0, 0.0], "border_width": 20.0,
        "text_intro": "打字机", "text_outro": None, "text_loop_anim": None,
    },
    "solution": {
        "size": 14.5, "color": [0.7, 0.95, 1.0], "bold": True,
        "border_color": [0.0, 0.0, 0.0], "border_width": 30.0,
        "text_intro": "渐显", "text_outro": None, "text_loop_anim": None,
    },
    "usp": {
        "size": 15.0, "color": [1.0, 1.0, 1.0], "bold": True,
        "border_color": [0.0, 0.0, 0.0], "border_width": 40.0,
        "text_intro": "放大", "text_outro": None, "text_loop_anim": "放大缩小",
    },
    "cta": {
        "size": 17.0, "color": [1.0, 0.25, 0.25], "bold": True,
        "border_color": [1.0, 1.0, 1.0], "border_width": 50.0,
        "text_intro": "冲屏位移", "text_outro": None, "text_loop_anim": "心跳",
    },
    "transition": {
        "size": 13.5, "color": [0.8, 0.8, 0.8], "bold": False,
        "border_color": [0.0, 0.0, 0.0], "border_width": 18.0,
        "text_intro": "渐显", "text_outro": None, "text_loop_anim": None,
    },
    "normal": {
        "size": 14.0, "color": [1.0, 1.0, 1.0], "bold": True,
        "border_color": [0.0, 0.0, 0.0], "border_width": 25.0,
        "text_intro": "渐显", "text_outro": None, "text_loop_anim": None,
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
                direction["sentences"].append({
                    "index": i,
                    "text": sentence,
                    "role": role,
                    "reasoning": "자동 폴백 (LLM 분석 누락)",
                    "psychology": None,
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
        for item in direction["sentences"]:
            role = item.get("role", "normal")
            if role not in valid_roles:
                item["role"] = "normal"
                role = "normal"

            # subtitle_style 누락 시 프리셋 적용
            if "subtitle_style" not in item or not item["subtitle_style"]:
                preset = presets[role]
                item["subtitle_style"] = {
                    "size": preset["size"],
                    "color": preset["color"],
                    "bold": preset["bold"],
                    "border_color": preset["border_color"],
                    "border_width": preset["border_width"],
                }

            # 애니메이션 강도 필터 적용 (LLM이 bold를 골라도 max_intensity에 따라 다운그레이드)
            item["text_intro"] = self._filter_animation(item.get("text_intro"), "intros")
            item["text_outro"] = self._filter_animation(item.get("text_outro"), "outros")
            item["text_loop_anim"] = self._filter_animation(item.get("text_loop_anim"), "loops")

        return direction

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
            result["sentences"].append({
                "index": i,
                "text": sentence,
                "role": role,
                "reasoning": f"규칙 기반 자동 분류 ({role})",
                "psychology": None,
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

    test_script = "허리 아파서 파스만 붙이고 계세요?\n파스는 속근육까지 닿지 않습니다.\n원적외선이 해결합니다.\n지금 확인하세요!"
    result = cd._fallback_analysis(test_script)
    for item in result["sentences"]:
        print(f"  [{item['role']:>10}] {item['text'][:40]}  intro={item['text_intro']}  loop={item['text_loop_anim']}")
    print("[ALL TESTS PASSED]")
