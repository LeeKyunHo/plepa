# -*- coding: utf-8 -*-
"""
scripts/generate_inspection_viewer.py
output/inspection_batch/ 디렉토리 내의 모든 캐릭터(aya, har, kao, mai, shz, yur, hay 등)를
동적으로 탐색하여 모바일 친화형 상단 고정 탭 네비게이션, 터치 덧칠 에디터, 무검열 원본 복원 및 실시간 리롤 뷰어를 생성합니다.
- 포즈 라벨은 단일 진실 공급원(sdxl_pose_database.json)에서 실시간 조회하여 최신 표준 명칭을 렌더링합니다.
- UI 상단 고정(Sticky Header Wrap)으로 스크롤 중에도 언제든지 캐릭터 탭 전환, 새로고침 및 최상단 이동 가능.
- 각 카드별 우상단 "🎲 리롤(재생성)" 원클릭 버튼 구비.
- 각 카드별 하단 "✏️ 덧칠" 및 "🔄 원본(오리지널 복원)" 2-Button 액션 행 구비.
"""

import html
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from plepa_engine.config import DEFAULT_ROSTER
from plepa_engine.services.character_service import default_character_service
from plepa_engine.services.pose_service import default_pose_service

INSPECT_DIR = ROOT / "output" / "inspection_batch"

CHAR_DISPLAY_NAMES = {
    "aya": "아야 (Aya)",
    "har": "하루 (Haru)",
    "kao": "카오 (Kaoruko)",
    "mai": "마이 (Mai)",
    "shz": "시즈 (Shizuku)",
    "yur": "유리 (Yuriko)",
    "hay": "설하율 (Hayool)",
}


def _discover_character_meta() -> tuple[Dict[str, str], Dict[str, str]]:
    display_map: Dict[str, str] = dict(CHAR_DISPLAY_NAMES)
    roster_map: Dict[str, str] = {}
    try:
        for r_name in default_character_service.list_rosters():
            for _, ch, _ in default_character_service.list_characters(r_name):
                code = str(getattr(ch, "prefix", "") or "").lower()
                if not code:
                    continue
                roster_map.setdefault(code, r_name)
                if code not in display_map:
                    char_name = str(getattr(ch, "name", "") or "").strip()
                    display_map[code] = f"{char_name} ({code})" if char_name and char_name != code else code.upper()
    except Exception:
        pass
    return display_map, roster_map


def generate_inspection_html(
    inspection_dir: Path = INSPECT_DIR,
    roster: Optional[str] = None,
) -> Path:
    html_path = inspection_dir / "index.html"
    target_roster = roster or DEFAULT_ROSTER
    char_display_map, char_roster_map = _discover_character_meta()

    # 최신 포즈 DB 로드 (단일 진실 공급원, 로스터별 동적 조회)
    pose_dbs: Dict[str, Dict] = {}

    def _get_pose_db(r_name: str) -> Dict:
        if r_name not in pose_dbs:
            pose_dbs[r_name] = default_pose_service.load_pose_db(engine="sdxl", roster=r_name)
        return pose_dbs[r_name]

    default_pose_db = _get_pose_db(target_roster)

    found_chars: List[str] = []
    assets_by_char: Dict[str, List[Dict[str, str]]] = {}

    if inspection_dir.exists():
        for d in sorted(inspection_dir.iterdir()):
            if d.is_dir() and not d.name.startswith((".", "_", "ground_truth")):
                webp_files = list(d.rglob("*.webp"))
                if webp_files:
                    c_code = d.name
                    found_chars.append(c_code)
                    assets_by_char[c_code] = []
                    c_roster = roster if roster else char_roster_map.get(c_code.lower(), target_roster)
                    pose_db = _get_pose_db(c_roster) or default_pose_db

                    for img_p in sorted(webp_files):
                        parts = img_p.stem.split("_")
                        p_code = parts[1] if len(parts) > 1 else ""
                        # 1순위: DB 최신 라벨, 2순위: 파일명 라벨
                        db_entry = pose_db.get(p_code) or pose_db.get(p_code.upper()) or default_pose_db.get(p_code)
                        if db_entry and getattr(db_entry, "label", None):
                            label = db_entry.label
                        else:
                            label = parts[2] if len(parts) > 2 else p_code

                        subfolder = img_p.parent.name
                        mtime_int = int(img_p.stat().st_mtime)
                        rel_path = f"{c_code}/{subfolder}/{img_p.name}?t={mtime_int}"

                        assets_by_char[c_code].append({
                            "code": p_code,
                            "label": label,
                            "path": rel_path,
                            "subfolder": subfolder,
                            "size_kb": f"{img_p.stat().st_size // 1024} KB",
                        })

    if not found_chars:
        fallback_char = "aya"
        try:
            chars = default_character_service.list_characters(target_roster)
            if chars:
                fallback_char = str(getattr(chars[0][1], "prefix", "aya") or "aya").lower()
        except Exception:
            pass
        found_chars = [fallback_char]
        assets_by_char[fallback_char] = []

    first_char = found_chars[0]
    first_char_js = json.dumps(first_char, ensure_ascii=False).replace("</", "<\\/")
    total_count = sum(len(items) for items in assets_by_char.values())

    # 동적 탭 버튼 생성
    tabs_html_list = []
    for idx, c_code in enumerate(found_chars):
        c_name = char_display_map.get(c_code.lower(), c_code.upper())
        c_count = len(assets_by_char[c_code])
        active_cls = " active" if idx == 0 else ""
        safe_char = html.escape(c_code, quote=True)
        safe_name = html.escape(c_name, quote=True)
        tabs_html_list.append(
            f'<button class="tab-btn{active_cls}" data-char="{safe_char}" onclick="switchChar(this.dataset.char)">{safe_name} ({c_count}장)</button>'
        )
    tabs_html = "\n  ".join(tabs_html_list)

    # 각 캐릭터별 그리드 생성
    grids_html_list = []
    for idx, c_code in enumerate(found_chars):
        display_style = "grid" if idx == 0 else "none"
        safe_char = html.escape(c_code, quote=True)
        cards_html_list = []
        for item in assets_by_char[c_code]:
            tag_badge = '<span class="badge normal">일상</span>' if item["subfolder"] == "01_normal" else '<span class="badge hscene">H씬</span>'
            safe_sub = html.escape(item["subfolder"], quote=True)
            safe_path = html.escape(item["path"], quote=True)
            safe_code = html.escape(item["code"], quote=True)
            safe_label = html.escape(item["label"], quote=True)
            safe_size = html.escape(item["size_kb"], quote=True)
            cards_html_list.append(f"""
            <div class="card" data-subfolder="{safe_sub}">
              <div class="img-box" data-path="{safe_path}" onclick="openLightbox(this.dataset.path)">
                <img src="{safe_path}" loading="lazy" alt="#{safe_code}">
                <div class="code-badge">#{safe_code}</div>
                <button class="reroll-badge-btn" id="reroll-btn-{safe_char}-{safe_code}" data-path="{safe_path}" data-char="{safe_char}" data-pose="{safe_code}" data-label="{safe_label}" onclick="enqueueReroll(event, this.dataset.path, this.dataset.char, this.dataset.pose, this.dataset.label)" title="새로운 무작위 시드로 리롤">🎲 리롤</button>
              </div>
              <div class="meta">
                <div class="label-row">{tag_badge} <span class="label-text">#{safe_code} {safe_label}</span></div>
                <div class="sub-info">{safe_size}</div>
                <div class="card-btn-row">
                  <button class="action-btn retouch-btn" data-path="{safe_path}" data-pose="{safe_code}" data-label="{safe_label}" onclick="openRetouch(event, this.dataset.path, this.dataset.pose, this.dataset.label)">✏️ 덧칠</button>
                  <button class="action-btn recensor-btn" data-path="{safe_path}" data-char="{safe_char}" data-pose="{safe_code}" data-label="{safe_label}" onclick="reapplyCensor(event, this.dataset.path, this.dataset.char, this.dataset.pose, this.dataset.label)">⚡ 재검열</button>
                  <button class="action-btn origin-btn" data-path="{safe_path}" data-pose="{safe_code}" data-label="{safe_label}" onclick="restoreOrigin(event, this.dataset.path, this.dataset.pose, this.dataset.label)">🔄 원본</button>
                </div>
              </div>
            </div>
            """)
        cards_html = "\n".join(cards_html_list) if cards_html_list else '<div class="empty-msg">아직 생성된 이미지가 없습니다.</div>'
        grids_html_list.append(f'<div id="grid-{safe_char}" class="grid" style="display: {display_style};">\n{cards_html}\n</div>')
    grids_html = "\n\n".join(grids_html_list)

    html_content = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<title>PLEPA {html.escape(target_roster.upper())} 포즈 검수 갤러리</title>
