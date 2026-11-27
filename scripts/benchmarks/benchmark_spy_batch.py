from __future__ import annotations

import argparse
import html as html_lib
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import plepa_engine.censor as censor

SPY_ASSETS_DIR = Path(r"C:\Users\rbsgh\kiro\projects\spy\assets")
OUTPUT_DIR = ROOT_DIR / "output" / "test_batch_spy"

CHAR_NAMES: Dict[str, str] = {
    "chl": "클로에 (Chloe)",
    "cla": "클라라 (Clara)",
    "dom": "도미니크 (Dominique)",
    "evl": "에블린 (Evelyn)",
    "kzk": "카즈키 (Kazuki)",
    "rvn": "레이븐 (Raven)",
    "scl": "스칼렛 (Scarlet)",
    "srh": "세라 (Sarah)",
    "vic": "빅토리아 (Victoria)",
    "viv": "비비안 (Vivian)",
}


def parse_filename(stem: str) -> Tuple[str, str, str]:
    """chl_100_펠라치오강 -> (chl, 100, 펠라치오강)"""
    parts = stem.split("_", 2)
    char_code = parts[0]
    pose_code = parts[1] if len(parts) > 1 and parts[1].isdigit() else "000"
    label = parts[2] if len(parts) > 2 else stem
    return char_code, pose_code, label


def render_spy_gallery_html(records: List[Dict[str, Any]], out_html: Path) -> None:
    """SPY H씬 510장 전용 원클릭 1:1 토글 비교 웹 갤러리를 생성합니다."""
    total = len(records)
    det_succ = sum(1 for r in records if r["det_count"] >= 1)
    fn_cnt = sum(1 for r in records if r["det_count"] == 0)
    multi_cnt = sum(1 for r in records if r["det_count"] >= 2)
    avg_sec = sum(r["elapsed_sec"] for r in records) / max(1, total)

    items_json = json.dumps(records, ensure_ascii=False)

    html_content = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>PLEPA Phase P2.5 SPY H-씬 전수 검열 갤러리 (510장)</title>
