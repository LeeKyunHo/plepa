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

        expected_threads = max(2, (os.cpu_count() or 4) - 2)
        self.assertEqual(os.environ.get("OMP_NUM_THREADS"), str(expected_threads))
        self.assertEqual(os.environ.get("MKL_NUM_THREADS"), str(expected_threads))
        self.assertEqual(torch.get_num_threads(), expected_threads)

        if os.name == "nt":
            p = psutil.Process(os.getpid())
            self.assertEqual(p.nice(), psutil.BELOW_NORMAL_PRIORITY_CLASS)



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

if __name__ == "__main__":
    unittest.main()
