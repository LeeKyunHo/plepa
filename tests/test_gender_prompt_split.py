import unittest
from plepa_engine.models import CharacterAppearance, CharacterConfig, PoseEntry
from plepa_engine.prompt_builder import assemble_flux_prompt, assemble_sdxl_prompt


class TestGenderPromptSplit(unittest.TestCase):
    def setUp(self):
        self.fem = CharacterConfig(
            prefix="fem",
            name="테스트 여성",
            gender="female",
            appearance=CharacterAppearance(
                face_and_hair="long blonde hair, blue eyes",
                physique="slender figure, busty",
                outfit="school uniform, blazer, pleated skirt",
            ),
            sdxl_positive="1girl, long blonde hair, blue eyes, school uniform, blazer",
        )
        self.oto = CharacterConfig(
            prefix="oto",
            name="테스트 오토코노코",
            gender="otokonoko",
            appearance=CharacterAppearance(
                face_and_hair="short pink hair, amber eyes",
                physique="slender feminine boy, petite",
                outfit="sailor suit, shorts",
            ),
            sdxl_positive="1boy, otokonoko, short pink hair, amber eyes, sailor suit",
        )

    def test_pose_entry_gender_prompt_dispatch(self):
        pose = PoseEntry(
            code="N01",
            section="h_scenes",
            label="정상위삽입",
            prompt="fallback common prompt",
            prompt_female="female missionary position, vaginal penetration",
            prompt_otokonoko="otokonoko missionary position, receptive anal sex, feminine boy",
            required_outfit="nude",
        )

        # 여성 캐릭터 검증
        self.assertEqual(pose.get_prompt("female"), "female missionary position, vaginal penetration")
        self.assertEqual(pose.get_prompt("girl"), "female missionary position, vaginal penetration")

        # 오토코노코 캐릭터 검증
        self.assertEqual(pose.get_prompt("otokonoko"), "otokonoko missionary position, receptive anal sex, feminine boy")

        # 미지정 또는 다른 성별일 때 기본 prompt 폴백
        self.assertEqual(pose.get_prompt("male"), "fallback common prompt")
        self.assertEqual(pose.get_prompt(""), "female missionary position, vaginal penetration")

    def test_assemble_flux_prompt_with_gender_split(self):
        pose = PoseEntry(
            code="N01",
            section="h_scenes",
            label="정상위삽입",
            prompt="generic penetration",
            prompt_female="female missionary position, vaginal penetration, gentle thrusting",
            prompt_otokonoko="otokonoko missionary position, receptive anal sex, blushing boy",
            required_outfit="nude",
        )

        # 여성 플럭스 조립 프롬프트
        prompt_fem, nude_fem = assemble_flux_prompt(self.fem, pose)
        self.assertTrue(nude_fem)
        self.assertIn("female missionary position, vaginal penetration", prompt_fem)
        self.assertNotIn("receptive anal sex", prompt_fem)

        # 오토코노코 플럭스 조립 프롬프트
        prompt_oto, nude_oto = assemble_flux_prompt(self.oto, pose)
        self.assertTrue(nude_oto)
        self.assertIn("otokonoko missionary position, receptive anal sex", prompt_oto)
        self.assertNotIn("vaginal penetration", prompt_oto)

    def test_assemble_sdxl_prompt_with_gender_split(self):
        pose = PoseEntry(
            code="N01",
            section="h_scenes",
            label="정상위삽입",
            prompt="generic penetration",
            prompt_female="missionary, vaginal penetration",
            prompt_otokonoko="missionary, anal, otokonoko",
            required_outfit="nude",
        )

        pos_fem, _, _ = assemble_sdxl_prompt(self.fem, pose)
        self.assertIn("vaginal penetration", pos_fem)
        self.assertNotIn("anal, otokonoko", pos_fem)

        pos_oto, _, _ = assemble_sdxl_prompt(self.oto, pose)
        self.assertIn("anal, otokonoko", pos_oto)
        self.assertNotIn("vaginal penetration", pos_oto)

    def test_pose_entry_fallback_when_gender_prompt_not_provided(self):
        """일반 공용 씬(A 감정, B 행동 등)에서 prompt_female/otokonoko가 없을 때 기본 prompt가 정상 작동하는지 검증"""
        pose = PoseEntry(
            code="A01",
            section="emotions",
            label="평상시",
            prompt="standing proudly, gentle smile, looking at viewer",
            required_outfit="default",
        )

        prompt_fem, _ = assemble_flux_prompt(self.fem, pose)
        self.assertIn("standing proudly, gentle smile", prompt_fem)

        prompt_oto, _ = assemble_flux_prompt(self.oto, pose)
        self.assertIn("standing proudly, gentle smile", prompt_oto)


if __name__ == "__main__":
    unittest.main()
