"""
AdForge x Hypit: 레티라겐 모공/프락셀 광고 영상 A-Grade 완전 리마스터 파이프라인
- Pretendard-Black 모던 네오고딕 자막
- 2-컬러 룰 (순백색 + 네온 옐로우)
- 세이프존 (MarginV=480, 릴스/쇼츠 UI 완벽 회피)
- 1.0~1.5초 짧은 호흡 키네틱 워드-청크 분할
- 118%~125% 디지털 펀치인(Punch-in) & 켄 번스(Ken Burns) 줌인
- 모션 그래픽 오버레이 (나비존 경고 뱃지 & 타겟 락온, 광채 스파클, 2단 성분 인포그래픽, 50% 특가 배너)
- 10단 레이어 SFX 타격감 사운드 디자인
"""

import os
import sys
import json
import asyncio
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from pydub import AudioSegment

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# 폰트 경로
FONT_BLACK = r"C:\Users\5700G\AppData\Local\Microsoft\Windows\Fonts\Pretendard-Black.otf"
FONT_BOLD = r"C:\Users\5700G\AppData\Local\Microsoft\Windows\Fonts\Pretendard-Bold.otf"

# 기본 에셋 디렉토리
BASE_MODEL_DIR = r"C:\Users\5700G\Desktop\레티라겐\윤라영님모델_소스"
BASE_XHS_DIR = r"C:\Users\5700G\Desktop\레티라겐\xhs_sources"
BASE_SFX_DIR = r"C:\Users\5700G\Desktop\효과음"
LOCAL_SFX_DIR = os.path.abspath("local_assets/sfx")

TEMP_DIR = os.path.abspath("temp_videos/retiragen_remastered")
OUTPUT_MP4 = os.path.abspath("outputs/retiragen_pore_remastered.mp4")
OUTPUT_TILE = os.path.abspath("outputs/retiragen_pore_remastered_tile16.jpg")

os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(os.path.dirname(OUTPUT_MP4), exist_ok=True)