<style>
  :root {{
    --bg: #090c15;
    --card-bg: #121626;
    --border: #212840;
    --text: #f1f5f9;
    --text-muted: #94a3b8;
    --accent: #38bdf8;
    --h-accent: #f43f5e;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Pretendard", "Segoe UI", Roboto, sans-serif;
    padding-bottom: 90px;
  }}

  /* 상단 고정 통합 네비게이션 래퍼 */
  .sticky-top-container {{
    position: sticky;
    top: 0;
    z-index: 1000;
    background: rgba(9, 12, 21, 0.96);
    backdrop-filter: blur(12px);
    border-bottom: 1px solid var(--border);
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.55);
  }}

  header {{
    padding: 10px 14px 6px;
  }}
  .title-row {{
    display: flex;
    justify-content: space-between;
    align-items: center;
  }}
  h1 {{
    font-size: 1.02rem;
    font-weight: 800;
    color: #fff;
    display: flex;
    align-items: center;
    gap: 6px;
  }}
  .header-actions {{
    display: flex;
    align-items: center;
    gap: 6px;
  }}
  .queue-status-pill {{
    background: rgba(245, 158, 11, 0.16);
    border: 1px solid rgba(245, 158, 11, 0.75);
    color: #fbbf24;
    font-size: 0.72rem;
    font-weight: 700;
    padding: 3px 8px;
    border-radius: 9999px;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    white-space: nowrap;
    cursor: pointer;
    animation: pulse-queue 1.8s infinite;
  }}
  @keyframes pulse-queue {{
    0% {{ box-shadow: 0 0 0 0 rgba(245, 158, 11, 0.45); }}
    70% {{ box-shadow: 0 0 0 5px rgba(245, 158, 11, 0); }}
    100% {{ box-shadow: 0 0 0 0 rgba(245, 158, 11, 0); }}
  }}
  .queue-spin {{
    display: inline-block;
    animation: spin-slow 3s linear infinite;
  }}
  @keyframes spin-slow {{
    100% {{ transform: rotate(360deg); }}
  }}
  .top-btn {{
    background: #1e293b;
    border: 1px solid rgba(56, 189, 248, 0.5);
    color: #38bdf8;
    font-size: 0.72rem;
    font-weight: 700;
    padding: 4px 9px;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.15s ease;
    display: inline-flex;
    align-items: center;
    gap: 3px;
  }}
  .top-btn:active {{
    background: #0284c7;
    color: #fff;
  }}
  .refresh-btn {{
    border-color: rgba(52, 211, 153, 0.6);
    color: #34d399;
  }}
  .refresh-btn:active {{
    background: #059669;
    color: #fff;
  }}
  .counter {{
    background: #0369a1;
    color: #e0f2fe;
    font-size: 0.68rem;
    padding: 2px 7px;
    border-radius: 9999px;
    font-weight: 700;
    white-space: nowrap;
  }}
  .subtitle {{
    font-size: 0.72rem;
    color: var(--text-muted);
    margin-top: 2px;
  }}

  /* 캐릭터 탭 바 (스크롤 가능 & 상단 고정) */
  .tabs {{
    display: flex;
    padding: 6px 10px;
    gap: 6px;
    overflow-x: auto;
    white-space: nowrap;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: none;
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  }}
  .tabs::-webkit-scrollbar {{ display: none; }}
  .tab-btn {{
    flex: 0 0 auto;
    background: #1e263d;
    border: 1px solid var(--border);
    color: var(--text-muted);
    padding: 6px 12px;
    font-size: 0.8rem;
    font-weight: 700;
    border-radius: 8px;
    cursor: pointer;
    text-align: center;
    transition: all 0.15s ease;
  }}
  .tab-btn.active {{
    background: #0284c7;
    color: #fff;
    border-color: #38bdf8;
    box-shadow: 0 0 10px rgba(56, 189, 248, 0.35);
  }}

  /* 카테고리 필터 바 */
  .sub-filter {{
    display: flex;
    gap: 6px;
    padding: 6px 10px 8px;
    overflow-x: auto;
    white-space: nowrap;
  }}
  .filter-btn {{
    background: #151b2e;
    border: 1px solid var(--border);
    color: #cbd5e1;
    font-size: 0.7rem;
    padding: 4px 10px;
    border-radius: 6px;
    cursor: pointer;
    flex-shrink: 0;
    transition: all 0.15s ease;
  }}
  .filter-btn.active {{
    background: #1e293b;
    color: #38bdf8;
    border-color: #38bdf8;
    font-weight: 700;
  }}

  /* 카드 그리드 */
  .grid {{
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 8px;
    padding: 10px;
  }}
  @media (min-width: 600px) {{
    .grid {{
      grid-template-columns: repeat(3, 1fr);
      gap: 12px;
      padding: 14px;
    }}
  }}
  @media (min-width: 900px) {{
    .grid {{
      grid-template-columns: repeat(4, 1fr);
      gap: 16px;
    }}
  }}
  .card {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 10px;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    position: relative;
  }}
  .img-box {{
    position: relative;
    width: 100%;
    aspect-ratio: 832 / 1216;
    background: #000;
    cursor: pointer;
  }}
  .img-box img {{
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }}
  .code-badge {{
    position: absolute;
    top: 6px;
    left: 6px;
    background: rgba(0, 0, 0, 0.78);
    color: #38bdf8;
    font-size: 0.7rem;
    font-weight: 800;
    padding: 2px 6px;
    border-radius: 4px;
    border: 1px solid rgba(56, 189, 248, 0.4);
    z-index: 5;
  }}
  /* 우상단 🎲 리롤 버튼 */
  .reroll-badge-btn {{
    position: absolute;
    top: 6px;
    right: 6px;
    background: rgba(15, 23, 42, 0.88);
    color: #fbbf24;
    font-size: 0.68rem;
    font-weight: 800;
    padding: 2px 7px;
    border-radius: 5px;
    border: 1px solid rgba(251, 191, 36, 0.6);
    cursor: pointer;
    backdrop-filter: blur(4px);
    transition: all 0.15s ease;
    z-index: 10;
  }}
  .reroll-badge-btn:active {{
    background: #d97706;
    color: #fff;
    transform: scale(0.94);
  }}
  .reroll-badge-btn.queued {{
    background: #b45309;
    color: #fff;
    border-color: #f59e0b;
    cursor: wait;
    animation: pulse 1.4s infinite;
  }}
  .reroll-badge-btn.processing {{
    background: #0284c7;
    color: #fff;
    border-color: #38bdf8;
    cursor: wait;
    animation: pulse 0.85s infinite;
  }}
  .reroll-badge-btn.done {{
    background: #059669;
    color: #fff;
    border-color: #34d399;
  }}
  .reroll-badge-btn.qc-warn {{
    background: #d97706;
    color: #fff;
    border-color: #fbbf24;
  }}
  .reroll-badge-btn.failed {{
    background: #dc2626;
    color: #fff;
    border-color: #f87171;
  }}
  .reroll-badge-btn.loading {{
    background: #334155;
    color: #94a3b8;
    border-color: #64748b;
    cursor: wait;
    animation: pulse 1.2s infinite;
  }}
  @keyframes pulse {{
    0%, 100% {{ opacity: 1; }}
    50% {{ opacity: 0.45; }}
  }}

  .meta {{
    padding: 8px 10px;
  }}
  .label-row {{
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 0.76rem;
    font-weight: 700;
    color: #fff;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }}
  .badge {{
    font-size: 0.65rem;
    padding: 1px 5px;
    border-radius: 4px;
    font-weight: 700;
    white-space: nowrap;
  }}
  .badge.normal {{ background: #065f46; color: #a7f3d0; }}
  .badge.hscene {{ background: #881337; color: #fecdd3; }}
  .label-text {{ overflow: hidden; text-overflow: ellipsis; }}
  .sub-info {{
    font-size: 0.68rem;
    color: var(--text-muted);
    margin-top: 2px;
  }}

  /* 카드 하단 버튼 2열 행 */
  .card-btn-row {{
    display: flex;
    gap: 6px;
    margin-top: 6px;
  }}
  .action-btn {{
    flex: 1;
    border-radius: 6px;
    font-size: 0.7rem;
    font-weight: 700;
    padding: 6px 0;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 3px;
    transition: all 0.15s ease;
    white-space: nowrap;
  }}
  .retouch-btn {{
    background: #1e293b;
    border: 1px solid #334155;
    color: #38bdf8;
  }}
  .retouch-btn:active {{
    background: #0284c7;
    color: #fff;
  }}
  .recensor-btn {{
    background: #172554;
    border: 1px solid #1d4ed8;
    color: #93c5fd;
  }}
  .recensor-btn:active {{
    background: #2563eb;
    color: #fff;
  }}
  .recensor-btn:disabled {{
    opacity: 0.5;
    cursor: not-allowed;
  }}
  .origin-btn {{
    background: #24211b;
    border: 1px solid #78350f;
    color: #fbbf24;
  }}
  .origin-btn:active {{
    background: #d97706;
    color: #fff;
  }}
  .censor-toolbar {{
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 0 10px 8px;
    flex-wrap: wrap;
  }}
  .censor-select {{
    background: #151b2e;
    border: 1px solid var(--border);
    color: #f1f5f9;
    font-size: 0.72rem;
    padding: 4px 8px;
    border-radius: 6px;
    outline: none;
  }}
  .anchor-toggle {{
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 0.72rem;
    color: #cbd5e1;
    background: #151b2e;
    border: 1px solid var(--border);
    padding: 4px 8px;
    border-radius: 6px;
    cursor: pointer;
    user-select: none;
  }}

  /* 플로팅 최상단 이동 버튼 */
  .floating-top-btn {{
    display: none;
    position: fixed;
    bottom: 22px;
    right: 18px;
    z-index: 999;
    background: rgba(15, 23, 42, 0.92);
    color: #38bdf8;
    border: 1px solid rgba(56, 189, 248, 0.6);
    padding: 10px 16px;
    border-radius: 9999px;
    font-size: 0.8rem;
    font-weight: 800;
    cursor: pointer;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.6);
    backdrop-filter: blur(8px);
    transition: all 0.2s ease;
  }}
  .floating-top-btn:active {{
    transform: scale(0.95);
    background: #0284c7;
    color: #fff;
  }}

  /* Retouch Modal */
  .retouch-modal {{
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.96);
    z-index: 2000;
    flex-direction: column;
    overflow: hidden;
  }}
  .retouch-modal.active {{ display: flex; }}
  .modal-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 14px;
    background: #0f172a;
    border-bottom: 1px solid #1e293b;
  }}
  .modal-title {{
    font-size: 0.88rem;
    font-weight: 800;
    color: #f8fafc;
    display: flex;
    align-items: center;
    gap: 8px;
  }}
  .close-btn {{
    background: #334155;
    color: #cbd5e1;
    border: none;
    border-radius: 6px;
    padding: 6px 12px;
    font-weight: 700;
    font-size: 0.8rem;
    cursor: pointer;
  }}
  .canvas-container {{
    flex: 1;
    position: relative;
    display: flex;
    justify-content: center;
    align-items: center;
    background: #000;
    overflow: hidden;
    touch-action: none;
  }}
  #editor-canvas {{
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
    touch-action: none;
    box-shadow: 0 0 20px rgba(0,0,0,0.8);
  }}
  .modal-toolbar {{
    background: #0f172a;
    border-top: 1px solid #1e293b;
    padding: 8px 12px;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }}
  .tool-group {{
    display: flex;
    align-items: center;
    gap: 6px;
  }}
  .tool-btn {{
    background: #1e293b;
    border: 1px solid #334155;
    color: #cbd5e1;
    padding: 6px 10px;
    border-radius: 6px;
    font-size: 0.75rem;
    font-weight: 700;
    cursor: pointer;
  }}
  .tool-btn.active {{
    background: #0284c7;
    color: #fff;
    border-color: #38bdf8;
  }}
  .save-btn {{
    background: #059669;
    color: #fff;
    border: none;
    padding: 6px 14px;
    border-radius: 6px;
    font-size: 0.78rem;
    font-weight: 800;
    cursor: pointer;
  }}
  .save-btn:disabled {{
    background: #475569;
    cursor: not-allowed;
  }}
  .toast {{
    display: none;
    position: fixed;
    bottom: 24px;
    left: 50%;
    transform: translateX(-50%);
    background: #059669;
    color: #fff;
    padding: 9px 20px;
    border-radius: 9999px;
    font-size: 0.82rem;
    font-weight: 800;
    z-index: 3000;
    box-shadow: 0 4px 14px rgba(0,0,0,0.5);
    white-space: nowrap;
  }}
  .lightbox {{
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.92);
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
  .empty-msg {{
    grid-column: 1 / -1;
    text-align: center;
    padding: 40px 20px;
    color: var(--text-muted);
    font-size: 0.85rem;
  }}
</style>
</head>
<body>

<div class="sticky-top-container">
  <header>
    <div class="title-row">
      <h1>🔬 캠퍼스 6인 전역 검수 갤러리</h1>
      <div class="header-actions">
        <div id="queue-status-badge" class="queue-status-pill" style="display: none;" onclick="showQueueToast()">
          <span class="queue-spin">⏳</span>
          <span id="queue-status-text">대기열 0건</span>
        </div>
        <button class="top-btn refresh-btn" onclick="refreshPage()">🔄 새로고침</button>
        <button class="top-btn" onclick="scrollToTop()">🔝 맨위로</button>
        <div class="counter" id="total-badge">총 {total_count}장 로드</div>
      </div>
    </div>
    <div class="subtitle">캠퍼스 6인 전원 + ADR-86 콤팩트 언더마스킹 + 3단계 표준화(시작/절정/사후)</div>
  </header>

  <div class="tabs">
    {tabs_html}
  </div>

  <div class="sub-filter">
    <button class="filter-btn active" onclick="filterFolder('all')">전체 보기</button>
    <button class="filter-btn" onclick="filterFolder('01_normal')">01 일상/감정</button>
    <button class="filter-btn" onclick="filterFolder('02_h_scenes')">02 로맨스/H씬</button>
  </div>
  <div class="censor-toolbar">
    <label for="global-censor-style" style="font-size:0.7rem;color:#94a3b8;font-weight:700;">검열 스타일</label>
    <select id="global-censor-style" class="censor-select">
      <option value="white_silhouette" selected>white_silhouette (백색 실루엣)</option>
      <option value="black_silhouette">black_silhouette (흑색 실루엣)</option>
      <option value="manga_bar">manga_bar (망가 회전 바)</option>
      <option value="manga_glow">manga_glow (망가 화이트 글로우)</option>
      <option value="mosaic">mosaic (모자이크)</option>
      <option value="bar">bar (검은 바)</option>
      <option value="slim_bar">slim_bar (슬림 바)</option>
      <option value="shadow">shadow (그림자)</option>
      <option value="debug_bbox">debug_bbox (디버그 박스)</option>
    </select>
    <label class="anchor-toggle" title="YOLO 미검출 시 포즈 앵커 폴백 마스킹 활성화">
      <input type="checkbox" id="global-anchor-fallback" />
      <span>anchor_fallback</span>
    </label>
  </div>
</div>

{grids_html}

<button id="floating-top-btn" class="floating-top-btn" onclick="scrollToTop()">▲ TOP</button>

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
  function getPlepaAuthHeaders(extra) {{
    const headers = Object.assign({{}}, extra || {{}});
    const token = new URLSearchParams(window.location.search).get('token');
    if (token) headers['X-Plepa-Token'] = token;
    return headers;
  }}

  let currentChar = sessionStorage.getItem('plepa_inspect_char') || {first_char_js};
  let currentFilter = sessionStorage.getItem('plepa_inspect_filter') || 'all';

  function scrollToTop() {{
    window.scrollTo({{ top: 0, behavior: 'smooth' }});
  }}

  function refreshPage() {{
    sessionStorage.setItem('plepa_inspect_char', currentChar);
    sessionStorage.setItem('plepa_inspect_filter', currentFilter);
    showToast('🔄 갤러리 새로고침 중...');
    setTimeout(() => {{
      window.location.reload();
    }}, 250);
  }}

  function switchChar(charId) {{
    currentChar = charId;
    sessionStorage.setItem('plepa_inspect_char', charId);
    document.querySelectorAll('.tab-btn').forEach(btn => {{
      btn.classList.toggle('active', btn.dataset.char === charId);
    }});
    document.querySelectorAll('.grid').forEach(grid => {{
      grid.style.display = grid.id === ('grid-' + charId) ? 'grid' : 'none';
    }});
    applySubFilter();
    scrollToTop();
  }}

  function filterFolder(folder) {{
    currentFilter = folder;
    sessionStorage.setItem('plepa_inspect_filter', folder);
    document.querySelectorAll('.filter-btn').forEach(btn => {{
      btn.classList.toggle('active', btn.textContent.includes(folder === 'all' ? '전체' : (folder === '01_normal' ? '01' : '02')));
    }});
    applySubFilter();
  }}

  function applySubFilter() {{
    const activeGrid = document.getElementById('grid-' + currentChar);
    if (!activeGrid) return;
    const cards = activeGrid.querySelectorAll('.card');
    cards.forEach(card => {{
      if (currentFilter === 'all' || card.dataset.subfolder === currentFilter) {{
        card.style.display = 'flex';
      }} else {{
        card.style.display = 'none';
      }}
    }});
  }}

  function openLightbox(src) {{
    document.getElementById('lightbox-img').src = src;
    document.getElementById('lightbox').classList.add('active');
  }}
  function closeLightbox() {{
    document.getElementById('lightbox').classList.remove('active');
  }}

  /* 플로팅 탑 버튼 스크롤 감지 */
  window.addEventListener('scroll', () => {{
    const topBtn = document.getElementById('floating-top-btn');
    if (topBtn) {{
      if (window.scrollY > 280) {{
        topBtn.style.display = 'block';
      }} else {{
        topBtn.style.display = 'none';
      }}
    }}
  }});

  /* 🎲 비동기 작업 큐 기반 리롤(재생성) 관리 시스템 */
  let rerollPollTimer = null;
  let activeTrackedJobs = new Set();
  let rerollQueueData = null;

  function showQueueToast() {{
    if (!rerollQueueData || rerollQueueData.total_pending === 0) {{
      showToast('현재 대기열이 비어있습니다.');
      return;
    }}
    const txt = `대기열: 진행 ${{rerollQueueData.processing_count}}건, 대기 ${{rerollQueueData.queued_count}}건 (총 ${{rerollQueueData.total_pending}}건)`;
    showToast(txt);
  }}

  async function enqueueReroll(e, path, charCode, poseCode, label) {{
    if (e) e.stopPropagation();
    const confirmed = confirm(`[#${{poseCode}} ${{label}}]\n이 이미지를 새로운 무작위 시드로 리롤(대기열 등록)하시겠습니까?\n순차 작업 큐에 등록되어 GPU 과부하 없이 안전하게 1건씩 차례대로 재생성됩니다.`);
    if (!confirmed) return;

    const btn = document.getElementById(`reroll-btn-${{charCode}}-${{poseCode}}`) || e.target;
    btn.innerHTML = '⏳ 등록중';
    btn.disabled = true;

    let cleanRel = path.split('?')[0];
    cleanRel = cleanRel.replace(/^\\/?inspect\\//, '').replace(/^\\//, '');

    try {{
      const censorOpts = getCensorOptions();
      const resp = await fetch('/api/reroll_queue', {{
        method: 'POST',
        headers: getPlepaAuthHeaders({{ 'Content-Type': 'application/json' }}),
        body: JSON.stringify({{
          file_path: cleanRel,
          char_code: charCode,
          pose_code: poseCode,
          label: label || '',
          censor_style: censorOpts.censor_style,
          censor_targets: censorOpts.censor_targets,
          min_confidence: censorOpts.min_confidence,
          enable_anchor_fallback: censorOpts.enable_anchor_fallback
        }})
      }});
      const result = await resp.json();
      if (result.success && result.job) {{
        const job = result.job;
        activeTrackedJobs.add(job.job_id);

        if (job.status === 'processing' || job.queue_position === 0) {{
          btn.innerHTML = '⚙️ 생성중';
          btn.className = 'reroll-badge-btn processing';
        }} else {{
          btn.innerHTML = `⏳ 대기 #${{job.queue_position}}`;
          btn.className = 'reroll-badge-btn queued';
        }}
        showToast(`[#${{poseCode}}] 대기열 등록 완료 (순번: #${{job.queue_position}})`);
        startRerollPolling();
      }} else {{
        alert('대기열 등록 실패: ' + (result.error || '알 수 없는 오류'));
        btn.innerHTML = '🎲 리롤';
        btn.className = 'reroll-badge-btn';
        btn.disabled = false;
      }}
    }} catch (err) {{
      alert('통신 오류: ' + err);
      btn.innerHTML = '🎲 리롤';
      btn.className = 'reroll-badge-btn';
      btn.disabled = false;
    }}
  }}

  /* 하위 호환 별칭 */
  function rerollPose(e, path, charCode, poseCode, label) {{
    enqueueReroll(e, path, charCode, poseCode, label);
  }}

  function startRerollPolling() {{
    if (rerollPollTimer) return;
    pollRerollQueue();
    rerollPollTimer = setInterval(pollRerollQueue, 1800);
  }}

  async function pollRerollQueue() {{
    try {{
      const resp = await fetch('/api/reroll_queue_status', {{
        headers: getPlepaAuthHeaders()
      }});
      const json = await resp.json();
      if (!json.success || !json.data) return;

      const data = json.data;
      rerollQueueData = data;
      const qBadge = document.getElementById('queue-status-badge');
      const qText = document.getElementById('queue-status-text');

      if (data.total_pending > 0) {{
        if (qBadge) qBadge.style.display = 'inline-flex';
        let parts = [];
        if (data.processing_count > 0) parts.push(`⚙️ 진행 1건`);
        if (data.queued_count > 0) parts.push(`대기 ${{data.queued_count}}건`);
        if (qText) qText.textContent = parts.join(' | ') || `대기열 ${{data.total_pending}}건`;
      }} else {{
        if (qBadge && qBadge.style.display !== 'none') {{
          if (qText) qText.textContent = '✅ 완료!';
          setTimeout(() => {{
            if (rerollQueueData && rerollQueueData.total_pending === 0 && qBadge) {{
              qBadge.style.display = 'none';
            }}
          }}, 2500);
        }}
        if (activeTrackedJobs.size === 0) {{
          clearInterval(rerollPollTimer);
          rerollPollTimer = null;
        }}
      }}

      // 개별 작업 상태 버튼 및 이미지 실시간 갱신
      if (data.jobs) {{
        for (const [jobId, job] of Object.entries(data.jobs)) {{
          const btn = document.getElementById(`reroll-btn-${{job.char_code}}-${{job.pose_code}}`);
          if (!btn) continue;

          if (job.status === 'processing') {{
            btn.innerHTML = '⚙️ 생성중';
            btn.className = 'reroll-badge-btn processing';
            btn.disabled = true;
          }} else if (job.status === 'queued') {{
            btn.innerHTML = `⏳ 대기 #${{job.queue_position}}`;
            btn.className = 'reroll-badge-btn queued';
            btn.disabled = true;
          }} else if (job.status === 'done' && activeTrackedJobs.has(jobId)) {{
            activeTrackedJobs.delete(jobId);
            const hasQcWarn = job.qc_passed === false;
            if (hasQcWarn) {{
              btn.innerHTML = '⚠️ QC경고';
              btn.title = job.qc_reason || 'Auto-QC 기준 미달';
              btn.className = 'reroll-badge-btn qc-warn';
            }} else {{
              btn.innerHTML = '✅ 완료!';
              btn.className = 'reroll-badge-btn done';
            }}

            // 이미지 즉시 리로드 (캐시버스팅)
            const cleanRel = job.file_path.replace(/^\\/?inspect\\//, '').replace(/^\\//, '');
            const t = Date.now();
            document.querySelectorAll(`img[src*="${{cleanRel}}"]`).forEach(img => {{
              img.src = cleanRel + '?t=' + t;
            }});
            if (hasQcWarn) {{
              showToast(`⚠️ [#${{job.pose_code}}] QC경고 (${{job.qc_reason || '기준 미달'}})`);
            }} else {{
              showToast(`🎉 [#${{job.pose_code}}] 새 이미지 리롤 생성 완료!`);
            }}

            setTimeout(() => {{
              btn.innerHTML = '🎲 리롤';
              btn.title = '새로운 무작위 시드로 리롤';
              btn.className = 'reroll-badge-btn';
              btn.disabled = false;
            }}, hasQcWarn ? 4500 : 3000);
          }} else if (job.status === 'failed' && activeTrackedJobs.has(jobId)) {{
            activeTrackedJobs.delete(jobId);
            btn.innerHTML = '❌ 실패';
            btn.className = 'reroll-badge-btn failed';
            showToast(`❌ [#${{job.pose_code}}] 리롤 실패: ${{job.error}}`);

            setTimeout(() => {{
              btn.innerHTML = '🎲 리롤';
              btn.className = 'reroll-badge-btn';
              btn.disabled = false;
            }}, 3500);
          }}
        }}
      }}
    }} catch (err) {{
      console.warn('Queue poll error:', err);
    }}
  }}

  function getCensorOptions() {{
    const styleEl = document.getElementById('global-censor-style');
    const anchorEl = document.getElementById('global-anchor-fallback');
    return {{
      censor_style: styleEl ? styleEl.value : 'white_silhouette',
      censor_targets: 'penis',
      min_confidence: 0.16,
      enable_anchor_fallback: !!(anchorEl && anchorEl.checked)
    }};
  }}

  /* 0.2초 즉시 재검열 함수 */
  async function reapplyCensor(e, path, charCode, poseCode, label) {{
    if (e) e.stopPropagation();
    const btn = e && e.currentTarget ? e.currentTarget : null;
    const prevText = btn ? btn.innerHTML : '⚡ 재검열';
    if (btn) {{
      btn.disabled = true;
      btn.innerHTML = '⏳ 처리중';
    }}

    let cleanRel = path.split('?')[0];
    cleanRel = cleanRel.replace(/^\\/?inspect\\//, '').replace(/^\\//, '');
    const opts = getCensorOptions();

    try {{
      const resp = await fetch('/api/reapply_censor', {{
        method: 'POST',
        headers: getPlepaAuthHeaders({{ 'Content-Type': 'application/json' }}),
        body: JSON.stringify({{
          file_path: cleanRel,
          char_code: charCode || '',
          pose_code: poseCode || '',
          censor_style: opts.censor_style,
          censor_targets: opts.censor_targets,
          min_confidence: opts.min_confidence,
          enable_anchor_fallback: opts.enable_anchor_fallback
        }})
      }});
      const result = await resp.json();
      if (resp.ok && result.success) {{
        const syncNote = result.synced_asset ? ' (에셋 동기화)' : '';
        showToast(`⚡ [#${{poseCode}}] ${{opts.censor_style}} 재검열 완료${{syncNote}} (탐지 ${{result.detected_count ?? 0}}건)`);
        const t = Date.now();
        document.querySelectorAll('img').forEach(img => {{
          const rawSrc = (img.getAttribute('src') || '').split('?')[0];
          if (rawSrc === cleanRel || rawSrc.endsWith('/' + cleanRel)) {{
            img.src = cleanRel + '?t=' + t;
          }}
        }});
      }} else {{
        alert('재검열 실패: ' + (result.error || result.detail || '알 수 없는 오류'));
      }}
    }} catch (err) {{
      alert('통신 오류: ' + err);
    }} finally {{
      if (btn) {{
        btn.disabled = false;
        btn.innerHTML = prevText;
      }}
    }}
  }}

  /* 오리지널 원본 복원 함수 */
  async function restoreOrigin(e, path, code, label) {{
    if (e) e.stopPropagation();
    const confirmed = confirm(`[#${{code}} ${{label}}]\n오리지널(무검열 원본) 이미지로 변경하시겠습니까?\n기존 검열 및 덧칠 내역이 원본으로 교체됩니다.`);
    if (!confirmed) return;

    let cleanRel = path.split('?')[0];
    cleanRel = cleanRel.replace(/^\\/?inspect\\//, '').replace(/^\\//, '');

    try {{
      const resp = await fetch('/api/restore_origin', {{
        method: 'POST',
        headers: getPlepaAuthHeaders({{ 'Content-Type': 'application/json' }}),
        body: JSON.stringify({{ file_path: cleanRel }})
      }});
      const result = await resp.json();
      if (result.success) {{
        showToast('✅ 오리지널 원본으로 변경 완료!');
        const t = Date.now();
        document.querySelectorAll('img').forEach(img => {{
          const rawSrc = (img.getAttribute('src') || '').split('?')[0];
          if (rawSrc === cleanRel || rawSrc.endsWith('/' + cleanRel)) {{
            img.src = cleanRel + '?t=' + t;
          }}
        }});
      }} else {{
        alert('원본 변경 실패: ' + (result.error || '알 수 없는 오류'));
      }}
    }} catch (err) {{
      alert('통신 오류: ' + err);
    }}
  }}

  /* Retouch Canvas Logic */
  let currentImgPath = '';
  let currentImgObj = null;
  let canvas = null;
  let ctx = null;
  let isDrawing = false;
  let currentTool = 'brush';
  let brushRadius = 28;
  let undoStack = [];

  function openRetouch(e, path, code, label) {{
    if (e) e.stopPropagation();
    currentImgPath = path;
    document.getElementById('modal-title').textContent = `#${{code}} ${{label}} 덧칠 편집`;
    const modal = document.getElementById('retouch-modal');
    modal.classList.add('active');

    canvas = document.getElementById('editor-canvas');
    ctx = canvas.getContext('2d');
    undoStack = [];

    currentImgObj = new Image();
    currentImgObj.crossOrigin = 'anonymous';
    currentImgObj.onload = function() {{
      canvas.width = currentImgObj.naturalWidth || 832;
      canvas.height = currentImgObj.naturalHeight || 1216;
      ctx.drawImage(currentImgObj, 0, 0);
      saveState();
    }};
    currentImgObj.src = path + (path.includes('?') ? '&' : '?') + 't=' + Date.now();
  }}

  function closeRetouch() {{
    document.getElementById('retouch-modal').classList.remove('active');
  }}

  function setTool(tool) {{
    currentTool = tool;
    document.getElementById('btn-brush').classList.toggle('active', tool === 'brush');
    document.getElementById('btn-eraser').classList.toggle('active', tool === 'eraser');
  }}

  function updateBrushSize(val) {{
    brushRadius = parseInt(val);
    document.getElementById('brush-size-val').textContent = val;
  }}

  function saveState() {{
    if (undoStack.length >= 15) undoStack.shift();
    undoStack.push(ctx.getImageData(0, 0, canvas.width, canvas.height));
  }}

  function undoStroke() {{
    if (undoStack.length > 1) {{
      undoStack.pop();
      const prev = undoStack[undoStack.length - 1];
      ctx.putImageData(prev, 0, 0);
    }}
  }}

  function resetCanvas() {{
    if (currentImgObj) {{
      ctx.drawImage(currentImgObj, 0, 0);
      saveState();
    }}
  }}

  function getCanvasCoords(e) {{
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    let clientX = e.clientX;
    let clientY = e.clientY;
    if (e.touches && e.touches.length > 0) {{
      clientX = e.touches[0].clientX;
      clientY = e.touches[0].clientY;
    }}
    return {{
      x: (clientX - rect.left) * scaleX,
      y: (clientY - rect.top) * scaleY
    }};
  }}

  function startDraw(e) {{
    e.preventDefault();
    isDrawing = true;
    const pos = getCanvasCoords(e);
    drawCircle(pos.x, pos.y);
  }}

  function moveDraw(e) {{
    if (!isDrawing) return;
    e.preventDefault();
    const pos = getCanvasCoords(e);
    drawCircle(pos.x, pos.y);
  }}

  function stopDraw(e) {{
    if (isDrawing) {{
      isDrawing = false;
      saveState();
    }}
  }}

  function drawCircle(x, y) {{
    ctx.save();
    if (currentTool === 'brush') {{
      const grad = ctx.createRadialGradient(x, y, brushRadius * 0.4, x, y, brushRadius);
      grad.addColorStop(0, 'rgba(255, 255, 255, 1.0)');
      grad.addColorStop(0.85, 'rgba(255, 255, 255, 0.95)');
      grad.addColorStop(1, 'rgba(255, 255, 255, 0.0)');
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(x, y, brushRadius, 0, Math.PI * 2);
      ctx.fill();
    }} else {{
      if (currentImgObj) {{
        ctx.save();
        ctx.beginPath();
        ctx.arc(x, y, brushRadius, 0, Math.PI * 2);
        ctx.clip();
        ctx.drawImage(currentImgObj, 0, 0);
        ctx.restore();
      }}
    }}
    ctx.restore();
  }}

  window.addEventListener('DOMContentLoaded', () => {{
    const cv = document.getElementById('editor-canvas');
    cv.addEventListener('mousedown', startDraw);
    cv.addEventListener('mousemove', moveDraw);
    window.addEventListener('mouseup', stopDraw);

    cv.addEventListener('touchstart', startDraw, {{ passive: false }});
    cv.addEventListener('touchmove', moveDraw, {{ passive: false }});
    window.addEventListener('touchend', stopDraw);

    // 저장된 이전 캐릭터/필터 상태 자동 복원
    if (currentChar && currentChar !== '{first_char}') {{
      switchChar(currentChar);
    }}
    if (currentFilter && currentFilter !== 'all') {{
      filterFolder(currentFilter);
    }}

    // 최초 큐 상태 체크 (이전 진행 작업 복원)
    pollRerollQueue().then(() => {{
      if (rerollQueueData && rerollQueueData.total_pending > 0) {{
        startRerollPolling();
      }}
    }});
  }});

  async function saveRetouch() {{
    const saveBtn = document.getElementById('btn-save');
    saveBtn.disabled = true;
    saveBtn.textContent = '⏳ 저장 중...';

    try {{
      const dataUrl = canvas.toDataURL('image/webp', 0.95);
      let cleanRel = currentImgPath.split('?')[0];
      cleanRel = cleanRel.replace(/^\\/?inspect\\//, '').replace(/^\\//, '');

      const resp = await fetch('/api/retouch_censor', {{
        method: 'POST',
        headers: getPlepaAuthHeaders({{ 'Content-Type': 'application/json' }}),
        body: JSON.stringify({{
          file_path: cleanRel,
          image_base64: dataUrl
        }})
      }});
      const result = await resp.json();
      if (result.success) {{
        showToast('✅ 저장 완료!');
        const t = Date.now();
        document.querySelectorAll('img').forEach(img => {{
          const rawSrc = (img.getAttribute('src') || '').split('?')[0];
          if (rawSrc === cleanRel || rawSrc.endsWith('/' + cleanRel)) {{
            img.src = cleanRel + '?t=' + t;
          }}
        }});
        setTimeout(() => {{
          closeRetouch();
          saveBtn.disabled = false;
          saveBtn.textContent = '💾 저장 완료';
        }}, 600);
      }} else {{
        alert('저장 실패: ' + (result.error || '알 수 없는 오류'));
        saveBtn.disabled = false;
        saveBtn.textContent = '💾 저장 완료';
      }}
    }} catch (err) {{
      alert('통신 오류: ' + err);
      saveBtn.disabled = false;
      saveBtn.textContent = '💾 저장 완료';
    }}
  }}

  function showToast(msg) {{
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.style.display = 'block';
    setTimeout(() => {{ t.style.display = 'none'; }}, 2000);
  }}
</script>

</body>
</html>
"""

    inspection_dir.mkdir(parents=True, exist_ok=True)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"Generated dynamic multi-character inspection HTML at {html_path}")
    print(f"Characters found: {found_chars}")
    print(f"Total assets loaded: {total_count}")
    return html_path


if __name__ == "__main__":
    generate_inspection_html()
