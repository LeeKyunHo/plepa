"""
Phase H1-Eval: 파일럿 8종 포즈 Before(기존 본체) vs After(Phase H1 ADR-100) 정량 비교 및 갤러리 생성기.

기존 `projects/campus/assets`와 `output/test_batch_h1_pilot`을 대상으로:
1. `face_height_ratio` (여캐 얼굴 크기 비율: detect_faces conf >= 0.65 기준)
2. `persons / heads / faces / hands` 검출 수 및 Auto-QC / 재시도 / 생성 소요시간
3. `censor_area_ratio` (원본 _origin 대비 실제 검열본 화이트 실루엣 면적 비율 %)
4. 모바일·PC 비교 갤러리(`output/test_batch_h1_pilot/index.html`) 및 `h1_eval_result.json` 생성
"""

from __future__ import annotations

import argparse
import html
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from plepa_engine.censor import detect_genitals
from plepa_engine.qa_validator import (
    HAS_IMGUTILS,
    configure_qa_runtime,
    detect_faces,
    detect_hands,
    detect_heads,
    detect_person,
    validate_generated_image,
)
from plepa_engine.services.pose_service import default_pose_service

DEFAULT_POSES = ["072", "080", "086", "088", "091", "092", "100", "104"]
DEFAULT_CHARS = ["aya", "shz"]
TIER_LABELS = {
    0: "Tier 0 · 오프스크린 POV",
    1: "Tier 1 · 손·극부위 크롭",
    2: "Tier 2 · 실루엣·등/실루엣 밀착",
    3: "Tier 3 · 콤팩트 봉사 POV",
}


def find_pose_webp(folder: Path, char_code: str, pose_code: str) -> Optional[Path]:
    """캐릭터·포즈 코드에 해당하는 WebP 파일을 탐색합니다."""
    if not folder.is_dir():
        return None
    matches = sorted(folder.glob(f"{char_code}_{pose_code}_*.webp"))
    if matches:
        return matches[0]
    exact = folder / f"{char_code}_{pose_code}.webp"
    return exact if exact.exists() else None


def compute_censor_area_ratio(origin_path: Path, censored_path: Path) -> Tuple[float, int]:
    """
    원본(_origin) 대비 검열본에서 화이트 실루엣 마스킹으로 덮인 픽셀 비율(%)과 픽셀 수를 계산합니다.
    WebP 손실 재인코딩 오차(±10)를 배제하기 위해 밝기 최솟값 >= 235 및 채널 차이 >= 12 조건을 적용합니다.
    """
    if not origin_path.exists() or not censored_path.exists():
        return 0.0, 0
    if origin_path.read_bytes() == censored_path.read_bytes():
        return 0.0, 0

    with Image.open(origin_path) as im_o, Image.open(censored_path) as im_c:
        arr_o = np.asarray(im_o.convert("RGB"), dtype=np.int16)
        arr_c = np.asarray(im_c.convert("RGB"), dtype=np.int16)

    if arr_o.shape != arr_c.shape:
        return 0.0, 0

    max_diff = np.max(np.abs(arr_c - arr_o), axis=2)
    cens_min = np.min(arr_c, axis=2)
    masked = (cens_min >= 235) & (max_diff >= 12)
    masked_px = int(np.count_nonzero(masked))
    total_px = int(arr_o.shape[0] * arr_o.shape[1])
    ratio_pct = round((masked_px / max(1, total_px)) * 100.0, 3)
    return ratio_pct, masked_px


