"""
scripts/run_ratatata_mix_benchmark.py
Ratatata74 중심 25개 하이브리드 조합 (하율 13조합 65장 + 유아 12조합 60장 = 총 125장)
5대 대표 포즈 (000, 028, 076, 095, 106)
벤치마크 일괄 생성 및 인터랙티브 HTML 뷰어 자동 생성 스크립트.

사용법:
  python scripts/run_ratatata_mix_benchmark.py --mock         # 0.1초 파이프라인 및 HTML 뷰어 검증
  python scripts/run_ratatata_mix_benchmark.py --dry-run      # 프롬프트 및 설정 사전 점검
  python scripts/run_ratatata_mix_benchmark.py                # 125장 본 생성 실행
  python scripts/run_ratatata_mix_benchmark.py --char hay     # 하율(hay) 13조합(65장)만 실행
  python scripts/run_ratatata_mix_benchmark.py --char yua     # 유아(yua) 12조합(60장)만 실행
  python scripts/run_ratatata_mix_benchmark.py --combo 01     # 특정 조합 번호만 단독 실행
"""

from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path
import sys
from typing import Dict, List, Tuple

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from plepa_engine.config import PROJECTS_DIR
from plepa_engine.services.generation_service import GenerationParams, GenerationService

# 5대 대표 벤치마크 포즈
BENCHMARK_POSES = ["000", "028", "076", "095", "106"]
POSE_LABELS = {
    "000": "평상",
    "028": "엉덩이애무",
    "076": "수유대딸",
    "095": "웨딩섹스",
    "106": "샤워섹스강",
}

