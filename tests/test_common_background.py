"""
tests/test_common_background.py
공용 배경(None / Simple White / Studio) 프리셋 및 배경 차단 로직 단위 테스트.
"""

from __future__ import annotations

import unittest
from plepa_engine.models import CharacterConfig, PoseEntry
from plepa_engine.prompt_builder import _is_no_background, assemble_flux_prompt, assemble_sdxl_prompt
from plepa_engine.services.background_service import BackgroundService, default_background_service, is_no_background_preset
from plepa_engine.services.pose_service import default_pose_service


class TestCommonBackground(unittest.TestCase):
    def setUp(self):
        self.bg_svc = default_background_service
        self.pose_svc = default_pose_service
        self.dummy_char = CharacterConfig.from_dict({
            "prefix": "test_hero",
            "name": "테스트 히어로",
            "gender": "female",
            "appearance": {
                "face_and_hair": "long silver hair, blue eyes",
                "physique": "curvy body, slender waist",
                "outfit": "white dress",
            },
            "sdxl_positive": "masterpiece, best quality, glossy skin BREAK 1girl, solo, long silver hair, blue eyes, white dress",
            "sdxl_negative": "lowres, bad quality, 3d, realistic",
        })

    def test_common_presets_structure(self):
        """공용 배경 프리셋 목록 및 순서 검증."""
        bgs = self.bg_svc.get_backgrounds("don", engine="sdxl")
        keys = list(bgs.keys())
        self.assertIn("none", keys)
        self.assertIn("white_studio", keys)
        self.assertIn("grey_studio", keys)
        self.assertIn("default", keys)
        # 'none'이 최상위인지 확인
        self.assertEqual(keys[0], "none")

    def test_engine_specific_prompt_resolution(self):
        """SDXL 및 FLUX 엔진별 프롬프트 자동 분기 검증."""
        sdxl_prompt = self.bg_svc.get_preset("don", key="none", engine="sdxl")
        flux_prompt = self.bg_svc.get_preset("don", key="none", engine="flux")

        self.assertIn("simple background", sdxl_prompt)
        self.assertIn("white background", sdxl_prompt)

        self.assertIn("Isolated on a completely solid pure white background", flux_prompt)
        self.assertIn("no scenery", flux_prompt)

    def test_is_no_background_helpers(self):
        """무배경 판별 헬퍼 함수 동작 검증."""
        self.assertTrue(is_no_background_preset("none"))
        self.assertTrue(is_no_background_preset("no_bg"))
        self.assertTrue(_is_no_background("simple background, white background, solid background"))
        self.assertTrue(_is_no_background("Isolated on a completely solid pure white background"))
        self.assertFalse(_is_no_background("modern luxury apartment living room interior"))

    def test_sdxl_assemble_with_none_background(self):
        """SDXL 조립 시 none 배경 선택 시 긍정/부정 태그 주입 및 배경 차단 검증."""
        sdxl_db = self.pose_svc.load_pose_db(engine="sdxl")
        pose_000 = sdxl_db["000"]
        pose_024 = sdxl_db["024"]
        none_bg = self.bg_svc.get_preset("don", key="none", engine="sdxl")

        # 1. 감정 포즈 (000)
        pos_000, neg_000, _ = assemble_sdxl_prompt(self.dummy_char, pose_000, bg_prompt=none_bg)
        self.assertIn("white background", pos_000)
        self.assertIn("detailed background", neg_000)
        self.assertIn("furniture", neg_000)

        # 2. 일반 착의 뒤태 포즈 (024)
        pos_024, neg_024, _ = assemble_sdxl_prompt(self.dummy_char, pose_024, bg_prompt=none_bg)
        self.assertIn("white background", pos_024)
        self.assertIn("solid background", pos_024)
        self.assertIn("detailed background", neg_024)
        self.assertIn("outdoors, indoors, scenery", neg_024)

    def test_flux_assemble_with_none_background(self):
        """FLUX 조립 시 none 배경 선택 시 자연어 치환 및 무배경 서술 검증."""
        flux_db = self.pose_svc.load_pose_db(engine="flux")
        pose_000 = flux_db["000"]
        pose_024 = flux_db["024"]
        none_bg = self.bg_svc.get_preset("don", key="none", engine="flux")

        prompt_000, _ = assemble_flux_prompt(self.dummy_char, pose_000, bg_prompt=none_bg)
        self.assertIn("pure white background", prompt_000.lower())
        self.assertNotIn("Clean minimalist indoor background", prompt_000)

        prompt_024, _ = assemble_flux_prompt(self.dummy_char, pose_024, bg_prompt=none_bg)
        self.assertIn("pure white minimalist background", prompt_024.lower())
        self.assertIn("no furniture and no scenery", prompt_024.lower())


if __name__ == "__main__":
    unittest.main()
