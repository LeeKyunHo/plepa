"""
scripts/run_hybrid_artist_benchmark.py
K-성인웹툰 물광 & 관능 쿨뷰티 하이브리드 작가 조합 4종 실측 벤치마크 러너

[조합 4선]:
1. combo_a (K-성인웹툰 물광 정점): kimsan + guira + dooky + shirabii
2. combo_b (라타타타 하이브리드 입체광): ratatatat74 + Krenz Cushart + guira + tamano_kedama
3. combo_c (볼륨 중량감 묵직 특화): z_ton + fukuro_daikokuten + ratatatat74 + hizuki_yeo
4. combo_d (YD 융합 K-핀업 쿨뷰티): YD + guira + kimsan + shirabii

[4대 검증 포즈]:
000: 평상 (기준 쿨뷰티 & 셔츠 풀린 상반신 가슴 물광)
088: 후배위약 (첨부 1번 상단 둔부 오일 물광)
076: 수유대딸 (첨부 1번 하단 바스트/손 애무 씬)
106: 샤워섹스강 (첨부 2/3번 전신 땀/수분 광택)
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw, ImageFont

from plepa_engine.config import PROJECTS_DIR
from plepa_engine.services.generation_service import GenerationParams, GenerationService
from plepa_engine.services.pose_service import default_pose_service

BENCHMARK_POSES = ["000", "088", "076", "106"]
POSE_LABELS = {
    "000": "평상 (상반신 쿨뷰티)",
    "088": "후배위약 (배면 둔부 물광)",
    "076": "수유대딸 (바스트 애무)",
    "106": "샤워섹스강 (전신 수분 광택)",
}

COMBOS: List[Dict[str, str]] = [
    {
        "id": "combo_a",
        "title": "조합 A: K-웹툰 물광 정점",
        "short_title": "A. K-웹툰 정점",
        "subtitle": "kimsan + guira + dooky + shirabii",
        "tag": "(artist:kimsan:0.95), (artist:guira:0.90), (artist:dooky:0.85), (artist:shirabii:0.80), (oily skin:1.15), (skin glisten:1.1), sweat drops",
        "desc": "한국 성인웹툰의 매끄러운 피부 베이스 + guira의 극강 오일 광택 + shirabii의 도도한 고양이상 눈매",
        "badge_color": "#2563eb",
    },
    {
        "id": "combo_b",
        "title": "조합 B: 라타타타 하이브리드 입체광",
        "short_title": "B. 라타타 하이브리드",
        "subtitle": "ratatatat74 + Krenz + guira + tamano_kedama",
        "tag": "(artist:ratatatat74:0.95), (artist:krenz_cushart:0.85), (artist:guira:0.85), (artist:tamano_kedama:0.75), (oily skin:1.15), (skin glisten:1.1), sweat drops",
        "desc": "Krenz Cushart의 정밀 투시/실내 조명 + ratatata의 쫀득한 윤기 + tamano_kedama의 투명한 눈망울",
        "badge_color": "#db2777",
    },
    {
        "id": "combo_c",
        "title": "조합 C: 볼륨 중량감 묵직 특화",
        "short_title": "C. 볼륨 중량감",
        "subtitle": "z_ton + fukuro_daikokuten + ratatatat74 + hizuki_yeo",
        "tag": "(artist:z-ton:0.85), (artist:fukuro_daikokuten:0.90), (artist:ratatatat74:0.90), (artist:hizuki_yeo:0.80), (oily skin:1.15), (skin glisten:1.1), sweat drops",
        "desc": "z_ton과 fukuro의 묵직하게 처지는 폭유/골반 볼륨감 + hizuki_yeo의 부드러운 스킨 톤",
        "badge_color": "#d97706",
    },
    {
        "id": "combo_d",
        "title": "조합 D: YD 융합 K-핀업 쿨뷰티",
        "short_title": "D. YD 융합 핀업",
        "subtitle": "YD + guira + kimsan + shirabii",
        "tag": "(artist:yd:1.00), (artist:guira:0.90), (artist:kimsan:0.85), (artist:shirabii:0.80), (oily skin:1.15), (skin glisten:1.1), sweat drops",
        "desc": "첨부 이미지 흑발 포니테일과 판박이인 YD의 핀업 유전자 + kimsan과 guira의 질척한 물광 셰이딩",
        "badge_color": "#7c3aed",
    },
]


def get_font(size: int = 20) -> ImageFont.ImageFont:
    for p in ["C:/Windows/Fonts/malgunbd.ttf", "C:/Windows/Fonts/malgun.ttf", "C:/Windows/Fonts/arialbd.ttf"]:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def generate_html_viewer(benchmark_dir: Path) -> Path:
    html_path = benchmark_dir / "index.html"
    
    # 데이터 구조 조립
    matrix_data = []
    for c in COMBOS:
        combo_item = {
            "id": c["id"],
            "title": c["title"],
            "short_title": c["short_title"],
            "subtitle": c["subtitle"],
            "desc": c["desc"],
            "tag": c["tag"],
            "badge_color": c["badge_color"],
            "poses": {},
        }
        for code in BENCHMARK_POSES:
            lbl = POSE_LABELS[code].split()[0]
            fname = f"hay_{code}_{c['id']}.webp"
            fpath = benchmark_dir / c["id"] / fname
            combo_item["poses"][code] = {
                "rel_path": f"{c['id']}/{fname}",
                "exists": fpath.exists() and fpath.stat().st_size > 5000,
                "label": POSE_LABELS[code],
            }
        matrix_data.append(combo_item)

    json_matrix = json.dumps(matrix_data, ensure_ascii=False)
    has_contact = (benchmark_dir / "master_comparison_4x4.webp").exists()

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=3.0, user-scalable=yes">
<title>K-성인웹툰 물광 & 관능 쿨뷰티 하이브리드 작가 조합 벤치마크</title>
<style>
  :root {{
    --bg: #0b0d14;
    --card-bg: #141724;
    --border: #242a3e;
    --text: #f1f5f9;
    --text-muted: #94a3b8;
    --accent: #6366f1;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Pretendard", "Segoe UI", Roboto, sans-serif;
    padding-bottom: 60px;
    line-height: 1.5;
  }}
  header {{
    background: #111422;
    border-bottom: 1px solid var(--border);
    padding: 16px;
    position: sticky;
    top: 0;
    z-index: 100;
    backdrop-filter: blur(10px);
  }}
  .header-top {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
  }}
  h1 {{
    font-size: 1.15rem;
    font-weight: 800;
    color: #fff;
    display: flex;
    align-items: center;
    gap: 6px;
  }}
  .badge {{
    background: #4338ca;
    color: #e0e7ff;
    font-size: 0.72rem;
    padding: 2px 8px;
    border-radius: 9999px;
    font-weight: 600;
  }}
  .header-desc {{
    font-size: 0.78rem;
    color: var(--text-muted);
    margin-top: 4px;
  }}
  .nav-bar {{
    display: flex;
    gap: 6px;
    margin-top: 10px;
    overflow-x: auto;
    padding-bottom: 2px;
    scrollbar-width: none;
  }}
  .nav-bar::-webkit-scrollbar {{ display: none; }}
  .nav-link {{
    background: #1e2438;
    color: #cbd5e1;
    text-decoration: none;
    font-size: 0.74rem;
    padding: 5px 9px;
    border-radius: 6px;
    white-space: nowrap;
    border: 1px solid var(--border);
  }}
  .tabs {{
    display: flex;
    background: #111422;
    border-bottom: 1px solid var(--border);
    padding: 6px 12px;
    gap: 8px;
    overflow-x: auto;
    scrollbar-width: none;
  }}
  .tabs::-webkit-scrollbar {{ display: none; }}
  .tab-btn {{
    background: transparent;
    color: var(--text-muted);
    border: 1px solid transparent;
    padding: 7px 14px;
    border-radius: 8px;
    font-size: 0.84rem;
    font-weight: 600;
    cursor: pointer;
    white-space: nowrap;
    transition: all 0.2s;
  }}
  .tab-btn.active {{
    background: var(--accent);
    color: #fff;
  }}
  .container {{
    padding: 12px;
  }}
  .summary-banner {{
    background: #181c30;
    border: 1px solid #313854;
    border-radius: 12px;
    padding: 12px 14px;
    margin-bottom: 14px;
    font-size: 0.8rem;
    color: #cbd5e1;
  }}
  
  /* 포즈별 4조합 동시 비교 뷰 */
  .pose-section {{
    margin-bottom: 24px;
  }}
  .pose-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 10px;
    padding-bottom: 6px;
    border-bottom: 1px solid var(--border);
  }}
  .pose-title {{
    font-size: 1rem;
    font-weight: 700;
    color: #fff;
    display: flex;
    align-items: center;
    gap: 6px;
  }}
  .combo-grid-4 {{
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 10px;
  }}
  @media (min-width: 900px) {{
    .combo-grid-4 {{
      grid-template-columns: repeat(4, 1fr);
      gap: 14px;
    }}
  }}
  .combo-card {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 10px;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }}
  .card-top {{
    padding: 8px 10px;
    background: #181d30;
    border-bottom: 1px solid var(--border);
    font-size: 0.8rem;
    font-weight: 700;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }}
  .combo-badge {{
    font-size: 0.68rem;
    padding: 2px 6px;
    border-radius: 4px;
    color: #fff;
    font-weight: bold;
  }}
  .img-box {{
    width: 100%;
    aspect-ratio: 832 / 1216;
    background: #07090f;
    position: relative;
    overflow: hidden;
  }}
  .img-box img {{
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
    cursor: zoom-in;
  }}
  .placeholder {{
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    height: 100%;
    color: #64748b;
    font-size: 0.8rem;
    gap: 6px;
  }}
  .card-footer {{
    padding: 8px 10px;
    font-size: 0.72rem;
    color: var(--text-muted);
  }}
  .tag-code {{
    display: block;
    font-family: monospace;
    font-size: 0.66rem;
    color: #a5b4fc;
    margin-top: 3px;
    word-break: break-all;
  }}
  
  /* 마스터 4x4 컨택트 시트 뷰 */
  .contact-sheet-box {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow: hidden;
    margin-bottom: 16px;
  }}
  .contact-sheet-box img {{
    width: 100%;
    height: auto;
    display: block;
    cursor: zoom-in;
  }}

  /* 모달 라이트박스 */
  .lightbox {{
    display: none;
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0, 0, 0, 0.94);
    z-index: 1000;
    justify-content: center;
    align-items: center;
    padding: 10px;
  }}
  .lightbox.active {{ display: flex; }}
  .lightbox img {{
    max-width: 100%;
    max-height: 94vh;
    object-fit: contain;
    border-radius: 6px;
  }}
</style>
</head>
<body>

<header>
  <div class="header-top">
    <h1><span>✨ 하이브리드 물광 쿨뷰티 4대 조합</span></h1>
    <span class="badge">설하율(hay) · 16장 실측</span>
  </div>
  <div class="header-desc">
    K-성인웹툰 물광/오일 스킨 & 쿨뷰티 폭유 셰이딩 1:1 비교 검증 (고정 시드 1001)
  </div>
  <div class="nav-bar">
    <a href="/artist2/" class="nav-link">🔞 40인 성인작가 ➔</a>
    <a href="/ratatata/" class="nav-link">⚡ 라타타타 믹스 ➔</a>
    <a href="/artist1/" class="nav-link">🎨 80인 작가 화풍 ➔</a>
    <a href="/" class="nav-link">🔬 4대 체위 통계 ➔</a>
  </div>
</header>

<div class="tabs">
  <button class="tab-btn active" onclick="switchView('compare')">🔍 포즈별 4조합 1:1 비교</button>
  <button class="tab-btn" onclick="switchView('sheet')">📋 4x4 통합 컨택트시트</button>
  <button class="tab-btn" onclick="switchView('combo')">🎨 조합별 모아보기</button>
</div>

<div class="container">
  <div class="summary-banner">
    💡 <strong>비교 포인트</strong>: 셔츠/탑 사이로 터져나오는 가슴·둔부의 <strong>오일/땀방울 물광 텍스처</strong>, 흑발 쿨뷰티 눈매 선화 정밀도, 그리고 어두운 실내 <strong>림라이트</strong> 명암비입니다.
  </div>

  <!-- 1. 포즈별 4조합 1:1 비교 모드 -->
  <div id="view-compare">
"""

    for code in BENCHMARK_POSES:
        lbl = POSE_LABELS[code]
        html += f"""
    <div class="pose-section">
      <div class="pose-header">
        <span class="pose-title">#{code} {lbl}</span>
        <span style="font-size:0.75rem; color:#818cf8;">시드 1001 동시 비교</span>
      </div>
      <div class="combo-grid-4">
"""
        for c in COMBOS:
            cid = c["id"]
            pdata = None
            fname = f"hay_{code}_{cid}.webp"
            fpath = benchmark_dir / cid / fname
            exists = fpath.exists() and fpath.stat().st_size > 5000
            rel_url = f"{cid}/{fname}"

            html += f"""
        <div class="combo-card">
          <div class="card-top">
            <span>{c['short_title']}</span>
            <span class="combo-badge" style="background:{c['badge_color']};">{cid.upper()}</span>
          </div>
          <div class="img-box">
"""
            if exists:
                html += f"""            <img src="{rel_url}" alt="{c['title']}" onclick="openLightbox(this.src)" loading="lazy">"""
            else:
                html += f"""
            <div class="placeholder">
              <span>⏳ 렌더링 대기</span>
              <span style="font-size:0.7rem;">#{code}</span>
            </div>
"""
            html += f"""
          </div>
          <div class="card-footer">
            <div>{c['subtitle']}</div>
            <span class="tag-code">{c['tag'][:45]}...</span>
          </div>
        </div>
"""
        html += """
      </div>
    </div>
"""

    html += f"""
  </div>

  <!-- 2. 4x4 마스터 컨택트 시트 뷰 -->
  <div id="view-sheet" style="display:none;">
    <div class="contact-sheet-box">
      <div style="padding:10px 14px; background:#181d30; font-size:0.88rem; font-weight:bold; display:flex; justify-content:space-between;">
        <span>📊 4대 포즈 × 4대 조합 = 16장 통합 컨택트 시트</span>
        <span style="font-size:0.75rem; color:#818cf8;">터치 시 원본 확대</span>
      </div>
"""
    if has_contact:
        html += """      <img src="master_comparison_4x4.webp" alt="4x4 마스터 컨택트 시트" onclick="openLightbox(this.src)">"""
    else:
        html += """      <div style="padding:40px; text-align:center; color:#64748b;">16장 렌더링 완료 후 자동 생성됩니다.</div>"""

    html += """
    </div>
  </div>

  <!-- 3. 조합별 모아보기 뷰 -->
  <div id="view-combo" style="display:none;">
"""
    for c in COMBOS:
        cid = c["id"]
        html += f"""
    <div style="margin-bottom:24px; background:var(--card-bg); border:1px solid var(--border); border-radius:12px; padding:14px;">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
        <h3 style="font-size:1rem; color:#fff;">{c['title']}</h3>
        <span class="combo-badge" style="background:{c['badge_color']};">{cid.upper()}</span>
      </div>
      <p style="font-size:0.8rem; color:#cbd5e1; margin-bottom:6px;">💡 {c['desc']}</p>
      <code style="display:block; background:#0b0d14; padding:6px 10px; border-radius:6px; font-size:0.72rem; color:#a5b4fc; margin-bottom:12px; word-break:break-all;">{c['tag']}</code>
      
      <div class="combo-grid-4">
"""
        for code in BENCHMARK_POSES:
            fname = f"hay_{code}_{cid}.webp"
            fpath = benchmark_dir / cid / fname
            exists = fpath.exists() and fpath.stat().st_size > 5000
            rel_url = f"{cid}/{fname}"
            lbl = POSE_LABELS[code].split()[0]
            html += f"""
        <div style="background:#0e111b; border:1px solid var(--border); border-radius:8px; overflow:hidden;">
          <div style="padding:6px 8px; font-size:0.74rem; font-weight:bold; color:#cbd5e1; background:#161a29;">#{code} {lbl}</div>
          <div class="img-box">
"""
            if exists:
                html += f"""            <img src="{rel_url}" alt="{code}" onclick="openLightbox(this.src)" loading="lazy">"""
            else:
                html += """            <div class="placeholder"><span>대기 중</span></div>"""
            html += """
          </div>
        </div>
"""
        html += """
      </div>
    </div>
"""

    html += """
  </div>
</div>

<div class="lightbox" id="lightbox" onclick="closeLightbox()">
  <img id="lightbox-img" src="" alt="확대 보기">
</div>

<script>
  function switchView(mode) {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.getElementById('view-compare').style.display = (mode === 'compare') ? 'block' : 'none';
    document.getElementById('view-sheet').style.display = (mode === 'sheet') ? 'block' : 'none';
    document.getElementById('view-combo').style.display = (mode === 'combo') ? 'block' : 'none';
    event.target.classList.add('active');
  }

  function openLightbox(src) {
    const lb = document.getElementById('lightbox');
    document.getElementById('lightbox-img').src = src;
    lb.classList.add('active');
  }

  function closeLightbox() {
    document.getElementById('lightbox').classList.remove('active');
  }
</script>

</body>
</html>
"""
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    return html_path


