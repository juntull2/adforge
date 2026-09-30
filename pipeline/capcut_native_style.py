"""Small, editable CapCut-native style policy for generated drafts.

The metadata comes from the installed pyCapCut catalog. These are draft
materials, so the editor can change or remove every choice after opening it.
"""

from pycapcut.metadata.text_intro import TextIntro
from pycapcut.metadata.transition_meta import TransitionType
from pycapcut.metadata.video_scene_effect import VideoSceneEffectType


PROBLEM_WORDS = ("고민", "걱정", "문제", "통증", "아프", "충격", "놀라", "왜")
RESULT_WORDS = ("만족", "해결", "개선", "좋아", "효과", "변화", "미소", "광채")
CTA_WORDS = ("구매", "주문", "할인", "클릭", "링크", "지금", "확인")


def classify_sentence(sentence: str, index: int) -> str:
    if index == 0:
        return "hook"
    if any(word in sentence for word in CTA_WORDS):
        return "cta"
    if any(word in sentence for word in RESULT_WORDS):
        return "result"
    if any(word in sentence for word in PROBLEM_WORDS):
        return "problem"
    return "body"


def apply_text_animation(segment, role: str, duration_us: int) -> str:
    """Attach one restrained built-in intro animation to a subtitle."""
    if duration_us < 300_000:
        return "none"
    animation = {
        "hook": TextIntro.弹出,
        "cta": TextIntro.向上弹入,
        "result": TextIntro.微光弹入,
        "problem": TextIntro.渐显,
        "body": TextIntro.渐显,
    }[role]
    segment.add_animation(animation, duration=min(450_000, duration_us // 3))
    return animation.value.title


def apply_video_style(segment, role: str, has_next_clip: bool, duration_us: int) -> dict:
    """Attach selected CapCut effect and a transition to the next clip."""
    applied = {"effect": None, "transition": None}
    if role == "hook" and duration_us >= 800_000:
        segment.add_effect(VideoSceneEffectType.Blinking, params=[15, None, None, None, None, None])
        applied["effect"] = "Blinking"
    elif role == "result" and duration_us >= 800_000:
        segment.add_effect(VideoSceneEffectType.kirakira, params=[25, 15])
        applied["effect"] = "kirakira"

    if has_next_clip and duration_us >= 900_000:
        transition = TransitionType.White_Flash if role == "problem" else TransitionType.叠化
        segment.add_transition(transition, duration=min(300_000, duration_us // 4))
        applied["transition"] = transition.value.name
    return applied
