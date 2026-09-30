"""Conservative, explainable matching of script cuts to local media.

Only filename, folder name, and optional assets.json tags are used. This is a
recommendation layer; it does not claim to understand unlabelled video frames.

rank_shot_sources() scores each cut: the cut's own words count most, the rest of
its sentence and the neighbouring sentences add context, and the sentence role
(hook/problem/result/cta/body) adds a small nudge. A cut without keywords still
gets a source that fits where it sits in the script.
"""

import hashlib
import os
import re
from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from pipeline.asset_indexer import AssetIndexer
from pipeline.shot_planner import MIN_SLOWMO_SPEED


CONCEPTS = {
    "skin": ("피부", "살결", "얼굴", "skin", "face"),
    "pore": ("모공", "블랙헤드", "화이트헤드", "피지", "모낭", "압출", "pore"),
    "acne": ("여드름", "트러블", "뾰루지", "좁쌀", "화농", "염증", "acne", "blemish", "pimple"),
    "scar": ("흉터", "패인", "요철", "자국", "scar"),
    "wrinkle": ("주름", "탄력", "wrinkle"),
    "clean_skin": ("깨끗", "매끈", "맑은", "맑아", "투명", "광채", "윤기", "물광", "꿀피부", "도자기",
                   "clean_skin", "clean skin", "glow", "好皮", "通透"),
    "regen": ("새살", "재생", "차오르", "회복", "진정"),
    "before_after": ("전후", "비포", "애프터", "달라졌", "달라진", "before", "after"),
    "product": ("제품", "상품", "패키지", "상자", "박스", "product", "packshot"),
    "ingredient": ("성분", "원료", "함유", "추출물", "ingredient"),
    "supplement": ("영양제", "캡슐", "알약", "알씩", "복용", "섭취", "먹는", "먹어", "먹고", "먹으", "먹었",
                   "capsule", "supplement", "pill"),
    "pharmacy": ("약국", "약사", "pharmacy"),
    "unboxing": ("언박싱", "택배", "개봉", "unboxing", "package"),
    "mirror": ("거울", "mirror"),
    "phone": ("핸드폰", "휴대폰", "스마트폰", "폰 ", "폰을", "폰으로", "검색", "phone", "smartphone"),
    "hospital": ("병원", "피부과", "의사", "시술", "레이저", "프락셀", "클리닉", "hospital", "clinic", "doctor"),
    "worry": ("고민", "걱정", "한숨", "답답", "짜증", "스트레스", "속상", "우울", "신경 쓰", "신경쓰",
              "머리 짚", "그때뿐", "소용없", "소용이 없", "효과 없", "효과가 없", "실패",
              "worry", "frustration"),
    "happy": ("만족", "웃", "미소", "감탄", "행복", "기뻐", "기분 좋", "환하", "happy", "smile", "relief"),
    "greeting": ("인사", "안녕", "반가", "hello"),
    "thumbs_up": ("따봉", "최고", "강추", "엄지", "thumbs"),
    "surprise": ("놀라", "놀랐", "깜짝", "충격", "대박", "surprise", "shock"),
    "secret": ("비밀", "몰래", "꿀팁", "알려드", "알려줄", "나만 알", "secret"),
    "stop": ("잠깐", "멈춰", "스톱", "스크롤", "stop"),
    "no": ("엑스", "절대", "안 돼", "안돼", "금지", "하지 마", "하지마"),
    "glare": ("째려", "노려", "응시", "쳐다", "stare"),
    "come_in": ("드루와", "들어와", "어서 와", "어서와", "오세요"),
    "severe": ("심한", "심해", "심하", "심각", "극심", "severe"),
    "pain": ("아프", "아파", "통증", "허리", "pain", "back_pain"),
    "exercise": ("운동", "스트레칭", "exercise", "stretch", "fitness"),
    "senior": ("어르신", "노인", "시니어", "senior", "elderly"),
    "review": ("후기", "리뷰", "숏폼", "ugc", "review"),
    "purchase": ("구매", "할인", "주문", "클릭", "링크", "프로필", "바로가기", "신청", "혜택", "화살표",
                 "buy", "purchase", "cta"),
}
# "약" alone is too short for substring matching ("약간", "예약", "약 2주"), so it
# only counts as a standalone word.
CONCEPT_PATTERNS = {
    "supplement": re.compile(r"(?<![가-힣])약(?:을|이|은|만|도|으로|\s(?!\s*\d))"),
}

