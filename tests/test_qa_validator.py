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


if __name__ == "__main__":
    unittest.main()