def inspect_single_asset(
    origin_path: Path,
    censored_path: Path,
    *,
    pose_code: str,
    roster: str,
    is_solo_scene: bool,
    is_two_person: bool,
    is_offscreen_partner: bool,
    is_kiss_scene: bool,
    section: str,
    prompt_text: str,
) -> Dict[str, Any]:
    """단일 원본+검열 에셋 쌍에 대해 ONNX 검출·얼굴비율·Auto-QC·검열면적을 측정합니다."""
    configure_qa_runtime()
    with Image.open(origin_path) as raw_im:
        img = raw_im.convert("RGB")
        img_w, img_h = img.size

    persons = heads = faces = hands = 0
    face_height_ratio = 0.0
    max_face_score = 0.0

    if HAS_IMGUTILS:
        raw_persons = [p for p in detect_person(img) if p[2] >= 0.55]
        raw_heads = [h for h in detect_heads(img) if h[2] >= 0.55]
        raw_faces = [f for f in detect_faces(img) if f[2] >= 0.65]
        raw_hands = [h for h in detect_hands(img) if h[2] >= 0.60]

        persons = len(raw_persons)
        heads = len(raw_heads)
        faces = len(raw_faces)
        hands = len(raw_hands)

        if raw_faces:
            max_face_h = max(max(0.0, float(f[0][3] - f[0][1])) for f in raw_faces)
            face_height_ratio = round(max_face_h / max(1, img_h), 4)
            max_face_score = round(max(float(f[2]) for f in raw_faces), 3)

    qc_passed, qc_reason, qc_metrics = validate_generated_image(
        image=origin_path,
        is_solo_scene=is_solo_scene,
        is_two_person=is_two_person,
        is_offscreen_partner=is_offscreen_partner,
        is_kiss_scene=is_kiss_scene,
        section=section,
        prompt=prompt_text,
    )

    censor_pct, censor_px = compute_censor_area_ratio(origin_path, censored_path)
    genital_boxes = detect_genitals(str(origin_path), targets=("penis",), pose_code=pose_code, roster=roster)

    return {
        "width": img_w,
        "height": img_h,
        "persons": persons,
        "heads": heads,
        "faces": faces,
        "hands": hands,
        "face_height_ratio": face_height_ratio,
        "max_face_score": max_face_score,
        "censor_area_ratio": censor_pct,
        "censor_pixels": censor_px,
        "genital_detections": len(genital_boxes),
        "h1_qc_passed": bool(qc_passed),
        "h1_qc_reason": qc_reason or "",
        "blur_score": float(qc_metrics.get("blur_score", 0.0)),
    }


def _avg(values: List[float], digits: int = 3) -> float:
    return round(sum(values) / len(values), digits) if values else 0.0


def build_pose_summary(records: List[Dict[str, Any]], poses: List[str]) -> List[Dict[str, Any]]:
    """8개 파일럿 포즈별 Before vs After 평균 지표를 집계합니다."""
    rows: List[Dict[str, Any]] = []
    for code in poses:
        sub = [r for r in records if r["pose_code"] == code]
        if not sub:
            continue
        b_faces = [r["before"]["face_height_ratio"] for r in sub]
        a_faces = [r["after"]["face_height_ratio"] for r in sub]
        b_cens = [r["before"]["censor_area_ratio"] for r in sub]
        a_cens = [r["after"]["censor_area_ratio"] for r in sub]

        b_persons = [r["before"]["persons"] for r in sub]
        a_persons = [r["after"]["persons"] for r in sub]
        b_heads = [r["before"]["heads"] for r in sub]
        a_heads = [r["after"]["heads"] for r in sub]
        b_face_cnt = [r["before"]["faces"] for r in sub]
        a_face_cnt = [r["after"]["faces"] for r in sub]
        b_hands = [r["before"]["hands"] for r in sub]
        a_hands = [r["after"]["hands"] for r in sub]

        first_pass = sum(1 for r in sub if r["manifest"]["qc_passed"] and r["manifest"]["retries"] == 0)
        final_pass = sum(1 for r in sub if r["manifest"]["qc_passed"])

        rows.append(
            {
                "pose_code": code,
                "label": sub[0]["label"],
                "mob_tier": sub[0]["mob_tier"],
                "n": len(sub),
                "before_face_ratio": _avg(b_faces, 4),
                "after_face_ratio": _avg(a_faces, 4),
                "face_ratio_delta": round(_avg(a_faces, 4) - _avg(b_faces, 4), 4),
                "before_censor_pct": _avg(b_cens, 3),
                "after_censor_pct": _avg(a_cens, 3),
                "censor_pct_delta": round(_avg(a_cens, 3) - _avg(b_cens, 3), 3),
                "before_persons_avg": _avg(b_persons, 2),
                "after_persons_avg": _avg(a_persons, 2),
                "before_heads_avg": _avg(b_heads, 2),
                "after_heads_avg": _avg(a_heads, 2),
                "before_faces_avg": _avg(b_face_cnt, 2),
                "after_faces_avg": _avg(a_face_cnt, 2),
                "before_hands_avg": _avg(b_hands, 2),
                "after_hands_avg": _avg(a_hands, 2),
                "after_first_pass": first_pass,
                "after_final_pass": final_pass,
                "after_retries_total": sum(int(r["manifest"]["retries"]) for r in sub),
                "after_duration_avg": _avg([float(r["manifest"]["duration_sec"]) for r in sub], 2),
            }
        )
    return rows


