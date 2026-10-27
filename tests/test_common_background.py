"""
tests/test_common_background.py
공용 배경(None / Simple White / Studio) 프리셋 및 배경 차단 로직 단위/계약 테스트.
"""

from __future__ import annotations

import unittest
from plepa_engine.models import CharacterConfig, PoseEntry
from plepa_engine.prompt_builder import _is_no_background, assemble_flux_prompt, assemble_sdxl_prompt
from plepa_engine.services.background_service import default_background_service, is_no_background_preset


class TestCommonBackground(unittest.TestCase):
    def setUp(self):
        self.bg_svc = default_background_service
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
        """공용 배경 프리셋 목록 및 최상위 'none' 순서 계약 검증."""
        bgs = self.bg_svc.get_backgrounds("campus", engine="sdxl")
        keys = list(bgs.keys())
        self.assertIn("none", keys)
        self.assertIn("white_studio", keys)
        self.assertIn("grey_studio", keys)
        self.assertIn("default", keys)
        self.assertEqual(keys[0], "none")

    def test_engine_specific_prompt_resolution(self):
        """SDXL 및 FLUX 엔진별 프롬프트 자동 분기 검증."""
        sdxl_prompt = self.bg_svc.get_preset("campus", key="none", engine="sdxl")
        flux_prompt = self.bg_svc.get_preset("campus", key="none", engine="flux")

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
        pose_emotion = PoseEntry(
            code="T00",
            section="emotions",
            label="평상",
            prompt="standing, looking at viewer, gentle smile, clean background, cowboy shot",
        )
        pose_daily = PoseEntry(
            code="T24",
            section="poses",
            label="뒤태",
            prompt="standing, from behind, looking back at viewer",
        )
        none_bg = self.bg_svc.get_preset("campus", key="none", engine="sdxl")

        pos_0, neg_0, _ = assemble_sdxl_prompt(self.dummy_char, pose_emotion, bg_prompt=none_bg)
        self.assertIn("white background", pos_0)
        self.assertIn("detailed background", neg_0)
        self.assertIn("furniture", neg_0)

        pos_24, neg_24, _ = assemble_sdxl_prompt(self.dummy_char, pose_daily, bg_prompt=none_bg)
        self.assertIn("white background", pos_24)
        self.assertIn("solid background", pos_24)
        self.assertIn("detailed background", neg_24)
        self.assertIn("outdoors, indoors, scenery", neg_24)

    def test_flux_assemble_with_none_background(self):
        """FLUX 조립 시 none 배경 선택 시 자연어 치환 및 무배경 서술 검증."""
        pose_emotion = PoseEntry(
            code="T00",
            section="emotions",
            label="평상",
            prompt="Standing naturally with a gentle smile. Clean minimalist indoor background.",
        )
        pose_daily = PoseEntry(
            code="T24",
            section="poses",
            label="뒤태",
            prompt="Standing from behind looking back over shoulder in a cozy room.",
        )
        none_bg = self.bg_svc.get_preset("campus", key="none", engine="flux")

        prompt_0, _ = assemble_flux_prompt(self.dummy_char, pose_emotion, bg_prompt=none_bg)
        self.assertIn("pure white background", prompt_0.lower())
        self.assertNotIn("Clean minimalist indoor background", prompt_0)

        prompt_24, _ = assemble_flux_prompt(self.dummy_char, pose_daily, bg_prompt=none_bg)
        self.assertIn("pure white minimalist background", prompt_24.lower())
        self.assertIn("no furniture and no scenery", prompt_24.lower())


if __name__ == "__main__":
    unittest.main()
