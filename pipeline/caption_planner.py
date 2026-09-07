"""
CaptionPlanner — EditPlan to CaptionPlan 변환 엔진 (STEP 4-2)

역할 및 책임:
1. STEP 3 EditPlan을 입력받아 STEP 4-1 CaptionPlan을 생성하는 다운스트림 계층.
2. EditPlan의 타임라인(timeline_start, timeline_end, duration)을 100% 손실 없이 보존.
3. 단어 단위 발화 타이밍(CaptionWord)을 deterministic하게 생성.
4. emphasis_words와 단어를 정밀 매칭하여 caption-os keyword index를 안전하게 추출.
5. 무효 씬(empty text, zero duration, invalid timeline) 안전한 필터링 및 디버그 추적.
"""

import os
import re
from typing import List, Dict, Tuple, Optional, Any, Set
from models.edit_plan import EditPlan, SceneEdit
from models.caption_plan import CaptionPlan, CaptionEvent, CaptionWord, VALID_CAPTION_STYLES


# -------------------------------------------------------------------
# 한국어 토크나이징 및 정규화 도우미
# -------------------------------------------------------------------

KOREAN_PARTICLES = (
    "에서는", "에게서", "으로부터", "에서",
    "으로", "까지", "부터", "에게", "한테",
    "처럼", "마다", "보다", "은", "는",
    "이", "가", "을", "를", "에", "로",
    "도", "만", "의", "와", "과", "서",
    "께", "요", "죠"
)


def normalize_token(text: str) -> str:
    """구두점 및 특수문자 제거 후 소문자화"""
    cleaned = re.sub(r'[^\w가-힣0-9a-zA-Z]', '', text)
    return cleaned.strip().lower()


def strip_korean_particles(token: str) -> str:
    """단어 끝의 조사/어미를 안전하게 제거"""
    norm = normalize_token(token)
    for p in KOREAN_PARTICLES:
        if norm.endswith(p) and len(norm) > len(p):
            stem = norm[:-len(p)]
            if len(stem) >= 1:
                return stem
    return norm


def calculate_token_speech_weight(token: str) -> float:
    """한국어 단어 발화 가중치 (글자 수 및 문장부호 반영)"""
    letters = len(re.sub(r'[\s.,!?…]', '', token))
    punct = len(re.findall(r'[,!?…]', token))
    return max(1.0, letters + (punct * 0.5))


# -------------------------------------------------------------------
# CaptionPlanner 본체
# -------------------------------------------------------------------

