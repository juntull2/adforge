"""Let an LLM read the whole script and pick context-fitting sources for each cut.

Only the script text and relative source labels (source folder name + relative
file path, never absolute paths) are sent. The model can only answer with ids
from the catalog; unknown ids are dropped and those cuts keep the rule-based
ranking from local_media_selector.
"""

import json
import re
import time
from collections import Counter
from typing import Dict, List, Sequence, Tuple

import requests

from pipeline.local_media_selector import ROLE_LABELS, MediaItem

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
MAX_IDS_PER_CUT = 3
MAX_CANDIDATES = 6

# NVIDIA-hosted models that answered for an nvapi- key on 2026-09-29, in fallback order.
# NVIDIA retires hosted models on a schedule (HTTP 410 "reached its end of life") and
# some ids are not enabled for every account (HTTP 404), so a dead pick falls through.
NVIDIA_MODELS = (
    "moonshotai/kimi-k3",                 # ~25s for 12 cuts, Korean reasons
    "nvidia/nemotron-3-super-120b-a12b",  # ~28s, occasionally 503 overloaded
    "deepseek-ai/deepseek-v4.1-flash",    # answers, but took over 60s on this task
)
# The whole AI step (all fallbacks together) gives up after this many seconds.
TOTAL_TIMEOUT_SEC = 240
# 404: not enabled for this account, 410: retired, 503: temporarily overloaded
_TRY_NEXT_STATUS = {404, 410, 503}


class _TryNextModel(Exception):
    """This model cannot answer right now; another model may."""

_PROMPT = """너는 숏폼 광고 영상 편집자야. [대본 컷]은 나레이션을 컷 단위로 나눈 것이고, 컷마다 화면에 소스 하나가 나와(컷 하나는 최대 3초).
대본 전체 흐름(후킹 → 문제·공감 → 해결·제품 → 결과 → 구매 유도)과 각 컷이 말하는 내용을 파악해서, [소스 목록]에서 그 순간 화면에 가장 어울리는 소스를 골라.

규칙
- [소스 목록]의 id만 써. 소스 설명은 파일명과 폴더명이야.
- 컷마다 어울리는 순서대로 id를 최대 3개 골라. 첫 번째가 실제로 쓰일 소스야.
- 대사에 단어가 직접 없어도 문맥을 반영해. 예: "이거 하나로 끝냈어요"의 "이거"는 제품을 가리켜.
- 바로 앞 컷과 같은 소스를 첫 번째로 고르지 말고, 같은 소스를 여러 컷에 반복하는 것도 줄여.
- 컷 길이보다 짧은 영상은 가능하면 피해.
- 장면 역할(후킹/문제/결과/구매 유도/본문)에 맞는 분위기의 소스를 우선해.
- why는 한국어로 20자 안팎의 짧은 이유만 써.
- 설명 없이 JSON만 출력해. 형식: {"cuts":[{"cut":"c0","ids":["a3","g1"],"why":"짧은 이유"}]}

[대본 컷]
<<CUTS>>

[소스 목록]
<<SOURCES>>"""


def _endpoint(api_key: str, model: str) -> Tuple[str, List[str]]:
    """Endpoint and the models to try in order (the selected one first)."""
    if api_key.startswith("sk-or-"):
        return OPENROUTER_URL, [model or "openai/gpt-4o-mini"]
    if api_key.startswith("nvapi-"):
        first = model or NVIDIA_MODELS[0]
        return NVIDIA_URL, [first] + [m for m in NVIDIA_MODELS if m != first]
    # Plain OpenAI keys: provider-prefixed names from the other model lists do not apply.
    return OPENAI_URL, [model if model and "/" not in model else "gpt-4o-mini"]