<style>
  :root {{
    --bg: #0b0f19;
    --card: #131d31;
    --text: #f1f5f9;
    --muted: #94a3b8;
    --primary: #38bdf8;
    --accent: #22c55e;
    --danger: #ef4444;
    --border: #1e293b;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans KR", sans-serif;
    min-height: 100vh;
    padding-bottom: 60px;
  }}
  header {{
    position: sticky;
    top: 0;
    z-index: 40;
    background: rgba(11, 15, 25, 0.94);
    backdrop-filter: blur(12px);
    border-bottom: 1px solid var(--border);
    padding: 12px 18px;
  }}
  .top-row {{
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }}
  h1 {{
    font-size: 1.15rem;
    font-weight: 700;
    display: flex;
    align-items: center;
    gap: 8px;
  }}
  .sub {{
    font-size: 0.8rem;
    color: var(--muted);
    margin-top: 4px;
  }}
  .stats-bar {{
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 10px;
  }}
  .stat-pill {{
    background: var(--card);
    border: 1px solid var(--border);
    padding: 4px 10px;
    border-radius: 999px;
    font-size: 0.75rem;
    font-weight: 600;
  }}
  .stat-pill b {{ color: var(--primary); }}
  .stat-pill.succ b {{ color: var(--accent); }}
  .stat-pill.danger b {{ color: var(--danger); }}

  .controls-row {{
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    margin-top: 12px;
  }}
  .btn {{
    border: 1px solid var(--border);
    background: var(--card);
    color: var(--text);
    padding: 6px 12px;
    border-radius: 8px;
    font-size: 0.8rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.15s ease;
  }}
  .btn:hover {{
    border-color: var(--primary);
  }}
  .btn.active {{
    background: var(--primary);
    color: #0b0f19;
    border-color: var(--primary);
  }}
  .filter-group {{
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    align-items: center;
  }}
  .char-btn {{
    font-size: 0.72rem;
    padding: 4px 8px;
    border-radius: 6px;
  }}

  /* Grid */
  .grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: 12px;
    padding: 16px 18px;
  }}
  @media (max-width: 640px) {{
    .grid {{
      grid-template-columns: repeat(2, 1fr);
      gap: 8px;
      padding: 10px;
    }}
  }}

  .card {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 10px;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    cursor: pointer;
    transition: transform 0.15s ease, border-color 0.15s ease;
    user-select: none;
  }}
  .card:hover {{
    transform: translateY(-2px);
    border-color: rgba(56, 189, 248, 0.4);
  }}
  .card-img-wrap {{
    position: relative;
    width: 100%;
    aspect-ratio: 832 / 1216;
    background: #000;
    overflow: hidden;
  }}
  .card-img {{
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
    transition: opacity 0.1s ease;
  }}
  .card-badge {{
    position: absolute;
    top: 6px;
    left: 6px;
    background: rgba(11, 15, 25, 0.82);
    backdrop-filter: blur(4px);
    padding: 3px 6px;
    border-radius: 6px;
    font-size: 0.65rem;
    font-weight: 700;
    color: #fff;
    border: 1px solid rgba(255, 255, 255, 0.15);
  }}
  .card-style-tag {{
    position: absolute;
    top: 6px;
    right: 6px;
    background: var(--primary);
    color: #0b0f19;
    padding: 2px 6px;
    border-radius: 5px;
    font-size: 0.65rem;
    font-weight: 800;
  }}
  .card-style-tag.orig {{
    background: #64748b;
    color: #fff;
  }}
  .card-info {{
    padding: 8px 10px;
    display: flex;
    flex-direction: column;
    gap: 3px;
  }}
  .card-title {{
    font-size: 0.78rem;
    font-weight: 700;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }}
  .card-sub {{
    font-size: 0.68rem;
    color: var(--muted);
    display: flex;
    justify-content: space-between;
  }}

  /* Lightbox Modal */
  .modal {{
    display: none;
    position: fixed;
    inset: 0;
    z-index: 100;
    background: rgba(3, 7, 18, 0.96);
    flex-direction: column;
  }}
  .modal.open {{ display: flex; }}
  .modal-top {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 18px;
    border-bottom: 1px solid var(--border);
  }}
  .modal-title {{
    font-size: 0.95rem;
    font-weight: 700;
  }}
  .modal-body {{
    flex: 1;
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 10px;
  }}
  .modal-img {{
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
    border-radius: 6px;
  }}
  .modal-nav {{
    position: absolute;
    top: 50%;
    transform: translateY(-50%);
    background: rgba(15, 23, 42, 0.75);
    color: #fff;
    border: 1px solid rgba(255, 255, 255, 0.2);
    width: 44px;
    height: 60px;
    border-radius: 8px;
    font-size: 1.4rem;
    cursor: pointer;
  }}
  .modal-prev {{ left: 12px; }}
  .modal-next {{ right: 12px; }}
  .modal-foot {{
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 12px;
    padding: 12px 18px;
    border-top: 1px solid var(--border);
  }}
</style>
</head>
<body>
<header>
  <div class="top-row">
    <div>
      <h1>🕵️ PLEPA Phase P2.5 SPY H-씬 전수 검열 갤러리</h1>
      <div class="sub">키로(SPY) 10인 510장 전수 검열 테스트 · Semantic-Guided SAM 2.1 + YOLO-seg (P2.5)</div>
    </div>
    <div style="display:flex; gap:8px;">
      <button class="btn active" id="btnGlobP25" onclick="setGlobalStyle('p25')">🚀 white_p25</button>
      <button class="btn" id="btnGlobOrig" onclick="setGlobalStyle('orig')">원본 (Origin)</button>
    </div>
  </div>
  <div class="stats-bar">
    <div class="stat-pill">총 <b>{total}</b>장</div>
    <div class="stat-pill succ">탐지 성공 <b>{det_succ}</b>장 ({det_succ/max(1,total)*100:.1f}%)</div>
    <div class="stat-pill {'danger' if fn_cnt > 0 else ''}">미탐(FN) <b>{fn_cnt}</b>장</div>
    <div class="stat-pill">다중 탐지 <b>{multi_cnt}</b>건</div>
    <div class="stat-pill">평균 처리속도 <b>{avg_sec:.3f}</b>s/장</div>
  </div>
  <div class="controls-row">
    <span style="font-size:0.75rem; color:var(--muted); font-weight:700;">캐릭터:</span>
    <div class="filter-group" id="charFilters">
      <button class="btn char-btn active" onclick="filterChar('all')">전체 (510)</button>
    </div>
  </div>
</header>

<main>
  <div class="grid" id="gridContainer"></div>
</main>