# 25개 Ratatata 하이브리드 조합 정의
# 구조: (조합ID, 캐릭터, 서브작가이름, 프롬프트태그, 시너지설명)
RATATATA_COMBOS: List[Tuple[str, str, str, str, str]] = [
    # --- [하율 hay: 쿨뷰티 & 단아함 & 성숙 육감미 13조합] ---
    ("01_hiten", "hay", "Hiten", "(artist:ratatata74:1.05), (artist:hiten:0.95)", "투명한 역광과 청초한 눈망울, 궁극의 갭모에"),
    ("02_tiv", "hay", "Tiv", "(artist:ratatata74:0.95), (artist:tiv:1.05)", "정밀한 극세사 선화와 메이저 라노벨급 단아함"),
    ("03_anmi", "hay", "Anmi", "(artist:ratatata74:1.0), (artist:anmi:0.9)", "복숭앗빛 투명 피부와 부드러운 수채 채색"),
    ("04_morikura_en", "hay", "Morikura En", "(artist:ratatata74:1.0), (artist:morikura_en:0.9)", "따뜻한 빛과 찰랑이는 흑발 머릿결 건강미"),
    ("05_ciloranko", "hay", "Ciloranko", "(artist:ratatata74:1.0), (artist:ciloranko:0.95)", "붉게 달아오른 살결과 관능적인 땀방울 디테일"),
    ("06_homunculus", "hay", "Homunculus", "(artist:ratatata74:1.0), (artist:homunculus:0.85)", "부드럽고 말랑말랑한 푹신한 육덕 질감"),
    ("07_alcheman", "hay", "Alchemaniac", "(artist:ratatata74:1.0), (artist:alchemaniac:0.95)", "묵직한 조명 대비와 탄탄한 각선미"),
    ("08_marushin", "hay", "Marushin", "(artist:ratatata74:0.95), (artist:marushin:0.95)", "한국형 성인 웹툰 선화와 성숙한 누나 이목구비"),
    ("09_ask", "hay", "Ask", "(artist:ratatata74:1.0), (artist:ask_(askzy):0.95)", "유화 붓 터치와 중후한 화보 표지 무드"),
    ("10_ruan_jia", "hay", "Ruan佳", "(artist:ratatata74:1.0), (artist:ruan_jia:0.85)", "영화 스틸컷 같은 묵직한 공간감과 공기감"),
    ("11_krenz", "hay", "Krenz Cushart", "(artist:ratatata74:1.05), (artist:krenz_cushart:0.85)", "과감한 앵글 투시와 정밀한 빛 계산"),
    ("12_chuzenji", "hay", "Chuzenji", "(artist:ratatata74:0.95), (artist:chuzenji:0.95)", "날렵하고 세련된 쿨시크 턱선과 정밀 질감"),
    ("13_tony_taka", "hay", "Tony Taka", "(artist:ratatata74:1.0), (artist:tony_taka:0.9)", "단정한 고전 흑발 미소녀의 완성된 이목구비"),

    # --- [유아 yua: 앙큼 & 도발 & 장난기 넘치는 갸루미 12조합] ---
    ("14_kantoku", "yua", "Kantoku", "(artist:ratatata74:1.0), (artist:kantoku:0.95)", "화사한 체크무늬 의상과 체리빛 볼터치"),
    ("15_nanashi", "yua", "Nanashi", "(artist:ratatata74:1.0), (artist:nanashi_(774):0.9)", "나가토로 특유의 앙큼한 눈매와 장난기 어린 도발"),
    ("16_asanagi", "yua", "Asanagi", "(artist:ratatata74:0.95), (artist:asanagi:0.95)", "탄탄하고 묵직한 골반과 육덕 하체 실루엣"),
    ("17_mizuryu_kei", "yua", "Mizuryu Kei", "(artist:ratatata74:1.0), (artist:mizuryu_kei:0.9)", "달아오른 암컷 얼굴, 혀 내밀기, 하트눈 표정"),
    ("18_kappe", "yua", "Kappe", "(artist:ratatata74:1.05), (artist:kappe:0.95)", "반짝이는 애니메이션 셀 채색과 도회적 인상"),
    ("19_guira", "yua", "Guira", "(artist:ratatata74:1.0), (artist:guira:0.9)", "오일을 바른 듯 촉촉한 글로시 립과 바디 광택"),
    ("20_cogecha", "yua", "Cogecha", "(artist:ratatata74:1.0), (artist:cogecha:0.85)", "오묘한 보랏빛/핑크빛 잔선과 화려한 그러데이션"),
    ("21_wlop", "yua", "WLOP", "(artist:ratatata74:1.0), (artist:wlop:0.8)", "신비로운 반사광과 메탈릭한 장신구 텍스처"),
    ("22_mika_pikazo", "yua", "Mika Pikazo", "(artist:ratatata74:1.0), (artist:mika_pikazo:0.9)", "비비드한 원색과 보석처럼 빛나는 화려한 눈동자"),
    ("23_lam", "yua", "Lam", "(artist:ratatata74:1.0), (artist:lam_(ramu):0.9)", "카리스마 있는 아이라인과 앙칼진 눈빛"),
    ("24_yoneyama_mai", "yua", "Yoneyama Mai", "(artist:ratatata74:1.0), (artist:yoneyama_mai:0.85)", "유리 같은 굴절과 역동적인 포즈 텐션"),
    ("25_redrop", "yua", "ReDrop", "(artist:ratatata74:1.0), (artist:redrop:0.95)", "FGO 공식 일러스트급 화려함과 레이스 디테일"),
]


def generate_html_viewer(benchmark_dir: Path, tasks: List[Dict]) -> Path:
    """Ratatata 하이브리드 조합 전용 모던 인터랙티브 HTML 뷰어 생성."""
    html_path = benchmark_dir / "index.html"
    
    cards_data = []
    for t in tasks:
        combo_id = t["combo_id"]
        char = t["char"]
        partner = t["partner"]
        tag = t["tag"]
        desc = t["desc"]
        
        char_korean = "설하율 (하율)" if char == "hay" else "설유아 (유아)"
        
        poses_data = []
        for code in BENCHMARK_POSES:
            label = POSE_LABELS[code]
            fname = f"{char}_{code}_{label}.webp"
            fpath = benchmark_dir / combo_id / fname
            rel_path = f"{combo_id}/{fname}"
            exists = fpath.exists()
            poses_data.append({
                "code": code,
                "label": label,
                "filename": fname,
                "rel_path": rel_path,
                "exists": exists,
            })
            
        cards_data.append({
            "combo_id": combo_id,
            "char": char,
            "char_korean": char_korean,
            "partner": partner,
            "tag": tag,
            "desc": desc,
            "poses": poses_data,
        })

    json_cards = json.dumps(cards_data, ensure_ascii=False)

    html_content = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Ratatata74 하이브리드 화풍 25선 벤치마크 (총 125장)</title>