def _error_detail(response) -> str:
    try:
        data = response.json()
    except ValueError:
        data = None
    detail = ""
    if isinstance(data, dict):
        error = data.get("error")
        detail = (error.get("message") if isinstance(error, dict) else error) or data.get("detail") or data.get("title")
    detail = str(detail or response.text or response.reason or "")
    return re.sub(r"\s*for account '[^']*'", "", detail)[:160]


def _catalog_entries(catalog: Sequence[MediaItem]) -> List[dict]:
    """One line per named file; numbered files collapse into one line per folder."""
    entries: List[dict] = []
    groups: Dict[str, List[MediaItem]] = {}
    for item in catalog:
        if item.group:
            groups.setdefault(item.group, []).append(item)
            continue
        kind = f"영상 {item.duration_sec:.1f}초" if item.media_type == "video" else "사진"
        entries.append({"id": f"a{len(entries)}", "line": f"{kind} | {item.label}", "paths": [item.path]})
    for number, (group, members) in enumerate(groups.items()):
        counts = Counter(member.media_type for member in members)
        kinds = " + ".join(f"{'영상' if kind == 'video' else '사진'} {count}개"
                           for kind, count in sorted(counts.items(), reverse=True))
        entries.append({"id": f"g{number}", "line": f"{kinds} 묶음 | {group}/",
                        "paths": [member.path for member in members]})
    return entries


def _cut_lines(script_shots: Sequence[dict]) -> Tuple[List[str], Dict[str, Tuple[int, int]]]:
    lines: List[str] = []
    index: Dict[str, Tuple[int, int]] = {}
    for pos, sentence in enumerate(script_shots):
        role = ROLE_LABELS.get(sentence.get("role") or "body", "본문")
        for cut_no, shot in enumerate(sentence.get("shots", [])):
            cut_id = f"c{len(index)}"
            index[cut_id] = (pos, cut_no)
            text = re.sub(r"\s+", " ", shot.get("text", "")).strip()
            seconds = float(shot.get("duration_sec") or 0.0)
            lines.append(f"{cut_id} | 문장{pos + 1} | {role} | {seconds:.1f}초 | {text}")
    return lines, index


def _chat(url: str, api_key: str, model: str, prompt: str, timeout: int) -> str:
    try:
        response = requests.post(
            url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            # Reasoning models spend part of the budget before the JSON answer.
            json={"model": model, "messages": [{"role": "user", "content": prompt}],
                  "temperature": 0.2, "max_tokens": 8192},
            timeout=timeout,
        )
    except requests.Timeout as err:
        raise _TryNextModel(f"{model}: {timeout}초 안에 응답 없음") from err
    if response.status_code != 200:
        message = f"{model}: HTTP {response.status_code} {_error_detail(response)}"
        if response.status_code in _TRY_NEXT_STATUS:
            raise _TryNextModel(message)
        raise RuntimeError(message)  # bad key, rate limit, bad request: another model will not help
    return response.json()["choices"][0]["message"].get("content") or ""