<!-- Lightbox Modal -->
<div class="modal" id="modal">
  <div class="modal-top">
    <div class="modal-title" id="modalTitle"></div>
    <button class="btn" onclick="closeModal()">✕ 닫기</button>
  </div>
  <div class="modal-body">
    <button class="modal-nav modal-prev" onclick="prevModal(event)">‹</button>
    <img id="modalImg" class="modal-img" src="" alt="preview" onclick="toggleModalStyle()">
    <button class="modal-nav modal-next" onclick="nextModal(event)">›</button>
  </div>
  <div class="modal-foot">
    <button class="btn" id="modalToggleBtn" onclick="toggleModalStyle()">스타일 전환 (Space)</button>
    <span style="font-size:0.8rem; color:var(--muted);" id="modalCount"></span>
  </div>
</div>

<script>
const ITEMS = {items_json};
let currentGlobalStyle = 'p25';
let perCardStyle = {{}}; // idx -> 'p25' | 'orig'
let activeChar = 'all';
let filteredIndices = [];
let modalIdx = -1;

const CHAR_MAP = {json.dumps(CHAR_NAMES, ensure_ascii=False)};

function init() {{
  // build char buttons
  const charFilterEl = document.getElementById('charFilters');
  const chars = Array.from(new Set(ITEMS.map(it => it.char))).sort();
  chars.forEach(ch => {{
    const cnt = ITEMS.filter(it => it.char === ch).length;
    const btn = document.createElement('button');
    btn.className = 'btn char-btn';
    btn.textContent = `${{ch.toUpperCase()}} (${{cnt}})`;
    btn.onclick = () => filterChar(ch);
    charFilterEl.appendChild(btn);
  }});

  applyFilter();
}}

function filterChar(ch) {{
  activeChar = ch;
  document.querySelectorAll('.char-btn').forEach(btn => {{
    if (ch === 'all' && btn.textContent.startsWith('전체')) btn.classList.add('active');
    else if (btn.textContent.startsWith(ch.toUpperCase())) btn.classList.add('active');
    else btn.classList.remove('active');
  }});
  applyFilter();
}}

function applyFilter() {{
  const grid = document.getElementById('gridContainer');
  grid.innerHTML = '';
  filteredIndices = [];

  ITEMS.forEach((it, idx) => {{
    if (activeChar !== 'all' && it.char !== activeChar) return;
    filteredIndices.push(idx);

    const card = document.createElement('div');
    card.className = 'card';
    card.id = `card-${{idx}}`;

    const style = perCardStyle[idx] || currentGlobalStyle;
    const imgSrc = style === 'p25' ? it.p25_rel : it.orig_rel;

    card.innerHTML = `
      <div class="card-img-wrap" onclick="openModal(${{idx}})">
        <img class="card-img" id="img-${{idx}}" src="${{imgSrc}}" loading="lazy" alt="${{it.file}}">
        <span class="card-badge">${{it.char.toUpperCase()}} #${{it.pose_code}} · 탐지 ${{it.det_count}}</span>
        <span class="card-style-tag ${{style === 'orig' ? 'orig' : ''}}" id="tag-${{idx}}">${{style === 'p25' ? 'P2.5' : '원본'}}</span>
      </div>
      <div class="card-info" onclick="toggleCardStyle(${{idx}}, event)">
        <div class="card-title">${{it.label}}</div>
        <div class="card-sub">
          <span>${{CHAR_MAP[it.char] || it.char}}</span>
          <span>${{it.elapsed_sec}}s</span>
        </div>
      </div>
    `;
    grid.appendChild(card);
  }});
}}

function setGlobalStyle(st) {{
  currentGlobalStyle = st;
  document.getElementById('btnGlobP25').classList.toggle('active', st === 'p25');
  document.getElementById('btnGlobOrig').classList.toggle('active', st === 'orig');

  ITEMS.forEach((_, idx) => {{
    delete perCardStyle[idx];
    updateCard(idx, st);
  }});
  if (modalIdx >= 0) {{
    updateModalImg();
  }}
}}

function toggleCardStyle(idx, event) {{
  if (event) event.stopPropagation();
  const cur = perCardStyle[idx] || currentGlobalStyle;
  const next = cur === 'p25' ? 'orig' : 'p25';
  perCardStyle[idx] = next;
  updateCard(idx, next);
}}