<style>
  :root {{
    --bg-main: #0f111a;
    --bg-card: #181b2a;
    --bg-hover: #22263d;
    --text-main: #f1f5f9;
    --text-muted: #94a3b8;
    --accent: #f43f5e;
    --accent-glow: rgba(244, 63, 94, 0.35);
    --border: #2e344d;
    --tag-bg: #2d1824;
    --tag-text: #fda4af;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background-color: var(--bg-main);
    color: var(--text-main);
    font-family: -apple-system, BlinkMacSystemFont, "Pretendard", "Segoe UI", Roboto, sans-serif;
    padding: 16px;
    line-height: 1.5;
  }}
  header {{
    text-align: center;
    padding: 24px 12px 16px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 20px;
  }}
  h1 {{
    font-size: 1.5rem;
    font-weight: 800;
    color: #fff;
    margin-bottom: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    flex-wrap: wrap;
  }}
  .badge-ratatata {{
    background: linear-gradient(135deg, #e11d48, #be123c);
    color: #fff;
    font-size: 0.85rem;
    padding: 2px 10px;
    border-radius: 9999px;
    font-weight: 700;
  }}
  .subtitle {{
    color: var(--text-muted);
    font-size: 0.88rem;
  }}
  .controls {{
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    justify-content: center;
    margin-bottom: 20px;
    position: sticky;
    top: 10px;
    z-index: 100;
    background: rgba(15, 17, 26, 0.9);
    backdrop-filter: blur(8px);
    padding: 10px;
    border-radius: 12px;
    border: 1px solid var(--border);
  }}
  .filter-btn {{
    background: var(--bg-card);
    color: var(--text-muted);
    border: 1px solid var(--border);
    padding: 6px 14px;
    border-radius: 8px;
    cursor: pointer;
    font-size: 0.85rem;
    font-weight: 600;
    transition: all 0.2s;
  }}
  .filter-btn:hover, .filter-btn.active {{
    background: var(--accent);
    color: #fff;
    border-color: var(--accent);
    box-shadow: 0 0 12px var(--accent-glow);
  }}
  .search-input {{
    background: var(--bg-card);
    border: 1px solid var(--border);
    color: #fff;
    padding: 6px 14px;
    border-radius: 8px;
    font-size: 0.85rem;
    outline: none;
    min-width: 180px;
  }}
  .grid {{
    display: flex;
    flex-direction: column;
    gap: 24px;
    max-width: 1400px;
    margin: 0 auto;
  }}
  .artist-card {{
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 16px;
    transition: transform 0.2s, box-shadow 0.2s;
  }}
  .artist-card:hover {{
    border-color: var(--accent);
    box-shadow: 0 4px 20px rgba(0,0,0,0.4);
  }}
  .card-header {{
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 12px;
    border-bottom: 1px solid rgba(255,255,255,0.06);
    padding-bottom: 10px;
    flex-wrap: wrap;
    gap: 8px;
  }}
  .artist-title {{
    font-size: 1.15rem;
    font-weight: 800;
    color: #fff;
    display: flex;
    align-items: center;
    gap: 8px;
  }}
  .char-tag {{
    font-size: 0.75rem;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 6px;
  }}
  .char-tag.hay {{ background: #1e293b; color: #94a3b8; border: 1px solid #334155; }}
  .char-tag.yua {{ background: #3b1d28; color: #f472b6; border: 1px solid #701a35; }}
  .prompt-tag {{
    background: var(--tag-bg);
    color: var(--tag-text);
    font-family: monospace;
    font-size: 0.8rem;
    padding: 3px 8px;
    border-radius: 6px;
    border: 1px solid rgba(244, 63, 94, 0.3);
  }}
  .artist-desc {{
    font-size: 0.85rem;
    color: var(--text-muted);
    width: 100%;
    margin-top: 4px;
  }}
  .images-row {{
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 10px;
  }}
  @media (max-width: 900px) {{
    .images-row {{ grid-template-columns: repeat(3, 1fr); }}
  }}
  @media (max-width: 600px) {{
    .images-row {{ grid-template-columns: repeat(2, 1fr); }}
  }}
  .img-slot {{
    background: rgba(0,0,0,0.3);
    border-radius: 8px;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    position: relative;
    border: 1px solid rgba(255,255,255,0.04);
  }}
  .img-slot img {{
    width: 100%;
    aspect-ratio: 832 / 1216;
    object-fit: cover;
    display: block;
    cursor: pointer;
    transition: opacity 0.2s;
  }}
  .img-slot img:hover {{
    opacity: 0.9;
  }}
  .img-placeholder {{
    width: 100%;
    aspect-ratio: 832 / 1216;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    color: #475569;
    font-size: 0.8rem;
    background: #0d0f17;
  }}
  .img-label {{
    padding: 6px;
    text-align: center;
    font-size: 0.75rem;
    font-weight: 600;
    color: #cbd5e1;
    background: rgba(15, 17, 26, 0.85);
  }}
  .pose-code {{
    color: var(--accent);
    font-weight: 700;
  }}
  /* 모달 */
  .modal {{
    display: none;
    position: fixed;
    top: 0; left: 0; width: 100%; height: 100%;
    background: rgba(0,0,0,0.92);
    z-index: 1000;
    justify-content: center;
    align-items: center;
    padding: 20px;
  }}
  .modal img {{
    max-width: 95vw;
    max-height: 90vh;
    border-radius: 8px;
    box-shadow: 0 0 30px rgba(0,0,0,0.8);
    object-fit: contain;
  }}
</style>
</head>
<body>

<header>
  <h1>
    <span class="badge-ratatata">Ratatata74</span>
    <span>하이브리드 화풍 25선 벤치마크 (125장)</span>
  </h1>
  <div class="subtitle">
    Ratatata74의 쫀득한 윤기/육감 바디 + 25인 메이저 작가의 선화·눈동자·채색 황금비율 융합
  </div>
</header>

<div class="controls">
  <button class="filter-btn active" onclick="filterChar('all')">전체 (25개 조합)</button>
  <button class="filter-btn" onclick="filterChar('hay')">설하율 (13조합 · 쿨뷰티/단아)</button>
  <button class="filter-btn" onclick="filterChar('yua')">설유아 (12조합 · 앙큼/도발/갸루)</button>
  <input type="text" class="search-input" placeholder="작가명 검색..." oninput="searchArtist(this.value)">
</div>

<main class="grid" id="artistGrid"></main>

<div class="modal" id="imgModal" onclick="closeModal()">
  <img id="modalImg" src="" alt="확대 이미지">
</div>

<script>
  const cardsData = {json_cards};

  function renderCards(data) {{
    const grid = document.getElementById("artistGrid");
    grid.innerHTML = "";
    
    data.forEach(item => {{
      const card = document.createElement("div");
      card.className = "artist-card";
      card.dataset.char = item.char;
      card.dataset.partner = item.partner.toLowerCase();
      
      let posesHtml = "";
      item.poses.forEach(p => {{
        if (p.exists) {{
          posesHtml += `
            <div class="img-slot">
              <img src="${{p.rel_path}}" alt="${{p.label}}" onclick="openModal('${{p.rel_path}}')" loading="lazy">
              <div class="img-label"><span class="pose-code">${{p.code}}</span> ${{p.label}}</div>
            </div>
          `;
        }} else {{
          posesHtml += `
            <div class="img-slot">
              <div class="img-placeholder">
                <div>⏳ 생성 대기</div>
                <div style="font-size:0.7rem; margin-top:4px;">${{p.code}} ${{p.label}}</div>
              </div>
              <div class="img-label"><span class="pose-code">${{p.code}}</span> ${{p.label}}</div>
            </div>
          `;
        }}
      }});
      
      card.innerHTML = `
        <div class="card-header">
          <div class="artist-title">
            <span>${{item.combo_id}} : Ratatata74 × ${{item.partner}}</span>
            <span class="char-tag ${{item.char}}">${{item.char_korean}}</span>
          </div>
          <span class="prompt-tag">${{item.tag}}</span>
          <div class="artist-desc">💡 ${{item.desc}}</div>
        </div>
        <div class="images-row">
          ${{posesHtml}}
        </div>
      `;
      grid.appendChild(card);
    }});
  }}

  let currentChar = 'all';
  let currentSearch = '';

  function applyFilters() {{
    const filtered = cardsData.filter(item => {{
      const matchChar = (currentChar === 'all') || (item.char === currentChar);
      const matchSearch = !currentSearch || 
        item.partner.toLowerCase().includes(currentSearch) ||
        item.combo_id.toLowerCase().includes(currentSearch) ||
        item.desc.toLowerCase().includes(currentSearch);
      return matchChar && matchSearch;
    }});
    renderCards(filtered);
  }}

  function filterChar(char) {{
    currentChar = char;
    document.querySelectorAll(".filter-btn").forEach(btn => btn.classList.remove("active"));
    event.target.classList.add("active");
    applyFilters();
  }}

  function searchArtist(query) {{
    currentSearch = query.trim().toLowerCase();
    applyFilters();
  }}

  function openModal(src) {{
    const modal = document.getElementById("imgModal");
    const img = document.getElementById("modalImg");
    img.src = src;
    modal.style.display = "flex";
  }}

  function closeModal() {{
    document.getElementById("imgModal").style.display = "none";
  }}

  // 초기 렌더링
  renderCards(cardsData);
</script>

</body>
</html>
"""
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    return html_path


def main():
    parser = argparse.ArgumentParser(description="Ratatata74 하이브리드 화풍 25선 벤치마크 러너")
    parser.add_argument("--mock", action="store_true", help="0.1초 가상 파일 생성으로 HTML 뷰어 검증")
    parser.add_argument("--dry-run", action="store_true", help="생성 없이 프롬프트 및 설정 점검")
    parser.add_argument("--char", choices=["hay", "yua"], default=None, help="특정 캐릭터만 실행")
    parser.add_argument("--combo", type=str, default=None, help="특정 조합 번호/ID만 실행 (예: 01, hiten)")
    args = parser.parse_args()

    benchmark_dir = PROJECTS_DIR / "ykn" / "artist_benchmark_ratatata"
    benchmark_dir.mkdir(parents=True, exist_ok=True)

    # 작업 필터링
    selected_combos = []
    for cid, char, partner, tag, desc in RATATATA_COMBOS:
        if args.char and char != args.char:
            continue
        if args.combo and (args.combo not in cid and args.combo.lower() not in partner.lower()):
            continue
        selected_combos.append({
            "combo_id": cid,
            "char": char,
            "partner": partner,
            "tag": tag,
            "desc": desc,
        })

    total_tasks = len(selected_combos) * len(BENCHMARK_POSES)
    print("=" * 80)
    print(f" [RATATATA MIX BENCHMARK] 총 {len(selected_combos)}개 조합 × 5개 포즈 = 총 {total_tasks}장 렌더링")
    print(f" 저장 위치: {benchmark_dir}")
    print("=" * 80)

    # 1. HTML 뷰어 선제 생성
    html_file = generate_html_viewer(benchmark_dir, selected_combos)
    print(f"[HTML 뷰어 생성 완료] {html_file}")

    if args.mock:
        print("[MOCK 모드] 0.1초 가상 파일 생성 중...")
        for c in selected_combos:
            combo_dir = benchmark_dir / c["combo_id"]
            combo_dir.mkdir(parents=True, exist_ok=True)
            for code in BENCHMARK_POSES:
                lbl = POSE_LABELS[code]
                fname = f"{c['char']}_{code}_{lbl}.webp"
                (combo_dir / fname).write_text("mock webp")
        generate_html_viewer(benchmark_dir, selected_combos)
        print("[MOCK 완료] 가상 이미지 생성 및 뷰어 갱신 완료.")
        return

    if args.dry_run:
        print("[DRY-RUN 모드] 프롬프트 조립 시뮬레이션:")
        for idx, c in enumerate(selected_combos, 1):
            print(f"  [{idx}/{len(selected_combos)}] {c['combo_id']} ({c['char']}): {c['tag']} - {c['desc']}")
        return

    # 실 생성 러너 구동
    service = GenerationService()
    success_count = 0
    fail_count = 0
    start_time = time.time()

    for c_idx, c in enumerate(selected_combos, 1):
        combo_id = c["combo_id"]
        char = c["char"]
        partner = c["partner"]
        tag = c["tag"]
        combo_dir = benchmark_dir / combo_id
        combo_dir.mkdir(parents=True, exist_ok=True)

        print("\n" + "-" * 75)
        print(f" [{c_idx}/{len(selected_combos)}] 조합 시작: {combo_id} (캐릭터: {char})")
        print(f" 태그: {tag} ({c['desc']})")
        print("-" * 75)

        for p_idx, code in enumerate(BENCHMARK_POSES, 1):
            label = POSE_LABELS[code]
            target_filename = f"{char}_{code}_{label}.webp"
            final_target_path = combo_dir / target_filename

            # 이미 완비된 경우 스마트 스킵
            if final_target_path.exists() and final_target_path.stat().st_size > 5000:
                print(f"  [{p_idx}/5] 스킵 (이미 완료됨): {target_filename}")
                success_count += 1
                continue

            print(f"  [{p_idx}/5] 렌더링 시작: 포즈 {code} ({label}) -> {target_filename}")

            params = GenerationParams(
                character_expr=char,
                pose_expr=code,
                roster="ykn",
                custom_pos=tag,
                ckpt_tag=f"mix_{combo_id}",
                overwrite=True,
                engine="sdxl",
                censor=True,
                mock=args.mock,
                dry_run=args.dry_run,
                no_ref=True,  # 순수 화풍 영향력을 위해 IP-Adapter 비활성화
            )

            try:
                res = service.run_batch(params, quiet=True)
                if res and res[0].success:
                    gen_path = res[0].image_path
                    if gen_path and Path(gen_path).exists():
                        shutil.copy2(gen_path, final_target_path)
                        print(f"  [완료] 저장 완료: {final_target_path.name} ({final_target_path.stat().st_size // 1024} KB)")
                        success_count += 1
                    else:
                        print(f"  [경고] 이미지 파일 경로 없음: {target_filename}")
                        fail_count += 1
                else:
                    err_msg = res[0].error_message if res else "Unknown Error"
                    print(f"  [오류] 포즈 {code} 생성 실패: {err_msg}")
                    fail_count += 1

            except Exception as e:
                print(f"  [예외 발생] 포즈 {code}: {e}")
                fail_count += 1

            # 임시 격리 디렉토리 정리
            temp_isolate_dir = PROJECTS_DIR / "ykn" / "assets" / f"mix_{combo_id}"
            if temp_isolate_dir.exists():
                try:
                    shutil.rmtree(temp_isolate_dir, ignore_errors=True)
                except Exception:
                    pass

        # 1개 조합(5장) 끝날 때마다 HTML 뷰어 실시간 갱신 (진행 상황 실시간 확인 가능)
        generate_html_viewer(benchmark_dir, selected_combos)

    elapsed = time.time() - start_time
    print("\n" + "=" * 80)
    print(f" [RATATATA MIX BENCHMARK 완료]")
    print(f" 성공: {success_count}장 / 실패: {fail_count}장 / 소요 시간: {elapsed:.1f}초")
    print(f" 뷰어 링크: {html_file}")
    print("=" * 80)


if __name__ == "__main__":
    main()
