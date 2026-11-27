"""
tests/test_plepa_upscaler.py
scripts/plepa_upscaler.py의 PoseService API 호환성, 2-Track 서브폴더 수집, _origin/_4k 제외 및 None 해상도 방어 검증.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import plepa_engine.services.pose_service as pose_svc_mod
import scripts.plepa_upscaler as upscaler_cli


def test_collect_target_files_uses_load_pose_db_and_scans_subfolders(tmp_path, monkeypatch):
    """collect_target_files가 load_pose_db/resolve_pose_codes를 호출하고 2-Track 서브폴더 내 정규 에셋만 수집하는지 검증."""
    projects_dir = tmp_path / "projects"
    char_assets = projects_dir / "campus" / "assets" / "aya"
    (char_assets / "01_normal").mkdir(parents=True)
    (char_assets / "02_h_scenes").mkdir(parents=True)
    origin_assets = projects_dir / "campus" / "assets" / "aya_origin" / "02_h_scenes"
    origin_assets.mkdir(parents=True)

    target_normal = char_assets / "01_normal" / "aya_000_평상.webp"
    target_h = char_assets / "02_h_scenes" / "aya_064_애무.webp"
    excluded_4k = char_assets / "01_normal" / "aya_000_평상_4k.webp"
    excluded_censored = char_assets / "02_h_scenes" / "aya_064_애무_censored.webp"
    excluded_origin = origin_assets / "aya_064_애무.webp"

    for fp in (target_normal, target_h, excluded_4k, excluded_censored, excluded_origin):
        fp.write_bytes(b"RIFF_DUMMY")

    monkeypatch.setattr(upscaler_cli, "PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(
        upscaler_cli.default_character_service,
        "resolve_characters",
        lambda expr, roster="campus": [(SimpleNamespace(prefix="aya"), roster)],
    )
    monkeypatch.setattr(
        upscaler_cli.default_pose_service,
        "load_pose_db",
        lambda engine="sdxl", roster=None: {"000": SimpleNamespace(code="000"), "064": SimpleNamespace(code="064")},
    )
    monkeypatch.setattr(
        upscaler_cli.default_pose_service,
        "resolve_pose_codes",
        lambda expr, db=None, roster=None: ["000", "064"],
    )

    files = upscaler_cli.collect_target_files(roster="campus", character_expr="aya", pose_expr="000,064")
    assert files == sorted([target_normal, target_h])


def test_upscaler_main_handles_none_dimensions_cleanly(tmp_path, monkeypatch):
    """get_image_dimensions가 None을 반환해도 main()이 크래시 없이 업스케일을 완수하는지 검증."""
    src_img = tmp_path / "aya_000_평상.webp"
    out_img = tmp_path / "aya_000_평상_4k.webp"
    src_img.write_bytes(b"SRC")
    out_img.write_bytes(b"OUT")

    monkeypatch.setattr(upscaler_cli.default_upscale_service, "get_image_dimensions", lambda p: None)
    monkeypatch.setattr(
        upscaler_cli.default_upscale_service,
        "upscale_file",
        lambda f, overwrite=False, upscale_model="4x-UltraSharp.pth": out_img,
    )

    rc = upscaler_cli.main(["-i", str(src_img)])
    assert rc == 0
    assert not hasattr(pose_svc_mod.default_pose_service, "load_db")