class CaptionPlanner:
    """광고 타임라인(EditPlan)을 바탕으로 자막 계획(CaptionPlan)을 설계하는 엔진"""

    def __init__(self):
        pass

    def build_plan(
        self,
        edit_plan: EditPlan,
        lang: str = "ko",
        metadata_override: Optional[Dict[str, Any]] = None,
    ) -> CaptionPlan:
        """EditPlan을 완전한 CaptionPlan으로 변환한다.
        
        원칙:
        - EditPlan의 timeline_start / timeline_end를 그대로 start / end로 보존한다.
        - EditPlan.duration을 CaptionPlan.duration으로 정확히 유지한다.
        - 100% 결정론적(Deterministic)으로 동작한다.
        """
        if not edit_plan or not edit_plan.scenes:
            return CaptionPlan(
                lang=lang,
                duration=0.0,
                events=[],
                metadata={"status": "empty_input"}
            )

        events: List[CaptionEvent] = []
        skipped_scenes: List[Dict[str, Any]] = []
        unmatched_log: List[Dict[str, Any]] = []

        for scene in edit_plan.scenes:
            # 텍스트 추출 (caption_text 우선, fallback으로 script)
            caption_text = (scene.caption_text or scene.script or "").strip()

            # 1. 씬 유효성 검사 및 Skip 처리
            if not caption_text:
                skipped_scenes.append({
                    "scene_id": scene.scene_id,
                    "reason": "empty caption text",
                    "start": scene.timeline_start,
                    "end": scene.timeline_end,
                })
                continue

            if scene.timeline_end < scene.timeline_start:
                skipped_scenes.append({
                    "scene_id": scene.scene_id,
                    "reason": f"invalid timeline: end ({scene.timeline_end}) < start ({scene.timeline_start})",
                    "start": scene.timeline_start,
                    "end": scene.timeline_end,
                })
                continue

            if scene.timeline_start == scene.timeline_end:
                skipped_scenes.append({
                    "scene_id": scene.scene_id,
                    "reason": "zero duration",
                    "start": scene.timeline_start,
                    "end": scene.timeline_end,
                })
                continue

            # 2. CaptionEvent 생성
            event, unmatched = self.build_event(scene, caption_text)
            if event:
                events.append(event)
                if unmatched:
                    unmatched_log.append({
                        "scene_id": scene.scene_id,
                        "unmatched": unmatched
                    })

        # 3. 시간 순서 정렬 보장 (기존 순서 존중 + timeline_start 기준)
        events.sort(key=lambda ev: (ev.start, ev.scene_id))

        # 4. 메타데이터 구성
        metadata = {
            "source": "EditPlan",
            "generator": "CaptionPlanner_v1",
            "total_scenes": len(edit_plan.scenes),
            "total_events": len(events),
            "skipped_count": len(skipped_scenes),
            "skipped_scenes": skipped_scenes,
            "unmatched_emphasis": unmatched_log,
        }
        if metadata_override:
            metadata.update(metadata_override)

        caption_plan = CaptionPlan(
            lang=lang,
            duration=round(edit_plan.duration, 3),
            events=events,
            metadata=metadata,
        )

        caption_plan.validate(raise_error=True)
        return caption_plan

    def build_event(
        self, scene: SceneEdit, caption_text: str
    ) -> Tuple[CaptionEvent, List[str]]:
        """하나의 SceneEdit로부터 CaptionEvent와 미매칭 emphasis 리스트 생성"""
        start = round(float(scene.timeline_start), 3)
        end = round(float(scene.timeline_end), 3)

        # 1. 단어 단위 발화 타이밍 생성
        words = self.build_words(caption_text, start, end)

        # 2. emphasis_words -> keywords 인덱스 매칭
        keywords, unmatched = self.match_emphasis_keywords(words, scene.emphasis_words)

        # 3. 스타일 및 위치 전달 (기존 값 보존)
        style = scene.caption_style if scene.caption_style in VALID_CAPTION_STYLES else "karaoke"
        position = scene.caption_position or "center_bottom"

        event = CaptionEvent(
            scene_id=scene.scene_id,
            start=start,
            end=end,
            text=caption_text,
            words=words,
            keywords=keywords,
            style=style,
            anchor_top=None,  # 다음 단계(스타일/계층)에서 결정
            size=None,
            font=None,
            position=position,
            role=scene.role or "normal",
            emphasis_words=list(scene.emphasis_words),
        )
        event.validate(raise_error=True)
        return event, unmatched

    def build_words(
        self, text: str, start: float, end: float
    ) -> List[CaptionWord]:
        """텍스트를 공백 기준으로 분리하고 시간 범위 [start, end]를 발화 가중치로 분배"""
        tokens = text.strip().split()
        if not tokens:
            return []

        total_duration = max(0.01, end - start)
        if len(tokens) == 1:
            return [CaptionWord(w=tokens[0], start=start, end=end)]

        weights = [calculate_token_speech_weight(t) for t in tokens]
        total_weight = sum(weights) or float(len(tokens))

        words: List[CaptionWord] = []
        cur_time = start

        for i, (token, weight) in enumerate(zip(tokens, weights)):
            if i == len(tokens) - 1:
                # 마지막 단어는 누적 오차 없이 정확히 end로 마감
                w_start = round(cur_time, 3)
                w_end = round(end, 3)
            else:
                dur_fraction = total_duration * (weight / total_weight)
                w_start = round(cur_time, 3)
                w_end = round(cur_time + dur_fraction, 3)
                cur_time += dur_fraction

            words.append(CaptionWord(w=token, start=w_start, end=w_end))

        return words

    def match_emphasis_keywords(
        self, words: List[CaptionWord], emphasis_words: List[str]
    ) -> Tuple[List[int], List[str]]:
        """emphasis_words를 단어 목록과 매칭하여 고유한 keyword 인덱스 목록 추출.
        
        규칙 (우선순위):
        1. 복합어 다중 단어 슬라이스 매칭 (Compound slice)
        2. 완전 일치 (Exact match)
        3. 구두점 제거 후 일치 (Punctuation match)
        4. 한국어 조사 제거 후 어근 일치 (Particle match)
        5. 부분 문자열 포함 일치 (Substring match, 길이 >= 2)
        """
        if not words or not emphasis_words:
            return [], []

        matched_indices: Set[int] = set()
        unmatched: List[str] = []

        norm_words = [normalize_token(w.w) for w in words]
        stem_words = [strip_korean_particles(w.w) for w in words]

        for emp in emphasis_words:
            emp_clean = emp.strip()
            if not emp_clean:
                continue

            emp_tokens = emp_clean.split()
            emp_matched = False

            # 1. 다중 단어 복합어 매칭 (예: "허리 통증")
            if len(emp_tokens) > 1:
                k = len(emp_tokens)
                emp_token_norms = [normalize_token(t) for t in emp_tokens]
                emp_token_stems = [strip_korean_particles(t) for t in emp_tokens]

                for i in range(len(words) - k + 1):
                    match_ok = True
                    for j in range(k):
                        w_idx = i + j
                        if not (
                            emp_token_norms[j] == norm_words[w_idx]
                            or emp_token_stems[j] == stem_words[w_idx]
                            or (len(emp_token_norms[j]) >= 2 and emp_token_norms[j] in norm_words[w_idx])
                        ):
                            match_ok = False
                            break
                    if match_ok:
                        for j in range(k):
                            matched_indices.add(i + j)
                        emp_matched = True

            # 2. 단일 단어 / 개별 매칭
            emp_norm = normalize_token(emp_clean)
            emp_stem = strip_korean_particles(emp_clean)

            if not emp_norm:
                continue

            for i, w in enumerate(words):
                w_norm = norm_words[i]
                w_stem = stem_words[i]

                # (a) 완전 일치 / 구두점 일치
                if emp_norm == w_norm:
                    matched_indices.add(i)
                    emp_matched = True
                    continue

                # (b) 한국어 조사 제거 일치
                if (emp_stem == w_stem) or (emp_norm == w_stem) or (emp_stem == w_norm):
                    matched_indices.add(i)
                    emp_matched = True
                    continue

                # (c) 부분 문자열 포함 (길이 2 이상)
                if len(emp_norm) >= 2 and (emp_norm in w_norm or emp_stem in w_norm):
                    matched_indices.add(i)
                    emp_matched = True
                    continue

            if not emp_matched:
                unmatched.append(emp_clean)

        # 오름차순 정렬 및 유효 인덱스 범위 확인
        keywords = sorted([idx for idx in matched_indices if 0 <= idx < len(words)])
        return keywords, unmatched

    # ---------------------------------------------------------------
    # 디버그 마크다운 리포트 생성
    # ---------------------------------------------------------------

    def generate_debug_report(
        self,
        caption_plan: CaptionPlan,
        edit_plan: EditPlan,
        path: Optional[str] = None
    ) -> str:
        """사람이 검수할 수 있는 상세 타임라인 디버그 마크다운 생성"""
        lines = [
            "# CaptionPlanner Debug Report",
            "",
            f"- **Input EditPlan Scenes**: `{len(edit_plan.scenes)}`",
            f"- **Output Caption Events**: `{len(caption_plan.events)}`",
            f"- **EditPlan Duration**: `{edit_plan.duration:.2f}s`",
            f"- **CaptionPlan Duration**: `{caption_plan.duration:.2f}s`",
            f"- **Duration Match**: `{'MATCH' if abs(edit_plan.duration - caption_plan.duration) < 1e-3 else 'MISMATCH'}`",
            "",
            "## Timeline Mapping Table",
            "",
            "| Scene | Start | End | Duration | Role | Text | Emphasis Words | Keywords | Matched Tokens |",
            "|---|---:|---:|---:|---|---|---|---|---|",
        ]

        for ev in caption_plan.events:
            kw_tokens = []
            if ev.words and ev.keywords:
                for k in ev.keywords:
                    if 0 <= k < len(ev.words):
                        kw_tokens.append(f"`{ev.words[k].w}`")
            kw_token_str = ", ".join(kw_tokens) if kw_tokens else "-"
            emp_str = ", ".join(ev.emphasis_words) if ev.emphasis_words else "-"
            kw_str = str(ev.keywords) if ev.keywords else "[]"

            lines.append(
                f"| `{ev.scene_id}` | {ev.start:.2f}s | {ev.end:.2f}s | {ev.duration:.2f}s | `{ev.role}` | \"{ev.text}\" | {emp_str} | {kw_str} | {kw_token_str} |"
            )

        # 스킵된 씬 정보
        skipped = caption_plan.metadata.get("skipped_scenes", [])
        if skipped:
            lines.extend([
                "",
                "## Skipped Scenes",
                "",
                "| Scene | Start | End | Reason |",
                "|---|---:|---:|---|",
            ])
            for s in skipped:
                lines.append(f"| `{s.get('scene_id')}` | {s.get('start', 0):.2f}s | {s.get('end', 0):.2f}s | {s.get('reason')} |")

        # 미매칭 키워드 정보
        unmatched_list = caption_plan.metadata.get("unmatched_emphasis", [])
        if unmatched_list:
            lines.extend([
                "",
                "## Unmatched Emphasis Words",
                "",
                "| Scene | Unmatched Words |",
                "|---|---|",
            ])
            for u in unmatched_list:
                lines.append(f"| `{u.get('scene_id')}` | {', '.join(u.get('unmatched', []))} |")

        text = "\n".join(lines)
        if path:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        return text
