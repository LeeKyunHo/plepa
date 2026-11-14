# -*- coding: utf-8 -*-
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from plepa_engine.qa_validator import validate_generated_image


class TestQAValidator(unittest.TestCase):
    def test_validate_generated_image_clean(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_img = Path(tmp_dir) / "clean_test.webp"
            img = Image.new("RGB", (256, 256), color=(200, 200, 200))
            img.save(test_img, "WEBP")

            passed, reason, details = validate_generated_image(
                test_img,
                is_solo_scene=True,
                is_two_person=False,
                is_offscreen_partner=False,
                section="H-Scenes (Oral/Hand)",
            )
            self.assertTrue(passed)
            self.assertFalse(reason)
            self.assertEqual(details["persons"], 0)
            self.assertIn("blur_score", details)

    def test_validate_generated_image_blur_detection(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_img = Path(tmp_dir) / "flat_test.webp"
            # 단색 이미지는 엣지가 없으므로 Laplacian 점수가 0.0
            img = Image.new("RGB", (256, 256), color=(128, 128, 128))
            img.save(test_img, "WEBP")

            passed, reason, details = validate_generated_image(
                test_img,
                check_blur=True,
                min_blur_score=50.0,
            )
            self.assertFalse(passed)
            self.assertIn("블러/초점 이탈 감지", reason)
            self.assertLess(details["blur_score"], 50.0)

    def test_cpu_thread_limit_and_priority(self):
        import os
        import torch
        import psutil
        from plepa_engine.qa_validator import configure_qa_runtime

        p = psutil.Process(os.getpid()) if os.name == "nt" else None
        orig_nice = p.nice() if p is not None else None
        try:
            if p is not None:
                p.nice(psutil.NORMAL_PRIORITY_CLASS)

            expected_threads = configure_qa_runtime(force=True)
            self.assertEqual(os.environ.get("OMP_NUM_THREADS"), str(expected_threads))
            self.assertEqual(os.environ.get("MKL_NUM_THREADS"), str(expected_threads))
            self.assertEqual(torch.get_num_threads(), expected_threads)

            if p is not None:
                # 기본 호출에서는 웹 서버/프로세스 우선순위를 강등하지 않음
                self.assertEqual(p.nice(), psutil.NORMAL_PRIORITY_CLASS)
                # low_priority=True 명시 시에만 우선순위 하향
                configure_qa_runtime(force=True, low_priority=True)
                self.assertEqual(p.nice(), psutil.BELOW_NORMAL_PRIORITY_CLASS)
        finally:
            if p is not None and orig_nice is not None:
                p.nice(orig_nice)



    def test_multi_hand_and_close_up_focus_logic(self):
        # QA Validator의 키워드 인식 분기 검증
        from unittest.mock import patch

        img = Image.new("RGB", (256, 256), color=(200, 200, 200))

        # 1. multi_hand 키워드 포함 시 손 3개 허용 (Reject 안 됨)
        with patch("plepa_engine.qa_validator.detect_hands", return_value=[((0, 0, 10, 10), "hand", 0.9)] * 3),              patch("plepa_engine.qa_validator.detect_person", return_value=[((0, 0, 10, 10), "person", 0.9)]),              patch("plepa_engine.qa_validator.detect_heads", return_value=[((0, 0, 10, 10), "head", 0.9)]):
            
            # 일반 1인 씬: 손 3개 -> False (리젝트)
            passed_normal, reason_normal, _ = validate_generated_image(
                img, is_solo_scene=True, is_two_person=False, prompt="1girl, solo, standing"
            )
            self.assertFalse(passed_normal)
            self.assertIn("손 증식", reason_normal)

            # paizuri 키워드 포함 씬: 손 3개 -> True (합격)
            passed_pz, _, _ = validate_generated_image(
                img, is_solo_scene=True, is_two_person=False, prompt="1girl, solo, paizuri, chest focus"
            )
            self.assertTrue(passed_pz)

        # 2. 2인 씬이지만 상반신 클로즈업 포커스에서 모브 얼굴(faces > 1) 침범 시 즉시 리젝트
        with patch("plepa_engine.qa_validator.detect_person", return_value=[((0, 0, 10, 10), "person", 0.9)] * 2),              patch("plepa_engine.qa_validator.detect_heads", return_value=[((0, 0, 10, 10), "head", 0.9)]),              patch("plepa_engine.qa_validator.detect_faces", return_value=[((0, 0, 10, 10), "face", 0.9)] * 2):
            
            passed_closeup, reason_closeup, _ = validate_generated_image(
                img, is_solo_scene=False, is_two_person=True, prompt="1girl, upper body close-up, bust shot, face focus"
            )
            self.assertFalse(passed_closeup)
            self.assertIn("모브 얼굴 침범 감지", reason_closeup)

    def test_offscreen_partner_branch_validation(self):
        """오프스크린 파트너 씬(is_two_person=True, is_offscreen_partner=True) 엄격 검증."""
        from unittest.mock import patch

        img = Image.new("RGB", (256, 256), color=(200, 200, 200))

        # faces=2 -> 불량
        with patch("plepa_engine.qa_validator.detect_person", return_value=[((0, 0, 100, 200), "person", 0.9)] * 2), \
             patch("plepa_engine.qa_validator.detect_heads", return_value=[((20, 20, 80, 80), "head", 0.9)]), \
             patch("plepa_engine.qa_validator.detect_faces", return_value=[((25, 25, 75, 75), "face", 0.9)] * 2), \
             patch("plepa_engine.qa_validator.detect_hands", return_value=[]):
            passed, reason, _ = validate_generated_image(
                img, is_solo_scene=False, is_two_person=True, is_offscreen_partner=True, prompt="1girl, fellatio, pov"
            )
            self.assertFalse(passed)
            self.assertIn("오프스크린 파트너 씬 모브 얼굴 노출", reason)

        # heads=2 -> 불량 (detect_faces Short-Circuit)
        with patch("plepa_engine.qa_validator.detect_person", return_value=[((0, 0, 100, 200), "person", 0.9)] * 2), \
             patch("plepa_engine.qa_validator.detect_heads", return_value=[((20, 20, 80, 80), "head", 0.9)] * 2):
            passed, reason, _ = validate_generated_image(
                img, is_solo_scene=False, is_two_person=True, is_offscreen_partner=True, prompt="1girl, handjob"
            )
            self.assertFalse(passed)
            self.assertIn("오프스크린 파트너 씬 머리 초과", reason)

        # faces=1, heads=1, hands=3 -> 정상 통과
        with patch("plepa_engine.qa_validator.detect_person", return_value=[((0, 0, 100, 200), "person", 0.9)] * 2), \
             patch("plepa_engine.qa_validator.detect_heads", return_value=[((20, 20, 80, 80), "head", 0.9)]), \
             patch("plepa_engine.qa_validator.detect_faces", return_value=[((25, 25, 75, 75), "face", 0.9)]), \
             patch("plepa_engine.qa_validator.detect_hands", return_value=[((10, 10, 30, 30), "hand", 0.9)] * 3):
            passed, reason, _ = validate_generated_image(
                img, is_solo_scene=False, is_two_person=True, is_offscreen_partner=True, prompt="1girl, handjob"
            )
            self.assertTrue(passed, reason)

    def test_faceless_male_and_is_kiss_scene_preservation(self):
        """2인 중거리 샷 faceless 위반 차단 및 호출자 is_kiss_scene 인자 보존 검증."""
        from unittest.mock import patch

        img = Image.new("RGB", (256, 256), color=(200, 200, 200))

        with patch("plepa_engine.qa_validator.detect_person", return_value=[((0, 0, 100, 200), "person", 0.9)] * 2), \
             patch("plepa_engine.qa_validator.detect_heads", return_value=[((20, 20, 80, 80), "head", 0.9)] * 2), \
             patch("plepa_engine.qa_validator.detect_faces", return_value=[((25, 25, 75, 75), "face", 0.9)] * 2), \
             patch("plepa_engine.qa_validator.detect_hands", return_value=[]):
            # 1. faceless male 명시 중거리 씬(클로즈업 키워드 없음) + faces=2 -> 불량
            passed, reason, _ = validate_generated_image(
                img,
                is_solo_scene=False,
                is_two_person=True,
                is_kiss_scene=False,
                prompt="1girl, 1boy, faceless male, missionary, bedroom",
            )
            self.assertFalse(passed)
            self.assertIn("faceless 위반", reason)

            # 2. 호출자가 is_kiss_scene=True를 명시 전달한 경우 프롬프트에 kiss가 없어도 보존됨
            passed_kiss, reason_kiss, _ = validate_generated_image(
                img,
                is_solo_scene=False,
                is_two_person=True,
                is_kiss_scene=True,
                prompt="1girl, 1boy, faceless male, embrace",
            )
            self.assertTrue(passed_kiss, reason_kiss)

    def test_color_burn_detection_and_clean_backgrounds(self):
        """Color Burn(과포화 네온/클리핑) 불량 감지 및 정상 흰색/밤 배경 오탐 방지 검증."""
        from unittest.mock import patch

        burned_img = Image.new("RGB", (256, 256), color=(255, 0, 255))
        with patch("plepa_engine.qa_validator.detect_person") as m_person:
            passed, reason, metrics = validate_generated_image(burned_img, prompt="1girl, solo")
            self.assertFalse(passed)
            self.assertIn("색감 과포화(Color Burn)", reason)
            self.assertGreaterEqual(metrics["color_burn_ratio"], 0.9)
            m_person.assert_not_called()

        for clean_rgb in ((255, 255, 255), (10, 14, 28)):
            clean_img = Image.new("RGB", (256, 256), color=clean_rgb)
            with patch("plepa_engine.qa_validator.detect_person", return_value=[((0, 0, 100, 200), "person", 0.9)]), \
                 patch("plepa_engine.qa_validator.detect_heads", return_value=[((20, 20, 80, 80), "head", 0.9)]), \
                 patch("plepa_engine.qa_validator.detect_faces", return_value=[((25, 25, 75, 75), "face", 0.9)]), \
                 patch("plepa_engine.qa_validator.detect_hands", return_value=[]):
                passed, reason, metrics = validate_generated_image(clean_img, prompt="1girl, solo")
                self.assertTrue(passed, reason)
                self.assertEqual(metrics["color_burn_ratio"], 0.0)

    def test_short_circuit_and_subject_lower_bound_and_portrait_aspect(self):
        """detect_person 초과 시 후속 모델 Short-Circuit, 피사체 증발 하한, 1인 화각 드리프트 검증."""
        from unittest.mock import patch

        img = Image.new("RGB", (256, 256), color=(200, 200, 200))

        # 1. detect_person 초과 시 detect_heads/faces/hands 호출되지 않음
        with patch("plepa_engine.qa_validator.detect_person", return_value=[((0, 0, 100, 200), "person", 0.9)] * 2), \
             patch("plepa_engine.qa_validator.detect_heads") as m_heads, \
             patch("plepa_engine.qa_validator.detect_faces") as m_faces, \
             patch("plepa_engine.qa_validator.detect_hands") as m_hands:
            passed, reason, _ = validate_generated_image(img, is_solo_scene=True, prompt="1girl, solo")
            self.assertFalse(passed)
            self.assertIn("인원 초과", reason)
            m_heads.assert_not_called()
            m_faces.assert_not_called()
            m_hands.assert_not_called()

        # 2. 일반 인물 씬 피사체 증발(persons=0) 감지 + 후속 모델 Short-Circuit
        with patch("plepa_engine.qa_validator.detect_person", return_value=[]), \
             patch("plepa_engine.qa_validator.detect_hands") as m_hands:
            passed, reason, _ = validate_generated_image(img, is_solo_scene=True, prompt="1girl, solo, standing")
            self.assertFalse(passed)
            self.assertIn("피사체 증발", reason)
            m_hands.assert_not_called()

        # 3. 국소/하반신 클로즈업은 persons=0/heads=0이어도 허용
        with patch("plepa_engine.qa_validator.detect_person", return_value=[]), \
             patch("plepa_engine.qa_validator.detect_heads", return_value=[]), \
             patch("plepa_engine.qa_validator.detect_faces", return_value=[]), \
             patch("plepa_engine.qa_validator.detect_hands", return_value=[]):
            passed, reason, _ = validate_generated_image(
                img, is_solo_scene=True, prompt="1girl, pov crotch, crotch focus"
            )
            self.assertTrue(passed, reason)

        # 4. 1인 단독 상반신 씬 화각 드리프트(얼굴 비율 < 8%) 공통 감지
        with patch("plepa_engine.qa_validator.detect_person", return_value=[((0, 0, 50, 200), "person", 0.9)]), \
             patch("plepa_engine.qa_validator.detect_heads", return_value=[((10, 10, 30, 25), "head", 0.9)]), \
             patch("plepa_engine.qa_validator.detect_faces", return_value=[((12, 12, 22, 22), "face", 0.9)]), \
             patch("plepa_engine.qa_validator.detect_hands", return_value=[]):
            passed, reason, metrics = validate_generated_image(
                img, is_solo_scene=True, prompt="1girl, solo, upper body, standing"
            )
            self.assertFalse(passed)
            self.assertIn("화각 드리프트", reason)
            self.assertLess(metrics["face_height_ratio"], 0.08)

if __name__ == "__main__":
    unittest.main()
