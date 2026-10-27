"""
tests/test_censor_anchor.py
포즈 DB 메타데이터 기반 동적 체위 카테고리 분류 및 안전 앵커 박스 계약 검증 테스트.
"""

import unittest
from PIL import Image
from plepa_engine.censor import (
    NON_EXPOSURE_H_POSES,
    POSE_SAFE_ANCHORS,
    censor_image,
    get_pose_anchor_box,
    get_pose_category,
)
from plepa_engine.services.pose_service import default_pose_service


class TestCensorAnchor(unittest.TestCase):
    def setUp(self):
        self.db = default_pose_service.load_pose_db(engine="sdxl", roster="campus")

    def test_pose_category_dynamic_classification_contract(self):
        """포즈 DB의 라벨/프롬프트 특성에 따라 체위 카테고리가 동적으로 정확히 분류되는지 계약 검증."""
        for code, entry in self.db.items():
            if not code.isdigit():
                continue
            c_int = int(code)

            # 비노출 면제 포즈
            if code in NON_EXPOSURE_H_POSES:
                self.assertIsNone(get_pose_category(code))
                continue

            # 일상 및 감정 포즈 (000~059)
            if c_int < 60:
                self.assertIsNone(get_pose_category(code))
                continue

            # 성인 및 공용 구강 대역은 모두 유효한 카테고리를 반환해야 함
            if (64 <= c_int <= 79) or (80 <= c_int <= 139) or (150 <= c_int <= 209):
                cat = get_pose_category(code)
                self.assertIn(
                    cat,
                    POSE_SAFE_ANCHORS,
                    f"포즈 {code}({entry.label})의 카테고리 '{cat}'가 POSE_SAFE_ANCHORS에 정의되어 있어야 합니다.",
                )

                # 라벨 기반 핵심 체위 일치성 검증
                label = entry.label
                if "후배위" in label:
                    self.assertEqual(cat, "doggystyle", f"{code}_{label}은 doggystyle이어야 합니다.")
                elif "기승위" in label:
                    self.assertEqual(cat, "cowgirl", f"{code}_{label}은 cowgirl이어야 합니다.")
                elif "정상위" in label or "웨딩섹스" in label:
                    self.assertEqual(cat, "missionary", f"{code}_{label}은 missionary여야 합니다.")
                elif "측위" in label:
                    self.assertEqual(cat, "side", f"{code}_{label}은 side여야 합니다.")
                elif "파이즈리약" in label or "가슴사정" in label:
                    self.assertEqual(cat, "paizuri", f"{code}_{label}은 paizuri여야 합니다.")
                elif "펠라치오" in label or "딥스로트" in label:
                    self.assertEqual(cat, "fellatio", f"{code}_{label}은 fellatio여야 합니다.")

    def test_get_pose_anchor_box_coordinates_contract(self):
        """모든 POSE_SAFE_ANCHORS 카테고리가 유효한 픽셀 박스를 산출하는지 검증."""
        w, h = 1000, 1000
        for code, entry in self.db.items():
            cat = get_pose_category(code)
            if cat is not None:
                box = get_pose_anchor_box(code, w, h)
                self.assertIsNotNone(box)
                x1, y1, x2, y2 = box
                self.assertGreaterEqual(x1, 0)
                self.assertGreaterEqual(y1, 0)
                self.assertLess(x1, x2)
                self.assertLess(y1, y2)
                self.assertLessEqual(x2, w)
                self.assertLessEqual(y2, h)

    def test_censor_image_anchor_fallback(self):
        """성기 미탐지 빈 이미지에서 enable_anchor_fallback 동작 계약 검증."""
        img = Image.new("RGB", (500, 500), color=(255, 255, 255))

        # 성인 체위 포즈 코드 1개를 동적 선택
        adult_code = next(
            code for code in sorted(self.db)
            if code.isdigit() and get_pose_category(code) is not None
        )

        # 기본값(enable_anchor_fallback=False): 인위적 사각형 아티팩트 방지를 위해 0 반환
        _, count = censor_image(img, pose_code=adult_code, enable_anchor_fallback=False)
        self.assertEqual(count, 0)

        # 명시적 폴백 활성화(enable_anchor_fallback=True): 안전 앵커 1건 적용
        _, count2 = censor_image(img, pose_code=adult_code, enable_anchor_fallback=True)
        self.assertEqual(count2, 1)


if __name__ == "__main__":
    unittest.main()
