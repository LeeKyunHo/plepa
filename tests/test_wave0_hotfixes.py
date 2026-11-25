"""
tests/test_wave0_hotfixes.py
Wave 0 치명 결함 4종 종결 회귀 테스트:
1. gallery.py 라이트박스 _batch_manifest.json(items: list) 파싱 무결성 (TD-01)
2. CharacterSchema / characters.py 저장 / CharacterService.clone_character 무손실 왕복 보존 (TD-02)
3. settings.py 원클릭 프리셋 영속화 및 GenerationService 설정 우선순위(params > config > profile) (TD-03)
4. scripts/sync_to_kiro.py 안전 실행 차단 가드(--force-unsafe 필수) (TD-04)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import plepa_engine.services.character_service as char_svc_mod
import plepa_engine.services.config_service as cfg_svc_mod
from plepa_engine.checkpoint_service import CheckpointService
from plepa_engine.services.character_service import CharacterService
from plepa_engine.services.config_service import ConfigService, DEFAULT_CONFIG
from plepa_engine.services.generation_service import (
    GenerationParams,
    resolve_effective_sdxl_params,
)
from plepa_engine.services.repository import Repository
from plepa_engine.services.schemas import CharacterSchema
from plepa_gui.pages.characters import build_updated_character_schema
from plepa_gui.pages.gallery import parse_manifest_items_map
from plepa_gui.pages.settings import apply_settings_preset
import scripts.sync_to_kiro as sync_to_kiro


def test_lightbox_manifest_list_items_parsing_no_crash():
    """_save_batch_manifest가 생성하는 list 형태 items 및 상위 timestamp를 크래시 없이 인덱싱해야 합니다."""
    raw_manifest = {
        "prefix": "aya",
        "roster": "campus",
        "timestamp": "2026-11-25T21:00:00",
        "items": [
            {"code": "000", "label": "평상", "seed": 123456, "success": True},
            {"code": "034", "label": "가슴에얼굴묻기", "seed": 987654, "timestamp": "2026-11-25T20:30:00"},
        ],
    }
    parsed = parse_manifest_items_map(raw_manifest)
    assert parsed["000"]["seed"] == 123456
    assert parsed["000"]["timestamp"] == "2026-11-25T21:00:00"
    assert parsed["034"]["seed"] == 987654
    assert parsed["034"]["timestamp"] == "2026-11-25T20:30:00"
    assert parse_manifest_items_map(None) == {}
    assert parse_manifest_items_map(["invalid"]) == {}


def test_character_gui_save_and_clone_preserve_extended_fields(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """캐릭터 GUI 폼 저장 및 복제 마법사 실행 시 확장 필드와 미지 커스텀 키가 100% 보존되어야 합니다."""
    projects_dir = tmp_path / "projects"
    char_dir = projects_dir / "campus" / "characters"
    char_dir.mkdir(parents=True)
    monkeypatch.setattr(char_svc_mod, "PROJECTS_DIR", projects_dir)

    repo = Repository(backup_dir=tmp_path / "backups")
    svc = CharacterService(repo=repo)

    original_payload = {
        "prefix": "mai",
        "name": "하세가와 마이",
        "gender": "female",
        "faction": "faculty",
        "appearance": {
            "face_and_hair": "ash gray hair, eyeglasses",
            "physique": "petite, busty",
            "outfit": "white lab coat, turtleneck",
        },
        "lora": {"name": "mai_v1.safetensors", "weight": 0.75},
        "style_keywords": "masterpiece",
        "sdxl_positive": "masterpiece BREAK 1girl, eyeglasses, lab coat",
        "sdxl_nude_positive": "masterpiece BREAK 1girl, eyeglasses, bare skin",
        "sdxl_negative": "worst quality, lowres",
        "ref_weight": 0.65,
        "default_mode": "sdxl",
        "outfits": {
            "swimsuit": "black bikini",
            "bunny": "black bunny suit",
        },
        "profiles": {
            "casual": {"outfit": "knit sweater"},
        },
        "pose_restrictions": {
            "exclude": ["999"],
        },
        "signature_accessories": ["rimless eyeglasses"],
        "custom_extra_meta": {"voice_tone": "calm", "version": 2},
    }
    src_file = char_dir / "mai.json"
    src_file.write_text(json.dumps(original_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # 1. GUI 폼 로드 -> 일부 필드 수정 -> build_updated_character_schema -> save_character 왕복 검증
    loaded_schema = CharacterSchema.model_validate(repo.read_json(src_file))
    form_fields = {
        "prefix": loaded_schema.prefix,
        "name": "하세가와 마이 (수정)",
        "gender": loaded_schema.gender,
        "is_adult": loaded_schema.is_adult,
        "face_and_hair": loaded_schema.appearance.face_and_hair,
        "physique": loaded_schema.appearance.physique,
        "outfit": loaded_schema.appearance.outfit,
        "lora_name": loaded_schema.lora.name or "",
        "lora_weight": loaded_schema.lora.weight,
        "style_keywords": loaded_schema.style_keywords,
        "sdxl_positive": loaded_schema.sdxl_positive or "",
        "sdxl_nude_positive": loaded_schema.sdxl_nude_positive or "",
        "sdxl_negative": loaded_schema.sdxl_negative or "",
        "ref_weight": 0.5,
        "default_mode": loaded_schema.default_mode or "",
    }
    updated_schema = build_updated_character_schema(loaded_schema, form_fields)
    saved_path = svc.save_character(roster="campus", char=updated_schema, original_file=src_file)
    saved_raw = repo.read_json(saved_path)

    assert saved_raw["name"] == "하세가와 마이 (수정)"
    assert saved_raw["ref_weight"] == 0.5
    assert saved_raw["sdxl_nude_positive"] == original_payload["sdxl_nude_positive"]
    assert saved_raw["outfits"] == original_payload["outfits"]
    assert saved_raw["profiles"] == original_payload["profiles"]
    assert saved_raw["pose_restrictions"] == original_payload["pose_restrictions"]
    assert saved_raw["signature_accessories"] == original_payload["signature_accessories"]
    assert saved_raw["faction"] == "faculty"
    assert saved_raw["custom_extra_meta"] == {"voice_tone": "calm", "version": 2}

    # 2. clone_character 복제 마법사 무손실 보존 검증
    cloned_path = svc.clone_character(
        src_prefix="mai",
        src_roster="campus",
        new_prefix="mai_alt",
        new_name="마이 변형",
        overrides={"appearance": {"physique": "slender"}},
    )
    cloned_raw = repo.read_json(cloned_path)
    assert cloned_raw["prefix"] == "mai_alt"
    assert cloned_raw["name"] == "마이 변형"
    assert cloned_raw["appearance"]["physique"] == "slender"
    assert cloned_raw["appearance"]["face_and_hair"] == "ash gray hair, eyeglasses"
    assert cloned_raw["sdxl_nude_positive"] == original_payload["sdxl_nude_positive"]
    assert cloned_raw["outfits"] == original_payload["outfits"]
    assert cloned_raw["pose_restrictions"] == original_payload["pose_restrictions"]
    assert cloned_raw["signature_accessories"] == original_payload["signature_accessories"]
    assert cloned_raw["custom_extra_meta"] == {"voice_tone": "calm", "version": 2}


def test_settings_preset_persistence_and_generation_config_priority(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """/settings 프리셋 적용이 디스크에 영구 저장되어야 하며, GenerationService는 params > config > profile 우선순위를 준수해야 합니다."""
    import plepa_engine.config as engine_cfg

    for attr in (
        "DEFAULT_SDXL_CKPT",
        "DEFAULT_SDXL_WIDTH",
        "DEFAULT_SDXL_HEIGHT",
        "DEFAULT_SDXL_STEPS",
        "DEFAULT_SDXL_CFG",
        "DEFAULT_SDXL_SAMPLER",
        "DEFAULT_SDXL_SCHEDULER",
    ):
        monkeypatch.setattr(engine_cfg, attr, getattr(engine_cfg, attr))

    cfg_path = tmp_path / "config.json"
    monkeypatch.setattr(cfg_svc_mod, "CONFIG_FILE", cfg_path)
    repo = Repository(backup_dir=tmp_path / "backups")
    cfg_svc = ConfigService(repo=repo)

    form = dict(DEFAULT_CONFIG)
    apply_settings_preset("wai", form, config_svc=cfg_svc)
    reloaded = cfg_svc.get_config()
    assert reloaded["sdxl_ckpt"] == "waiIllustriousSDXL_v160.safetensors"
    assert reloaded["sdxl_width"] == 896
    assert reloaded["sdxl_height"] == 1152
    assert reloaded["sdxl_cfg"] == 6.0
    assert reloaded["sdxl_sampler"] == "euler_ancestral"

    # 사용자 커스텀 /settings 저장값(steps=34, cfg=5.3)이 기본 체크포인트 프로필(steps=28, cfg=4.0)보다 우선 적용되는지 검증
    custom_conf = cfg_svc.save_config({
        "sdxl_ckpt": DEFAULT_CONFIG["sdxl_ckpt"],
        "sdxl_width": 896,
        "sdxl_height": 1152,
        "sdxl_steps": 34,
        "sdxl_cfg": 5.3,
        "sdxl_sampler": "euler",
        "sdxl_scheduler": "normal",
    })
    default_prof = CheckpointService().get_profile_for_checkpoint(custom_conf["sdxl_ckpt"])

    # 1) params 미지정 시 /settings(conf) 값 채택
    w, h, steps, cfg, sampler, scheduler = resolve_effective_sdxl_params(
        GenerationParams(character_expr="aya", pose_expr="000"),
        custom_conf,
        default_prof,
    )
    assert (w, h, steps, cfg, sampler, scheduler) == (896, 1152, 34, 5.3, "euler", "normal")

    # 2) params 명시 시 params 최우선 채택
    w2, h2, steps2, cfg2, sampler2, scheduler2 = resolve_effective_sdxl_params(
        GenerationParams(character_expr="aya", pose_expr="000", steps=40, cfg=6.5, sampler="dpmpp_2m"),
        custom_conf,
        default_prof,
    )
    assert (w2, h2, steps2, cfg2, sampler2, scheduler2) == (896, 1152, 40, 6.5, "dpmpp_2m", "normal")

    # 3) params.ckpt로 다른 체크포인트를 일회성 오버라이드한 경우 해당 체크포인트 프로필 우선
    wai_ckpt = "WAI-NSFW-illustrious-v7.safetensors"
    wai_prof = CheckpointService().get_profile_for_checkpoint(wai_ckpt)
    w3, h3, _, _, _, _ = resolve_effective_sdxl_params(
        GenerationParams(character_expr="aya", pose_expr="000", ckpt=wai_ckpt),
        custom_conf,
        wai_prof,
    )
    assert (w3, h3) == (wai_prof.width, wai_prof.height)


def test_sync_to_kiro_blocked_without_force_unsafe(tmp_path: Path):
    """scripts/sync_to_kiro.py는 --force-unsafe 없이는 일반 실행과 --dry-run 모두 즉시 차단(exit 2)되어야 합니다."""
    fake_kiro = tmp_path / "kiro"
    fake_kiro.mkdir()

    assert sync_to_kiro.main(["--kiro-dir", str(fake_kiro)]) == 2
    assert sync_to_kiro.main(["--kiro-dir", str(fake_kiro), "--dry-run"]) == 2
    assert list(fake_kiro.iterdir()) == []