CONCEPT_WEIGHTS = {"skin": 1, "review": 1, "product": 2, "happy": 2, "worry": 2}

CONCEPT_LABELS = {
    "skin": "피부", "pore": "모공·피지", "acne": "여드름·트러블", "scar": "흉터·요철", "wrinkle": "주름",
    "clean_skin": "깨끗한 피부", "regen": "재생·회복", "before_after": "전후 비교", "product": "제품",
    "ingredient": "성분", "supplement": "복용", "pharmacy": "약국", "unboxing": "언박싱", "mirror": "거울",
    "phone": "휴대폰", "hospital": "병원·시술", "worry": "고민", "happy": "만족·미소", "greeting": "인사",
    "thumbs_up": "추천", "surprise": "놀람", "secret": "비밀·꿀팁", "stop": "멈춤", "no": "금지",
    "glare": "응시", "come_in": "유도", "severe": "심한 증상", "pain": "통증", "exercise": "운동",
    "senior": "시니어", "review": "후기", "purchase": "구매 유도",
}

ROLE_LABELS = {"hook": "후킹", "problem": "문제", "result": "결과", "cta": "구매 유도", "body": "본문"}

# Concepts that suit a sentence role even when its words name none of them.
ROLE_CONCEPTS = {
    "hook": {"stop", "secret", "surprise", "glare", "severe", "phone", "no"},
    "problem": {"worry", "mirror", "acne", "pore", "scar", "severe", "hospital", "pain"},
    "result": {"happy", "clean_skin", "regen", "thumbs_up", "before_after"},
    "cta": {"purchase", "come_in", "thumbs_up", "product", "greeting"},
    "body": {"product", "ingredient", "supplement", "pharmacy", "review"},
}

STOP_WORDS = {
    # file and folder noise
    "video", "videos", "image", "clip", "stock", "media", "asset", "trim", "collage", "cat",
    "dlbunny", "com", "xhs", "소스", "영상", "사진", "장면", "숏컷", "무자막", "샤오홍슈",
    # everyday words that carry no visual meaning
    "이거", "이게", "이건", "그거", "저거", "진짜", "정말", "너무", "완전", "그냥", "이제", "지금",
    "오늘", "우리", "저도", "제가", "여러분", "하나", "있는", "하는", "보는", "없는", "되는", "같은",
    "이런", "그런", "저런", "하고", "해서", "그래서", "하지만", "근데", "그리고", "위에", "옆에",
}
SUPPORTED_EXTENSIONS = {".mp4", ".mov", ".jpg", ".jpeg", ".png"}
# Numbered files (01.jpg, IMG_1234.jpg) are described by their folder, so they share a group.
_GENERIC_STEM = re.compile(r"^(?:img|image|dsc|vid|video|clip|mvimg|pxl)?[\s_\-]*\d+(?:[\s_\-]*\(\d+\))?$", re.I)
_SCORE_FLOOR = 1.0
# A source that names an upcoming cut's own words is saved for that cut instead of
# being spent earlier on context-only evidence.
_RESERVE_LOOKAHEAD = 4
_RESERVE_PENALTY = 1.5


@dataclass(frozen=True)
class MediaItem:
    path: str               # absolute path
    label: str              # "<source folder>/<relative path without extension>"
    media_type: str         # "video" | "image"
    duration_sec: float
    orientation: str
    concepts: frozenset
    word_keys: frozenset    # prefixes used for literal word matches
    group: str = ""         # shared folder label for generically numbered files


def _concepts(text: str) -> set:
    lower = text.lower()
    found = {name for name, aliases in CONCEPTS.items() if any(alias in lower for alias in aliases)}
    found.update(name for name, pattern in CONCEPT_PATTERNS.items() if pattern.search(lower))
    return found