def _parse_cuts(raw: str) -> list:
    text = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.S)
    text = re.sub(r"```(?:json)?", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("AI 응답에서 JSON을 찾지 못했습니다.")
    data = json.loads(text[start:end + 1])
    cuts = data.get("cuts") if isinstance(data, dict) else None
    if not isinstance(cuts, list):
        raise ValueError("AI 응답에 cuts 목록이 없습니다.")
    return cuts


def pick_sources_with_llm(
    script_shots: Sequence[dict],
    catalog: Sequence[MediaItem],
    api_key: str,
    model: str = "",
    timeout: int = 120,
) -> Tuple[Dict[Tuple[int, int], dict], str]:
    """Ask the model for sources per cut.

    Returns (picks, model_used). picks is {(sentence_pos, cut_idx): {"choices":
    [[paths], ...], "why": str}} for the cuts answered with valid ids; each choice
    is a list because a folder of numbered files is offered as one entry. With an
    NVIDIA key, a retired/unavailable/overloaded model or an unreadable answer
    falls through to the next model in NVIDIA_MODELS. Other errors propagate so
    the caller can fall back to the rule-based ranking.
    """
    if not api_key:
        raise ValueError("LLM API 키가 없습니다.")
    entries = _catalog_entries(catalog)
    lines, cut_index = _cut_lines(script_shots)
    url, models = _endpoint(api_key, model)
    if not entries or not lines:
        return {}, ""
    prompt = (_PROMPT.replace("<<CUTS>>", "\n".join(lines))
              .replace("<<SOURCES>>", "\n".join(f"{e['id']} | {e['line']}" for e in entries)))

    failures: List[str] = []
    deadline = time.monotonic() + TOTAL_TIMEOUT_SEC
    for model_name in models:
        remaining = int(deadline - time.monotonic())
        if remaining < 15:
            failures.append(f"전체 {TOTAL_TIMEOUT_SEC}초 제한 초과")
            break
        try:
            rows = _parse_cuts(_chat(url, api_key, model_name, prompt, min(timeout, remaining)))
        except _TryNextModel as err:
            failures.append(str(err))
            continue
        except ValueError as err:  # answered, but not with the requested JSON
            failures.append(f"{model_name}: {err}")
            continue
        return _picks_from_rows(rows, entries, cut_index), model_name
    raise RuntimeError(" / ".join(failures))


def _picks_from_rows(rows: list, entries: List[dict], cut_index: Dict[str, Tuple[int, int]]) -> Dict[Tuple[int, int], dict]:
    by_id = {entry["id"]: entry["paths"] for entry in entries}
    picks: Dict[Tuple[int, int], dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = cut_index.get(str(row.get("cut", "")).strip())
        ids = row.get("ids") or []
        if isinstance(ids, str):
            ids = [ids]
        choices: List[List[str]] = []
        for raw_id in ids:
            paths = by_id.get(str(raw_id).strip())
            if paths and paths not in choices:
                choices.append(paths)
        if key is not None and choices:
            picks[key] = {"choices": choices[:MAX_IDS_PER_CUT], "why": str(row.get("why") or "").strip()[:80]}
    return picks


def merge_ai_picks(
    ranking: Sequence[Sequence[Sequence[dict]]],
    ai_picks: Dict[Tuple[int, int], dict],
    script_shots: Sequence[dict],
) -> List[List[List[dict]]]:
    """Put the AI's picks first for each cut and keep rule-based alternates behind them.

    A folder of numbered files resolves to its least-used members so images rotate
    instead of repeating. Cuts the model skipped keep their rule-based ranking.
    """
    used: Counter = Counter()
    prev = None
    merged: List[List[List[dict]]] = []
    for pos, sentence in enumerate(script_shots):
        per_cut: List[List[dict]] = []
        for cut_no, _shot in enumerate(sentence.get("shots", [])):
            rule = ranking[pos][cut_no] if pos < len(ranking) and cut_no < len(ranking[pos]) else []
            pick = ai_picks.get((pos, cut_no))
            candidates: List[dict] = []
            seen = set()
            if pick:
                reason = f"AI 문맥: {pick['why']}" if pick.get("why") else "AI 문맥 분석"
                for paths in pick["choices"]:
                    ordered = sorted(paths, key=lambda p: (used[p], p == prev))
                    for path in ordered[:2 if len(paths) > 1 else 1]:
                        if path not in seen:
                            seen.add(path)
                            candidates.append({"path": path, "score": None, "reason": reason})
                if len(candidates) > 1 and candidates[0]["path"] == prev:
                    candidates.append(candidates.pop(0))
            for candidate in rule:
                if candidate["path"] not in seen:
                    seen.add(candidate["path"])
                    candidates.append(candidate)
            candidates = candidates[:MAX_CANDIDATES]
            if candidates:
                used[candidates[0]["path"]] += 1
                prev = candidates[0]["path"]
            per_cut.append(candidates)
        merged.append(per_cut)
    return merged
