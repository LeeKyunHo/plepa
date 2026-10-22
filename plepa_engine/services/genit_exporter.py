"""
plepa_engine.services.genit_exporter
Genit 상용 표준 형식({{url}}캐릭터코드/상황코드.webp)으로 에셋을 자동 변환 및 패키징하는 전담 익스포터.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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
    def resolve_export_code(char_name: str, char_prefix: str, custom_code: Optional[str] = None) -> str:
        """캐릭터 이름 또는 prefix를 기반으로 Genit 2글자 캐릭터 코드를 결정합니다."""
        if custom_code and custom_code.strip():
            return custom_code.strip().upper()

        # 사전 정의 프리셋 검사
        for name_key, code_val in DEFAULT_GENIT_CHARACTER_MAP.items():
            if name_key in char_name:
                return code_val

        # fallback: prefix의 앞 2글자 대문자
        clean_prefix = re.sub(r"[^A-Za-z0-9]", "", char_prefix)
        if len(clean_prefix) >= 2:
            return clean_prefix[:2].upper()
        return (clean_prefix + "X")[:2].upper()

    def export_character(
        self,
        roster: str,
        char_prefix: str,
        char_name: str,
        output_dir: Optional[Path] = None,
        custom_export_code: Optional[str] = None,
    ) -> Tuple[int, Path, str]:
        """
        단일 캐릭터의 생성된 에셋들을 Genit 규격(output_dir/{export_code}/{상황코드}.webp)으로 복사/내보냅니다.
        내보내기 완료 시 해당 폴더에 [포즈코드 | 파일명 | 한글상황설명] 매핑 시트(_genit_prompt_sheet.md)를 자동 생성합니다.
        반환값: (내보낸 파일 수, 대상 폴더 경로, 결정된 캐릭터 코드)
        """
        from plepa_engine.services.pose_service import default_pose_service

        export_code = self.resolve_export_code(char_name, char_prefix, custom_export_code)
        target_root = output_dir or (ROOT_DIR / "dist" / "genit")
        target_dir = target_root / export_code
        target_dir.mkdir(parents=True, exist_ok=True)

        assets_dir = PROJECTS_DIR / roster / "assets" / char_prefix
        if not assets_dir.is_dir():
            return 0, target_dir, export_code

        pose_db = default_pose_service.load_pose_db(engine="sdxl", roster=roster)
        exported_count = 0
        sheet_rows = []

        for webp_file in sorted(assets_dir.rglob("*.webp")):
            if "_origin" in webp_file.parts or webp_file.name.startswith("."):
                continue
            internal_code = extract_pose_code_from_filename(webp_file.name)
            if not internal_code:
                continue

            genit_code = denormalize_genit_code(internal_code)
            dest_file = target_dir / f"{genit_code}.webp"

            shutil.copy2(webp_file, dest_file)
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

        # _genit_prompt_sheet.md 마크다운 시트 생성
        sheet_path = target_dir / "_genit_prompt_sheet.md"
        sheet_content = [
            f"# 젠잇(Genit) 프롬프트 매핑 시트 - {char_name} (`{export_code}`)",
            f"",
            f"- **캐릭터 식별자**: `{char_prefix}`",
            f"- **젠잇 코드**: `{export_code}`",
            f"- **내보낸 에셋 수**: {exported_count}개",
            f"- **원본 로스터**: `{roster}`",
            f"",
            f"| 젠잇 포즈코드 | 출력 파일명 | 한글 라벨 | 상황 및 연출 설명 |",
            f"| :---: | :--- | :--- | :--- |",
        ] + sheet_rows
        with open(sheet_path, "w", encoding="utf-8") as sf:
            sf.write("\n".join(sheet_content) + "\n")

        return exported_count, target_dir, export_code


default_genit_exporter = GenitExporter()
