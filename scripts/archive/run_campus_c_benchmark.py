"""
scripts/run_campus_c_benchmark.py
캠퍼스 대표 4인 (하루, 아야메, 카오루, 마이) × 2대 포즈 (000, 088) × C-1 vs C-2 비교 벤치마크

[조합 2선]:
- C-1 (미세 감쇄): ratatatat74 0.80
- C-2 (중간 감쇄): ratatatat74 0.70

[대상 캐릭터 (캠퍼스 4인)]:
- har (하루 / 가린눈 모브 선배)
- aya (아야메 / 실버 단발 쿨뷰티)
- kao (카오루 / 흑발 사이드포니 육감미)
- mai (마이 / 안경 폭유 조교수)

[대상 포즈]:
- 000: 평상 (상반신 이목구비 & 가슴 물광)
- 088: 후배위약 (배면 둔부 오일 물광)

총 4캐릭 × 2포즈 × 2조합 = 16장 (시드 1001 고정)
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

CHARACTERS = [
    {"code": "har", "name": "하루 (Haru)", "desc": "가린눈 모브 선배 & 라이트 브라운 숏보브 & 숨겨진 거유"},
    {"code": "aya", "name": "아야메 (Ayame)", "desc": "교토 쿨뷰티 & 플래티넘 실버 숏보브 & 슬렌더"},
    {"code": "kao", "name": "카오루 (Kaoru)", "desc": "오사카 육감미 & 흑발 사이드 포니테일 & 글래머"},
    {"code": "mai", "name": "마이 (Mai)", "desc": "지적인 조교수 & 애쉬 그레이 로우 포니테일 & 무테 안경 & 폭유"},
]

POSES = [
    {"code": "000", "label": "평상 (상반신 쿨뷰티)"},
    {"code": "088", "label": "후배위약 (배면 둔부 물광)"},
]

COMBOS = [
    {
        "id": "c1",
        "title": "C-1 미세감쇄 (라타타 0.80)",
        "short_title": "C-1 (0.80)",
        "ratatata_weight": 0.80,
        "tag": "(artist:z-ton:0.85), (artist:fukuro_daikokuten:0.90), (artist:ratatatat74:0.80), (artist:hizuki_yeo:0.80), (oily skin:1.15), (skin glisten:1.1), sweat drops",
        "desc": "z-ton/fukuro의 볼륨감 + 라타타 0.80의 요염한 눈매",
        "color": "#059669",
    },
    {
        "id": "c2",
        "title": "C-2 중간감쇄 (라타타 0.70)",
        "short_title": "C-2 (0.70)",
        "ratatata_weight": 0.70,
        "tag": "(artist:z-ton:0.85), (artist:fukuro_daikokuten:0.90), (artist:ratatatat74:0.70), (artist:hizuki_yeo:0.80), (oily skin:1.15), (skin glisten:1.1), sweat drops",
        "desc": "hizuki_yeo의 정갈하고 매끄러운 고급 K-웹툰 채색미 극대화",
        "color": "#2563eb",
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
    has_contact = (benchmark_dir / "master_campus_c_contact.webp").exists()

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=3.0, user-scalable=yes">
<title>캠퍼스 대표 4인 C-1 vs C-2 1:1 비교 뷰어</title>
<style>
  :root {{
    --bg: #090c15;
    --card-bg: #121626;
    --border: #212840;
    --text: #f1f5f9;
    --text-muted: #94a3b8;
    --accent: #0ea5e9;
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
    background: #0f1322;
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
    background: #0369a1;
    color: #e0f2fe;
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
    background: #182036;
    color: #cbd5e1;
    text-decoration: none;
    font-size: 0.74rem;
    padding: 5px 9px;
    border-radius: 6px;
    white-space: nowrap;
    border: 1px solid var(--border);
  }}
  .filter-bar {{
    display: flex;
    background: #0f1322;
    border-bottom: 1px solid var(--border);
    padding: 8px 12px;
    gap: 6px;
    overflow-x: auto;
    scrollbar-width: none;
  }}
  .filter-bar::-webkit-scrollbar {{ display: none; }}
  .filter-btn {{
    background: transparent;
    color: var(--text-muted);
    border: 1px solid var(--border);
    padding: 6px 12px;
    border-radius: 6px;
    font-size: 0.8rem;
    font-weight: 600;
    cursor: pointer;
    white-space: nowrap;
  }}
  .filter-btn.active {{
    background: var(--accent);
    color: #fff;
    border-color: var(--accent);
  }}
  .container {{
    padding: 12px;
  }}
  .summary-banner {{
    background: #131b2e;
    border: 1px solid #1e293b;
    border-radius: 12px;
    padding: 12px 14px;
    margin-bottom: 16px;
    font-size: 0.8rem;
    color: #cbd5e1;
  }}
  .unit-card {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 12px;
    margin-bottom: 20px;
    overflow: hidden;
  }}
  .unit-header {{
    padding: 10px 14px;
    background: #161c30;
    border-bottom: 1px solid var(--border);
    display: flex;
    justify-content: space-between;
    align-items: center;
  }}
  .unit-title {{
    font-size: 0.95rem;
    font-weight: bold;
    color: #fff;
  }}
  .unit-desc {{
    font-size: 0.75rem;
    color: var(--text-muted);
    margin-top: 2px;
  }}
  .compare-2col {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
    padding: 12px;
  }}
  .col-box {{
    background: #0b0e18;
    border: 1px solid var(--border);
    border-radius: 8px;
    overflow: hidden;
  }}
  .col-header {{
    padding: 6px 10px;
    font-size: 0.76rem;
    font-weight: bold;
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: #151a2c;
  }}
  .img-wrap {{
    width: 100%;
    aspect-ratio: 832 / 1216;
    background: #05070d;
    position: relative;
    overflow: hidden;
  }}
  .img-wrap img {{
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
    cursor: zoom-in;
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
    <h1><span>🎓 캠퍼스 대표 4인 C-1 vs C-2 비교</span></h1>
    <span class="badge">16장 실측 (시드 1001)</span>
  </div>
  <div class="header-desc">
    하루 · 아야메 · 카오루 · 마이 × [C-1 라타타 0.80] vs [C-2 라타타 0.70]
  </div>
  <div class="nav-bar">
    <a href="/c_tuning/" class="nav-link">🎯 하율 C조합 감쇄 ➔</a>
    <a href="/hybrid/" class="nav-link">✨ 4대 조합 전체 ➔</a>
    <a href="/artist2/" class="nav-link">🔞 40인 성인작가 ➔</a>
    <a href="/" class="nav-link">🔬 4대 체위 통계 ➔</a>
  </div>
</header>

<div class="filter-bar">
  <button class="filter-btn active" onclick="filterChar('all')">전체 (4인)</button>
  <button class="filter-btn" onclick="filterChar('har')">하루 (har)</button>
  <button class="filter-btn" onclick="filterChar('aya')">아야메 (aya)</button>
  <button class="filter-btn" onclick="filterChar('kao')">카오루 (kao)</button>
  <button class="filter-btn" onclick="filterChar('mai')">마이 (mai)</button>
</div>

<div class="container">
  <div class="summary-banner">
    💡 <strong>관전 포인트</strong>: 흑발뿐만 아니라 <strong>갈색 숏보브(하루)</strong>, <strong>은발(아야메)</strong>, <strong>오사카 흑발(카오루)</strong>, <strong>애쉬그레이 안경(마이)</strong> 등 다양한 외형에서 <strong>C-1(0.80)</strong>과 <strong>C-2(0.70)</strong>가 각각 어떻게 발현되는지 나란히 비교합니다.
  </div>
"""

    for ch in CHARACTERS:
        for pos in POSES:
            c_code = ch["code"]
            p_code = pos["code"]

            img_c1 = f"c1/{c_code}_{p_code}_c1.webp"
            img_c2 = f"c2/{c_code}_{p_code}_c2.webp"
            exists_c1 = (benchmark_dir / img_c1).exists()
            exists_c2 = (benchmark_dir / img_c2).exists()

            html += f"""
  <div class="unit-card" data-char="{c_code}">
    <div class="unit-header">
      <div>
        <div class="unit-title">{ch['name']} · #{p_code} {pos['label']}</div>
        <div class="unit-desc">{ch['desc']}</div>
      </div>
      <span style="font-size:0.75rem; color:#38bdf8;">시드 1001</span>
    </div>
    <div class="compare-2col">
      <!-- C-1 -->
      <div class="col-box">
        <div class="col-header">
          <span style="color:#34d399;">C-1 (라타타 0.80)</span>
          <span style="font-size:0.68rem; color:#a7f3d0;">미세감쇄</span>
        </div>
        <div class="img-wrap">
"""
            if exists_c1:
                html += f"""          <img src="{img_c1}" alt="{c_code}_{p_code}_c1" onclick="openLightbox(this.src)" loading="lazy">"""
            else:
                html += """          <div style="height:100%; display:flex; align-items:center; justify-content:center; color:#475569; font-size:0.75rem;">대기 중</div>"""
            html += f"""
        </div>
      </div>

      <!-- C-2 -->
      <div class="col-box">
        <div class="col-header">
          <span style="color:#60a5fa;">C-2 (라타타 0.70)</span>
          <span style="font-size:0.68rem; color:#bfdbfe;">중간감쇄</span>
        </div>
        <div class="img-wrap">
"""
            if exists_c2:
                html += f"""          <img src="{img_c2}" alt="{c_code}_{p_code}_c2" onclick="openLightbox(this.src)" loading="lazy">"""
            else:
                html += """          <div style="height:100%; display:flex; align-items:center; justify-content:center; color:#475569; font-size:0.75rem;">대기 중</div>"""
            html += """
        </div>
      </div>
    </div>
  </div>
"""

    html += """
  <!-- 마스터 컨택트 시트 -->
  <div style="margin-top:24px; background:var(--card-bg); border:1px solid var(--border); border-radius:12px; overflow:hidden;">
    <div style="padding:10px 14px; background:#161c30; font-size:0.85rem; font-weight:bold; display:flex; justify-content:space-between;">
      <span>📋 캠퍼스 4인 × 2포즈 × 2조합 = 16장 마스터 컨택트 시트</span>
      <span style="font-size:0.75rem; color:#38bdf8;">터치 시 확대</span>
    </div>
"""
    if has_contact:
        html += """    <img src="master_campus_c_contact.webp" alt="마스터 컨택트 시트" style="width:100%; display:block; cursor:zoom-in;" onclick="openLightbox(this.src)">"""
    else:
        html += """    <div style="padding:30px; text-align:center; color:#475569;">16장 렌더링 완료 후 자동 생성됩니다.</div>"""

    html += """
  </div>
</div>

<div class="lightbox" id="lightbox" onclick="closeLightbox()">
  <img id="lightbox-img" src="" alt="확대">
</div>

<script>
  function filterChar(code) {
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');
    document.querySelectorAll('.unit-card').forEach(card => {
      if (code === 'all' || card.dataset.char === code) {
        card.style.display = 'block';
      } else {
        card.style.display = 'none';
      }
    });
  }

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


def render_campus_contact_sheet(benchmark_dir: Path) -> Path:
    """4개 캐릭터 × 4열 (000 C1, 000 C2, 088 C1, 088 C2) = 16장 컨택트 시트 합성."""
    cell_w, cell_h = 416, 608
    header_h = 100
    label_h = 36
    side_w = 120

    columns = [
        ("000", "c1", "평상 C-1 (0.80)", "#059669"),
        ("000", "c2", "평상 C-2 (0.70)", "#2563eb"),
        ("088", "c1", "후배위 C-1 (0.80)", "#059669"),
        ("088", "c2", "후배위 C-2 (0.70)", "#2563eb"),
    ]

    total_w = side_w + cell_w * 4 + 30
    total_h = header_h + (cell_h + label_h + 10) * 4 + 20

    sheet = Image.new("RGB", (total_w, total_h), color=(10, 13, 22))
    draw = ImageDraw.Draw(sheet)

    title_font = get_font(28)
    sub_font = get_font(18)
    header_font = get_font(20)
    label_font = get_font(16)

    # 헤더
    draw.text((20, 20), "PLEPA 캠퍼스 4인 C-1(0.80) vs C-2(0.70) 16장 통합 벤치마크", fill=(255, 255, 255), font=title_font)
    draw.text((20, 60), "하루 · 아야메 · 카오루 · 마이 · 고정 시드 1001 · 행: 4인 캐릭터 / 열: 포즈 및 튜닝 스텝", fill=(148, 163, 184), font=sub_font)

    # 열 헤더
    for col_idx, (p_code, c_code, col_lbl, col_bg) in enumerate(columns):
        cx = side_w + col_idx * cell_w + 10
        draw.rounded_rectangle([cx, header_h - 28, cx + cell_w - 10, header_h - 4], radius=6, fill=col_bg)
        draw.text((cx + 12, header_h - 26), f"#{p_code} {col_lbl}", fill=(255, 255, 255), font=header_font)

    # 셀 합성
    for row_idx, ch in enumerate(CHARACTERS):
        ry = header_h + row_idx * (cell_h + label_h + 10)
        c_code = ch["code"]

        draw.text((15, ry + cell_h // 2 - 20), f"{ch['name'].split()[0]}\n({c_code})", fill=(203, 213, 225), font=header_font)

        for col_idx, (p_code, combo_id, col_lbl, col_bg) in enumerate(columns):
            rx = side_w + col_idx * cell_w + 10
            img_file = benchmark_dir / combo_id / f"{c_code}_{p_code}_{combo_id}.webp"

            if img_file.exists():
                try:
                    with Image.open(img_file) as im:
                        im_thumb = im.convert("RGB").resize((cell_w - 10, cell_h), Image.Resampling.LANCZOS)
                        sheet.paste(im_thumb, (rx, ry))
                except Exception:
                    draw.rectangle([rx, ry, rx + cell_w - 10, ry + cell_h], fill=(20, 25, 40))
            else:
                draw.rectangle([rx, ry, rx + cell_w - 10, ry + cell_h], fill=(20, 25, 40))

            draw.rectangle([rx, ry + cell_h, rx + cell_w - 10, ry + cell_h + label_h], fill=(18, 22, 35))
            draw.text((rx + 8, ry + cell_h + 8), f"{c_code} | #{p_code} | {combo_id.upper()}", fill=(186, 230, 253), font=label_font)

    contact_path = benchmark_dir / "master_campus_c_contact.webp"
    sheet.save(contact_path, "WEBP", quality=92)
    return contact_path


def main():
    benchmark_dir = PROJECTS_DIR / "campus" / "artist_benchmark_c1_c2"
    benchmark_dir.mkdir(parents=True, exist_ok=True)

    for c in COMBOS:
        (benchmark_dir / c["id"]).mkdir(parents=True, exist_ok=True)

    generate_html_viewer(benchmark_dir)

    print("=" * 80)
    print(" [캠퍼스 대표 4인 C-1 vs C-2 실측 벤치마크]")
    print(" 대상: 하루(har), 아야메(aya), 카오루(kao), 마이(mai)")
    print(" 포즈: 000(평상), 088(후배위) | 고정 시드 1001")
    print(" 총 16장 (C-1 8장 + C-2 8장)")
    print(f" 저장 위치: {benchmark_dir}")
    print("=" * 80)

    service = GenerationService()
    success_count = 0
    fail_count = 0
    start_time = time.time()

    for ch_idx, ch in enumerate(CHARACTERS, 1):
        c_code = ch["code"]
        print(f"\n▶ [{ch_idx}/4] 캐릭터: {ch['name']} ({c_code})")

        for p_idx, pos in enumerate(POSES, 1):
            p_code = pos["code"]

            for cmb in COMBOS:
                combo_id = cmb["id"]
                target_fname = f"{c_code}_{p_code}_{combo_id}.webp"
                final_path = benchmark_dir / combo_id / target_fname

                if final_path.exists() and final_path.stat().st_size > 5000:
                    print(f"  [스킵] 이미 완료됨: {target_fname}")
                    success_count += 1
                    continue

                print(f"  [{combo_id.upper()}] 포즈 #{p_code} ({pos['label'].split()[0]}) 렌더링 중...")
                params = GenerationParams(
                    character_expr=c_code,
                    pose_expr=p_code,
                    roster="campus",
                    custom_pos=cmb["tag"],
                    ckpt_tag=f"campus_{c_code}_{p_code}_{combo_id}",
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
                            shutil.copy2(gen_p, final_path)
                            size_kb = final_path.stat().st_size // 1024
                            print(f"     ✅ 성공 ({dur:.1f}초, {size_kb} KB) -> {final_path.name}")
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

                tmp_d = PROJECTS_DIR / "campus" / "assets" / f"campus_{c_code}_{p_code}_{combo_id}"
                if tmp_d.exists():
                    shutil.rmtree(tmp_d, ignore_errors=True)

            generate_html_viewer(benchmark_dir)

    print("\n▶ 16장 렌더링 완료. 마스터 4x4 컨택트 시트 합성 중...")
    render_campus_contact_sheet(benchmark_dir)
    generate_html_viewer(benchmark_dir)

    elapsed = time.time() - start_time
    print("=" * 80)
    print(f" [완료] 성공: {success_count}장 / 실패: {fail_count}장 (소요 시간: {elapsed:.1f}초)")
    print(f" 뷰어 파일: {benchmark_dir / 'index.html'}")
    print("=" * 80)


if __name__ == "__main__":
    main()
