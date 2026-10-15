# -*- coding: utf-8 -*-
import pytest
from PIL import Image
from plepa_engine.qa_validator import validate_generated_image


def test_validate_generated_image_clean(tmp_path):
    # 단색 더미 이미지 생성 (얼굴/손/인원 감지되지 않는 안전한 이미지)
    test_img = tmp_path / "clean_test.webp"
    img = Image.new("RGB", (256, 256), color=(200, 200, 200))
    img.save(test_img, "WEBP")

    # 1인 씬 검증 통과 여부 확인
    passed, reason, details = validate_generated_image(
        test_img,
        is_solo_scene=True,
        is_two_person=False,
        is_offscreen_partner=False,
        section="H-Scenes (Oral/Hand)",
    )
    assert passed is True
    assert not reason
    assert details["persons"] == 0
