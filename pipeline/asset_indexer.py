"""
AssetIndexer — 로컬 미디어 에셋 스캔, 메타데이터 추출 및 인덱싱

책임:
1. 로컬 폴더(영상/이미지)를 순회하며 기술적 속성(해상도, fps, 길이, orientation) 추출 (FFprobe)
2. 파일명 및 디렉토리 구조로부터 의미론적 메타데이터(subject, action, emotion, shot_type, tags) 파싱
3. mtime 기반 증분 캐싱 지원 (반복 스캔 시 수 ms 내 완료)
4. 수동 오버라이드(assets.json 매니페스트) 지원 및 향후 VLM(CLIP/Vision) 연동 슬롯 제공
"""

import os
import re
import json
import subprocess
import hashlib
from typing import List, Dict, Optional, Tuple
from models.asset import AssetMetadata


# 지원 미디어 확장자
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".webm", ".mkv"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


# 시각적 의미 사전 (영문 키워드 + 한글 동의어 매핑)
TAG_SYNONYM_RULES = [
    # 시니어 / 대상자
    {
        "keys": ["senior", "elderly", "old", "grandma", "grandpa", "노인", "어르신", "부모님", "시니어", "어머니", "아버지"],
        "subject": ["senior"],
        "tags": ["senior", "elderly", "어르신", "노인", "부모님", "시니어"],
        "marketing_roles": ["hook", "empathy"]
    },
    # 허리 / 척추 / 통증
    {
        "keys": ["back_pain", "spine", "back", "pain", "waist", "허리", "요통", "척추", "통증", "아픔", "결림", "디스크"],
        "subject": ["spine", "back"],
        "action": ["pain"],
        "emotion": ["pain", "frustration"],
        "tags": ["back_pain", "spine", "pain", "허리", "요통", "척추", "통증"],
        "marketing_roles": ["hook", "empathy", "agitate"]
    },
    # 마사지 / 찜질 / 온열
    {
        "keys": ["massage", "heat", "patch", "therapy", "warm", "마사지", "안마", "찜질", "온열", "파스", "원적외선", "근적외선"],
        "action": ["massage", "heat_therapy"],
        "emotion": ["relief"],
        "tags": ["massage", "heat_therapy", "마사지", "찜질", "온열", "원적외선"],
        "marketing_roles": ["solution", "usp"]
    },
    # 스트레칭
    {
        "keys": ["stretching", "stretch", "스트레칭", "이완", "유연성"],
        "action": ["stretching"],
        "emotion": ["relief", "active"],
        "tags": ["stretching", "스트레칭", "이완", "유연성", "근육"],
        "marketing_roles": ["solution", "empathy"]
    },
    # 요가 / 명상
    {
        "keys": ["yoga", "meditation", "요가", "명상", "호흡"],
        "action": ["yoga"],
        "emotion": ["relief", "neutral"],
        "tags": ["yoga", "요가", "명상", "스트레칭"],
        "marketing_roles": ["solution", "empathy"]
    },
    # 운동 / 피트니스 / 헬스
    {
        "keys": ["exercise", "fitness", "workout", "gym", "운동", "피트니스", "헬스", "재활", "하체", "근력"],
        "action": ["exercise", "fitness"],
        "emotion": ["active"],
        "tags": ["exercise", "fitness", "workout", "운동", "피트니스", "재활"],
        "marketing_roles": ["solution", "usp"]
    },
    # 피부과 / 병원 / 클리닉
    {
        "keys": ["dermatology", "clinic", "hospital", "doctor", "피부과", "병원", "의사", "클리닉", "진료"],
        "environment": ["clinic"],
        "subject": ["doctor", "patient"],
        "tags": ["dermatology", "clinic", "hospital", "피부과", "병원", "의료"],
        "marketing_roles": ["hook", "evidence", "agitate"]
    },
    # 비용 / 결제 / 영수증
    {
        "keys": ["bill", "payment", "money", "receipt", "영수증", "비용", "돈", "결제", "청구"],
        "action": ["bill_payment"],
        "emotion": ["frustration", "shock"],
        "tags": ["medical_bill", "payment", "money", "영수증", "비용", "돈"],
        "marketing_roles": ["hook", "agitate"]
    },
    # 제품 / 디바이스 / 언박싱
    {
        "keys": ["product", "device", "unboxing", "review", "제품", "기기", "복대", "언박싱", "착용"],
        "subject": ["product"],
        "action": ["product_demonstration"],
        "shot_type": "product",
        "tags": ["product", "device", "제품", "기기", "복대", "시연"],
        "marketing_roles": ["solution", "usp"]
    },
    # CTA / 구매 / 링크
    {
        "keys": ["cta", "buy", "purchase", "order", "구매", "클릭", "링크", "할인", "특가", "환불"],
        "action": ["call_to_action"],
        "emotion": ["urgency"],
        "shot_type": "text_overlay",
        "tags": ["cta", "purchase", "구매", "할인", "환불", "링크"],
        "marketing_roles": ["cta"]
    },
]