function updateCard(idx, st) {{
  const it = ITEMS[idx];
  const imgEl = document.getElementById(`img-${{idx}}`);
  const tagEl = document.getElementById(`tag-${{idx}}`);
  if (!imgEl || !tagEl) return;
  imgEl.src = st === 'p25' ? it.p25_rel : it.orig_rel;
  tagEl.textContent = st === 'p25' ? 'P2.5' : '원본';
  tagEl.classList.toggle('orig', st === 'orig');
}}

// Modal
function openModal(idx) {{
  modalIdx = idx;
  document.getElementById('modal').classList.add('open');
  updateModal();
}}

function closeModal() {{
  document.getElementById('modal').classList.remove('open');
  modalIdx = -1;
}}

function updateModal() {{
  if (modalIdx < 0) return;
  const it = ITEMS[modalIdx];
  const st = perCardStyle[modalIdx] || currentGlobalStyle;
  document.getElementById('modalTitle').textContent = `${{CHAR_MAP[it.char] || it.char}} #${{it.pose_code}} ${{it.label}} (${{st === 'p25' ? 'P2.5 검열' : '무검열 원본'}}, 탐지 ${{it.det_count}}건, ${{it.elapsed_sec}}s)`;
  document.getElementById('modalCount').textContent = `${{filteredIndices.indexOf(modalIdx) + 1}} / ${{filteredIndices.length}}`;
  updateModalImg();
}}

function updateModalImg() {{
  const it = ITEMS[modalIdx];
  const st = perCardStyle[modalIdx] || currentGlobalStyle;
  const img = document.getElementById('modalImg');
  img.src = st === 'p25' ? it.p25_rel : it.orig_rel;
  document.getElementById('modalToggleBtn').textContent = st === 'p25' ? '원본 보기 (Space)' : 'P2.5 검열 보기 (Space)';
}}

function toggleModalStyle() {{
  if (modalIdx < 0) return;
  const cur = perCardStyle[modalIdx] || currentGlobalStyle;
  const next = cur === 'p25' ? 'orig' : 'p25';
  perCardStyle[modalIdx] = next;
  updateCard(modalIdx, next);
  updateModal();
}}

function prevModal(e) {{
  if (e) e.stopPropagation();
  const curPos = filteredIndices.indexOf(modalIdx);
  if (curPos > 0) {{
    modalIdx = filteredIndices[curPos - 1];
    updateModal();
  }}
}}

function nextModal(e) {{
  if (e) e.stopPropagation();
  const curPos = filteredIndices.indexOf(modalIdx);
  if (curPos < filteredIndices.length - 1) {{
    modalIdx = filteredIndices[curPos + 1];
    updateModal();
  }}
}}

window.addEventListener('keydown', e => {{
  if (document.getElementById('modal').classList.contains('open')) {{
    if (e.key === 'Escape') closeModal();
    else if (e.key === 'ArrowLeft') prevModal();
    else if (e.key === 'ArrowRight') nextModal();
    else if (e.code === 'Space') {{
      e.preventDefault();
      toggleModalStyle();
    }}
  }}
}});

