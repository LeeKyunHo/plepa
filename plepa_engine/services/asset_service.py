"""
plepa_engine.services.asset_service
생성된 캐릭터 에셋 파일 인덱싱, 갤러리 매트릭스 매핑, 레퍼런스 이미지 탐색 및 안전 삭제.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from plepa_engine.config import DEFAULT_ROSTER, PROJECTS_DIR
from plepa_engine.services.repository import Repository, default_repo


class AssetService:
    """에셋 파일 및 갤러리 데이터 관리 서비스."""

    def __init__(self, repo: Optional[Repository] = None):
        self.repo = repo or default_repo

    def get_character_asset_dir(self, prefix: str, roster: str = DEFAULT_ROSTER) -> Path:
        """캐릭터 에셋 디렉터리 경로 반환."""
        return PROJECTS_DIR / roster / "assets" / prefix

    def find_reference_image(
        self,
        prefix: str,
        roster: str = DEFAULT_ROSTER,
        custom_path: Optional[str] = None
    ) -> Optional[Path]:
        """캐릭터의 참조 이미지를 탐색합니다 (지정 경로 -> references/{prefix}.{ext} 순)."""
        if custom_path:
            p = Path(custom_path)
            if p.is_file():
                return p
            cand = PROJECTS_DIR / roster / "references" / custom_path
            if cand.is_file():
                return cand
            raise FileNotFoundError(f"지정한 레퍼런스 이미지를 찾을 수 없습니다: {custom_path}")

        ref_dir = PROJECTS_DIR / roster / "references"
        if not ref_dir.is_dir():
            return None

        for ext in (".webp", ".png", ".jpg", ".jpeg"):
            cand = ref_dir / f"{prefix}{ext}"
            if cand.is_file():
                return cand

        return None

    def list_character_assets(self, prefix: str, roster: str = DEFAULT_ROSTER) -> List[Dict[str, Any]]:
        """
        해당 캐릭터의 에셋 파일들을 검색하여 메타데이터 리스트를 반환합니다.
        반환: List[{ code, label, path, censored_path, origin_path, size_bytes, mtime }]
        """
        asset_dir = self.get_character_asset_dir(prefix, roster)
        if not asset_dir.is_dir():
            return []

        origin_dir = PROJECTS_DIR / roster / "assets" / f"{prefix}_origin"

        # { "000": { "path": ..., "censored_path": ..., "origin_path": ... } }
        items_by_code: Dict[str, Dict[str, Any]] = {}

        # 영숫자 포즈 코드 규격 지원 (예: 000, A00, C01, N01, N28 등)
        pattern = re.compile(rf"^{re.escape(prefix)}_([A-Za-z0-9]+)(?:_(.*?))?(?:_censored)?\.(webp|png)$")

        for f in sorted(asset_dir.rglob(f"{prefix}_*")):
            if not f.is_file():
                continue
            m = pattern.match(f.name)
            if not m:
                continue

            code = m.group(1)
            raw_label = m.group(2) or ""
            is_censored = "_censored" in f.name

            if code not in items_by_code:
                items_by_code[code] = {
                    "code": code,
                    "label": raw_label,
                    "path": None,
                    "censored_path": None,
                    "origin_path": None,
                    "size_bytes": 0,
                    "mtime": 0.0,
                }

            if is_censored:
                items_by_code[code]["censored_path"] = f
            else:
                items_by_code[code]["path"] = f
                items_by_code[code]["label"] = raw_label or items_by_code[code]["label"]
                items_by_code[code]["size_bytes"] = f.stat().st_size
                items_by_code[code]["mtime"] = f.stat().st_mtime

                # {prefix}_origin 폴더 내 동일 파일명의 무검열 원본 매핑
                if origin_dir.is_dir():
                    origin_cand = origin_dir / f.name
                    if not origin_cand.is_file():
                        code_matches = list(origin_dir.rglob(f"{prefix}_{code}*"))
                        if code_matches:
                            origin_cand = code_matches[0]
                    if origin_cand.is_file():
                        items_by_code[code]["origin_path"] = origin_cand
                        if not items_by_code[code]["censored_path"]:
                            # 본 폴더의 파일이 검열본으로 교체 배치된 경우
                            items_by_code[code]["censored_path"] = f

        # 정렬 키: 숫자 단독(000) -> 영문+숫자(A00, C01, N01) -> 일반 문자열
        def _code_sort_key(k: str) -> Tuple[int, Any, Any]:
            if k.isdigit():
                return (0, "", int(k))
            if len(k) >= 2 and k[0].isalpha() and k[1:].isdigit():
                return (1, k[0].upper(), int(k[1:]))
            return (2, k, 0)

        # 리스트로 변환 (정렬: 코드 오름차순)
        result = [v for k, v in sorted(items_by_code.items(), key=lambda x: _code_sort_key(x[0])) if v["path"] is not None]
        return result

    def get_matrix_map(
        self,
        prefixes: List[str],
        codes: List[str],
        roster: str = DEFAULT_ROSTER
    ) -> Dict[str, Dict[str, Optional[Path]]]:
        """
        캐릭터(행) x 포즈(열) 매트릭스 그리드를 위한 맵을 생성합니다.
        반환: { prefix: { code: Path 또는 None } }
        """
        matrix: Dict[str, Dict[str, Optional[Path]]] = {}
        for prefix in prefixes:
            matrix[prefix] = {code: None for code in codes}
            assets = self.list_character_assets(prefix, roster)
            for a in assets:
                c = a["code"]
                if c in matrix[prefix]:
                    matrix[prefix][c] = a["path"]
        return matrix

    def delete_asset(self, file_path: Path) -> Optional[Path]:
        """에셋 파일을 휴지통으로 안전하게 이동합니다."""
        return self.repo.move_to_trash(file_path)

    def delete_asset_bundle(self, file_path: Path) -> Dict[str, Any]:
        """
        에셋 파일과 관련된 쌍둥이 에셋(원본 _origin, 검열본 _censored)을 함께 휴지통으로 안전 이동합니다.
        """
        p = Path(file_path).resolve()
        if not p.is_file():
            return {"success": False, "filename": p.name, "moved": [], "code": None, "prefix": None}

        moved: List[Dict[str, str]] = []
        main_trash = self.repo.move_to_trash(p)
        if main_trash:
            moved.append({"original": str(p), "trash": str(main_trash)})

        m = re.match(r"^([a-zA-Z0-9]+)_([a-zA-Z0-9]+)", p.name)
        prefix = m.group(1) if m else None
        code = m.group(2) if m else None

        if prefix:
            for parent in p.parents:
                if parent.name == prefix and parent.parent.name == "assets":
                    origin_root = parent.parent / f"{prefix}_origin"
                    if origin_root.is_dir():
                        sub_rel = p.parent.relative_to(parent)
                        cand_sub = origin_root / sub_rel / p.name
                        cand_flat = origin_root / p.name
                        for cand in (cand_sub, cand_flat):
                            if cand.is_file():
                                o_trash = self.repo.move_to_trash(cand)
                                if o_trash:
                                    moved.append({"original": str(cand), "trash": str(o_trash)})
                    break

        return {
            "success": len(moved) > 0,
            "filename": p.name,
            "moved": moved,
            "code": code,
            "prefix": prefix,
        }

    def restore_asset_bundle(self, moved_list: List[Dict[str, str]]) -> bool:
        """휴지통으로 이동되었던 에셋 번들을 원래 위치로 복원(Undo)합니다."""
        import shutil
        success = True
        for item in moved_list:
            trash_p = Path(item["trash"])
            orig_p = Path(item["original"])
            if trash_p.is_file():
                try:
                    orig_p.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(trash_p), str(orig_p))
                except Exception:
                    success = False
        return success

    def get_missing_poses_by_character(self, roster: str = DEFAULT_ROSTER) -> Dict[str, List[str]]:
        """
        로스터 내 각 캐릭터별로 아직 생성되지 않은(누락된) 포즈 코드 목록을 전수 계산합니다.
        """
        from plepa_engine.services.character_service import default_character_service
        from plepa_engine.services.pose_service import default_pose_service

        chars = default_character_service.list_characters(roster=roster)
        pose_db = default_pose_service.load_pose_db(engine="sdxl", roster=roster)
        all_codes = set(pose_db.keys())

        otokonoko_range = {f"{i:03d}" for i in range(150, 210)} | {"133", "134", "135"}
        female_h_range = {f"{i:03d}" for i in range(80, 140)}

        missing_map: Dict[str, List[str]] = {}

        for char_item in chars:
            if isinstance(char_item, tuple):
                prefix, char_obj = char_item[0], char_item[1]
            else:
                prefix, char_obj = char_item.prefix, char_item
            existing_assets = self.list_character_assets(prefix, roster)
            existing_codes = {a["code"] for a in existing_assets}

            is_otoko = getattr(char_obj, "gender", "") == "otokonoko"
            expected_codes = set()
            for c in all_codes:
                if is_otoko:
                    if c in female_h_range:
                        continue
                    expected_codes.add(c)
                else:
                    if c in otokonoko_range:
                        continue
                    expected_codes.add(c)

            missing_codes = sorted(list(expected_codes - existing_codes))
            missing_map[prefix] = missing_codes

        return missing_map

    def list_misc_assets(self, roster: str = DEFAULT_ROSTER) -> List[Dict[str, Any]]:
        """
        포즈 번호 규격에 묶이지 않은 비포즈 에셋(레퍼런스, 배경, 샘플, 비규격 이미지)을 모두 검색합니다.
        반환: List[{ name, category, path, size_bytes, mtime, folder }]
        """
        roster_dir = PROJECTS_DIR / roster
        if not roster_dir.is_dir():
            return []

        results: List[Dict[str, Any]] = []
        valid_exts = {".webp", ".png", ".jpg", ".jpeg"}

        # 1. 레퍼런스 폴더 탐색 (하위 창고 폴더 포함)
        ref_dir = roster_dir / "references"
        if ref_dir.is_dir():
            for f in sorted(ref_dir.rglob("*")):
                if f.is_file() and f.suffix.lower() in valid_exts:
                    subfolder = f.parent.name
                    cat_label = "레퍼런스 (창고)" if subfolder != "references" else "레퍼런스"
                    results.append({
                        "name": f.name,
                        "category": cat_label,
                        "type": "reference",
                        "path": f,
                        "size_bytes": f.stat().st_size,
                        "mtime": f.stat().st_mtime,
                        "folder": f.parent.relative_to(roster_dir).as_posix(),
                    })

        # 2. 배경 폴더 탐색 (차후 생성될 backgrounds 및 background.json 연계)
        bg_dir = roster_dir / "backgrounds"
        if bg_dir.is_dir():
            for f in sorted(bg_dir.rglob("*")):
                if f.is_file() and f.suffix.lower() in valid_exts:
                    results.append({
                        "name": f.name,
                        "category": "배경 (BG)",
                        "type": "background",
                        "path": f,
                        "size_bytes": f.stat().st_size,
                        "mtime": f.stat().st_mtime,
                        "folder": f.parent.relative_to(roster_dir).as_posix(),
                    })

        # 3. 에셋 폴더 내 비정규 포즈 파일 및 샘플 이미지 탐색
        assets_dir = roster_dir / "assets"
        pose_pattern = re.compile(r"^.+_[A-Za-z0-9]+(?:_.*)?\.(webp|png)$")
        if assets_dir.is_dir():
            for f in sorted(assets_dir.rglob("*")):
                if f.is_file() and f.suffix.lower() in valid_exts:
                    # 3자리 포즈 번호 규격이 아닌 파일
                    if not pose_pattern.match(f.name):
                        results.append({
                            "name": f.name,
                            "category": "비규격/샘플",
                            "type": "sample",
                            "path": f,
                            "size_bytes": f.stat().st_size,
                            "mtime": f.stat().st_mtime,
                            "folder": f.parent.relative_to(roster_dir).as_posix(),
                        })

        # 최신 수정 순 정렬
        results.sort(key=lambda x: x["mtime"], reverse=True)
        return results

    def restore_from_origin(self, prefix: str, code: str, roster: str = DEFAULT_ROSTER) -> bool:
        """
        assets/{prefix}_origin/ 폴더의 원본 파일을 assets/{prefix}/로 덮어써서 무검열 원본으로 복원합니다.
        성공 시 True, 원본 파일이 없으면 False 반환. (V3 서브폴더 및 플랫 구조 동시 지원)
        """
        import shutil
        from plepa_engine.services.pose_service import default_pose_service
        from plepa_engine.reporter import get_subfolder_for_code

        origin_dir = PROJECTS_DIR / roster / "assets" / f"{prefix}_origin"
        asset_dir = self.get_character_asset_dir(prefix, roster)
        if not origin_dir.is_dir() or not asset_dir.is_dir():
            return False

        code_str = default_pose_service.normalize_code(code)
        matches = list(origin_dir.rglob(f"{prefix}_{code_str}*"))
        if not matches:
            return False

        src_file = matches[0]
        subfolder = get_subfolder_for_code(code_str)
        sub_asset_dir = asset_dir / subfolder

        existing_targets = list(asset_dir.rglob(f"{prefix}_{code_str}*"))
        if existing_targets:
            dst_file = existing_targets[0]
        else:
            sub_asset_dir.mkdir(parents=True, exist_ok=True)
            dst_file = sub_asset_dir / src_file.name

        shutil.copy2(src_file, dst_file)
        return True

    def audit_roster_assets(self, roster: str = DEFAULT_ROSTER) -> List[Dict[str, Any]]:
        """
        지정된 로스터 내 모든 캐릭터의 에셋 완비 상태, 누락 포즈, 구버전 라벨 불일치,
        _origin 무검열 백업 보유 여부를 1초 전수 감사하여 리스트로 반환합니다.
        """
        from plepa_engine.services.character_service import default_character_service
        from plepa_engine.services.pose_service import default_pose_service

        char_dir = PROJECTS_DIR / roster / "characters"
        if not char_dir.is_dir():
            return []

        pose_db = default_pose_service.load_pose_db(engine="sdxl", roster=roster)
        expected_codes = default_pose_service.resolve_pose_codes("all", pose_db, roster=roster)

        # 오토코노코 전용 V3 오프셋 매핑 셋 (기본 성인 080~139: +70 -> 150~209)
        otokonoko_offset_map = {
            f"{i:03d}": f"{i+70:03d}" for i in range(80, 140)
        }
        # 레거시 하위 호환
        otokonoko_offset_map.update({
            "130": "200",
            "131": "201",
            "132": "202",
        })

        results = []
        char_files = sorted(char_dir.glob("*.json"))

        for cf in char_files:
            try:
                char_obj, _ = default_character_service.find_character(cf.stem, roster=roster)
            except Exception:
                continue

            prefix = char_obj.prefix
            is_otokonoko = (getattr(char_obj, "gender", "") or "").lower() == "otokonoko"

            # 캐릭터 젠더별 맞춤 기대 코드 계산 (V3 규격)
            otokonoko_range = {f"{i:03d}" for i in range(150, 210)} | {"133", "134", "135"}
            female_h_range = {f"{i:03d}" for i in range(80, 140)}

            if is_otokonoko:
                char_expected_codes = [c for c in expected_codes if c not in female_h_range]
            else:
                char_expected_codes = [c for c in expected_codes if c not in otokonoko_range]

            assets = self.list_character_assets(prefix, roster=roster)
            assets_by_code = {a["code"]: a for a in assets}

            present_codes = set(assets_by_code.keys())
            missing_codes = [c for c in char_expected_codes if c not in present_codes]

            # 구버전 라벨 불일치 수 계산 (공백 및 언더스코어 정규화 비교)
            outdated_labels = 0
            for code, a in assets_by_code.items():
                if code in pose_db:
                    canonical_label = pose_db[code].label
                    clean_file_label = (a["label"] or "").replace("_", "").replace(" ", "")
                    clean_canon_label = (canonical_label or "").replace("_", "").replace(" ", "")
                    if clean_file_label and clean_canon_label and clean_file_label != clean_canon_label:
                        outdated_labels += 1

            # _origin 백업 보유 수 계산
            origin_count = sum(1 for a in assets if a.get("origin_path") is not None)

            expected_count = len(char_expected_codes)
            present_count = len(present_codes)
            rate = round((present_count / expected_count * 100), 1) if expected_count > 0 else 0.0

            results.append({
                "prefix": prefix,
                "name": char_obj.name,
                "gender": char_obj.gender,
                "expected_count": expected_count,
                "present_count": present_count,
                "missing_codes": missing_codes,
                "missing_count": len(missing_codes),
                "completion_rate": rate,
                "outdated_labels": outdated_labels,
                "origin_count": origin_count,
            })

        return results


default_asset_service = AssetService()
