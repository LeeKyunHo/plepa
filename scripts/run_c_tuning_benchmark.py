"""
scripts/run_c_tuning_benchmark.py
C 조합 (z_ton + fukuro + ratatatat74 + hizuki_yeo) 라타타타 비중 미세 감쇄 1:1 비교 벤치마크

[비교 스텝]:
1. c_orig (기준 C): ratatatat74 0.90 (기존 생성본 재사용)
2. c_tune_80 (미세 감쇄 -0.10): ratatatat74 0.80
3. c_tune_70 (중간 감쇄 -0.20): ratatatat74 0.70
4. c_tune_60 (은은 감쇄 -0.30): ratatatat74 0.60

[4대 포즈]: 000, 088, 076, 106 (시드 1001 고정)
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Dict, List

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

BENCHMARK_POSES = ["000", "088", "076", "106"]
POSE_LABELS = {
    "000": "평상 (상반신 쿨뷰티)",
    "088": "후배위약 (배면 둔부 물광)",
    "076": "수유대딸 (바스트 애무)",
    "106": "샤워섹스강 (전신 수분 광택)",
}

TUNING_STEPS = [
    {
        "id": "c_orig",
        "title": "C 기준 (라타타 0.90)",
        "short_title": "C. 기준 (0.90)",
        "ratatata_weight": 0.90,
        "tag": "(artist:z-ton:0.85), (artist:fukuro_daikokuten:0.90), (artist:ratatatat74:0.90), (artist:hizuki_yeo:0.80), (oily skin:1.15), (skin glisten:1.1), sweat drops",
        "desc": "기존 원본 C 조합: 볼륨감과 강한 관능미",
        "badge_color": "#d97706",
        "existing_folder": "combo_c",
    },
    {
        "id": "c_tune_80",
        "title": "C-1 미세감쇄 (라타타 0.80)",
        "short_title": "C-1. 미세 (0.80)",
        "ratatata_weight": 0.80,
        "tag": "(artist:z-ton:0.85), (artist:fukuro_daikokuten:0.90), (artist:ratatatat74:0.80), (artist:hizuki_yeo:0.80), (oily skin:1.15), (skin glisten:1.1), sweat drops",
        "desc": "라타타를 0.10 줄여 z-ton/fukuro의 볼륨과 hizuki_yeo의 부드러운 스킨 톤이 더욱 선명하게 부각",
        "badge_color": "#059669",
        "existing_folder": None,
    },
    {
        "id": "c_tune_70",
        "title": "C-2 중간감쇄 (라타타 0.70)",
        "short_title": "C-2. 중간 (0.70)",
        "ratatata_weight": 0.70,
        "tag": "(artist:z-ton:0.85), (artist:fukuro_daikokuten:0.90), (artist:ratatatat74:0.70), (artist:hizuki_yeo:0.80), (oily skin:1.15), (skin glisten:1.1), sweat drops",
        "desc": "라타타를 0.20 줄여 특유의 강한 만화체 느낌을 누르고 K-웹툰 특유의 정갈하고 매끄러운 질감 극대화",
        "badge_color": "#2563eb",
        "existing_folder": None,
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


def generate_tuning_html(tuning_dir: Path) -> Path:
    html_path = tuning_dir / "index.html"
    has_contact = (tuning_dir / "master_tuning_contact.webp").exists()

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=3.0, user-scalable=yes">
<title>조합 C 라타타타 비중 감쇄 미세 조율 1:1 비교 뷰어</title>
<style>
  :root {{
    --bg: #090b12;
    --card-bg: #131624;
    --border: #23293e;
    --text: #f1f5f9;
    --text-muted: #94a3b8;
    --accent: #10b981;
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
    background: #101322;
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
    background: #065f46;
    color: #a7f3d0;
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
    background: #1a2034;
    color: #cbd5e1;
    text-decoration: none;
    font-size: 0.74rem;
    padding: 5px 9px;
    border-radius: 6px;
    white-space: nowrap;
    border: 1px solid var(--border);
  }}
  .container {{
    padding: 12px;
  }}
  .summary-banner {{
    background: #141b2f;
    border: 1px solid #1e293b;
    border-radius: 12px;
    padding: 12px 14px;
    margin-bottom: 16px;
    font-size: 0.8rem;
    color: #cbd5e1;
  }}
  .pose-section {{
    margin-bottom: 26px;
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
  }}
  .compare-grid-3 {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
  }}
  @media (max-width: 600px) {{
    .compare-grid-3 {{
      grid-template-columns: repeat(3, 1fr);
      gap: 6px;
    }}
  }}
  .card {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }}
  .card-top {{
    padding: 6px 8px;
    background: #171c2e;
    font-size: 0.75rem;
    font-weight: bold;
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid var(--border);
  }}
  .badge-tag {{
    font-size: 0.65rem;
    padding: 2px 5px;
    border-radius: 4px;
    color: #fff;
  }}
  .img-box {{
    width: 100%;
    aspect-ratio: 832 / 1216;
    background: #05070d;
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
  .card-footer {{
    padding: 6px 8px;
    font-size: 0.68rem;
    color: var(--text-muted);
  }}
  .lightbox {{
    display: none;
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0, 0, 0, 0.95);
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
    <h1><span>🎯 C조합 라타타 비중 감쇄 1:1 비교</span></h1>
    <span class="badge">라타타 0.90 ➔ 0.80 ➔ 0.70</span>
  </div>
  <div class="header-desc">
    설하율(hay) · 고정 시드 1001 · 동일 4대 포즈 나란히 비교
  </div>
  <div class="nav-bar">
    <a href="/hybrid/" class="nav-link">✨ 4대 조합 전체 ➔</a>
    <a href="/artist2/" class="nav-link">🔞 40인 성인작가 ➔</a>
    <a href="/ratatata/" class="nav-link">⚡ 라타타타 믹스 ➔</a>
    <a href="/" class="nav-link">🔬 4대 체위 통계 ➔</a>
  </div>
</header>

<div class="container">
  <div class="summary-banner">
    🔍 <strong>라타타 감쇄 관전 포인트</strong>: 라타타 특유의 도발적 눈매/선화가 부드러워지면서, <strong>z-ton의 묵직한 볼륨감</strong>과 <strong>fukuro의 쫀득한 피부 광택</strong>이 얼마나 정갈하고 자연스럽게 드러나는지 비교해보세요.
  </div>
"""

    for code in BENCHMARK_POSES:
        lbl = POSE_LABELS[code]
        html += f"""
  <div class="pose-section">
    <div class="pose-header">
      <span class="pose-title">#{code} {lbl}</span>
      <span style="font-size:0.75rem; color:#10b981;">3단계 그라데이션 비교</span>
    </div>
    <div class="compare-grid-3">
"""
        for step in TUNING_STEPS:
            sid = step["id"]
            fname = f"hay_{code}_{sid}.webp"
            fpath = tuning_dir / sid / fname
            exists = fpath.exists() and fpath.stat().st_size > 5000
            rel_url = f"{sid}/{fname}"

            html += f"""
      <div class="card">
        <div class="card-top">
          <span>{step['short_title']}</span>
          <span class="badge-tag" style="background:{step['badge_color']};">{step['ratatata_weight']:.2f}</span>
        </div>
        <div class="img-box">
"""
            if exists:
                html += f"""          <img src="{rel_url}" alt="{step['title']}" onclick="openLightbox(this.src)" loading="lazy">"""
            else:
                html += """          <div style="height:100%; display:flex; align-items:center; justify-content:center; color:#475569; font-size:0.75rem;">대기 중</div>"""

            html += f"""
        </div>
        <div class="card-footer">
          <div>{step['title'].split()[0]}</div>
        </div>
      </div>
"""
        html += """
    </div>
  </div>
"""

    html += """
  <!-- 통합 컨택트 시트 -->
  <div style="margin-top:24px; background:var(--card-bg); border:1px solid var(--border); border-radius:10px; overflow:hidden;">
    <div style="padding:10px 14px; background:#171c2e; font-size:0.85rem; font-weight:bold; display:flex; justify-content:space-between;">
      <span>📋 4x3 미세조율 통합 컨택트 시트</span>
      <span style="font-size:0.75rem; color:#10b981;">터치 시 확대</span>
    </div>
"""
    if has_contact:
        html += """    <img src="master_tuning_contact.webp" alt="4x3 마스터 컨택트 시트" style="width:100%; display:block; cursor:zoom-in;" onclick="openLightbox(this.src)">"""
    else:
        html += """    <div style="padding:30px; text-align:center; color:#475569;">렌더링 완료 후 생성됩니다.</div>"""

    html += """
  </div>
</div>

<div class="lightbox" id="lightbox" onclick="closeLightbox()">
  <img id="lightbox-img" src="" alt="확대">
</div>

<script>
  function openLightbox(src) {
    document.getElementById('lightbox-img').src = src;
    document.getElementById('lightbox').classList.add('active');
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


def render_tuning_contact_sheet(tuning_dir: Path) -> Path:
    """4개 포즈 × 3개 스텝 = 12장 통합 컨택트 시트 합성."""
    cell_w, cell_h = 440, 640
    header_h = 100
    label_h = 36
    side_w = 120

    total_w = side_w + cell_w * len(TUNING_STEPS) + 30
    total_h = header_h + (cell_h + label_h + 10) * len(BENCHMARK_POSES) + 20

    sheet = Image.new("RGB", (total_w, total_h), color=(12, 15, 24))
    draw = ImageDraw.Draw(sheet)

    title_font = get_font(28)
    sub_font = get_font(18)
    header_font = get_font(20)
    label_font = get_font(16)

    # 1. 헤더
    draw.text((20, 20), "PLEPA C조합 라타타타 비중 감쇄 (0.90 ➔ 0.80 ➔ 0.70) 1:1 비교", fill=(255, 255, 255), font=title_font)
    draw.text((20, 60), "설하율(hay) · 고정 시드 1001 · 행: 4대 포즈 / 열: 라타타 비중 3단계", fill=(148, 163, 184), font=sub_font)

    # 2. 열 헤더
    for col_idx, step in enumerate(TUNING_STEPS):
        cx = side_w + col_idx * cell_w + 10
        draw.rounded_rectangle([cx, header_h - 28, cx + cell_w - 10, header_h - 4], radius=6, fill=step["badge_color"])
        draw.text((cx + 12, header_h - 26), f"{step['short_title']} (ratatata:{step['ratatata_weight']:.2f})", fill=(255, 255, 255), font=header_font)

    # 3. 셀 합성
    for row_idx, code in enumerate(BENCHMARK_POSES):
        ry = header_h + row_idx * (cell_h + label_h + 10)
        pose_lbl = POSE_LABELS[code].split()[0]

        draw.text((15, ry + cell_h // 2 - 20), f"#{code}\n{pose_lbl}", fill=(203, 213, 225), font=header_font)

        for col_idx, step in enumerate(TUNING_STEPS):
            rx = side_w + col_idx * cell_w + 10
            sid = step["id"]
            img_file = tuning_dir / sid / f"hay_{code}_{sid}.webp"

            if img_file.exists():
                try:
                    with Image.open(img_file) as im:
                        im_thumb = im.convert("RGB").resize((cell_w - 10, cell_h), Image.Resampling.LANCZOS)
                        sheet.paste(im_thumb, (rx, ry))
                except Exception:
                    draw.rectangle([rx, ry, rx + cell_w - 10, ry + cell_h], fill=(25, 30, 45))
            else:
                draw.rectangle([rx, ry, rx + cell_w - 10, ry + cell_h], fill=(25, 30, 45))

            draw.rectangle([rx, ry + cell_h, rx + cell_w - 10, ry + cell_h + label_h], fill=(20, 24, 38))
            draw.text((rx + 8, ry + cell_h + 8), f"#{code} | ratatata: {step['ratatata_weight']:.2f}", fill=(167, 243, 208), font=label_font)

    contact_path = tuning_dir / "master_tuning_contact.webp"
    sheet.save(contact_path, "WEBP", quality=92)
    return contact_path


def main():
    tuning_dir = PROJECTS_DIR / "ykn" / "artist_benchmark_c_tuning"
    tuning_dir.mkdir(parents=True, exist_ok=True)

    hybrid_dir = PROJECTS_DIR / "ykn" / "artist_benchmark_hybrid"

    # 1. c_orig는 기존 생성된 combo_c 이미지 복사하여 재사용 (0초 소모)
    c_orig_dir = tuning_dir / "c_orig"
    c_orig_dir.mkdir(parents=True, exist_ok=True)
    for code in BENCHMARK_POSES:
        src = hybrid_dir / "combo_c" / f"hay_{code}_combo_c.webp"
        dst = c_orig_dir / f"hay_{code}_c_orig.webp"
        if src.exists():
            shutil.copy2(src, dst)

    generate_tuning_html(tuning_dir)

    print("=" * 80)
    print(" [C조합 라타타타 비중 감쇄 미세 조율 벤치마크]")
    print(" C 기준 (0.90) vs C-1 미세감쇄 (0.80) vs C-2 중간감쇄 (0.70)")
    print(f" 대상 포즈: {', '.join(BENCHMARK_POSES)} (시드 1001)")
    print(f" 신규 생성 대상: 8장 (c_tune_80 4장 + c_tune_70 4장)")
    print("=" * 80)

    service = GenerationService()
    success_count = 0
    fail_count = 0
    start_time = time.time()

    new_steps = [s for s in TUNING_STEPS if s["id"] != "c_orig"]

    for p_idx, code in enumerate(BENCHMARK_POSES, 1):
        lbl = POSE_LABELS[code]
        print(f"\n▶ [{p_idx}/4] 포즈 #{code} ({lbl}) 튜닝 렌더링...")

        for s_idx, step in enumerate(new_steps, 1):
            sid = step["id"]
            sdir = tuning_dir / sid
            sdir.mkdir(parents=True, exist_ok=True)

            fname = f"hay_{code}_{sid}.webp"
            target_path = sdir / fname

            if target_path.exists() and target_path.stat().st_size > 5000:
                print(f"  [{s_idx}/2] {step['short_title']} 스킵 (이미 완료)")
                success_count += 1
                continue

            print(f"  [{s_idx}/2] {step['short_title']} 렌더링 중... (ratatata:{step['ratatata_weight']})")
            params = GenerationParams(
                character_expr="hay",
                pose_expr=code,
                roster="ykn",
                custom_pos=step["tag"],
                ckpt_tag=f"ctuning_{sid}_{code}",
                overwrite=True,
                engine="sdxl",
                censor=True,
                seed=1001,
                no_ref=True,
            )

            try:
                t0 = time.time()
                res = service.run_batch(params, quiet=True)
                dur = time.time() - t0

                if res and res[0].success and res[0].image_path:
                    gen_p = Path(res[0].image_path)
                    if gen_p.exists():
                        shutil.copy2(gen_p, target_path)
                        size_kb = target_path.stat().st_size // 1024
                        print(f"     ✅ 성공 ({dur:.1f}초, {size_kb} KB) -> {target_path.name}")
                        success_count += 1
                    else:
                        print("     ❌ 파일 없음")
                        fail_count += 1
                else:
                    err = res[0].error_message if res else "Unknown"
                    print(f"     ❌ 실패: {err}")
                    fail_count += 1
            except Exception as e:
                print(f"     ❌ 예외: {e}")
                fail_count += 1

            tmp_d = PROJECTS_DIR / "ykn" / "assets" / f"ctuning_{sid}_{code}"
            if tmp_d.exists():
                shutil.rmtree(tmp_d, ignore_errors=True)

        generate_tuning_html(tuning_dir)

    print("\n▶ 4x3 통합 컨택트 시트 합성 중...")
    render_tuning_contact_sheet(tuning_dir)
    generate_tuning_html(tuning_dir)

    elapsed = time.time() - start_time
    print("=" * 80)
    print(f" [완료] 성공: {success_count}장 / 실패: {fail_count}장 (소요 시간: {elapsed:.1f}초)")
    print(f" 뷰어 파일: {tuning_dir / 'index.html'}")
    print("=" * 80)


if __name__ == "__main__":
    main()
