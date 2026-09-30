"""User-installed fonts available for editable CapCut text clips."""

import glob
import os


FONT_FILES = {
    "양굵은구조폰트": ["yangfont02.ttf"],
    "상상토끼 꽃집막내딸": ["SSYoungestDaughterRegular.ttf", "*꽃집막내딸*.ttf"],
    "김씨와일드각체": ["[KIM]WILDgag-Bold.ttf"],
    "메모먼트꾹꾹체": ["memomentKkukkkuk.ttf"],
    "케리스케듀체": ["KERISKEDU.ttf", "KERISKEDU_R.ttf"],
    "HS잔다리체": ["HSJandari-Regular.ttf"],
    "속초바다 돋움체": ["SokchoBadaDotum.ttf"],
}


def available_user_fonts() -> dict:
    directories = [
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts"),
        os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts"),
        os.path.join(os.path.expanduser("~"), "Desktop", "폰트"),
    ]
    found = {}
    for name, patterns in FONT_FILES.items():
        for directory in directories:
            for pattern in patterns:
                # glob treats square brackets as a character class, so check exact names first.
                exact = os.path.join(directory, pattern)
                matches = [exact] if os.path.isfile(exact) else glob.glob(glob.escape(directory) + os.sep + pattern)
                if matches:
                    found[name] = matches[0]
                    break
            if name in found:
                break
    return found


def caption_rotation(font_name: str) -> float:
    return 8.0 if font_name == "속초바다 돋움체" else 0.0
