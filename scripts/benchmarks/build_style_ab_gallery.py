"""
scripts/build_style_ab_gallery.py
Style A/B Test 4열 비교 갤러리 (Before / After Glossy / Option A Legacy / Option B Balanced) 생성기.
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
STYLE_AB_DIR = ROOT / "output" / "style_ab_test"
OVERNIGHT_DIR = ROOT / "output" / "overnight_full_audit"
PROJECTS_DIR = ROOT / "projects"

TARGETS: List[Tuple[str, str, List[str]]] = [
    ("campus", "aya", ["000", "009", "020", "080", "086", "088"]),
    ("oto", "kei", ["000", "009", "020", "150", "156", "158"]),
]

WET_H_TARGETS: List[Tuple[str, str, List[str]]] = [
    ("campus", "aya", ["060", "080", "086", "088"]),
    ("campus", "shz", ["086", "092"]),
]


def _find_pose_web_path(base_dir: Path, web_prefix: str, char: str, code: str) -> Optional[str]:
    if not base_dir.is_dir():
        return None
    matches = sorted(
        p for p in base_dir.rglob(f"{char}_{code}_*.webp")
        if "_origin" not in p.parts
    )
    if not matches:
        return None
    rel = matches[0].relative_to(base_dir).as_posix()
    return f"{web_prefix}/{rel}"


def build_gallery() -> Path:
    STYLE_AB_DIR.mkdir(parents=True, exist_ok=True)
    sections_html: List[str] = []

    for roster, char, codes in TARGETS:
        rows_html: List[str] = []
        for code in codes:
            cols = [
                ("Before (원본)", _find_pose_web_path(PROJECTS_DIR / roster / "assets" / char, f"/projects/{roster}/assets/{char}", char, code)),
                ("After (Glossy)", _find_pose_web_path(OVERNIGHT_DIR / roster, f"/overnight/{roster}", char, code)),
                ("Option A (Legacy)", _find_pose_web_path(STYLE_AB_DIR / "mode_a_legacy" / roster / char, f"/style_ab/mode_a_legacy/{roster}/{char}", char, code)),
                ("Option B (Balanced)", _find_pose_web_path(STYLE_AB_DIR / "mode_b_balanced" / roster / char, f"/style_ab/mode_b_balanced/{roster}/{char}", char, code)),
            ]
            cards = []
            for label, src in cols:
                if src:
                    media = f'<a href="{html.escape(src)}" target="_blank"><img src="{html.escape(src)}" loading="lazy" alt="{html.escape(label)}"></a>'
                else:
                    media = '<div class="missing">미생성 / 없음</div>'
                cards.append(f'<div class="col"><div class="col-title">{html.escape(label)}</div>{media}</div>')

            rows_html.append(
                f'<section class="pose-row">'
                f'<h3>[{html.escape(roster)}/{html.escape(char)}] #{html.escape(code)}</h3>'
                f'<div class="grid-4">{"".join(cards)}</div>'
                f'</section>'
            )
        sections_html.append(f'<div class="char-block"><h2>{html.escape(char.upper())} ({html.escape(roster)})</h2>{"".join(rows_html)}</div>')

    wet_rows_html: List[str] = []
    for roster, char, codes in WET_H_TARGETS:
        for code in codes:
            cols = [
                ("Before (원본)", _find_pose_web_path(PROJECTS_DIR / roster / "assets" / char, f"/projects/{roster}/assets/{char}", char, code)),
                ("After (Glossy)", _find_pose_web_path(OVERNIGHT_DIR / roster, f"/overnight/{roster}", char, code)),
                ("Option A (Dry Legacy)", _find_pose_web_path(STYLE_AB_DIR / "mode_a_legacy" / roster / char, f"/style_ab/mode_a_legacy/{roster}/{char}", char, code)),
                ("Wet-H Booster (S2)", _find_pose_web_path(STYLE_AB_DIR / "mode_wet_h" / roster / char, f"/style_ab/mode_wet_h/{roster}/{char}", char, code)),
                ("Wet + Moody (S3)", _find_pose_web_path(STYLE_AB_DIR / "mode_wet_moody" / roster / char, f"/style_ab/mode_wet_moody/{roster}/{char}", char, code)),
            ]
            cards = []
            for label, src in cols:
                if src:
                    media = f'<a href="{html.escape(src)}" target="_blank"><img src="{html.escape(src)}" loading="lazy" alt="{html.escape(label)}"></a>'
                else:
                    media = '<div class="missing">미생성 / 없음</div>'
                cards.append(f'<div class="col"><div class="col-title">{html.escape(label)}</div>{media}</div>')
            wet_rows_html.append(
                f'<section class="pose-row">'
                f'<h3>[{html.escape(roster)}/{html.escape(char)}] #{html.escape(code)}</h3>'
                f'<div class="grid-5">{"".join(cards)}</div>'
                f'</section>'
            )
    sections_html.append(f'<div class="char-block"><h2>Phase S2/S3 Wet-H &amp; Moody Comparison (aya &amp; shz)</h2>{"".join(wet_rows_html)}</div>')

    page = f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PLEPA Style A/B 4-Column Comparison</title>
<style>
  body {{ margin: 0; padding: 16px; background: #0f1115; color: #e6e9ef; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
  h1 {{ margin: 0 0 8px; font-size: 20px; }}
  .sub {{ color: #9aa4b2; font-size: 13px; margin-bottom: 20px; }}
  .char-block {{ margin-bottom: 32px; }}
  h2 {{ font-size: 18px; border-bottom: 1px solid #262b36; padding-bottom: 6px; }}
  .pose-row {{ margin-bottom: 24px; background: #161922; border: 1px solid #262b36; border-radius: 10px; padding: 12px; }}
  .pose-row h3 {{ margin: 0 0 10px; font-size: 14px; color: #c7d2fe; }}
  .grid-4 {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }}
  .grid-5 {{ display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; }}
  @media (max-width: 900px) {{ .grid-4, .grid-5 {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} }}
  .col {{ background: #0f1115; border: 1px solid #262b36; border-radius: 8px; padding: 6px; }}
  .col-title {{ font-size: 12px; font-weight: 600; color: #9aa4b2; margin-bottom: 6px; text-align: center; }}
  .col img {{ width: 100%; height: auto; display: block; border-radius: 4px; }}
  .missing {{ height: 220px; display: flex; align-items: center; justify-content: center; color: #64748b; font-size: 12px; }}
</style>
</head>
<body>
  <h1>PLEPA Style A/B Test (4-Column Comparison)</h1>
  <div class="sub">Col 1: Before | Col 2: After (Glossy) | Col 3: Option A (Legacy) | Col 4: Option B (Balanced)</div>
  {"".join(sections_html)}
</body>
</html>
"""
    out_ab = STYLE_AB_DIR / "ab_comparison.html"
    out_idx = STYLE_AB_DIR / "index.html"
    out_ab.write_text(page, encoding="utf-8")
    out_idx.write_text(page, encoding="utf-8")
    return out_ab


if __name__ == "__main__":
    p = build_gallery()
    print(f"Generated: {p}")
