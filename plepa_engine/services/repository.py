"""
plepa_engine.services.repository
파일 원자적 저장(Atomic Save), 자동 회전 백업(.plepa_backup/), 일관된 JSON 직렬화 및 안전 삭제(Trash) 유틸리티.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel

from plepa_engine.config import ROOT_DIR

BACKUP_DIR = ROOT_DIR / ".plepa_backup"
DEFAULT_MAX_BACKUPS = 20


class Repository:
    """JSON 및 일반 파일의 원자적 저장 및 자동 백업 관리자."""

    def __init__(self, backup_dir: Path = BACKUP_DIR, max_backups: int = DEFAULT_MAX_BACKUPS):
        self.backup_dir = backup_dir
        self.max_backups = max_backups

    def read_json(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """JSON 파일을 읽어 파이썬 딕셔너리로 반환합니다."""
        p = Path(file_path).resolve()
        if not p.is_file():
            raise FileNotFoundError(f"파일을 찾을 수 없습니다: {p}")
        with open(p, "r", encoding="utf-8-sig") as f:
            return json.load(f)

    def write_json(
        self,
        file_path: Union[str, Path],
        data: Union[Dict[str, Any], List[Any], BaseModel],
        backup: bool = True
    ) -> Path:
        """
        데이터를 JSON 문자열로 직렬화하여 원자적(Atomic)으로 저장하고,
        기존 파일이 있을 경우 .plepa_backup/에 회전 백업을 남깁니다.
        """
        target = Path(file_path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(data, BaseModel):
            dict_data = data.model_dump(by_alias=True, exclude_none=False)
        else:
            dict_data = data

        formatted_json = json.dumps(dict_data, indent=2, ensure_ascii=False) + "\n"

        # 1. 자동 회전 백업
        if backup and target.is_file():
            self._create_backup(target)

        # 2. 원자적 쓰기 (동일 드라이브/디렉토리에 임시 파일 작성 후 os.replace)
        temp_file = target.with_suffix(f".tmp_{os.getpid()}_{int(time.time() * 1000)}")
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                f.write(formatted_json)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_file, target)
        except Exception:
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except OSError:
                    pass
            raise

        return target

    def _create_backup(self, target: Path) -> Optional[Path]:
        """지정된 파일의 스냅샷 백업을 생성하고 오래된 백업을 회전 삭제합니다."""
        try:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            backup_name = f"{target.stem}_{timestamp}{target.suffix}.bak"
            backup_path = self.backup_dir / backup_name

            shutil.copy2(target, backup_path)
            self._rotate_backups(target.stem)
            return backup_path
        except Exception as e:
            # 백업 실패가 본체 저장을 중단시키지 않도록 로깅만 수행
            print(f"[경고] 백업 생성 실패 ({target.name}): {e}")
            return None

    def _rotate_backups(self, stem: str) -> None:
        """동일한 파일 접두사의 백업이 max_backups개를 초과하면 오래된 파일부터 삭제합니다."""
        try:
            pattern = f"{stem}_*.bak"
            backups = sorted(
                self.backup_dir.glob(pattern),
                key=lambda p: p.stat().st_mtime
            )
            while len(backups) > self.max_backups:
                oldest = backups.pop(0)
                try:
                    oldest.unlink()
                except OSError:
                    pass
        except Exception:
            pass

    def move_to_trash(self, file_path: Union[str, Path]) -> Optional[Path]:
        """파일을 직접 영구 삭제하지 않고 상위 디렉터리의 _trash/ 폴더로 이동합니다."""
        p = Path(file_path).resolve()
        if not p.exists():
            return None

        trash_dir = p.parent / "_trash"
        trash_dir.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        trash_path = trash_dir / f"{timestamp}_{p.name}"

        shutil.move(str(p), str(trash_path))
        return trash_path


# 기본 공유 싱글톤 리포지토리 인스턴스
default_repo = Repository()
