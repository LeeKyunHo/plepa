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


if __name__ == "__main__":
    unittest.main()
