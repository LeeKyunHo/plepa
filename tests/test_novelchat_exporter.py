"""tests/test_novelchat_exporter.py — NovelchatExporter 단위 테스트."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from PIL import Image

from plepa_engine.services import novelchat_exporter as ne_mod
from plepa_engine.services.novelchat_exporter import NovelchatExporter


def _make_webp(path: Path, size=(64, 64), color=(120, 180, 220)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path, format="WEBP", quality=80)


def test_export_filename_mapping_and_origin_skip(tmp_path: Path) -> None:
    proj = tmp_path / "projects"
    aya_dir = proj / "campus" / "assets" / "aya"
    _make_webp(aya_dir / "01_normal" / "aya_000_평상.webp")
    _make_webp(aya_dir / "02_h_scenes" / "aya_085_정상위약.webp")
    _make_webp(aya_dir / "_origin" / "aya_000_평상.webp")
    _make_webp(proj / "campus" / "assets" / "aya_origin" / "aya_000_평상.webp")

    exporter = NovelchatExporter(projects_dir=proj, root_dir=tmp_path)
    res = exporter.export_roster("campus", include_adult=True)
    m = res["manifest"]

    assert m["exported_count"] == 2
    out_aya = tmp_path / "dist" / "novelchat" / "campus" / "aya"
    assert (out_aya / "평상_000.webp").is_file()
    assert (out_aya / "정상위_085.webp").is_file()
    assert m["characters"]["aya"]["default_image"] == "평상_000.webp"

    with open(tmp_path / "dist" / "novelchat" / "campus" / "upload_checklist.csv", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
    assert all(r["upload_tier"] == "Bronze" for r in rows)
    assert any(r["default_recommended"] == "★" and r["upload_name"] == "평상_000.webp" for r in rows)


def test_underscore_in_pool_raises(tmp_path: Path) -> None:
    bad_cfg = tmp_path / "bad_pools.json"
    bad_cfg.write_text(json.dumps({"pools": {"bad_pool": {"priority": 1, "is_adult": False, "codes": ["000"]}}}), encoding="utf-8")
    proj = tmp_path / "projects"
    _make_webp(proj / "campus" / "assets" / "aya" / "aya_000_평상.webp")

    exporter = NovelchatExporter(projects_dir=proj, root_dir=tmp_path)
    with pytest.raises(ValueError, match="언더스코어"):
        exporter.export_roster("campus", pool_config=bad_cfg, dry_run=True)


def test_dry_run_creates_no_files(tmp_path: Path) -> None:
    proj = tmp_path / "projects"
    _make_webp(proj / "campus" / "assets" / "aya" / "aya_000_평상.webp")

    exporter = NovelchatExporter(projects_dir=proj, root_dir=tmp_path)
    res = exporter.export_roster("campus", dry_run=True)
    assert res["manifest"]["exported_count"] == 1
    assert not (tmp_path / "dist").exists()


def test_budget_trim_enforces_limit(tmp_path: Path) -> None:
    proj = tmp_path / "projects"
    for prefix in ("aya", "yur"):
        for code in ("000", "001", "002", "003", "004", "005"):
            _make_webp(proj / "campus" / "assets" / prefix / f"{prefix}_{code}_테스트.webp")

    exporter = NovelchatExporter(projects_dir=proj, root_dir=tmp_path)
    with pytest.raises(ValueError, match="상한"):
        exporter.export_roster("campus", max_total=8, trim_to_limit=False, dry_run=True)

    res = exporter.export_roster("campus", max_total=8, trim_to_limit=True, dry_run=True)
    assert res["manifest"]["total_found"] == 12
    assert res["manifest"]["exported_count"] == 8
    assert res["manifest"]["excluded_count"] == 4


def test_oversized_file_optimized_without_touching_origin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    proj = tmp_path / "projects"
    src = proj / "campus" / "assets" / "aya" / "aya_000_평상.webp"
    _make_webp(src, size=(512, 512))
    orig_bytes = src.read_bytes()

    # MAX_FILE_BYTES를 작게 설정해 5MB 초과 경로 강제 검증
    monkeypatch.setitem(ne_mod.NOVELCHAT_LIMITS, "MAX_FILE_BYTES", 200)
    exporter = NovelchatExporter(projects_dir=proj, root_dir=tmp_path)
    res = exporter.export_roster("campus")
    assert res["optimized_count"] == 1
    assert src.read_bytes() == orig_bytes
