"""
plepa_engine.services.genit_exporter
Genit 상용 표준 형식({{url}}캐릭터코드/상황코드.webp)으로 에셋을 자동 변환 및 패키징하는 전담 익스포터.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageOps

from plepa_engine.config import PROJECTS_DIR, ROOT_DIR


# 기본 작가 캐릭터 코드 프리셋 매핑
DEFAULT_GENIT_CHARACTER_MAP = {
    "한지아": "AA",
    "서아윤": "BB",
    "정다솜": "CC",
    "차민희": "DD",
    "이수연": "EE",
    "김지아": "FF",
    "윤서희": "GG",
    "박채은": "HH",
}


def denormalize_genit_code(code: str) -> str:
    """
    내부 정규화 코드(A00, A01, B01, N01, D01 등)를 Genit 플랫폼 호출 규격(A0, A1, B1, N1, D1 등)으로 변환합니다.
    - A00 -> A0
    - A01 -> A1
    - B05 -> B5
    - N01 -> N1
    - D04 -> D4
    """
    code_s = code.upper().strip()
    if len(code_s) >= 2 and code_s[0].isalpha() and code_s[1:].isdigit():
        prefix_char = code_s[0]
        num_val = int(code_s[1:])
        return f"{prefix_char}{num_val}"
    return code_s


def extract_pose_code_from_filename(filename: str) -> Optional[str]:
    """
    에셋 파일명에서 포즈 코드를 추출합니다.
    예:
      - mal_A00_첫등장.webp -> A00
      - mal_A01_평상시기쁨.webp -> A01
      - ren_N01_정상위삽입.webp -> N01
      - mal_D01_수영복전신.webp -> D01
      - mal_034_가슴파묻힘.webp -> 034
    """
    stem = Path(filename).stem
    parts = stem.split("_")
    if len(parts) >= 2:
        candidate = parts[1]
        # 영문접두사+숫자 또는 3자리 숫자
        if re.match(r"^[A-Za-z]\d{2,3}$", candidate) or re.match(r"^\d{3}$", candidate):
            return candidate.upper()
    return None


class GenitExporter:
    """Genit 플랫폼 규격 에셋 패키징 및 내보내기 서비스."""

    @staticmethod
    def _load_roster_export_map(roster: Optional[str]) -> Dict[str, str]:
        """로스터 디렉토리 내 genit_map.json 설정(데이터 주도형 매핑)을 로드합니다."""
        if not roster:
            return {}
        map_path = PROJECTS_DIR / roster / "genit_map.json"
        if map_path.is_file():
            try:
                data = json.loads(map_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return {str(k): str(v).strip().upper() for k, v in data.items() if str(v).strip()}
            except Exception:
                return {}
        return {}

    @staticmethod
    def resolve_export_code(
        char_name: str,
        char_prefix: str,
        custom_code: Optional[str] = None,
        roster: Optional[str] = None,
    ) -> str:
        """캐릭터 이름 또는 prefix를 기반으로 Genit 2글자 캐릭터 코드를 결정합니다."""
        if custom_code and custom_code.strip():
            return custom_code.strip().upper()

        # 1. 로스터 데이터 주도형 매핑(projects/{roster}/genit_map.json) 우선 조회
        roster_map = GenitExporter._load_roster_export_map(roster)
        if char_prefix in roster_map:
            return roster_map[char_prefix]
        for name_key, code_val in roster_map.items():
            if name_key and name_key in char_name:
                return code_val

        # 2. 레거시 기본 프리셋 검사 (하위 호환)
        for name_key, code_val in DEFAULT_GENIT_CHARACTER_MAP.items():
            if name_key in char_name:
                return code_val

        # 3. fallback: prefix의 앞 2글자 대문자
        clean_prefix = re.sub(r"[^A-Za-z0-9]", "", char_prefix)
        if len(clean_prefix) >= 2:
            return clean_prefix[:2].upper()
        return (clean_prefix + "X")[:2].upper()

    @staticmethod
    def _write_export_image(
        src_file: Path,
        dest_file: Path,
        target_size: Optional[Tuple[int, int]] = None,
        webp_quality: int = 92,
    ) -> bool:
        """단일 WebP 에셋을 원자적으로 내보냅니다.

        target_size가 지정되고 원본 해상도와 다를 때만 비율 유지 중앙 크롭(Lanczos)으로
        리사이즈하여 저장하며, 동일 해상도이거나 target_size가 None이면 무손실 복사합니다.
        로컬 원본(src_file)은 절대 수정하지 않습니다.
        반환값: 리사이즈 수행 여부(True=리사이즈됨, False=원본 무손실 복사).
        """
        temp_dest = dest_file.parent / f".{dest_file.name}.{uuid.uuid4().hex[:8]}.tmp"
        resized = False
        try:
            if target_size is not None:
                with Image.open(src_file) as im:
                    if (im.width, im.height) != target_size:
                        fitted = ImageOps.fit(
                            im.convert("RGB"),
                            target_size,
                            method=Image.Resampling.LANCZOS,
                            centering=(0.5, 0.5),
                        )
                        fitted.save(temp_dest, format="WEBP", quality=webp_quality, method=4)
                        resized = True
                    else:
                        shutil.copy2(src_file, temp_dest)
            else:
                shutil.copy2(src_file, temp_dest)
            os.replace(temp_dest, dest_file)
            return resized
        finally:
            if temp_dest.exists():
                temp_dest.unlink(missing_ok=True)

    def export_character(
        self,
        roster: str,
        char_prefix: str,
        char_name: str,
        output_dir: Optional[Path] = None,
        custom_export_code: Optional[str] = None,
        target_size: Optional[Tuple[int, int]] = None,
        keep_original_filename: bool = False,
        webp_quality: int = 92,
    ) -> Tuple[int, Path, str]:
        """
        단일 캐릭터의 생성된 에셋들을 Genit 규격으로 복사/내보냅니다.
        - keep_original_filename=False (기본): output_dir/{export_code}/{상황코드}.webp
        - keep_original_filename=True: output_dir/{char_prefix}/{원본파일명}.webp (예: aya/aya_000_평상.webp)
        - target_size=(W, H): 원본이 해당 해상도와 다를 때만 비율 유지 중앙 크롭(Lanczos) 통일 (로컬 원본 무손실 보존)
        반환값: (내보낸 파일 수, 대상 폴더 경로, 결정된 캐릭터 코드)
        """
        from plepa_engine.services.pose_service import default_pose_service

        export_code = (
            char_prefix
            if keep_original_filename
            else self.resolve_export_code(char_name, char_prefix, custom_export_code, roster=roster)
        )
        target_root = output_dir or (ROOT_DIR / "dist" / "genit")
        target_dir = target_root / export_code
        target_dir.mkdir(parents=True, exist_ok=True)

        assets_dir = PROJECTS_DIR / roster / "assets" / char_prefix
        if not assets_dir.is_dir():
            return 0, target_dir, export_code

        pose_db = default_pose_service.load_pose_db(engine="sdxl", roster=roster)
        exported_count = 0
        resized_count = 0
        sheet_rows = []

        for webp_file in sorted(assets_dir.rglob("*.webp")):
            if "_origin" in webp_file.parts or webp_file.name.startswith("."):
                continue
            internal_code = extract_pose_code_from_filename(webp_file.name)
            if not internal_code:
                continue

            genit_code = denormalize_genit_code(internal_code)
            dest_name = webp_file.name if keep_original_filename else f"{genit_code}.webp"
            dest_file = target_dir / dest_name

            if self._write_export_image(
                webp_file,
                dest_file,
                target_size=target_size,
                webp_quality=webp_quality,
            ):
                resized_count += 1
            exported_count += 1

            # 프롬프트 시트용 정보 추출
            label = "미상"
            desc = ""
            norm_code = default_pose_service.normalize_code(internal_code)
            if norm_code in pose_db:
                p_entry = pose_db[norm_code]
                label = p_entry.label
                desc = p_entry.description or p_entry.section
            sheet_rows.append(f"| `{genit_code}` | `{dest_file.name}` | **{label}** | {desc} |")

        size_note = (
            f"`{target_size[0]}x{target_size[1]}` 통일 (리사이즈 {resized_count}장 / 원본 무손실 복사 {exported_count - resized_count}장)"
            if target_size is not None
            else "원본 해상도 유지 (무손실 복사)"
        )

        # _genit_prompt_sheet.md 마크다운 시트 원자적 생성
        sheet_path = target_dir / "_genit_prompt_sheet.md"
        sheet_content = [
            f"# 젠잇(Genit) 프롬프트 매핑 시트 - {char_name} (`{export_code}`)",
            f"",
            f"- **캐릭터 식별자**: `{char_prefix}`",
            f"- **젠잇 코드**: `{export_code}`",
            f"- **내보낸 에셋 수**: {exported_count}개",
            f"- **해상도 처리**: {size_note}",
            f"- **원본 로스터**: `{roster}`",
            f"",
            f"| 젠잇 포즈코드 | 출력 파일명 | 한글 라벨 | 상황 및 연출 설명 |",
            f"| :---: | :--- | :--- | :--- |",
        ] + sheet_rows
        temp_sheet = target_dir / f".{sheet_path.name}.{uuid.uuid4().hex[:8]}.tmp"
        try:
            with open(temp_sheet, "w", encoding="utf-8") as sf:
                sf.write("\n".join(sheet_content) + "\n")
                sf.flush()
                os.fsync(sf.fileno())
            os.replace(temp_sheet, sheet_path)
        finally:
            if temp_sheet.exists():
                temp_sheet.unlink(missing_ok=True)

        return exported_count, target_dir, export_code

    def export_roster(
        self,
        roster: str,
        output_dir: Optional[Path] = None,
        target_size: Optional[Tuple[int, int]] = None,
        keep_original_filename: bool = True,
        webp_quality: int = 92,
    ) -> Tuple[int, Path, int]:
        """로스터 내 모든 캐릭터의 에셋을 일괄 Genit 규격으로 내보냅니다.

        반환값: (총 내보낸 파일 수, 출력 루트 경로, 처리된 캐릭터 수)
        """
        from plepa_engine.services.character_service import default_character_service

        target_root = output_dir or (ROOT_DIR / "dist" / "genit" / roster)
        target_root.mkdir(parents=True, exist_ok=True)
        chars = default_character_service.list_characters(roster=roster)

        total_files = 0
        exported_chars = 0
        for _, c_obj, _ in chars:
            cnt, _, _ = self.export_character(
                roster=roster,
                char_prefix=c_obj.prefix,
                char_name=c_obj.name,
                output_dir=target_root,
                target_size=target_size,
                keep_original_filename=keep_original_filename,
                webp_quality=webp_quality,
            )
            if cnt > 0:
                total_files += cnt
                exported_chars += 1
        return total_files, target_root, exported_chars


default_genit_exporter = GenitExporter()
