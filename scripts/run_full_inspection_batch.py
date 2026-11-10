"""
scripts/run_full_inspection_batch.py
설하율(hay, YKN) & 하루(har, Campus) 2인 전역 포즈 일괄 생성 및 모바일 검수 러너

- 화풍 프리셋: C-1 (z-ton 0.85 + fukuro 0.90 + ratatatat74 0.80 + hizuki 0.80)
- 화각 앵커링 & 네거티브 1.25 클램핑 & 조명 충돌 정제 전역 패치 검증
- 땀/물광 동적 주입: 일상(000~059) 땀 배제 vs 로맨스/H씬(060+) 레퍼런스급 땀/물광 텍스처 주입
- 출력: output/inspection_batch/{char_code}/{01_normal | 02_h_scenes}/
- 모바일 뷰어: output/inspection_batch/index.html 실시간 자동 갱신
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from plepa_engine.config import PROJECTS_DIR
from plepa_engine.reporter import get_subfolder_for_code
from plepa_engine.services.character_service import default_character_service
from plepa_engine.services.generation_service import GenerationParams, GenerationService
from plepa_engine.services.pose_service import default_pose_service

INSPECTION_DIR = ROOT / "output" / "inspection_batch"

TARGET_CHARACTERS = [
    {
        "code": "hay",
        "roster": "ykn",
        "name": "설하율 (4녀 / 세미롱 흑발 쿨뷰티 & 타이트 블라우스)",
        "desc": "YKN 흑발 세미롱 & 쿨시크 뷰티 & 풍만한 볼륨감",
    },
    {
        "code": "har",
        "roster": "campus",
        "name": "하루 (여후배 / 가린눈 모브 후배)",
        "desc": "Campus 라이트 브라운 숏보브 & 가린눈 & 숨겨진 거유",
    },
]

# C-1 베이스 화풍 태그
C1_ARTIST_TAG = (
    "(artist:z-ton:0.85), (artist:fukuro_daikokuten:0.90), "
    "(artist:ratatatat74:0.80), (artist:hizuki_yeo:0.80)"
)


def get_contextual_quality_tag(code: str) -> str:
    """포즈 번호 대역에 따른 스마트 땀/물광 텍스처 동적 분리."""
    try:
        c = int(str(code).strip())
    except (ValueError, TypeError):
        return "(glossy skin:1.05)"

    if 0 <= c <= 19:
        # 완전 일상 감정 표현: 땀방울 절대 배제, 매끄럽고 윤기 있는 피부
        return "(glossy skin:1.05), soft shaded skin"
    elif 20 <= c <= 59:
        # 일반 일상 / 이벤트
        return "(glossy skin:1.05)"
    elif 60 <= c <= 79:
        # 로맨스, 애무, 구강 봉사: 상기된 홍조와 은은한 미세 땀
        return "(flushed skin:1.1), (light sweat:1.05), (glossy skin:1.1)"
    else:
        # 080+ 체위 H씬: 레퍼런스 스타일의 굵은 땀방울, 가슴골 땀, 번들거리는 오일/물광
        return "(sweaty skin:1.15), sweat drops, sweat on skin, dripping sweat, flushed body, (glossy skin:1.1)"


def get_active_female_poses(roster: str) -> List[Dict[str, str]]:
    """해당 로스터의 여성 유효 포즈 목록 (정규 000~139 대역, deprecated 및 오토코노코 전용 제외)."""
    pose_db = default_pose_service.load_pose_db(engine="sdxl", roster=roster)
    otoko_range = {f"{i:03d}" for i in range(150, 210)} | {"133", "134", "135"}

    valid = []
    for code, entry in sorted(pose_db.items()):
        if not code.isdigit():
            continue
        c_int = int(code)
        if c_int > 139 or code in otoko_range:
            continue
        if getattr(entry, "status", "") == "deprecated":
            continue
        # 영숫자 000~139 또는 유효 포즈
        label = getattr(entry, "label", code)
        section = getattr(entry, "section", "")
        valid.append({
            "code": code,
            "label": label,
            "section": section,
        })
    return valid


def generate_html_viewer(inspection_dir: Path) -> Path:
    """모바일 친화형 2인 전역 포즈 검수 인터랙티브 HTML 뷰어 및 캔버스 에디터 생성."""
    html_path = inspection_dir / "index.html"

    assets_by_char: Dict[str, List[Dict[str, str]]] = {"hay": [], "har": []}
    for char_info in TARGET_CHARACTERS:
        c_code = char_info["code"]
        char_dir = inspection_dir / c_code
        if not char_dir.exists():
            continue

        for img_p in sorted(char_dir.rglob("*.webp")):
            parts = img_p.stem.split("_")
            p_code = parts[1] if len(parts) > 1 else ""
            label = parts[2] if len(parts) > 2 else ""
            subfolder = img_p.parent.name
            mtime_int = int(img_p.stat().st_mtime)
            rel_path = f"{c_code}/{subfolder}/{img_p.name}?t={mtime_int}"

            assets_by_char[c_code].append({
                "code": p_code,
                "label": label or p_code,
                "path": rel_path,
                "subfolder": subfolder,
                "size_kb": f"{img_p.stat().st_size // 1024} KB",
            })

    total_count = len(assets_by_char["hay"]) + len(assets_by_char["har"])
    hay_count = len(assets_by_char["hay"])
    har_count = len(assets_by_char["har"])

    cards_html_hay = ""
    for item in assets_by_char["hay"]:
        tag_badge = '<span class="badge normal">일상</span>' if item["subfolder"] == "01_normal" else '<span class="badge hscene">H씬</span>'
        cards_html_hay += f"""
        <div class="card" data-subfolder="{item['subfolder']}">
          <div class="img-box" onclick="openLightbox('{item['path']}')">
            <img src="{item['path']}" loading="lazy" alt="#{item['code']}">
            <div class="code-badge">#{item['code']}</div>
          </div>
          <div class="meta">
            <div class="label-row">{tag_badge} <span class="label-text">{item['label']}</span></div>
            <div class="sub-info">{item['size_kb']}</div>
            <button class="retouch-btn" onclick="openRetouch(event, '{item['path']}', '{item['code']}', '{item['label']}')">✏️ 터치 덧칠</button>
          </div>
        </div>
        """

    cards_html_har = ""
    for item in assets_by_char["har"]:
        tag_badge = '<span class="badge normal">일상</span>' if item["subfolder"] == "01_normal" else '<span class="badge hscene">H씬</span>'
        cards_html_har += f"""
        <div class="card" data-subfolder="{item['subfolder']}">
          <div class="img-box" onclick="openLightbox('{item['path']}')">
            <img src="{item['path']}" loading="lazy" alt="#{item['code']}">
            <div class="code-badge">#{item['code']}</div>
          </div>
          <div class="meta">
            <div class="label-row">{tag_badge} <span class="label-text">{item['label']}</span></div>
            <div class="sub-info">{item['size_kb']}</div>
            <button class="retouch-btn" onclick="openRetouch(event, '{item['path']}', '{item['code']}', '{item['label']}')">✏️ 터치 덧칠</button>
          </div>
        </div>
        """

    raw_template = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<title>PLEPA 전역 포즈 품질 검수 갤러리</title>
<style>
  :root {
    --bg: #090c15;
    --card-bg: #121626;
    --border: #212840;
    --text: #f1f5f9;
    --text-muted: #94a3b8;
    --accent: #38bdf8;
    --h-accent: #f43f5e;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Pretendard", "Segoe UI", Roboto, sans-serif;
    padding-bottom: 80px;
  }
  header {
    background: rgba(18, 22, 38, 0.95);
    border-bottom: 1px solid var(--border);
    padding: 14px 16px;
    position: sticky;
    top: 0;
    z-index: 100;
    backdrop-filter: blur(10px);
  }
  .title-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  h1 {
    font-size: 1.1rem;
    font-weight: 800;
    color: #fff;
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .counter {
    background: #0369a1;
    color: #e0f2fe;
    font-size: 0.72rem;
    padding: 2px 8px;
    border-radius: 9999px;
    font-weight: 700;
  }
  .subtitle {
    font-size: 0.75rem;
    color: var(--text-muted);
    margin-top: 4px;
  }
  .tabs {
    display: flex;
    background: #14192b;
    border-bottom: 1px solid var(--border);
    padding: 6px 12px;
    gap: 8px;
  }
  .tab-btn {
    flex: 1;
    background: #1e263d;
    border: 1px solid var(--border);
    color: var(--text-muted);
    padding: 8px 10px;
    font-size: 0.82rem;
    font-weight: 700;
    border-radius: 8px;
    cursor: pointer;
    text-align: center;
  }
  .tab-btn.active {
    background: #0284c7;
    color: #fff;
    border-color: #38bdf8;
  }
  .sub-filter {
    display: flex;
    gap: 6px;
    padding: 8px 12px;
    background: #0b0e1a;
    border-bottom: 1px solid var(--border);
  }
  .filter-btn {
    background: #182036;
    border: 1px solid var(--border);
    color: #cbd5e1;
    font-size: 0.72rem;
    padding: 4px 10px;
    border-radius: 6px;
    cursor: pointer;
  }
  .filter-btn.active {
    background: #334155;
    color: #38bdf8;
    border-color: #38bdf8;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 8px;
    padding: 10px;
  }
  @media (min-width: 600px) {
    .grid {
      grid-template-columns: repeat(3, 1fr);
      gap: 12px;
      padding: 14px;
    }
  }
  @media (min-width: 900px) {
    .grid {
      grid-template-columns: repeat(4, 1fr);
      gap: 16px;
    }
  }
  .card {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 10px;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }
  .img-box {
    position: relative;
    width: 100%;
    aspect-ratio: 832 / 1216;
    background: #000;
    cursor: pointer;
  }
  .img-box img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }
  .code-badge {
    position: absolute;
    top: 6px;
    left: 6px;
    background: rgba(0, 0, 0, 0.75);
    color: #38bdf8;
    font-size: 0.7rem;
    font-weight: 800;
    padding: 2px 6px;
    border-radius: 4px;
    border: 1px solid rgba(56, 189, 248, 0.4);
  }
  .meta {
    padding: 8px 10px;
  }
  .label-row {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 0.78rem;
    font-weight: 700;
    color: #fff;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .badge {
    font-size: 0.65rem;
    padding: 1px 5px;
    border-radius: 4px;
    font-weight: 700;
    white-space: nowrap;
  }
  .badge.normal { background: #065f46; color: #a7f3d0; }
  .badge.hscene { background: #881337; color: #fecdd3; }
  .label-text { overflow: hidden; text-overflow: ellipsis; }
  .sub-info {
    font-size: 0.68rem;
    color: var(--text-muted);
    margin-top: 3px;
  }
  .retouch-btn {
    margin-top: 6px;
    width: 100%;
    background: #1e293b;
    border: 1px solid #334155;
    color: #38bdf8;
    font-size: 0.72rem;
    font-weight: 700;
    padding: 5px 0;
    border-radius: 6px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 4px;
    transition: all 0.15s ease;
  }
  .retouch-btn:active {
    background: #0284c7;
    color: #fff;
  }
  /* Retouch Modal */
  .retouch-modal {
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.96);
    z-index: 2000;
    flex-direction: column;
    overflow: hidden;
  }
  .retouch-modal.active { display: flex; }
  .modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 14px;
    background: #0f172a;
    border-bottom: 1px solid #1e293b;
  }
  .modal-title {
    font-size: 0.88rem;
    font-weight: 800;
    color: #f8fafc;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .close-btn {
    background: #334155;
    color: #cbd5e1;
    border: none;
    border-radius: 6px;
    padding: 6px 12px;
    font-weight: 700;
    font-size: 0.8rem;
    cursor: pointer;
  }
  .canvas-container {
    flex: 1;
    position: relative;
    display: flex;
    justify-content: center;
    align-items: center;
    background: #000;
    overflow: hidden;
    touch-action: none;
  }
  #editor-canvas {
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
    touch-action: none;
    box-shadow: 0 0 20px rgba(0,0,0,0.8);
  }
  .modal-toolbar {
    background: #0f172a;
    border-top: 1px solid #1e293b;
    padding: 8px 12px;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }
  .tool-group {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .tool-btn {
    background: #1e293b;
    border: 1px solid #334155;
    color: #cbd5e1;
    padding: 6px 10px;
    border-radius: 6px;
    font-size: 0.76rem;
    font-weight: 700;
    cursor: pointer;
  }
  .tool-btn.active {
    background: #0284c7;
    color: #fff;
    border-color: #38bdf8;
  }
  .save-btn {
    background: #059669;
    border: 1px solid #10b981;
    color: #fff;
    padding: 8px 16px;
    border-radius: 6px;
    font-size: 0.82rem;
    font-weight: 800;
    cursor: pointer;
    box-shadow: 0 0 10px rgba(16, 185, 129, 0.3);
  }
  .save-btn:active {
    background: #047857;
  }
  .toast {
    position: fixed;
    top: 20px;
    left: 50%;
    transform: translateX(-50%);
    background: #10b981;
    color: #fff;
    padding: 10px 20px;
    border-radius: 9999px;
    font-weight: 800;
    font-size: 0.85rem;
    z-index: 3000;
    display: none;
    box-shadow: 0 4px 15px rgba(0,0,0,0.5);
  }
  .lightbox {
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.95);
    z-index: 1000;
    justify-content: center;
    align-items: center;
    padding: 10px;
  }
  .lightbox.active { display: flex; }
  .lightbox img {
    max-width: 100%;
    max-height: 94vh;
    object-fit: contain;
    border-radius: 6px;
  }
  .empty-msg {
    grid-column: 1 / -1;
    text-align: center;
    padding: 40px 20px;
    color: var(--text-muted);
    font-size: 0.85rem;
  }
</style>
</head>
<body>

<header>
  <div class="title-row">
    <h1>🔬 전역 포즈 품질 검수 갤러리</h1>
    <div class="counter" id="total-badge">생성 완료: {{TOTAL_COUNT}}장</div>
  </div>
  <div class="subtitle">C-1 화풍 + 화각 앵커링 + 콤팩트 언더마스킹 + 인라인 터치 덧칠</div>
</header>

<div class="tabs">
  <button class="tab-btn active" onclick="switchChar('hay')">설하율 (hay: {{HAY_COUNT}}장)</button>
  <button class="tab-btn" onclick="switchChar('har')">하루 (har: {{HAR_COUNT}}장)</button>
</div>

<div class="sub-filter">
  <button class="filter-btn active" onclick="filterFolder('all')">전체 보기</button>
  <button class="filter-btn" onclick="filterFolder('01_normal')">01 일상/감정 (땀 배제)</button>
  <button class="filter-btn" onclick="filterFolder('02_h_scenes')">02 로맨스/H씬 (땀 활성)</button>
</div>

<div id="grid-hay" class="grid">
  {{CARDS_HAY}}
</div>

<div id="grid-har" class="grid" style="display: none;">
  {{CARDS_HAR}}
</div>

<div id="lightbox" class="lightbox" onclick="closeLightbox()">
  <img id="lightbox-img" src="" alt="Enlarged">
</div>

<div id="retouch-modal" class="retouch-modal">
  <div class="modal-header">
    <div class="modal-title" id="modal-title">✏️ 덧칠 에디터</div>
    <button class="close-btn" onclick="closeRetouch()">닫기 ✕</button>
  </div>
  <div class="canvas-container" id="canvas-container">
    <canvas id="editor-canvas"></canvas>
  </div>
  <div class="modal-toolbar">
    <div class="tool-group">
      <button class="tool-btn active" id="btn-brush" onclick="setTool('brush')">🖌️ 덧칠</button>
      <button class="tool-btn" id="btn-eraser" onclick="setTool('eraser')">🧹 지우개</button>
      <button class="tool-btn" onclick="undoStroke()">↩️ 취소</button>
      <button class="tool-btn" onclick="resetCanvas()">🔄 리셋</button>
    </div>
    <div class="tool-group">
      <span style="font-size:0.75rem; color:#94a3b8;">크기:</span>
      <input type="range" id="brush-size" min="6" max="70" value="28" style="width:75px;" oninput="updateBrushSize(this.value)">
      <span id="brush-size-val" style="font-size:0.72rem; color:#38bdf8; width:22px;">28</span>
    </div>
    <button class="save-btn" id="btn-save" onclick="saveRetouch()">💾 저장 완료</button>
  </div>
</div>

<div id="toast" class="toast">저장 완료!</div>

<script>
  let currentChar = 'hay';
  let currentFilter = 'all';

  function switchChar(charId) {
    currentChar = charId;
    document.querySelectorAll('.tab-btn').forEach((btn, idx) => {
      btn.classList.toggle('active', (charId === 'hay' && idx === 0) || (charId === 'har' && idx === 1));
    });
    document.getElementById('grid-hay').style.display = charId === 'hay' ? 'grid' : 'none';
    document.getElementById('grid-har').style.display = charId === 'har' ? 'grid' : 'none';
    applySubFilter();
  }

  function filterFolder(folder) {
    currentFilter = folder;
    document.querySelectorAll('.filter-btn').forEach(btn => {
      btn.classList.toggle('active', btn.textContent.includes(folder === 'all' ? '전체' : (folder === '01_normal' ? '01' : '02')));
    });
    applySubFilter();
  }

  function applySubFilter() {
    const activeGrid = document.getElementById('grid-' + currentChar);
    const cards = activeGrid.querySelectorAll('.card');
    cards.forEach(card => {
      if (currentFilter === 'all' || card.dataset.subfolder === currentFilter) {
        card.style.display = 'flex';
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

  /* Retouch Canvas Logic */
  let currentImgPath = '';
  let currentImgObj = null;
  let canvas = null;
  let ctx = null;
  let isDrawing = false;
  let currentTool = 'brush';
  let brushRadius = 28;
  let undoStack = [];

  function openRetouch(e, path, code, label) {
    if (e) e.stopPropagation();
    currentImgPath = path;
    document.getElementById('modal-title').textContent = `#${code} ${label} 덧칠 편집`;
    const modal = document.getElementById('retouch-modal');
    modal.classList.add('active');

    canvas = document.getElementById('editor-canvas');
    ctx = canvas.getContext('2d');
    undoStack = [];

    currentImgObj = new Image();
    currentImgObj.crossOrigin = 'anonymous';
    currentImgObj.onload = function() {
      canvas.width = currentImgObj.naturalWidth || 832;
      canvas.height = currentImgObj.naturalHeight || 1216;
      ctx.drawImage(currentImgObj, 0, 0);
      saveState();
    };
    currentImgObj.src = path + (path.includes('?') ? '&' : '?') + 't=' + Date.now();
  }

  function closeRetouch() {
    document.getElementById('retouch-modal').classList.remove('active');
  }

  function setTool(tool) {
    currentTool = tool;
    document.getElementById('btn-brush').classList.toggle('active', tool === 'brush');
    document.getElementById('btn-eraser').classList.toggle('active', tool === 'eraser');
  }

  function updateBrushSize(val) {
    brushRadius = parseInt(val);
    document.getElementById('brush-size-val').textContent = val;
  }

  function saveState() {
    if (undoStack.length >= 15) undoStack.shift();
    undoStack.push(ctx.getImageData(0, 0, canvas.width, canvas.height));
  }

  function undoStroke() {
    if (undoStack.length > 1) {
      undoStack.pop();
      const prev = undoStack[undoStack.length - 1];
      ctx.putImageData(prev, 0, 0);
    }
  }

  function resetCanvas() {
    if (currentImgObj) {
      ctx.drawImage(currentImgObj, 0, 0);
      saveState();
    }
  }

  function getCanvasCoords(e) {
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    let clientX = e.clientX;
    let clientY = e.clientY;
    if (e.touches && e.touches.length > 0) {
      clientX = e.touches[0].clientX;
      clientY = e.touches[0].clientY;
    }
    return {
      x: (clientX - rect.left) * scaleX,
      y: (clientY - rect.top) * scaleY
    };
  }

  function startDraw(e) {
    e.preventDefault();
    isDrawing = true;
    const pos = getCanvasCoords(e);
    drawCircle(pos.x, pos.y);
  }

  function moveDraw(e) {
    if (!isDrawing) return;
    e.preventDefault();
    const pos = getCanvasCoords(e);
    drawCircle(pos.x, pos.y);
  }

  function stopDraw(e) {
    if (isDrawing) {
      isDrawing = false;
      saveState();
    }
  }

  function drawCircle(x, y) {
    ctx.save();
    if (currentTool === 'brush') {
      const grad = ctx.createRadialGradient(x, y, brushRadius * 0.4, x, y, brushRadius);
      grad.addColorStop(0, 'rgba(255, 255, 255, 1.0)');
      grad.addColorStop(0.85, 'rgba(255, 255, 255, 0.95)');
      grad.addColorStop(1, 'rgba(255, 255, 255, 0.0)');
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(x, y, brushRadius, 0, Math.PI * 2);
      ctx.fill();
    } else {
      if (currentImgObj) {
        ctx.save();
        ctx.beginPath();
        ctx.arc(x, y, brushRadius, 0, Math.PI * 2);
        ctx.clip();
        ctx.drawImage(currentImgObj, 0, 0);
        ctx.restore();
      }
    }
    ctx.restore();
  }

  window.addEventListener('DOMContentLoaded', () => {
    const cv = document.getElementById('editor-canvas');
    cv.addEventListener('mousedown', startDraw);
    cv.addEventListener('mousemove', moveDraw);
    window.addEventListener('mouseup', stopDraw);

    cv.addEventListener('touchstart', startDraw, { passive: false });
    cv.addEventListener('touchmove', moveDraw, { passive: false });
    window.addEventListener('touchend', stopDraw);
  });

  async function saveRetouch() {
    const saveBtn = document.getElementById('btn-save');
    saveBtn.disabled = true;
    saveBtn.textContent = '⏳ 저장 중...';

    try {
      const dataUrl = canvas.toDataURL('image/webp', 0.95);
      let cleanRel = currentImgPath.split('?')[0];
      cleanRel = cleanRel.replace(/^\/?inspect\//, '').replace(/^\//, '');

      const resp = await fetch('/api/retouch_censor', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_path: cleanRel,
          image_base64: dataUrl
        })
      });
      const result = await resp.json();
      if (result.success) {
        showToast('✅ 저장 완료!');
        const t = Date.now();
        document.querySelectorAll(`img[src*="${currentImgPath.split('?')[0]}"]`).forEach(img => {
          img.src = currentImgPath.split('?')[0] + '?t=' + t;
        });
        setTimeout(() => {
          closeRetouch();
          saveBtn.disabled = false;
          saveBtn.textContent = '💾 저장 완료';
        }, 600);
      } else {
        alert('저장 실패: ' + (result.error || '알 수 없는 오류'));
        saveBtn.disabled = false;
        saveBtn.textContent = '💾 저장 완료';
      }
    } catch (err) {
      alert('통신 오류: ' + err);
      saveBtn.disabled = false;
      saveBtn.textContent = '💾 저장 완료';
    }
  }

  function showToast(msg) {
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.style.display = 'block';
    setTimeout(() => { t.style.display = 'none'; }, 2000);
  }
</script>

</body>
</html>
"""

    rendered_html = (
        raw_template
        .replace("{{TOTAL_COUNT}}", str(total_count))
        .replace("{{HAY_COUNT}}", str(hay_count))
        .replace("{{HAR_COUNT}}", str(har_count))
        .replace("{{CARDS_HAY}}", cards_html_hay or '<div class="empty-msg">아직 생성된 이미지가 없습니다.</div>')
        .replace("{{CARDS_HAR}}", cards_html_har or '<div class="empty-msg">아직 생성된 이미지가 없습니다.</div>')
    )

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(rendered_html)
    return html_path