window.addEventListener('DOMContentLoaded', init);
</script>
</body>
</html>
"""
    out_html.write_text(html_content, encoding="utf-8")
    print(f"[Gallery] SPY 510장 전용 갤러리 HTML 생성 완료: {out_html}")


def run_benchmark(chars: Optional[List[str]] = None, limit_per_char: Optional[int] = None) -> None:
    t_start = time.perf_counter()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    origin_dirs = sorted([d for d in SPY_ASSETS_DIR.glob("*_origin") if d.is_dir()])
    if chars:
        origin_dirs = [d for d in origin_dirs if d.name.replace("_origin", "") in chars]

    print(f"=== [SPY H-씬 Phase P2.5 전수 벤치마크] ===")
    print(f"대상 캐릭터: {[d.name.replace('_origin', '') for d in origin_dirs]} ({len(origin_dirs)}명)")

    all_records: List[Dict[str, Any]] = []
    total_files = 0
    fn_files: List[str] = []
    multi_files: List[str] = []

    for c_idx, orig_dir in enumerate(origin_dirs, 1):
        char_code = orig_dir.name.replace("_origin", "")
        char_label = CHAR_NAMES.get(char_code, char_code)
        files = sorted(list(orig_dir.glob("*.webp")))
        if limit_per_char and limit_per_char > 0:
            files = files[:limit_per_char]

        char_orig_out = OUTPUT_DIR / f"{char_code}_origin"
        char_p25_out = OUTPUT_DIR / f"{char_code}_p25"
        char_orig_out.mkdir(parents=True, exist_ok=True)
        char_p25_out.mkdir(parents=True, exist_ok=True)

        print(f"\n[{c_idx}/{len(origin_dirs)}] {char_label} ({char_code}) - {len(files)}장 시작")

        char_det_cnt = 0
        char_t0 = time.perf_counter()

        for f_idx, fpath in enumerate(files, 1):
            _, pose_code, label = parse_filename(fpath.stem)
            orig_dest = char_orig_out / fpath.name
            p25_dest = char_p25_out / fpath.name

            # copy origin if not exists
            if not orig_dest.exists() or orig_dest.stat().st_size != fpath.stat().st_size:
                shutil.copy2(fpath, orig_dest)

            # run P2.5 censor
            t0 = time.perf_counter()
            with Image.open(fpath) as img:
                orig_rgb = img.convert("RGB")
                cens_rgb, det_count = censor.censor_image(
                    orig_rgb,
                    style="white_silhouette",
                    targets=("penis",),
                    pose_code=pose_code,
                    roster="spy",
                    enable_anchor_fallback=False,
                )
            elapsed = time.perf_counter() - t0
            cens_rgb.save(p25_dest, "WEBP", quality=92)

            det_c = int(det_count)
            if det_c >= 1:
                char_det_cnt += 1
            else:
                fn_files.append(fpath.name)
            if det_c >= 2:
                multi_files.append(fpath.name)

            rec = {
                "char": char_code,
                "char_label": char_label,
                "file": fpath.name,
                "pose_code": pose_code,
                "label": label,
                "det_count": det_c,
                "elapsed_sec": round(elapsed, 3),
                "orig_rel": f"{char_code}_origin/{fpath.name}",
                "p25_rel": f"{char_code}_p25/{fpath.name}",
            }
            all_records.append(rec)
            total_files += 1

            if f_idx % 10 == 0 or f_idx == len(files):
                print(f"  [{f_idx:02d}/{len(files):02d}] {fpath.name} -> det={det_c} ({elapsed:.3f}s)")

        char_elapsed = time.perf_counter() - char_t0
        print(f"  -> {char_code} 완료: {char_det_cnt}/{len(files)} 탐지 성공 ({char_elapsed:.1f}s, avg {char_elapsed/max(1,len(files)):.3f}s/장)")

    total_time = time.perf_counter() - t_start

    # Save JSON result
    summary = {
        "label": "P2.5_SPY_ALL",
        "total_count": total_files,
        "det_success_count": sum(1 for r in all_records if r["det_count"] >= 1),
        "fn_count": len(fn_files),
        "fn_files": fn_files,
        "multi_count": len(multi_files),
        "multi_files": multi_files,
        "total_elapsed_sec": round(total_time, 2),
        "avg_sec": round(total_time / max(1, total_files), 3),
        "records": all_records,
    }
    result_json = OUTPUT_DIR / "spy_benchmark_result.json"
    result_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[Result] 통계 JSON 저장 완료: {result_json}")

    # Generate HTML Gallery
    out_html = OUTPUT_DIR / "index.html"
    render_spy_gallery_html(all_records, out_html)

    print("\n" + "=" * 70)
    print(f"=== [SPY 10인 510장 전수 검열 테스트 완결 보고] ===")
    print(f"  총 검사 수   : {total_files}장")
    print(f"  탐지 성공     : {summary['det_success_count']}장 ({summary['det_success_count']/max(1,total_files)*100:.2f}%)")
    print(f"  미탐(FN)     : {summary['fn_count']}장 ({summary['fn_count']/max(1,total_files)*100:.2f}%)")
    print(f"  다중 탐지     : {summary['multi_count']}건 (손분할 또는 복수 객체)")
    print(f"  총 소요 시간 : {total_time/60:.2f}분 (평균 {summary['avg_sec']}s/장)")
    print("=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(description="SPY H-씬 510장 Phase P2.5 전수 배치 검열 및 갤러리 생성")
    parser.add_argument("--chars", type=str, default=None, help="대상 캐릭터 쉼표 구분 (예: chl,cla,dom)")
    parser.add_argument("--limit-per-char", type=int, default=None, help="캐릭터당 최대 처리 수 (디버깅용)")
    args = parser.parse_args()

    chars_list = [c.strip() for c in args.chars.split(",")] if args.chars else None
    run_benchmark(chars=chars_list, limit_per_char=args.limit_per_char)


if __name__ == "__main__":
    main()
