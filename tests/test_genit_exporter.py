import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from plepa_engine.services.genit_exporter import (
    denormalize_genit_code,
    extract_pose_code_from_filename,
    GenitExporter,
)


class TestGenitExporter(unittest.TestCase):
    def test_denormalize_genit_code(self):
        # A00 -> A0
        self.assertEqual(denormalize_genit_code("A00"), "A0")
        self.assertEqual(denormalize_genit_code("A01"), "A1")
        self.assertEqual(denormalize_genit_code("A23"), "A23")

        # B01 -> B1, B22 -> B22
        self.assertEqual(denormalize_genit_code("B01"), "B1")
        self.assertEqual(denormalize_genit_code("B22"), "B22")

        # N01 -> N1, N74 -> N74
        self.assertEqual(denormalize_genit_code("N01"), "N1")
        self.assertEqual(denormalize_genit_code("N74"), "N74")

        # D01 -> D1, F07 -> F7
        self.assertEqual(denormalize_genit_code("D01"), "D1")
        self.assertEqual(denormalize_genit_code("F07"), "F7")

    def test_extract_pose_code_from_filename(self):
        self.assertEqual(extract_pose_code_from_filename("mal_A00_첫등장.webp"), "A00")
        self.assertEqual(extract_pose_code_from_filename("mal_A01_평상시기쁨.webp"), "A01")
        self.assertEqual(extract_pose_code_from_filename("ren_N01_정상위삽입.webp"), "N01")
        self.assertEqual(extract_pose_code_from_filename("mal_D01_수영복전신.webp"), "D01")
        self.assertEqual(extract_pose_code_from_filename("mal_034_가슴파묻힘.webp"), "034")

    def test_resolve_export_code(self):
        exporter = GenitExporter()
        self.assertEqual(exporter.resolve_export_code("한지아 (Jia)", "jia"), "AA")
        self.assertEqual(exporter.resolve_export_code("서아윤", "say"), "BB")
        self.assertEqual(exporter.resolve_export_code("정다솜", "jds"), "CC")
        self.assertEqual(exporter.resolve_export_code("차민희", "cmh"), "DD")
        self.assertEqual(exporter.resolve_export_code("이수연", "lsy"), "EE")
        self.assertEqual(exporter.resolve_export_code("김지아", "kja"), "FF")
        self.assertEqual(exporter.resolve_export_code("윤서희", "ysh"), "GG")
        self.assertEqual(exporter.resolve_export_code("박채은", "pce"), "HH")

        # 커스텀 지정 코드 우선
        self.assertEqual(exporter.resolve_export_code("한지아", "jia", "XX"), "XX")

        # 매핑에 없는 캐릭터는 prefix 앞 2글자
        self.assertEqual(exporter.resolve_export_code("마레나", "mal"), "MA")

    def test_export_character_unifies_target_size_without_modifying_originals(self):
        exporter = GenitExporter()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            projects_dir = tmp_path / "projects"
            src_dir = projects_dir / "campus" / "assets" / "aya" / "01_normal"
            src_dir.mkdir(parents=True, exist_ok=True)
            out_root = tmp_path / "dist"

            small_src = src_dir / "aya_000_평상.webp"
            large_src = src_dir / "aya_001_미소.webp"
            Image.new("RGB", (832, 1216), (120, 80, 200)).save(small_src, format="WEBP")
            Image.new("RGB", (1024, 1536), (40, 160, 220)).save(large_src, format="WEBP")

            with patch("plepa_engine.services.genit_exporter.PROJECTS_DIR", projects_dir):
                cnt, out_dir, final_code = exporter.export_character(
                    roster="campus",
                    char_prefix="aya",
                    char_name="후지사키 아야메",
                    output_dir=out_root,
                    target_size=(1024, 1536),
                    keep_original_filename=True,
                )

            self.assertEqual(cnt, 2)
            self.assertEqual(final_code, "aya")
            self.assertEqual(out_dir, out_root / "aya")

            # 내보낸 파일 2장 모두 1024x1536으로 통일됨
            with Image.open(out_dir / "aya_000_평상.webp") as im0:
                self.assertEqual(im0.size, (1024, 1536))
            with Image.open(out_dir / "aya_001_미소.webp") as im1:
                self.assertEqual(im1.size, (1024, 1536))

            # 로컬 원본은 100% 무손실 보존(832x1216 그대로)
            with Image.open(small_src) as orig0:
                self.assertEqual(orig0.size, (832, 1216))

    def test_export_character_auto_matches_portrait_and_landscape_orientation(self):
        exporter = GenitExporter()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            projects_dir = tmp_path / "projects"
            src_norm = projects_dir / "campus" / "assets" / "har" / "01_normal"
            src_h = projects_dir / "campus" / "assets" / "har" / "02_h_scenes"
            src_norm.mkdir(parents=True, exist_ok=True)
            src_h.mkdir(parents=True, exist_ok=True)
            out_root = tmp_path / "dist"

            portrait_src = src_norm / "har_003_수줍은홍조.webp"
            landscape_src = src_h / "har_060_딥키스.webp"
            Image.new("RGB", (832, 1216), (180, 120, 210)).save(portrait_src, format="WEBP")
            Image.new("RGB", (1216, 832), (80, 190, 160)).save(landscape_src, format="WEBP")

            with patch("plepa_engine.services.genit_exporter.PROJECTS_DIR", projects_dir):
                cnt, out_dir, final_code = exporter.export_character(
                    roster="campus",
                    char_prefix="har",
                    char_name="하루",
                    output_dir=out_root,
                    target_size=(1024, 1536),
                    keep_original_filename=True,
                )

            self.assertEqual(cnt, 2)
            self.assertEqual(final_code, "har")

            # 세로 원본은 1024x1536, 가로 원본은 1536x1024로 방향을 보존해 통일 리사이즈됨
            with Image.open(out_dir / "har_003_수줍은홍조.webp") as im_p:
                self.assertEqual(im_p.size, (1024, 1536))
            with Image.open(out_dir / "har_060_딥키스.webp") as im_l:
                self.assertEqual(im_l.size, (1536, 1024))

            # 로컬 원본 해상도는 무손실 보존됨
            with Image.open(landscape_src) as orig_l:
                self.assertEqual(orig_l.size, (1216, 832))


if __name__ == "__main__":
    unittest.main()