def run_inspection_batch(limit_per_char: Optional[int] = None, dry_run: bool = False):
    """2명 전역 포즈 일괄 생성 실행."""
    INSPECTION_DIR.mkdir(parents=True, exist_ok=True)
    for ch in TARGET_CHARACTERS:
        (INSPECTION_DIR / ch["code"] / "01_normal").mkdir(parents=True, exist_ok=True)
        (INSPECTION_DIR / ch["code"] / "02_h_scenes").mkdir(parents=True, exist_ok=True)

    generate_html_viewer(INSPECTION_DIR)

    print("=" * 80)
    print(" [플에파 2인 전역 포즈 품질 검수 일괄 생성 러너]")
    print(f" 대상 캐릭터: 설하율(hay, YKN) & 하루(har, Campus)")
    print(f" 화풍 프리셋: C-1 (z-ton 0.85 + fukuro 0.90 + ratatatat74 0.80 + hizuki 0.80)")
    print(f" 저장 디렉토리: {INSPECTION_DIR}")
    print("=" * 80)

    service = GenerationService()
    total_start = time.time()
    grand_success = 0
    grand_fail = 0

    for ch_idx, ch in enumerate(TARGET_CHARACTERS, 1):
        c_code = ch["code"]
        roster = ch["roster"]
        print(f"\n▶ [{ch_idx}/2] 캐릭터: {ch['name']} ({c_code}, {roster})")

        poses = get_active_female_poses(roster)
        if limit_per_char:
            poses = poses[:limit_per_char]

        print(f"   검수 대상 유효 포즈: 총 {len(poses)}종")

        char_success = 0
        char_fail = 0

        for p_idx, pos_info in enumerate(poses, 1):
            p_code = pos_info["code"]
            p_label = pos_info["label"]
            subfolder = get_subfolder_for_code(p_code)

            target_filename = f"{c_code}_{p_code}_{p_label}.webp"
            final_path = INSPECTION_DIR / c_code / subfolder / target_filename

            if final_path.exists() and final_path.stat().st_size > 5000:
                print(f"  [{p_idx}/{len(poses)}] [스킵 완료됨] #{p_code} {p_label}")
                char_success += 1
                grand_success += 1
                continue

            # 포즈 대역별 스마트 땀/물광 품질 태그 결합
            quality_tag = get_contextual_quality_tag(p_code)
            combined_custom_pos = f"{C1_ARTIST_TAG}, {quality_tag}"

            print(f"  [{p_idx}/{len(poses)}] [생성 중...] #{p_code} {p_label} ({subfolder})")

            if dry_run:
                print(f"     [DRY-RUN] custom_pos: {combined_custom_pos[:60]}...")
                char_success += 1
                grand_success += 1
                continue

            params = GenerationParams(
                character_expr=c_code,
                pose_expr=p_code,
                roster=roster,
                custom_pos=combined_custom_pos,
                ckpt_tag=f"inspect_{c_code}_{p_code}",
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
                        char_success += 1
                        grand_success += 1
                        # 5장마다 HTML 뷰어 갱신
                        if grand_success % 5 == 0:
                            generate_html_viewer(INSPECTION_DIR)
                    else:
                        print("     ❌ 생성 이미지 파일 미발견")
                        char_fail += 1
                        grand_fail += 1
                else:
                    err = res[0].error_message if res else "Unknown"
                    print(f"     ❌ 생성 실패: {err}")
                    char_fail += 1
                    grand_fail += 1
            except Exception as e:
                print(f"     ❌ 예외 발생: {e}")
                char_fail += 1
                grand_fail += 1

        print(f"  ▶ {c_code} 완료: 성공 {char_success}개 / 실패 {char_fail}개")
        generate_html_viewer(INSPECTION_DIR)

    total_dur = time.time() - total_start
    print("\n" + "=" * 80)
    print(f" [검수 배치 최종 완료 보고서]")
    print(f" 총 생성 결과: 성공 {grand_success}개 / 실패 {grand_fail}개 (총 소요 {total_dur:.1f}초)")
    print(f" 최종 HTML 뷰어: {INSPECTION_DIR / 'index.html'}")
    print("=" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="2인 전역 포즈 품질 검수 러너")
    parser.add_argument("--limit", type=int, default=None, help="캐릭터당 생성할 최대 포즈 수 (테스트용)")
    parser.add_argument("--dry-run", action="store_true", help="실제 ComfyUI 생성 없이 파라미터 및 대상 점검")
    args = parser.parse_args()

    run_inspection_batch(limit_per_char=args.limit, dry_run=args.dry_run)
