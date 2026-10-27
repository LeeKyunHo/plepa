import unittest
from PIL import Image
from plepa_engine.censor import (
    POSE_SAFE_ANCHORS,
    get_pose_category,
    get_pose_anchor_box,
    censor_image,
)


class TestCensorAnchor(unittest.TestCase):
    def test_pose_category_classification(self):
        # Fellatio & Deepthroat
        self.assertEqual(get_pose_category("086"), "fellatio")
        self.assertEqual(get_pose_category("120"), "fellatio")
        self.assertEqual(get_pose_category("127"), "fellatio")
        self.assertEqual(get_pose_category(156), "fellatio")
        self.assertEqual(get_pose_category("190"), "fellatio")

        # Doggystyle
        self.assertEqual(get_pose_category("088"), "doggystyle")
        self.assertEqual(get_pose_category("160"), "doggystyle")

        # Cowgirl
        self.assertEqual(get_pose_category("091"), "cowgirl")
        self.assertEqual(get_pose_category("161"), "cowgirl")

        # Missionary
        self.assertEqual(get_pose_category("080"), "missionary")
        self.assertEqual(get_pose_category("150"), "missionary")

        # Non-exposure poses (101 펠라사후, 104 입위강, 115 필로우토크)
        self.assertIsNone(get_pose_category("115"))
        self.assertIsNone(get_pose_category("104"))

        # Everyday pose (not adult)
        self.assertIsNone(get_pose_category("020"))
        self.assertIsNone(get_pose_category("050"))

    def test_get_pose_anchor_box(self):
        w, h = 1000, 1000
        box = get_pose_anchor_box("080", w, h)
        self.assertIsNotNone(box)
        x1, y1, x2, y2 = box
        # missionary: [0.34, 0.58, 0.66, 0.84]
        self.assertEqual(x1, 340)
        self.assertEqual(y1, 580)
        self.assertEqual(x2, 660)
        self.assertEqual(y2, 840)

        # paizuri: [0.34, 0.40, 0.66, 0.68]
        p_box = get_pose_anchor_box("165", w, h)
        self.assertIsNotNone(p_box)
        self.assertEqual(p_box, (340, 400, 660, 680))

        # fellatio: [0.36, 0.38, 0.64, 0.60]
        f_box = get_pose_anchor_box("086", w, h)
        self.assertIsNotNone(f_box)
        self.assertEqual(f_box, (360, 380, 640, 600))

    def test_censor_image_anchor_fallback(self):
        # Blank image where imgutils will find 0 genitals
        img = Image.new("RGB", (500, 500), color=(255, 255, 255))

        # Without fallback: returns 0 detections
        out_img, count = censor_image(img, pose_code="088", enable_anchor_fallback=False)
        self.assertEqual(count, 0)

        # With fallback: returns anchor box detection
        out_img2, count2 = censor_image(img, pose_code="088", enable_anchor_fallback=True)
        self.assertEqual(count2, 1)


if __name__ == "__main__":
    unittest.main()