def _tokens(text: str) -> set:
    return {t for t in re.findall(r"[a-zA-Z가-힣]{2,}", text.lower()) if t not in STOP_WORDS}


def _word_key(token: str) -> Optional[str]:
    """Korean words match on their first two syllables (particles vary); Latin on four letters."""
    if "가" <= token[0] <= "힣":
        return token[:2]
    return token[:4] if len(token) >= 4 else None


def _word_keys(text: str) -> Dict[str, str]:
    keys: Dict[str, str] = {}
    for token in sorted(_tokens(text)):
        key = _word_key(token)
        if key:
            keys.setdefault(key, token)
    return keys


def _cache_name(folder: str) -> str:
    digest = hashlib.sha1(os.path.abspath(folder).lower().encode("utf-8")).hexdigest()[:10]
    return f"asset_index_{digest}.json"


def build_media_catalog(folders: str | Sequence[str]) -> List[MediaItem]:
    """Index every supported file under the folders (recursively) once per call.

    Each folder keeps its own index cache, so several folders do not overwrite
    each other's cache and force a full ffprobe pass on every Streamlit rerun.
    """
    folder_list = [folders] if isinstance(folders, str) else list(folders or [])
    indexer = AssetIndexer(cache_dir="outputs")
    items: List[MediaItem] = []
    seen = set()
    for folder in folder_list:
        if not folder or not os.path.isdir(folder):
            continue
        root_name = os.path.basename(os.path.normpath(folder))
        for asset in indexer.scan_directory(folder, recursive=True, cache_name=_cache_name(folder)):
            path = os.path.abspath(asset.file_path)
            if path in seen or os.path.splitext(path)[1].lower() not in SUPPORTED_EXTENSIONS:
                continue
            seen.add(path)
            relative = os.path.relpath(path, folder)
            label = f"{root_name}/{os.path.splitext(relative)[0]}".replace("\\", "/")
            stem = os.path.splitext(os.path.basename(path))[0]
            parent = os.path.dirname(relative).replace("\\", "/")
            group = (f"{root_name}/{parent}" if parent else root_name) if _GENERIC_STEM.match(stem) else ""
            words = " ".join([label, *asset.tags, *asset.subject, *asset.action, *asset.emotion])
            items.append(MediaItem(
                path=path,
                label=label,
                media_type=asset.media_type,
                duration_sec=float(asset.duration_sec or 0.0),
                orientation=asset.orientation,
                concepts=frozenset(_concepts(words)),
                word_keys=frozenset(_word_keys(words)),
                group=group,
            ))
    items.sort(key=lambda item: item.label)
    return items


def _concept_text(concepts) -> str:
    return "·".join(CONCEPT_LABELS.get(c, c) for c in sorted(concepts))


