"""
tests.test_upscale
사후 단독 4K AI 업스케일러(UpscaleService) 및 단독 워크플로우 빌더 단위 테스트
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
from PIL import Image

from plepa_engine.workflow_templates import build_standalone_upscale_workflow
from plepa_engine.services.upscale_service import UpscaleService


def test_build_standalone_upscale_workflow_structure():
    """단독 4K 업스케일 워크플로우의 노드 구성 및 파이프라인 연결 무결성 테스트."""
    wf = build_standalone_upscale_workflow(
        image_name="test_input.webp",
        output_prefix="upscale_test",
        upscale_model="4x-UltraSharp.pth"
    )

    # 4개의 필수 노드 존재 여부 확인
    assert "1" in wf  # LoadImage
    assert "2" in wf  # UpscaleModelLoader
    assert "3" in wf  # ImageUpscaleWithModel
    assert "4" in wf  # SaveImage

    # 노드 파라미터 및 연결 상태 확인
    assert wf["1"]["inputs"]["image"] == "test_input.webp"
    assert wf["2"]["inputs"]["model_name"] == "4x-UltraSharp.pth"

    # ImageUpscaleWithModel 연결
    assert wf["3"]["inputs"]["upscale_model"] == ["2", 0]
    assert wf["3"]["inputs"]["image"] == ["1", 0]

    # SaveImage 연결
    assert wf["4"]["inputs"]["filename_prefix"] == "upscale_test"
    assert wf["4"]["inputs"]["images"] == ["3", 0]


def test_upscale_service_dimensions_and_4k_detection(tmp_path: Path):
    """이미지 해상도 조회 및 4K 판별 함수 정확도 테스트."""
    service = UpscaleService()

    # 1. 일반 1024x1536 더미 이미지 생성
    img_normal = Image.new("RGB", (1024, 1536), color=(255, 0, 0))
    path_normal = tmp_path / "normal.webp"
    img_normal.save(path_normal, "WEBP")

    dims = service.get_image_dimensions(path_normal)
    assert dims == (1024, 1536)
    assert service.is_already_4k(path_normal) is False

    # 2. 4K 4096x6144 더미 이미지 생성
    img_4k = Image.new("RGB", (4096, 6144), color=(0, 255, 0))
    path_4k = tmp_path / "ultra_4k.webp"
    img_4k.save(path_4k, "WEBP")

    dims_4k = service.get_image_dimensions(path_4k)
    assert dims_4k == (4096, 6144)
    assert service.is_already_4k(path_4k) is True

    # 3. 존재하지 않는 파일 예외 처리
    assert service.get_image_dimensions(tmp_path / "non_existent.webp") is None
    assert service.is_already_4k(tmp_path / "non_existent.webp") is False


def test_upscale_file_mocked_execution(tmp_path: Path):
    """UpscaleService.upscale_file의 클라이언트 호출 흐름 Mock 테스트."""
    mock_client = MagicMock()
    mock_client.check_connection.return_value = True
    mock_client.upload_image.return_value = "uploaded_char.webp"

    def fake_generate_image(workflow, output_path):
        out_img = Image.new("RGB", (4096, 6144), color=(50, 150, 250))
        out_img.save(output_path, "WEBP")
        return output_path

    mock_client.generate_image.side_effect = fake_generate_image

    service = UpscaleService(client=mock_client)

    # 입력 이미지 (유효한 더미 WebP 생성)
    test_file = tmp_path / "char_001.webp"
    img_in = Image.new("RGB", (1024, 1536), color=(100, 100, 200))
    img_in.save(test_file, "WEBP")

    result_path = service.upscale_file(test_file, overwrite=False)

    assert result_path is not None
    assert result_path.exists()
    assert result_path.name == "char_001_4k.webp"
    mock_client.generate_image.assert_called_once()