def generate_comparison_html(
    *,
    out_dir: Path,
    records: List[Dict[str, Any]],
    pose_rows: List[Dict[str, Any]],
    summary: Dict[str, Any],
) -> Path:
    """Before vs After 나란히·터치비교 HTML 뷰어를 생성합니다."""
    out_html = out_dir / "index.html"
    data_json = json.dumps(records, ensure_ascii=False).replace("</", "<\\/")
    pose_json = json.dumps(pose_rows, ensure_ascii=False).replace("</", "<\\/")

    html_doc = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Phase H1 Pilot Evaluation · Before vs After ({summary['total_pairs']}장 쌍 비교)</title>
<style>
  :root {{
    --bg: #0b0f19;
    --panel: #131a2a;
    --card: #1a2336;
    --border: rgba(255, 255, 255, 0.1);
    --text: #e2e8f0;
    --muted: #94a3b8;
    --primary: #38bdf8;
    --good: #34d399;
    --warn: #fbbf24;
    --bad: #fb7185;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans KR", sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.45;
    padding-bottom: 48px;
  }}
  header {{
    position: sticky;
    top: 0;
    z-index: 40;
    background: rgba(11, 15, 25, 0.92);
    backdrop-filter: blur(12px);
    border-bottom: 1px solid var(--border);
    padding: 12px 16px;
  }}
  .title-row {{
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
  }}
  h1 {{ font-size: 1.05rem; font-weight: 700; color: #fff; }}
  .kpi-bar {{
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 8px;
  }}
  .pill {{
    background: rgba(255,255,255,0.06);
    border: 1px solid var(--border);
    border-radius: 999px;
    padding: 4px 10px;
    font-size: 0.74rem;
    font-weight: 600;
  }}
  .pill b {{ color: var(--primary); }}
  .pill.good b {{ color: var(--good); }}
  .controls {{
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 10px;
  }}
  .btn {{
    background: var(--card);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 6px 10px;
    font-size: 0.76rem;
    font-weight: 600;
    cursor: pointer;
  }}
  .btn.active {{
    background: var(--primary);
    color: #08101e;
    border-color: var(--primary);
  }}
  .btn.good.active {{
    background: var(--good);
    color: #062116;
    border-color: var(--good);
  }}
  .section-wrap {{
    padding: 14px 16px 0;
  }}
  .table-wrap {{
    overflow-x: auto;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 12px;
    margin-bottom: 16px;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.76rem;
    white-space: nowrap;
  }}
  th, td {{
    padding: 8px 10px;
    border-bottom: 1px solid var(--border);
    text-align: center;
  }}
  th {{
    background: rgba(255,255,255,0.04);
    color: var(--muted);
    font-weight: 600;
  }}
  td:first-child, th:first-child {{ text-align: left; }}
  .grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(330px, 1fr));
    gap: 14px;
    padding: 4px 16px 16px;
  }}
  @media (max-width: 640px) {{
    .grid {{ grid-template-columns: 1fr; padding: 4px 10px 16px; }}
  }}
  .pair-card {{
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow: hidden;
  }}
  .pair-head {{
    padding: 10px 12px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid var(--border);
    gap: 8px;
  }}
  .pair-title {{ font-size: 0.88rem; font-weight: 700; color: #fff; }}
  .tier-tag {{
    font-size: 0.68rem;
    font-weight: 700;
    padding: 2px 7px;
    border-radius: 6px;
    background: rgba(56, 189, 248, 0.16);
    color: var(--primary);
  }}
  .pair-imgs {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 2px;
    background: #05080f;
  }}
  .img-slot {{
    position: relative;
    aspect-ratio: 832 / 1216;
    cursor: pointer;
    overflow: hidden;
  }}
  .img-slot img {{
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }}
  .slot-badge {{
    position: absolute;
    top: 6px;
    left: 6px;
    padding: 2px 7px;
    border-radius: 6px;
    font-size: 0.66rem;
    font-weight: 700;
    background: rgba(11, 15, 25, 0.82);
    color: #fff;
  }}
  .slot-badge.after {{ background: rgba(16, 185, 129, 0.88); color: #052014; }}
  .slot-metric {{
    position: absolute;
    bottom: 6px;
    left: 6px;
    right: 6px;
    padding: 4px 6px;
    border-radius: 6px;
    font-size: 0.66rem;
    background: rgba(11, 15, 25, 0.82);
    color: #e2e8f0;
  }}
  .pair-foot {{
    padding: 8px 12px;
    font-size: 0.72rem;
    color: var(--muted);
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    gap: 6px;
  }}
  .pos {{ color: var(--good); font-weight: 700; }}
  .neg {{ color: var(--bad); font-weight: 700; }}
  .modal {{
    display: none;
    position: fixed;
    inset: 0;
    z-index: 90;
    background: rgba(5, 8, 15, 0.95);
    flex-direction: column;
  }}
  .modal.open {{ display: flex; }}
  .modal-top {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 14px;
    border-bottom: 1px solid var(--border);
    gap: 8px;
  }}
  .modal-body {{
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 8px;
    overflow: hidden;
  }}
  .modal-body img {{
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
    border-radius: 8px;
  }}
  .modal-foot {{
    padding: 10px 14px;
    border-top: 1px solid var(--border);
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
    font-size: 0.78rem;
  }}
</style>
</head>
<body>
<header>
  <div class="title-row">
    <h1>🌸 Phase H1 (ADR-100) 파일럿 8종 Before vs After 비교</h1>
    <span style="font-size:0.75rem;color:var(--muted)">표본 N={summary['total_pairs']} ({html.escape(summary['chars_label'])})</span>
  </div>
  <div class="kpi-bar">
    <div class="pill good">After 초회 QC 통과 <b>{summary['after_first_pass_count']}/{summary['total_pairs']} ({summary['after_first_pass_rate']}%)</b></div>
    <div class="pill good">After 최종 QC 통과 <b>{summary['after_final_pass_count']}/{summary['total_pairs']} ({summary['after_final_pass_rate']}%)</b></div>
    <div class="pill">Face Ratio 평균 <b>{summary['before_face_ratio_avg']:.3f} → {summary['after_face_ratio_avg']:.3f}</b></div>
    <div class="pill">Tier 0~2 검열면적 <b>{summary['before_t02_censor_avg']:.2f}% → {summary['after_t02_censor_avg']:.2f}%</b></div>
    <div class="pill">Tier 3 검열면적 <b>{summary['before_t3_censor_avg']:.2f}% → {summary['after_t3_censor_avg']:.2f}%</b></div>
    <div class="pill">평균 소요 <b>{summary['after_duration_avg']:.1f}초</b></div>
  </div>
  <div class="controls">
    <button class="btn active" data-tier="all" onclick="setTier('all')">전체 티어</button>
    <button class="btn" data-tier="0" onclick="setTier('0')">Tier 0 (POV)</button>
    <button class="btn" data-tier="1" onclick="setTier('1')">Tier 1 (크롭)</button>
    <button class="btn" data-tier="2" onclick="setTier('2')">Tier 2 (밀착)</button>
    <button class="btn" data-tier="3" onclick="setTier('3')">Tier 3 (봉사)</button>
    <button class="btn active" data-char="all" onclick="setChar('all')">전체 캐릭</button>
    <button class="btn" data-char="aya" onclick="setChar('aya')">aya</button>
    <button class="btn" data-char="shz" onclick="setChar('shz')">shz</button>
    <button class="btn good active" id="btn-censor-toggle" onclick="toggleOriginMode()">표시: 검열본 (누르면 원본 비교)</button>
  </div>
</header>

<div class="section-wrap">
  <div class="table-wrap">
    <table id="summary-table">
      <thead>
        <tr>
          <th>포즈</th><th>Tier</th><th>Face Ratio (전→후)</th><th>검열면적 % (전→후)</th>
          <th>인원/머리/얼굴 (전→후)</th><th>After 초회통과 / 재시도</th><th>평균시간</th>
        </tr>
      </thead>
      <tbody></tbody>
    </table>
  </div>
</div>

<div class="grid" id="grid"></div>

<div class="modal" id="modal">
  <div class="modal-top">
    <strong id="modal-title" style="font-size:0.88rem"></strong>
    <div style="display:flex;gap:6px">
      <button class="btn good" id="modal-side-btn" onclick="toggleModalSide()">Before ↔ After 전환 (Space)</button>
      <button class="btn" onclick="closeModal()">닫기 (Esc)</button>
    </div>
  </div>
  <div class="modal-body" onclick="toggleModalSide()">
    <img id="modal-img" src="" alt="">
  </div>
  <div class="modal-foot">
    <div id="modal-meta"></div>
    <div style="display:flex;gap:6px">
      <button class="btn" onclick="stepModal(-1)">◀ 이전</button>
      <button class="btn" onclick="stepModal(1)">다음 ▶</button>
    </div>
  </div>
</div>

<script>
const ITEMS = {data_json};
const POSE_ROWS = {pose_json};
const TOKEN = new URLSearchParams(window.location.search).get('token') || '';

function withToken(relPath) {{
  if (!TOKEN) return relPath;
  const sep = relPath.includes('?') ? '&' : '?';
  return relPath + sep + 'token=' + encodeURIComponent(TOKEN);
}}

let curTier = 'all';
let curChar = 'all';
let showOrigin = false;
let filtered = [...ITEMS];
let modalIdx = 0;
let modalSide = 'after';

function setTier(t) {{
  curTier = t;
  document.querySelectorAll('[data-tier]').forEach(b => b.classList.toggle('active', b.dataset.tier === t));
  renderGrid();
}}

function setChar(c) {{
  curChar = c;
  document.querySelectorAll('[data-char]').forEach(b => b.classList.toggle('active', b.dataset.char === c));
  renderGrid();
}}

function toggleOriginMode() {{
  showOrigin = !showOrigin;
  const btn = document.getElementById('btn-censor-toggle');
  btn.textContent = showOrigin ? '표시: 원본(_origin) · 누르면 검열본' : '표시: 검열본 · 누르면 원본(_origin)';
  btn.classList.toggle('active', !showOrigin);
  renderGrid();
  if (document.getElementById('modal').classList.contains('open')) updateModal();
}}

function renderSummaryTable() {{
  const tbody = document.querySelector('#summary-table tbody');
  tbody.innerHTML = POSE_ROWS.map(r => {{
    const fDelta = r.face_ratio_delta >= 0 ? `<span class="pos">+${{r.face_ratio_delta.toFixed(3)}}</span>` : `<span class="neg">${{r.face_ratio_delta.toFixed(3)}}</span>`;
    const cDelta = r.censor_pct_delta <= 0 ? `<span class="pos">${{r.censor_pct_delta.toFixed(2)}}%</span>` : `<span class="neg">+${{r.censor_pct_delta.toFixed(2)}}%</span>`;
    return `<tr>
      <td><b>#${{r.pose_code}}</b> ${{r.label}}</td>
      <td>Tier ${{r.mob_tier}}</td>
      <td>${{r.before_face_ratio.toFixed(3)}} → <b>${{r.after_face_ratio.toFixed(3)}}</b> (${{fDelta}})</td>
      <td>${{r.before_censor_pct.toFixed(2)}}% → <b>${{r.after_censor_pct.toFixed(2)}}%</b> (${{cDelta}})</td>
      <td>${{r.before_persons_avg}}/${{r.before_heads_avg}}/${{r.before_faces_avg}} → <b>${{r.after_persons_avg}}/${{r.after_heads_avg}}/${{r.after_faces_avg}}</b></td>
      <td>${{r.after_first_pass}}/${{r.n}} (리롤 ${{r.after_retries_total}}회)</td>
      <td>${{r.after_duration_avg}}s</td>
    </tr>`;
  }}).join('');
}}

function renderGrid() {{
  filtered = ITEMS.filter(x => (curTier === 'all' || String(x.mob_tier) === curTier) && (curChar === 'all' || x.char_code === curChar));
  const grid = document.getElementById('grid');
  grid.innerHTML = filtered.map((x, idx) => {{
    const bSrc = withToken(showOrigin ? x.paths.before_origin : x.paths.before_censor);
    const aSrc = withToken(showOrigin ? x.paths.after_origin : x.paths.after_censor);
    const fDiff = x.after.face_height_ratio - x.before.face_height_ratio;
    const fSign = fDiff >= 0 ? `+${{fDiff.toFixed(3)}}` : fDiff.toFixed(3);
    const qcTag = x.manifest.qc_passed
      ? (x.manifest.retries === 0 ? '<span class="pos">초회 PASS</span>' : `<span class="pos">PASS (리롤 ${{x.manifest.retries}})</span>`)
      : `<span class="neg">FAIL: ${{x.manifest.qc_reason || ''}}</span>`;
    return `<div class="pair-card">
      <div class="pair-head">
        <div class="pair-title">#${{x.pose_code}} ${{x.label}} · ${{x.char_name}} (${{x.char_code}})</div>
        <span class="tier-tag">Tier ${{x.mob_tier}}</span>
      </div>
      <div class="pair-imgs">
        <div class="img-slot" onclick="openModal(${{idx}}, 'before')">
          <img src="${{bSrc}}" loading="lazy" alt="Before">
          <span class="slot-badge">Before</span>
          <div class="slot-metric">Face ${{x.before.face_height_ratio.toFixed(3)}} · 검열 ${{x.before.censor_area_ratio.toFixed(2)}}%<br>인원 ${{x.before.persons}} · 머리 ${{x.before.heads}} · 얼굴 ${{x.before.faces}} · 손 ${{x.before.hands}}</div>
        </div>
        <div class="img-slot" onclick="openModal(${{idx}}, 'after')">
          <img src="${{aSrc}}" loading="lazy" alt="After">
          <span class="slot-badge after">After (H1)</span>
          <div class="slot-metric">Face ${{x.after.face_height_ratio.toFixed(3)}} · 검열 ${{x.after.censor_area_ratio.toFixed(2)}}%<br>인원 ${{x.after.persons}} · 머리 ${{x.after.heads}} · 얼굴 ${{x.after.faces}} · 손 ${{x.after.hands}}</div>
        </div>
      </div>
      <div class="pair-foot">
        <span>Face Δ: <b class="${{fDiff >= 0 ? 'pos' : 'neg'}}">${{fSign}}</b> · ${{x.manifest.duration_sec}}s</span>
        <span>${{qcTag}}</span>
      </div>
    </div>`;
  }}).join('');
}}

function openModal(idx, side) {{
  modalIdx = idx;
  modalSide = side || 'after';
  document.getElementById('modal').classList.add('open');
  updateModal();
}}

function closeModal() {{
  document.getElementById('modal').classList.remove('open');
}}

function toggleModalSide() {{
  modalSide = modalSide === 'after' ? 'before' : 'after';
  updateModal();
}}

function stepModal(delta) {{
  if (!filtered.length) return;
  modalIdx = (modalIdx + delta + filtered.length) % filtered.length;
  updateModal();
}}

function updateModal() {{
  const item = filtered[modalIdx];
  if (!item) return;
  const isAfter = modalSide === 'after';
  const m = isAfter ? item.after : item.before;
  const rel = isAfter
    ? (showOrigin ? item.paths.after_origin : item.paths.after_censor)
    : (showOrigin ? item.paths.before_origin : item.paths.before_censor);
  document.getElementById('modal-img').src = withToken(rel);
  document.getElementById('modal-title').textContent = `[${{isAfter ? 'After H1' : 'Before'}} · ${{showOrigin ? '원본' : '검열본'}}] #${{item.pose_code}} ${{item.label}} - ${{item.char_name}} (Tier ${{item.mob_tier}})`;
  document.getElementById('modal-side-btn').textContent = isAfter ? 'After 보는 중 → Before 보기 (Space)' : 'Before 보는 중 → After 보기 (Space)';
  document.getElementById('modal-meta').textContent =
    `Face Ratio: ${{m.face_height_ratio.toFixed(3)}} | 검열면적: ${{m.censor_area_ratio.toFixed(2)}}% (${{m.genital_detections}}탐지) | 인원:${{m.persons}} 머리:${{m.heads}} 얼굴:${{m.faces}} 손:${{m.hands}} | 소요:${{item.manifest.duration_sec}}s`;
}}

window.addEventListener('keydown', e => {{
  if (!document.getElementById('modal').classList.contains('open')) return;
  if (e.key === 'Escape') closeModal();
  else if (e.key === 'ArrowLeft') stepModal(-1);
  else if (e.key === 'ArrowRight') stepModal(1);
  else if (e.code === 'Space') {{ e.preventDefault(); toggleModalSide(); }}
}});

renderSummaryTable();
renderGrid();
</script>
</body>
</html>
"""
    out_html.write_text(html_doc, encoding="utf-8")
    return out_html


def evaluate_pilot(
    *,
    out_dir: Path,
    roster: str,
    chars: List[str],
    poses: List[str],
) -> Dict[str, Any]:
    """전체 Before vs After 파일럿 평가를 실행하고 JSON·HTML을 저장합니다."""
    pose_db = default_pose_service.load_pose_db(engine="sdxl", roster=roster)
    media_root = out_dir / "compare_media"
    for sub in ("before_censor", "before_origin", "after_censor", "after_origin"):
        (media_root / sub).mkdir(parents=True, exist_ok=True)

    records: List[Dict[str, Any]] = []
    missing: List[str] = []

    for char_code in chars:
        manifest_path = out_dir / roster / char_code / "_batch_manifest.json"
        if not manifest_path.exists():
            missing.append(f"manifest:{manifest_path}")
            continue

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        char_name = manifest.get("character_name", char_code)
        manifest_items = {str(it["code"]).strip(): it for it in manifest.get("items", []) if "code" in it}

        b_cens_dir = ROOT / "projects" / roster / "assets" / char_code / "02_h_scenes"
        b_orig_dir = ROOT / "projects" / roster / "assets" / f"{char_code}_origin" / "02_h_scenes"
        a_cens_dir = out_dir / roster / char_code / "02_h_scenes"
        a_orig_dir = out_dir / roster / f"{char_code}_origin" / "02_h_scenes"

        for code in poses:
            pose = pose_db.get(code)
            if not pose:
                missing.append(f"pose_db:{code}")
                continue

            b_cens = find_pose_webp(b_cens_dir, char_code, code)
            b_orig = find_pose_webp(b_orig_dir, char_code, code)
            a_cens = find_pose_webp(a_cens_dir, char_code, code)
            a_orig = find_pose_webp(a_orig_dir, char_code, code)
            if not all([b_cens, b_orig, a_cens, a_orig]):
                missing.append(f"{char_code}_{code}")
                continue

            mob_tier = getattr(pose, "mob_tier", None)
            if mob_tier == 0:
                is_solo, is_two, is_off = True, False, True
            elif mob_tier in (1, 2, 3):
                is_solo, is_two, is_off = False, True, True
            else:
                is_solo = pose.is_solo_scene
                is_two = pose.is_two_person
                is_off = pose.is_offscreen_partner

            prompt_text = pose.get_prompt("female")
            is_kiss = "kiss" in prompt_text.lower() or code in ("060", "061", "019")

            before_m = inspect_single_asset(
                b_orig,
                b_cens,
                pose_code=code,
                roster=roster,
                is_solo_scene=is_solo,
                is_two_person=is_two,
                is_offscreen_partner=is_off,
                is_kiss_scene=is_kiss,
                section=pose.section,
                prompt_text=prompt_text,
            )
            after_m = inspect_single_asset(
                a_orig,
                a_cens,
                pose_code=code,
                roster=roster,
                is_solo_scene=is_solo,
                is_two_person=is_two,
                is_offscreen_partner=is_off,
                is_kiss_scene=is_kiss,
                section=pose.section,
                prompt_text=prompt_text,
            )

            fname = a_cens.name
            shutil.copy2(b_cens, media_root / "before_censor" / fname)
            shutil.copy2(b_orig, media_root / "before_origin" / fname)
            shutil.copy2(a_cens, media_root / "after_censor" / fname)
            shutil.copy2(a_orig, media_root / "after_origin" / fname)

            m_item = manifest_items.get(code, {})
            records.append(
                {
                    "char_code": char_code,
                    "char_name": char_name,
                    "pose_code": code,
                    "label": pose.label,
                    "mob_tier": mob_tier,
                    "tier_desc": TIER_LABELS.get(mob_tier, f"Tier {mob_tier}"),
                    "before": before_m,
                    "after": after_m,
                    "manifest": {
                        "success": bool(m_item.get("success", False)),
                        "duration_sec": float(m_item.get("duration_sec", 0.0)),
                        "qc_passed": bool(m_item.get("qc_passed", False)),
                        "qc_reason": m_item.get("qc_reason") or "",
                        "retries": int(m_item.get("retries", 0)),
                        "seed": m_item.get("seed"),
                    },
                    "paths": {
                        "before_censor": f"compare_media/before_censor/{fname}",
                        "before_origin": f"compare_media/before_origin/{fname}",
                        "after_censor": f"compare_media/after_censor/{fname}",
                        "after_origin": f"compare_media/after_origin/{fname}",
                    },
                }
            )

    if missing:
        raise RuntimeError(f"누락된 파일/매니페스트가 있습니다: {missing}")

    pose_rows = build_pose_summary(records, poses)
    t02 = [r for r in records if r["mob_tier"] in (0, 1, 2)]
    t3 = [r for r in records if r["mob_tier"] == 3]
    total_n = len(records)
    first_pass_cnt = sum(1 for r in records if r["manifest"]["qc_passed"] and r["manifest"]["retries"] == 0)
    final_pass_cnt = sum(1 for r in records if r["manifest"]["qc_passed"])

    summary = {
        "total_pairs": total_n,
        "chars": chars,
        "chars_label": ", ".join(chars),
        "poses": poses,
        "after_first_pass_count": first_pass_cnt,
        "after_first_pass_rate": round(first_pass_cnt * 100.0 / max(1, total_n), 1),
        "after_final_pass_count": final_pass_cnt,
        "after_final_pass_rate": round(final_pass_cnt * 100.0 / max(1, total_n), 1),
        "after_total_retries": sum(int(r["manifest"]["retries"]) for r in records),
        "after_duration_avg": _avg([float(r["manifest"]["duration_sec"]) for r in records], 2),
        "before_face_ratio_avg": _avg([r["before"]["face_height_ratio"] for r in records], 4),
        "after_face_ratio_avg": _avg([r["after"]["face_height_ratio"] for r in records], 4),
        "before_t02_censor_avg": _avg([r["before"]["censor_area_ratio"] for r in t02], 3),
        "after_t02_censor_avg": _avg([r["after"]["censor_area_ratio"] for r in t02], 3),
        "before_t3_censor_avg": _avg([r["before"]["censor_area_ratio"] for r in t3], 3),
        "after_t3_censor_avg": _avg([r["after"]["censor_area_ratio"] for r in t3], 3),
        "before_all_censor_avg": _avg([r["before"]["censor_area_ratio"] for r in records], 3),
        "after_all_censor_avg": _avg([r["after"]["censor_area_ratio"] for r in records], 3),
        "before_h1_qc_pass_count": sum(1 for r in records if r["before"]["h1_qc_passed"]),
        "after_h1_qc_pass_count": sum(1 for r in records if r["after"]["h1_qc_passed"]),
    }

    result = {"summary": summary, "pose_rows": pose_rows, "records": records}
    (out_dir / "h1_eval_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    html_path = generate_comparison_html(
        out_dir=out_dir,
        records=records,
        pose_rows=pose_rows,
        summary=summary,
    )
    print(f"[H1-Eval] JSON 저장 완료: {out_dir / 'h1_eval_result.json'}")
    print(f"[H1-Eval] HTML 갤러리 저장 완료: {html_path}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase H1 파일럿 8종 Before vs After 정량 비교 및 갤러리 생성")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "output" / "test_batch_h1_pilot")
    parser.add_argument("--roster", type=str, default="campus")
    parser.add_argument("--chars", type=str, default=",".join(DEFAULT_CHARS))
    parser.add_argument("--poses", type=str, default=",".join(DEFAULT_POSES))
    args = parser.parse_args()

    chars = [c.strip() for c in args.chars.split(",") if c.strip()]
    poses = [p.strip() for p in args.poses.split(",") if p.strip()]
    result = evaluate_pilot(out_dir=args.out_dir, roster=args.roster, chars=chars, poses=poses)
    print(json.dumps({"summary": result["summary"], "pose_rows": result["pose_rows"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