def rank_shot_sources(
    script_shots: Sequence[dict], catalog: Sequence[MediaItem], top_k: int = 5
) -> List[List[List[Dict]]]:
    """Rank candidate sources for every planned cut, in script order.

    script_shots: [{"sentence", "role", "shots": [{"text", "duration_sec"}]}]
    Returns ranking[sentence][cut] = [{"path", "score", "reason"}, ...] best first;
    an empty list means nothing in the folders relates to that cut.
    """
    sentence_concepts = [_concepts(s.get("sentence", "")) for s in script_shots]

    # Where each source matches a cut's own words (a weight >= 2 concept or a literal word).
    strong_at: Dict[str, List[int]] = {}
    cut_no = 0
    for sentence in script_shots:
        for shot in sentence.get("shots", []):
            text = shot.get("text", "")
            cut_c, words = _concepts(text), _word_keys(text)
            for item in catalog:
                strong = any(CONCEPT_WEIGHTS.get(c, 4) >= 2 for c in cut_c & item.concepts)
                if strong or (words.keys() & item.word_keys):
                    strong_at.setdefault(item.path, []).append(cut_no)
            cut_no += 1

    used: Counter = Counter()
    prev_path = None
    ranking: List[List[List[Dict]]] = []
    cut_no = -1
    for pos, sentence in enumerate(script_shots):
        role = sentence.get("role") or "body"
        role_wanted = ROLE_CONCEPTS.get(role, set())
        around = set()
        if pos > 0:
            around |= sentence_concepts[pos - 1]
        if pos + 1 < len(script_shots):
            around |= sentence_concepts[pos + 1]
        per_cut: List[List[Dict]] = []
        for shot in sentence.get("shots", []):
            cut_no += 1
            text = shot.get("text", "")
            cut_c = _concepts(text)
            sentence_c = sentence_concepts[pos] - cut_c
            context_c = around - cut_c - sentence_concepts[pos]
            words = _word_keys(text)
            cut_sec = float(shot.get("duration_sec") or 0.0)
            scored = []
            for item in catalog:
                hit_cut = cut_c & item.concepts
                hit_sentence = sentence_c & item.concepts
                hit_context = context_c & item.concepts
                hit_words = [words[key] for key in words.keys() & item.word_keys]
                hit_role = bool(role_wanted & item.concepts)
                if not (hit_cut or hit_sentence or hit_context or hit_words or hit_role):
                    continue
                score = (sum(CONCEPT_WEIGHTS.get(c, 4) for c in hit_cut)
                         + 0.5 * sum(CONCEPT_WEIGHTS.get(c, 4) for c in hit_sentence)
                         + 0.25 * sum(CONCEPT_WEIGHTS.get(c, 4) for c in hit_context)
                         + 1.5 * len(hit_words)
                         + (1.0 if hit_role else 0.0))
                if item.media_type == "video":
                    score += 0.5
                    if 0 < item.duration_sec < cut_sec * MIN_SLOWMO_SPEED:
                        score -= 1.0  # would need filler footage to cover the cut
                if item.orientation == "vertical_9_16":
                    score += 0.25
                score -= 1.5 * used[item.path]
                if item.path == prev_path:
                    score -= 4.0
                strong_cuts = strong_at.get(item.path, ())
                if cut_no not in strong_cuts and any(cut_no < later <= cut_no + _RESERVE_LOOKAHEAD
                                                     for later in strong_cuts):
                    score -= _RESERVE_PENALTY
                if score < _SCORE_FLOOR:
                    continue
                parts = []
                if hit_cut:
                    parts.append(_concept_text(hit_cut))
                if hit_words:
                    parts.append("단어 " + ", ".join(f"'{w}'" for w in sorted(hit_words)))
                if hit_sentence:
                    parts.append("문장 흐름 " + _concept_text(hit_sentence))
                if hit_context:
                    parts.append("앞뒤 문맥 " + _concept_text(hit_context))
                if hit_role:
                    parts.append(f"{ROLE_LABELS.get(role, role)} 장면")
                scored.append((score, item, " / ".join(parts)))
            scored.sort(key=lambda row: (-row[0], row[1].label))
            picks = [{"path": item.path, "score": round(score, 2), "reason": reason}
                     for score, item, reason in scored[:top_k]]
            if picks:
                used[picks[0]["path"]] += 1
                prev_path = picks[0]["path"]
            per_cut.append(picks)
        ranking.append(per_cut)
    return ranking


def suggest_local_media(sentences: List[str], folder: str | List[str]) -> List[Dict]:
    """Return one recommendation per sentence (the whole sentence as a single cut)."""
    from pipeline.capcut_native_style import classify_sentence

    catalog = build_media_catalog(folder)
    if not catalog:
        return [{"path": None, "score": 0, "reason": "소스 폴더 없음"} for _ in sentences]
    script = [{"sentence": s, "role": classify_sentence(s, i), "shots": [{"text": s, "duration_sec": 0}]}
              for i, s in enumerate(sentences)]
    results = []
    for per_cut in rank_shot_sources(script, catalog, top_k=1):
        best = per_cut[0][0] if per_cut and per_cut[0] else None
        results.append(best or {"path": None, "score": 0, "reason": "일치하는 태그 없음"})
    return results