class AssetIndexer:
    """미디어 에셋 색인 및 메타데이터 관리자"""

    def __init__(self, cache_dir: str = "outputs"):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    def scan_directory(
        self,
        dir_path: str,
        recursive: bool = True,
        use_cache: bool = True,
        cache_name: str = "asset_index.json",
    ) -> List[AssetMetadata]:
        """디렉토리를 스캔하여 AssetMetadata 목록을 생성한다.
        
        Args:
            dir_path: 스캔할 디렉토리 경로
            recursive: 하위 디렉토리 포함 여부
            use_cache: 캐시 사용 여부 (mtime 기반 증분 갱신)
            cache_name: 저장할 캐시 파일명
        """
        if not os.path.exists(dir_path):
            print(f"[AssetIndexer] 디렉토리 없음: {dir_path}")
            return []

        cache_path = os.path.join(self.cache_dir, cache_name)
        cached_entries: Dict[str, dict] = {}

        if use_cache and os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data.get("assets", []):
                        cached_entries[item["file_path"]] = item
            except Exception as e:
                print(f"[AssetIndexer] 캐시 로드 실패: {e}")

        # 파일 목록 수집
        media_files = []
        if recursive:
            for root, _, files in os.walk(dir_path):
                for f in files:
                    ext = os.path.splitext(f)[1].lower()
                    if ext in VIDEO_EXTENSIONS or ext in IMAGE_EXTENSIONS:
                        media_files.append(os.path.join(root, f))
        else:
            for f in os.listdir(dir_path):
                full_path = os.path.join(dir_path, f)
                if os.path.isfile(full_path):
                    ext = os.path.splitext(f)[1].lower()
                    if ext in VIDEO_EXTENSIONS or ext in IMAGE_EXTENSIONS:
                        media_files.append(full_path)

        # 수동 오버라이드 매니페스트 확인 (assets.json)
        manual_manifest = self._load_manual_manifest(dir_path)

        indexed_assets: List[AssetMetadata] = []

        for f_path in media_files:
            abs_path = os.path.abspath(f_path)
            try:
                stat = os.stat(abs_path)
                mtime = stat.st_mtime
                size = stat.st_size

                # 캐시 유효성 확인: 경로가 일치하고 mtime/size가 일치하면 재사용
                cached = cached_entries.get(abs_path)
                if cached and cached.get("_mtime") == mtime and cached.get("_size") == size:
                    asset = AssetMetadata.from_dict(cached)
                else:
                    asset = self.index_file(abs_path)
                    cached_data = asset.to_dict()
                    cached_data["_mtime"] = mtime
                    cached_data["_size"] = size
                    cached_entries[abs_path] = cached_data

                # 수동 오버라이드 병합
                f_name = os.path.basename(abs_path)
                if f_name in manual_manifest:
                    self._apply_manual_override(asset, manual_manifest[f_name])

                indexed_assets.append(asset)
            except Exception as ex:
                print(f"[AssetIndexer] 파일 색인 실패 ({abs_path}): {ex}")

        # 캐시 저장
        if use_cache:
            self._save_cache(cache_path, indexed_assets, cached_entries)

        print(f"[AssetIndexer] 색인 완료: {len(indexed_assets)}개 에셋 (스캔 대상: {dir_path})")
        return indexed_assets


    def index_file(self, file_path: str) -> AssetMetadata:
        """단일 파일에 대해 FFprobe 및 경로 파싱을 실행하여 AssetMetadata 생성"""
        ext = os.path.splitext(file_path)[1].lower()
        media_type = "video" if ext in VIDEO_EXTENSIONS else "image"

        # 1. 기술적 속성 추출 (FFprobe)
        tech_info = self.probe_media(file_path, media_type)

        # 2. 경로 및 파일명 기반 의미론적 속성 파싱
        sem_info = self.parse_metadata_from_path(file_path)

        # 3. AssetMetadata 결합
        asset = AssetMetadata(
            file_path=os.path.abspath(file_path),
            file_name=os.path.basename(file_path),
            media_type=media_type,
            width=tech_info.get("width", 0),
            height=tech_info.get("height", 0),
            duration_sec=tech_info.get("duration_sec", 0.0),
            fps=tech_info.get("fps", 30.0),
            subject=sem_info.get("subject", []),
            action=sem_info.get("action", []),
            environment=sem_info.get("environment", []),
            emotion=sem_info.get("emotion", []),
            shot_type=sem_info.get("shot_type", "any"),
            marketing_roles=sem_info.get("marketing_roles", []),
            tags=sem_info.get("tags", []),
        )
        asset.validate()
        return asset

    def probe_media(self, file_path: str, media_type: str) -> dict:
        """FFprobe를 사용하여 width, height, duration, fps를 추출한다."""
        result = {"width": 0, "height": 0, "duration_sec": 0.0, "fps": 30.0}

        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            file_path
        ]

        try:
            p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
            if p.returncode == 0 and p.stdout:
                stdout_text = p.stdout.decode("utf-8", errors="replace").strip()
                if stdout_text:
                    data = json.loads(stdout_text)
                    streams = data.get("streams", [])
                    format_info = data.get("format", {})

                    # 비디오 스트림 찾기
                    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
                    if video_stream:
                        result["width"] = int(video_stream.get("width", 0))
                        result["height"] = int(video_stream.get("height", 0))

                        # fps 계산
                        r_fps = video_stream.get("r_frame_rate", "30/1")
                        if "/" in r_fps:
                            num, den = r_fps.split("/")
                            try:
                                den_val = float(den)
                                result["fps"] = round(float(num) / den_val, 2) if den_val != 0 else 30.0
                            except ValueError:
                                result["fps"] = 30.0
                        else:
                            try:
                                result["fps"] = round(float(r_fps), 2)
                            except ValueError:
                                result["fps"] = 30.0

                        # duration
                        dur_str = video_stream.get("duration") or format_info.get("duration")
                        if dur_str:
                            result["duration_sec"] = round(float(dur_str), 2)
        except Exception as e:
            # ffprobe 에러 시 기본값 유지
            pass

        return result

    def parse_metadata_from_path(self, file_path: str) -> dict:
        """파일명 및 부모 폴더 경로로부터 의미론적 태그 및 속성을 추출한다."""
        filename = os.path.basename(file_path).lower()
        parent = os.path.basename(os.path.dirname(file_path)).lower()
        combined_text = f"{parent} {filename}"

        subjects = set()
        actions = set()
        environments = set()
        emotions = set()
        marketing_roles = set()
        tags = set()
        shot_type = "any"

        # 파일명 자체의 단어들 기본 태그로 추가
        raw_words = re.findall(r'[a-zA-Z0-9가-힣]+', combined_text)
        for w in raw_words:
            if len(w) > 1 and not w.isdigit():
                tags.add(w)

        # 사전 규칙 매칭
        for rule in TAG_SYNONYM_RULES:
            matched = False
            for k in rule["keys"]:
                if k in combined_text:
                    matched = True
                    break

            if matched:
                if "subject" in rule:
                    subjects.update(rule["subject"])
                if "action" in rule:
                    actions.update(rule["action"])
                if "environment" in rule:
                    environments.update(rule["environment"])
                if "emotion" in rule:
                    emotions.update(rule["emotion"])
                if "marketing_roles" in rule:
                    marketing_roles.update(rule["marketing_roles"])
                if "shot_type" in rule and shot_type == "any":
                    shot_type = rule["shot_type"]
                if "tags" in rule:
                    tags.update(rule["tags"])

        # shot_type 키워드 체크
        if "closeup" in combined_text or "close_up" in combined_text:
            shot_type = "closeup"
        elif "wide" in combined_text:
            shot_type = "wide"
        elif "cropped" in combined_text:
            shot_type = "medium"

        return {
            "subject": sorted(list(subjects)),
            "action": sorted(list(actions)),
            "environment": sorted(list(environments)),
            "emotion": sorted(list(emotions)),
            "marketing_roles": sorted(list(marketing_roles)),
            "tags": sorted(list(tags)),
            "shot_type": shot_type
        }

    def _load_manual_manifest(self, dir_path: str) -> Dict[str, dict]:
        """디렉토리 내 assets.json 매니페스트가 있을 경우 로드"""
        manifest_path = os.path.join(dir_path, "assets.json")
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return {item.get("file_name", ""): item for item in data}
                    elif isinstance(data, dict):
                        return data.get("assets", {})
            except Exception as e:
                print(f"[AssetIndexer] assets.json 로드 실패: {e}")
        return {}

    def _apply_manual_override(self, asset: AssetMetadata, override: dict):
        """수동 매니페스트 정보로 AssetMetadata 갱신"""
        for field_name in ("subject", "action", "environment", "emotion", "tags", "marketing_roles"):
            if field_name in override:
                val = override[field_name]
                if isinstance(val, list):
                    current = getattr(asset, field_name)
                    setattr(asset, field_name, sorted(list(set(current + val))))

        if "shot_type" in override:
            asset.shot_type = override["shot_type"]
        if "visual_quality" in override:
            asset.visual_quality = float(override["visual_quality"])
        if "highlight_ranges" in override:
            asset.highlight_ranges = override["highlight_ranges"]

    def _save_cache(self, cache_path: str, assets: List[AssetMetadata], cache_dict: Dict[str, dict]):
        """색인 결과 캐시 JSON 저장"""
        try:
            entries = []
            for a in assets:
                entry = dict(cache_dict.get(a.file_path, a.to_dict()))
                if "_mtime" not in entry or "_size" not in entry:
                    try:
                        st = os.stat(a.file_path)
                        entry["_mtime"] = st.st_mtime
                        entry["_size"] = st.st_size
                    except Exception:
                        pass
                entries.append(entry)

            output = {
                "total_assets": len(assets),
                "assets": entries
            }
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(output, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[AssetIndexer] 캐시 저장 실패: {e}")