def render_master_contact_sheet(benchmark_dir: Path) -> Optional[Path]:
    """16장 이미지를 4x4 매트릭스로 결합한 통합 컨택트 시트를 생성합니다."""
    # 그리드 규격: 4열(Combos A, B, C, D) × 4행(Poses 000, 088, 076, 106)
    cell_w, cell_h = 416, 608  # 절반 해상도로 압축하여 로딩 최적화
    header_h = 100
    label_h = 36
    side_w = 120
    
    total_w = side_w + cell_w * 4 + 30
    total_h = header_h + (cell_h + label_h + 10) * 4 + 20

    sheet = Image.new("RGB", (total_w, total_h), color=(15, 18, 28))
    draw = ImageDraw.Draw(sheet)

    title_font = get_font(28)
    sub_font = get_font(18)
    header_font = get_font(20)
    label_font = get_font(16)

    # 1. 메인 헤더
    draw.text((20, 20), "PLEPA K-성인웹툰 물광 & 관능 쿨뷰티 4대 조합 16장 통합 벤치마크", fill=(255, 255, 255), font=title_font)
    draw.text((20, 60), "설하율(hay) · 고정 시드 1001 · RTX 4060 Ti · 행: 4대 포즈 / 열: 4대 조합", fill=(148, 163, 184), font=sub_font)

    # 2. 열 헤더 (4대 조합)
    for col_idx, c in enumerate(COMBOS):
        cx = side_w + col_idx * cell_w + 10
        # 배경 배지
        draw.rounded_rectangle([cx, header_h - 28, cx + cell_w - 10, header_h - 4], radius=6, fill=c["badge_color"])
        draw.text((cx + 12, header_h - 26), f"{c['short_title']} ({c['subtitle'][:24]})", fill=(255, 255, 255), font=header_font)

    # 3. 4x4 셀 렌더링
    for row_idx, code in enumerate(BENCHMARK_POSES):
        ry = header_h + row_idx * (cell_h + label_h + 10)
        pose_lbl = POSE_LABELS[code].split()[0]

        # 행 레이블 (좌측)
        draw.text((15, ry + cell_h // 2 - 20), f"#{code}\n{pose_lbl}", fill=(203, 213, 225), font=header_font)

        for col_idx, c in enumerate(COMBOS):
            rx = side_w + col_idx * cell_w + 10
            cid = c["id"]
            img_file = benchmark_dir / cid / f"hay_{code}_{cid}.webp"

            if img_file.exists():
                try:
                    with Image.open(img_file) as im:
                        im_thumb = im.convert("RGB").resize((cell_w - 10, cell_h), Image.Resampling.LANCZOS)
                        sheet.paste(im_thumb, (rx, ry))
                except Exception:
                    draw.rectangle([rx, ry, rx + cell_w - 10, ry + cell_h], fill=(30, 35, 50))
            else:
                draw.rectangle([rx, ry, rx + cell_w - 10, ry + cell_h], fill=(30, 35, 50))
                draw.text((rx + 30, ry + cell_h // 2), "미생성", fill=(100, 116, 139), font=sub_font)

            # 셀 하단 태그
            draw.rectangle([rx, ry + cell_h, rx + cell_w - 10, ry + cell_h + label_h], fill=(22, 27, 42))
            draw.text((rx + 6, ry + cell_h + 8), f"#{code} | {cid.upper()}", fill=(165, 180, 252), font=label_font)

    contact_path = benchmark_dir / "master_comparison_4x4.webp"
    sheet.save(contact_path, "WEBP", quality=92)
    return contact_path


def main():
    parser = argparse.ArgumentParser(description="K-웹툰 물광 쿨뷰티 4대 조합 실측 벤치마크 러너")
    parser.add_argument("--mock", action="store_true", help="0.1초 가상 생성")
    parser.add_argument("--dry-run", action="store_true", help="생성 없이 시뮬레이션")
    args = parser.parse_args()

    benchmark_dir = PROJECTS_DIR / "ykn" / "artist_benchmark_hybrid"
    benchmark_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print(" [K-성인웹툰 물광 쿨뷰티 4대 조합 실측 벤치마크]")
    print(f" 대상 캐릭터: 설하율 (hay - 흑발 쿨뷰티 & 폭유)")
    print(f" 검증 포즈: 4종 ({', '.join(BENCHMARK_POSES)})")
    print(f" 조합 수: 4종 (총 16장) | 고정 시드: 1001")
    print(f" 저장 디렉토리: {benchmark_dir}")
    print("=" * 80)

    # 1. 초기 HTML 생성
    generate_html_viewer(benchmark_dir)

    if args.mock:
        print("[MOCK] 가상 16장 생성 중...")
        for c in COMBOS:
            cdir = benchmark_dir / c["id"]
            cdir.mkdir(parents=True, exist_ok=True)
            for code in BENCHMARK_POSES:
                dummy = Image.new("RGB", (832, 1216), color=(20, 30, 50))
                d = ImageDraw.Draw(dummy)
                d.text((50, 50), f"MOCK {c['id']} {code}", fill=(255, 255, 255), font=get_font(30))
                dummy.save(cdir / f"hay_{code}_{c['id']}.webp", "WEBP")
        render_master_contact_sheet(benchmark_dir)
        generate_html_viewer(benchmark_dir)
        print("[MOCK 완료]")
        return

    if args.dry_run:
        print("[DRY-RUN] 16장 작업 큐 시뮬레이션:")
        for c in COMBOS:
            for code in BENCHMARK_POSES:
                print(f"  - {c['id']} × #{code} ({POSE_LABELS[code]}): {c['tag']}")
        return

    # 실 생성 파이프라인
    service = GenerationService()
    success_count = 0
    fail_count = 0
    start_time = time.time()

    # 순서: 각 포즈별로 4대 조합을 나란히 생성하여 GPU 캐시 및 비교 효율 극대화
    for p_idx, code in enumerate(BENCHMARK_POSES, 1):
        lbl = POSE_LABELS[code]
        print(f"\n▶ [{p_idx}/4] 포즈 #{code} ({lbl}) 4대 조합 렌더링 시작...")

        for c_idx, c in enumerate(COMBOS, 1):
            cid = c["id"]
            cdir = benchmark_dir / cid
            cdir.mkdir(parents=True, exist_ok=True)

            fname = f"hay_{code}_{cid}.webp"
            final_target = cdir / fname

            if final_target.exists() and final_target.stat().st_size > 5000:
                print(f"  [{c_idx}/4] {cid.upper()} 스킵 (이미 완료됨)")
                success_count += 1
                continue

            print(f"  [{c_idx}/4] {cid.upper()} ({c['short_title']}) 생성 중... 시드 1001")
            params = GenerationParams(
                character_expr="hay",
                pose_expr=code,
                roster="ykn",
                custom_pos=c["tag"],
                ckpt_tag=f"hybrid_{cid}_{code}",
                overwrite=True,
                engine="sdxl",
                censor=True,
                seed=1001,  # 동일 시드로 엄밀한 통제 비교
                no_ref=True,
            )

            try:
                t0 = time.time()
                res = service.run_batch(params, quiet=True)
                dur = time.time() - t0

                if res and res[0].success and res[0].image_path:
                    gen_p = Path(res[0].image_path)
                    if gen_p.exists():
                        shutil.copy2(gen_p, final_target)
                        size_kb = final_target.stat().st_size // 1024
                        print(f"     ✅ 성공 ({dur:.1f}초, {size_kb} KB) -> {final_target.name}")
                        success_count += 1
                    else:
                        print(f"     ❌ 파일 없음")
                        fail_count += 1
                else:
                    err = res[0].error_message if res else "Unknown"
                    print(f"     ❌ 실패: {err}")
                    fail_count += 1
            except Exception as e:
                print(f"     ❌ 예외: {e}")
                fail_count += 1

            # 임시 디렉토리 청소
            tmp_d = PROJECTS_DIR / "ykn" / "assets" / f"hybrid_{cid}_{code}"
            if tmp_d.exists():
                shutil.rmtree(tmp_d, ignore_errors=True)

        # 포즈 1개(4조합) 끝날 때마다 HTML 실시간 갱신
        generate_html_viewer(benchmark_dir)

    # 전체 완료 후 마스터 4x4 컨택트 시트 렌더링
    print("\n▶ 16장 렌더링 완료. 4x4 통합 컨택트 시트 합성 중...")
    render_master_contact_sheet(benchmark_dir)
    generate_html_viewer(benchmark_dir)

    elapsed = time.time() - start_time
    print("=" * 80)
    print(f" [완료] 성공: {success_count}장 / 실패: {fail_count}장 (총 {elapsed:.1f}초 소요)")
    print(f" 뷰어 파일: {benchmark_dir / 'index.html'}")
    print("=" * 80)


if __name__ == "__main__":
    main()