# -------------------------------------------------------------------
# 1. 모션 그래픽 오버레이 PNG 자동 생성
# -------------------------------------------------------------------
def generate_graphic_overlays():
    print("🎨 1. 모션 그래픽 오버레이 에셋 생성 중...")
    overlay_dir = os.path.join(TEMP_DIR, "overlays")
    os.makedirs(overlay_dir, exist_ok=True)

    f_title = ImageFont.truetype(FONT_BLACK, 40)
    f_sub = ImageFont.truetype(FONT_BOLD, 32)
    f_badge = ImageFont.truetype(FONT_BLACK, 34)

    # (1) Scene 3: 나비존 요철 경고 & 타겟 락온
    img_warn = Image.new('RGBA', (1080, 1920), (0, 0, 0, 0))
    d_warn = ImageDraw.Draw(img_warn)
    # 상단 경고 뱃지
    d_warn.rounded_rectangle([120, 260, 960, 360], radius=50, fill=(20, 10, 10, 220), outline=(255, 45, 45, 255), width=4)
    d_warn.text((540, 310), '⚠️ WARNING : 나비존 요철 & 피지 과다', fill=(255, 255, 255), font=f_title, anchor='mm')
    # 중앙 타겟 락온 서클
    cx, cy, r = 540, 960, 160
    d_warn.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(255, 50, 50, 240), width=5)
    d_warn.ellipse([cx - 25, cy - 25, cx + 25, cy + 25], outline=(255, 255, 255, 255), width=3)
    # 십자선
    d_warn.line([cx - r - 35, cy, cx - r + 25, cy], fill=(255, 50, 50, 255), width=4)
    d_warn.line([cx + r - 25, cy, cx + r + 35, cy], fill=(255, 50, 50, 255), width=4)
    d_warn.line([cx, cy - r - 35, cx, cy - r + 25], fill=(255, 50, 50, 255), width=4)
    d_warn.line([cx, cy + r - 25, cx, cy + r + 35], fill=(255, 50, 50, 255), width=4)
    path_warn = os.path.join(overlay_dir, "warn_target.png")
    img_warn.save(path_warn)

    # (2) Scene 7 & 9: 17호 깐달걀 피부 광채 & 스파클
    img_glow = Image.new('RGBA', (1080, 1920), (0, 0, 0, 0))
    d_glow = ImageDraw.Draw(img_glow)
    d_glow.rounded_rectangle([180, 260, 900, 355], radius=45, fill=(10, 20, 30, 215), outline=(255, 230, 80, 255), width=3)
    d_glow.text((540, 307), '✨ [무보정 17호 깐달걀결 인증]', fill=(255, 245, 150), font=f_title, anchor='mm')
    # 스파클 반짝이들
    def draw_sparkle(draw, x, y, size):
        draw.line([x - size, y, x + size, y], fill=(255, 255, 220, 240), width=3)
        draw.line([x, y - size, x, y + size], fill=(255, 255, 220, 240), width=3)
        draw.ellipse([x - size//3, y - size//3, x + size//3, y + size//3], fill=(255, 255, 255, 255))
    draw_sparkle(d_glow, 320, 780, 40)
    draw_sparkle(d_glow, 760, 840, 50)
    draw_sparkle(d_glow, 520, 710, 30)
    path_glow = os.path.join(overlay_dir, "skin_glow.png")
    img_glow.save(path_glow)

    # (3) Scene 8: 레티라겐 과학적 성분 2단 팝업 뱃지
    img_mech = Image.new('RGBA', (1080, 1920), (0, 0, 0, 0))
    d_mech = ImageDraw.Draw(img_mech)
    # 뱃지 1: 레티놀
    d_mech.rounded_rectangle([70, 250, 1010, 345], radius=45, fill=(10, 25, 45, 225), outline=(0, 230, 255, 255), width=3)
    d_mech.text((540, 297), '💊 스위스산 순수 레티놀 ➔ 속피지선 바짝 건조', fill=(255, 255, 255), font=f_badge, anchor='mm')
    # 뱃지 2: 콜라겐
    d_mech.rounded_rectangle([70, 365, 1010, 460], radius=45, fill=(40, 15, 30, 225), outline=(255, 65, 150, 255), width=3)
    d_mech.text((540, 412), '🧬 초저분자 300Da 콜라겐 ➔ 진피 요철 살 채움', fill=(255, 255, 255), font=f_badge, anchor='mm')
    path_mech = os.path.join(overlay_dir, "mechanism_badges.png")
    img_mech.save(path_mech)

    # (4) Scene 10: 50% 반값 특가 CTA 배너
    img_cta = Image.new('RGBA', (1080, 1920), (0, 0, 0, 0))
    d_cta = ImageDraw.Draw(img_cta)
    d_cta.rounded_rectangle([150, 260, 930, 360], radius=50, fill=(240, 35, 35, 235), outline=(255, 255, 255, 255), width=4)
    d_cta.text((540, 310), '🔥 30일 기간 한정 50% 반값 특가', fill=(255, 255, 255), font=f_title, anchor='mm')
    path_cta = os.path.join(overlay_dir, "cta_banner.png")
    img_cta.save(path_cta)

    return {
        "warn": path_warn,
        "glow": path_glow,
        "mech": path_mech,
        "cta": path_cta
    }

# -------------------------------------------------------------------
# 2. 리마스터 씬 정의 (펀치인 화각 + 짧은 호흡 자막 + SFX)
# -------------------------------------------------------------------
REMASTERED_SCENES = [
    {
        "id": 1,
        "role": "hook",
        "dur": 2.83,
        "audio": os.path.abspath("temp_audio/retiragen_pore_v2/scene_01.wav"),
        "sub_chunks": [
            {"start": 0.00, "end": 1.30, "text": "전 피부과 프락셀 안 받아도"},
            {"start": 1.30, "end": 2.83, "text": "{\\c&H0000E6FF&\\fscx108\\fscy108}모공 요철 제로{\\c&H00FFFFFF&\\fscx100\\fscy100}예요!"}
        ],
        "cuts": [
            # 0.0 ~ 1.3s: 100% 정상 바스트
            {"asset": os.path.join(BASE_MODEL_DIR, "환하게 웃는 장면 - Trim.mp4"), "t": 1.30, "punch": 1.00},
            # 1.3 ~ 2.83s: 120% 디지털 펀치인!
            {"asset": os.path.join(BASE_MODEL_DIR, "환하게 웃는 장면 - Trim.mp4"), "t": 1.53, "punch": 1.20}
        ],
        "sfx_cues": [
            {"t": 0.0, "file": os.path.join(BASE_SFX_DIR, "4_임팩트(화면강조)", "뚜훅.wav"), "vol": -5},
            {"t": 0.0, "file": os.path.join(BASE_SFX_DIR, "5_화면전환효과", "Whoosh Transition 1.wav"), "vol": -8}
        ]
    },
    {
        "id": 2,
        "role": "pain_1",
        "dur": 4.30,
        "audio": os.path.abspath("temp_audio/retiragen_pore_v2/scene_02.wav"),
        "sub_chunks": [
            {"start": 0.00, "end": 2.10, "text": "유명한 모공 앰플, 레티놀 크림 다 써봐도"},
            {"start": 2.10, "end": 4.30, "text": "{\\c&H0000E6FF&\\fscx108\\fscy108}개기름 뜨고 화장 밀리고,{\\c&H00FFFFFF&\\fscx100\\fscy100}"}
        ],
        "cuts": [
            {"asset": os.path.join(BASE_MODEL_DIR, "거울 보며 짜증내는 장면.mp4"), "t": 2.10, "punch": 1.00},
            {"asset": os.path.join(BASE_MODEL_DIR, "거울 보며 짜증내는 장면.mp4"), "t": 2.20, "punch": 1.18}
        ],
        "sfx_cues": [
            {"t": 0.0, "file": os.path.join(BASE_SFX_DIR, "5_화면전환효과", "쉭.mp3"), "vol": -8},
            {"t": 2.1, "file": os.path.join(BASE_SFX_DIR, "5_화면전환효과", "Whoosh Transition 2.wav"), "vol": -10}
        ]
    },
    {
        "id": 3,
        "role": "pain_2",
        "dur": 5.11,
        "audio": os.path.abspath("temp_audio/retiragen_pore_v2/scene_03.wav"),
        "sub_chunks": [
            {"start": 0.00, "end": 2.40, "text": "심할 땐 피부가 아예 뒤집어지더라고요."},
            {"start": 2.40, "end": 5.11, "text": "결국 {\\c&H0000E6FF&\\fscx108\\fscy108}나비존 요철만 푹 파였죠.{\\c&H00FFFFFF&\\fscx100\\fscy100}"}
        ],
        "cuts": [
            # 켄 번스 슬로우 줌인 1.0 -> 1.15
            {"asset": os.path.join(BASE_XHS_DIR, "4_피부_숏폼영상_무자막", "07.mp4"), "t": 5.11, "punch": 1.12, "overlay": "warn"}
        ],
        "sfx_cues": [
            {"t": 0.0, "file": os.path.join(BASE_SFX_DIR, "효과음 삐빅.MP3"), "vol": -6},
            {"t": 0.0, "file": os.path.join(BASE_SFX_DIR, "4_임팩트(화면강조)", "Suspense 1.wav"), "vol": -6},
            {"t": 2.4, "file": os.path.join(BASE_SFX_DIR, "3_특수자막(강조용)", "쨍그랑.mp3"), "vol": -10}
        ]
    },
    {
        "id": 4,
        "role": "reveal_1",
        "dur": 5.77,
        "audio": os.path.abspath("temp_audio/retiragen_pore_v2/scene_04.wav"),
        "sub_chunks": [
            {"start": 0.00, "end": 2.80, "text": "근데 귤껍질 같던 볼살 매끈해진 거 보이세요?"},
            {"start": 2.80, "end": 5.77, "text": "전 {\\c&H0000E6FF&\\fscx108\\fscy108}레티놀 크림을 삼키기{\\c&H00FFFFFF&\\fscx100\\fscy100} 시작했어요."}
        ],
        "cuts": [
            {"asset": os.path.join(BASE_MODEL_DIR, "이거 비밀인데.. - Trim.mp4"), "t": 2.80, "punch": 1.15},
            {"asset": os.path.join(BASE_MODEL_DIR, "약 손바닥 위에 있는 장면 - Trim.mp4"), "t": 2.97, "punch": 1.08}
        ],
        "sfx_cues": [
            {"t": 0.0, "file": os.path.join(BASE_SFX_DIR, "5_화면전환효과", "Whoosh Transition 1.wav"), "vol": -8},
            {"t": 2.8, "file": os.path.join(BASE_SFX_DIR, "2_일반자막", "뽁.wav"), "vol": -6},
            {"t": 2.8, "file": os.path.join(BASE_SFX_DIR, "3_특수자막(강조용)", "Ding Sound Effect.mp3"), "vol": -10}
        ]
    },
    {
        "id": 5,
        "role": "reveal_2",
        "dur": 2.66,
        "audio": os.path.abspath("temp_audio/retiragen_pore_v2/scene_05.wav"),
        "sub_chunks": [
            {"start": 0.00, "end": 2.66, "text": "{\\c&H0000E6FF&\\fscx112\\fscy112}엥?! 레티놀 크림을 삼켜요?!{\\c&H00FFFFFF&\\fscx100\\fscy100}"}
        ],
        "cuts": [
            # 125% 스냅 줌인 펀치인!
            {"asset": os.path.join(BASE_MODEL_DIR, "폰 보고 놀나는 장면 - Trim.mp4".replace("놀나는", "놀라는")), "t": 2.66, "punch": 1.25}
        ],
        "sfx_cues": [
            {"t": 0.0, "file": os.path.join(BASE_SFX_DIR, "2_일반자막", "느낌표 물음표 (또독).wav"), "vol": -5}
        ]
    },
    {
        "id": 6,
        "role": "proof_1",
        "dur": 6.45,
        "audio": os.path.abspath("temp_audio/retiragen_pore_v2/scene_06.wav"),
        "sub_chunks": [
            {"start": 0.00, "end": 3.10, "text": "땡볕 야구장을 다녀와도 피지 터지기는커녕"},
            {"start": 3.10, "end": 6.45, "text": "{\\c&H0000E6FF&\\fscx108\\fscy108}요철이 팽팽하게 차오르는 거예요!{\\c&H00FFFFFF&\\fscx100\\fscy100}"}
        ],
        "cuts": [
            {"asset": os.path.join(BASE_MODEL_DIR, "약 복용 장면 - Trim.mp4"), "t": 3.10, "punch": 1.00},
            {"asset": os.path.join(BASE_XHS_DIR, "4_피부_숏폼영상_무자막", "14.mp4"), "t": 3.35, "punch": 1.18}
        ],
        "sfx_cues": [
            {"t": 0.0, "file": os.path.join(BASE_SFX_DIR, "2_일반자막", "뽁.wav"), "vol": -8},
            {"t": 3.1, "file": os.path.join(BASE_SFX_DIR, "6_기타활용", "마인크래프트 레벨 업 소리.mp3"), "vol": -10}
        ]
    },
    {
        "id": 7,
        "role": "proof_2",
        "dur": 4.77,
        "audio": os.path.abspath("temp_audio/retiragen_pore_v2/scene_07.wav"),
        "sub_chunks": [
            {"start": 0.00, "end": 2.20, "text": "그렇게 한 달 정도 꾸준히 먹어보니,"},
            {"start": 2.20, "end": 4.77, "text": "이젠 프라이머 없이도 {\\c&H0000E6FF&\\fscx108\\fscy108}매끈한 17호 피부!{\\c&H00FFFFFF&\\fscx100\\fscy100}"}
        ],
        "cuts": [
            {"asset": os.path.join(BASE_MODEL_DIR, "피부 클로즈업 - Trim.mp4"), "t": 2.20, "punch": 1.00},
            {"asset": os.path.join(BASE_MODEL_DIR, "피부 클로즈업 - Trim.mp4"), "t": 2.57, "punch": 1.18, "overlay": "glow"}
        ],
        "sfx_cues": [
            {"t": 0.0, "file": os.path.join(BASE_SFX_DIR, "5_화면전환효과", "쉭.mp3"), "vol": -8},
            {"t": 2.2, "file": os.path.join(BASE_SFX_DIR, "3_특수자막(강조용)", "티딩! 효과음.mp3"), "vol": -8}
        ]
    },
    {
        "id": 8,
        "role": "mechanism",
        "dur": 8.79,
        "audio": os.path.abspath("temp_audio/retiragen_pore_v2/scene_08.wav"),
        "sub_chunks": [
            {"start": 0.00, "end": 4.30, "text": "속피지선 바짝 말리고 초저분자 콜라겐 채우는 원리!"},
            {"start": 4.30, "end": 8.79, "text": "{\\c&H0000E6FF&\\fscx108\\fscy108}프락셀 레이저가 피부에 이식된 느낌?!{\\c&H00FFFFFF&\\fscx100\\fscy100}"}
        ],
        "cuts": [
            {"asset": os.path.join(BASE_MODEL_DIR, "제품 얼굴 옆에 들고 찍는 장면(좌우반전됨..) - Trim.mp4"), "t": 4.30, "punch": 1.00, "overlay": "mech"},
            {"asset": os.path.join(BASE_MODEL_DIR, "거울 보는 장면 - Trim.mp4"), "t": 4.49, "punch": 1.18}
        ],
        "sfx_cues": [
            {"t": 0.2, "file": os.path.join(LOCAL_SFX_DIR, "pop.mp3"), "vol": -5},
            {"t": 4.3, "file": os.path.join(BASE_SFX_DIR, "3_특수자막(강조용)", "뜨링!.wav"), "vol": -8}
        ]
    },
    {
        "id": 9,
        "role": "maintain",
        "dur": 3.64,
        "audio": os.path.abspath("temp_audio/retiragen_pore_v2/scene_09.wav"),
        "sub_chunks": [
            {"start": 0.00, "end": 1.70, "text": "하루 종일 자연광 맞아도"},
            {"start": 1.70, "end": 3.64, "text": "{\\c&H0000E6FF&\\fscx108\\fscy108}매끈한 깐달걀 피부 톤{\\c&H00FFFFFF&\\fscx100\\fscy100}이 쭈욱 유지돼요!"}
        ],
        "cuts": [
            {"asset": os.path.join(BASE_MODEL_DIR, "피부 클로즈업3 - Trim.mp4"), "t": 1.70, "punch": 1.00},
            {"asset": os.path.join(BASE_MODEL_DIR, "피부 클로즈업3 - Trim.mp4"), "t": 1.94, "punch": 1.20, "overlay": "glow"}
        ],
        "sfx_cues": [
            {"t": 0.0, "file": os.path.join(BASE_SFX_DIR, "5_화면전환효과", "Whoosh Transition 1.wav"), "vol": -8},
            {"t": 1.7, "file": os.path.join(BASE_SFX_DIR, "3_특수자막(강조용)", "Ding Sound Effect.mp3"), "vol": -8}
        ]
    },
    {
        "id": 10,
        "role": "cta",
        "dur": 5.27,
        "audio": os.path.abspath("temp_audio/retiragen_pore_v2/scene_10.wav"),
        "sub_chunks": [
            {"start": 0.00, "end": 2.50, "text": "{\\c&H0000E6FF&\\fscx108\\fscy108}30일 기간 한정 반값 할인!{\\c&H00FFFFFF&\\fscx100\\fscy100}"},
            {"start": 2.50, "end": 5.27, "text": "궁금한 분들은 아래 비밀링크 참고해 보세요 👇"}
        ],
        "cuts": [
            {"asset": os.path.join(BASE_MODEL_DIR, "화살표 아래로_CTA (손가락 모양이 좀..) - Trim.mp4"), "t": 2.50, "punch": 1.00, "overlay": "cta"},
            {"asset": os.path.join(BASE_MODEL_DIR, "따봉.mp4"), "t": 2.77, "punch": 1.18}
        ],
        "sfx_cues": [
            {"t": 0.0, "file": os.path.join(BASE_SFX_DIR, "6_기타활용", "Mouse Click.wav"), "vol": -5},
            {"t": 2.5, "file": os.path.join(BASE_SFX_DIR, "3_특수자막(강조용)", "Ding Ding Sound Effect.wav"), "vol": -6}
        ]
    }
]

# -------------------------------------------------------------------
# 3. ASS 고품질 세이프존 자막 파일 빌더 (Pretendard-Black, MarginV=480)
# -------------------------------------------------------------------
def build_remastered_ass(scenes, ass_path):
    print("📝 2. Pretendard-Black 기반 고가독성 세이프존 자막(ASS) 생성...")
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Pretendard-Black,64,&H00FFFFFF,&H000000FF,&H00181818,&H90000000,-1,0,0,0,100,100,0,0,1,3.0,3.5,2,40,40,480,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    base_time = 0.0

    def fmt_time(t):
        hrs = int(t // 3600)
        mins = int((t % 3600) // 60)
        secs = int(t % 60)
        cs = int(round((t - int(t)) * 100))
        if cs >= 100:
            cs = 99
        return f"{hrs:01d}:{mins:02d}:{secs:02d}.{cs:02d}"

    for s in scenes:
        for ch in s["sub_chunks"]:
            t_start = fmt_time(base_time + ch["start"])
            t_end = fmt_time(base_time + ch["end"])
            txt = ch["text"]
            events.append(f"Dialogue: 0,{t_start},{t_end},Default,,0,0,0,,{txt}")
        base_time += s["dur"]

    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(events) + "\n")
    print(f"  ✅ ASS 자막 파일 저장 완료: {ass_path}")

# -------------------------------------------------------------------
# 4. 개별 컷 렌더링 (디지털 펀치인 + 모션 그래픽 오버레이)
# -------------------------------------------------------------------
def render_cut_segment(cut, out_path, overlay_map):
    asset = cut["asset"]
    dur = cut["t"]
    punch = cut.get("punch", 1.0)
    overlay_key = cut.get("overlay")

    # 스케일 계산 (펀치인)
    base_w, base_h = 1080, 1920
    scaled_w = int(round(base_w * punch))
    scaled_h = int(round(base_h * punch))
    
    # 짝수 보정
    scaled_w = scaled_w if scaled_w % 2 == 0 else scaled_w + 1
    scaled_h = scaled_h if scaled_h % 2 == 0 else scaled_h + 1

    vf_filters = [
        f"scale={scaled_w}:{scaled_h}:force_original_aspect_ratio=increase",
        f"crop={base_w}:{base_h}:(in_w-out_w)/2:(in_h-out_h)/2",
        "fps=30"
    ]

    # 오버레이 그래픽이 있는 경우 필터 그래프 합성
    if overlay_key and overlay_key in overlay_map and os.path.exists(overlay_map[overlay_key]):
        ov_path = overlay_map[overlay_key].replace("\\", "/")
        cmd = [
            "ffmpeg", "-y",
            "-ss", "0.2", "-t", f"{dur:.3f}",
            "-stream_loop", "-1", "-i", asset,
            "-i", ov_path,
            "-t", f"{dur:.3f}",
            "-filter_complex",
            f"[0:v]{','.join(vf_filters)}[vbase];[vbase][1:v]overlay=0:0[vout]",
            "-map", "[vout]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-an", out_path
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-ss", "0.2", "-t", f"{dur:.3f}",
            "-stream_loop", "-1", "-i", asset,
            "-t", f"{dur:.3f}",
            "-vf", ",".join(vf_filters),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-an", out_path
        ]

    subprocess.run(cmd, capture_output=True, check=True)

# -------------------------------------------------------------------
# 5. 마스터 합성 (비디오 + 다중 SFX + BGM + ASS 자막 버닝)
# -------------------------------------------------------------------
def assemble_remastered_master(scenes, ass_path, overlay_map):
    print("🎬 3. 개별 펀치인 컷 및 오버레이 클립 렌더링...")
    cut_files = []
    cut_idx = 0
    for s in scenes:
        for c in s["cuts"]:
            cut_idx += 1
            cp = os.path.join(TEMP_DIR, f"cut_{cut_idx:02d}_s{s['id']:02d}.mp4")
            render_cut_segment(c, cp, overlay_map)
            cut_files.append(cp)
            print(f"  [Cut {cut_idx:02d}] Scene {s['id']:02d} ({c['t']:.2f}s, punch={c.get('punch', 1.0)}x)")

    # (1) 비디오 트랙 Concat
    raw_video = os.path.join(TEMP_DIR, "master_raw_video.mp4")
    concat_txt = os.path.join(TEMP_DIR, "video_list.txt")
    with open(concat_txt, "w", encoding="utf-8") as f:
        for cp in cut_files:
            f.write(f"file '{cp.replace(chr(92), '/')}'\n")

    cmd_vcat = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_txt,
        "-c", "copy", raw_video
    ]
    subprocess.run(cmd_vcat, capture_output=True, check=True)

    # (2) 풀 레이어 오디오 믹싱 (Voiceover + SFX 타격감 + BGM)
    print("🔊 4. 10단 레이어 SFX 타격감 오디오 마스터 믹싱...")
    master_voice = AudioSegment.empty()
    curr_ms = 0
    sfx_overlays = []

    for s in scenes:
        seg = AudioSegment.from_file(s["audio"])
        master_voice += seg

        # SFX 큐 믹싱
        for cue in s.get("sfx_cues", []):
            fpath = cue["file"]
            if os.path.exists(fpath):
                sfx_sound = AudioSegment.from_file(fpath) + cue.get("vol", -6)
                cue_pos_ms = curr_ms + int(cue["t"] * 1000)
                sfx_overlays.append((cue_pos_ms, sfx_sound))
        curr_ms += len(seg)

    total_len_ms = len(master_voice)
    full_audio = master_voice
    for pos_ms, snd in sfx_overlays:
        full_audio = full_audio.overlay(snd, position=pos_ms)

    # BGM 오버레이 (잔잔하게 -27dB)
    bgm_path = os.path.join(BASE_SFX_DIR, "1_BGM(일반)", "Its Jazz 30 sec.wav")
    if os.path.exists(bgm_path):
        bgm = AudioSegment.from_file(bgm_path) - 27
        bgm_looped = bgm * (int(total_len_ms / len(bgm)) + 2)
        bgm_trimmed = bgm_looped[:total_len_ms].fade_in(400).fade_out(1500)
        full_audio = full_audio.overlay(bgm_trimmed)

    master_audio_path = os.path.join(TEMP_DIR, "master_audio.wav")
    full_audio.export(master_audio_path, format="wav")

    # (3) 최종 MP4 합성 + Pretendard-Black 자막 하드서브 버닝
    print(f"🔥 5. 최종 마스터 MP4 렌더링 -> {OUTPUT_MP4}")
    escaped_ass = ass_path.replace("\\", "/").replace(":", "\\:")

    final_cmd = [
        "ffmpeg", "-y",
        "-i", raw_video,
        "-i", master_audio_path,
        "-vf", f"subtitles='{escaped_ass}'",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        OUTPUT_MP4
    ]
    subprocess.run(final_cmd, capture_output=True, check=True)
    print(f"🎉 리마스터 완성본 생성 완료: {OUTPUT_MP4}")

    # (4) 16컷 검증 타일 이미지 추출
    print(f"📸 6. Hypit media tile 16컷 검증 그리드 추출 -> {OUTPUT_TILE}")
    cmd_tile = [
        "hypit", "media", "tile", OUTPUT_MP4,
        "--frames", "16", "--columns", "4",
        "--to", OUTPUT_TILE
    ]
    subprocess.run(cmd_tile, capture_output=True, check=True, shell=True)
    print(f"✅ 리마스터 검증 타일 완성: {OUTPUT_TILE}")

def main():
    print("=" * 70)
    print("🚀 [AdForge x Hypit] 레티라겐 모공/프락셀 광고 A-Grade 리마스터 가동")
    print("=" * 70)

    overlay_map = generate_graphic_overlays()

    ass_path = os.path.join(TEMP_DIR, "remastered_safezone.ass")
    build_remastered_ass(REMASTERED_SCENES, ass_path)

    assemble_remastered_master(REMASTERED_SCENES, ass_path, overlay_map)

if __name__ == "__main__":
    main()
