"""
scripts/run_otoko_benchmark.py
메이드 로스터 오토코노코 3인방 (aoi, ren, yuk) × 5대 핵심 H씬 포즈 × 40인 작가 화풍
Ratatata 하이브리드 스트레스 벤치마크 및 인터랙티브 웹 뷰어 스크립트.

5대 포즈 (사용자 맞춤 선정):
  - 155: 정상위약 (안정적 대면 체위)
  - 158: 후배위약 (후방/골반 앵글)
  - 161: 기승위약 (상하 역전 체위)
  - 188: 교배프레스 (밀착 결합 구도)
  - 189: 들박 (공중 부양 서스펜디드 구도)

사용법:
  python scripts/run_otoko_benchmark.py --mock         # 0.1초 파이프라인 및 HTML 뷰어 검증
  python scripts/run_otoko_benchmark.py --dry-run      # 프롬프트 조립 점검
  python scripts/run_otoko_benchmark.py --char aoi     # 아오이(aoi)만 실행
  python scripts/run_otoko_benchmark.py --char aoi --artist hiten # 특정 작가 단독
  python scripts/run_otoko_benchmark.py                # 전체 벤치마크 실행
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
from plepa_engine.services.character_service import default_character_service

# 5대 대표 오토코노코 H씬 포즈
BENCHMARK_POSES = ["151", "156", "159", "161", "189"]
POSE_LABELS = {
    "151": "대면좌위",
    "156": "정상위강",
    "159": "후배위강",
    "161": "기승위약",
    "189": "들박",
}

# 40인 작가 화풍 풀 (ratatata74와 결합되는 하이브리드 스타일)
ARTISTS_40: List[Tuple[str, str, str]] = [
    # [1~10] 단아함 / 서정적 선화 / 메이저 애니풍
    ("tiv", "(artist:ratatata74:0.8), (artist:tiv:0.8)", "마사무네군의 리벤지 원화 / 맑고 정갈한 선화 미소년"),
    ("hiten", "(artist:ratatata74:0.8), (artist:hiten:0.8)", "서정적인 역광과 차분한 공기감, 흑발 쿨뷰티"),
    ("anmi", "(artist:ratatata74:0.8), (artist:anmi:0.8)", "복숭앗빛 투명 피부와 부드러운 수채 채색"),
    ("morikura_en", "(artist:ratatata74:0.8), (artist:morikura_en:0.8)", "따뜻한 자연광과 섬세한 머릿결 묘사"),
    ("rurudo", "(artist:ratatata74:0.8), (artist:rurudo:0.8)", "핑크/자색 계열의 몽환적 음영과 요염한 셰이딩"),
    ("kurehito_misaki", "(artist:ratatata74:0.8), (artist:kurehito_misaki:0.8)", "사에카노 원화 / 정교한 펜선과 세련된 명암"),
    ("fly", "(artist:ratatata74:0.8), (artist:fly_(flyfly):0.8)", "차분하고 서정적인 청초 감성 일러스트"),
    ("ciloranko", "(artist:ratatata74:0.8), (artist:ciloranko:0.8)", "수채화풍 몽환적 조명과 섬세한 땀방울 디테일"),
    ("atdan", "(artist:ratatata74:0.8), (artist:atdan:0.8)", "깊이 있는 공간감과 섬세한 천 질감 묘사"),
    ("ask", "(artist:ratatata74:0.8), (artist:ask_(askzy):0.8)", "유화 붓 터치와 중후한 화보 표지 무드"),

    # [11~20] 탄탄한 인체 / 웹툰 선화 / 관능미
    ("sho", "(artist:ratatata74:0.8), (artist:sho_(sho_lwlw):0.8)", "모던하고 감각적인 컬러링과 세련된 스타일"),
    ("asagi_syun", "(artist:ratatata74:0.8), (artist:asagi_syun:0.8)", "부드러운 살결 셰이딩과 매끄러운 바디 묘사"),
    ("kurogane_ken", "(artist:ratatata74:0.8), (artist:kurogane_ken:0.8)", "탄력 넘치는 바디라인과 광택 있는 피부 표현"),
    ("mignon", "(artist:ratatata74:0.8), (artist:mignon:0.8)", "매끄럽고 윤기 나는 살결, 요염한 인체 곡선"),
    ("hisasi", "(artist:ratatata74:0.8), (artist:hisasi:0.8)", "탄탄하고 매력적인 인체 비례, 몰입감 높은 표정"),
    ("homunculus", "(artist:ratatata74:0.8), (artist:homunculus:0.8)", "부드럽고 말랑말랑한 푹신한 살결 질감"),
    ("alcheman", "(artist:ratatata74:0.8), (artist:alchemaniac:0.8)", "묵직한 조명 대비와 탄탄한 각선미"),
    ("marushin", "(artist:ratatata74:0.8), (artist:marushin:0.8)", "한국형 성인 웹툰 선화와 매력적인 이목구비"),
    ("chuzenji", "(artist:ratatata74:0.8), (artist:chuzenji:0.8)", "날렵하고 세련된 쿨시크 턱선과 정밀 질감"),
    ("tony_taka", "(artist:ratatata74:0.8), (artist:tony_taka:0.8)", "단정한 고전 미소녀의 완성된 이목구비"),

    # [21~30] 앙큼 & 도발 & 강렬한 색감 / 개성 화풍
    ("kantoku", "(artist:ratatata74:0.8), (artist:kantoku:0.8)", "화사한 체크무늬 의상과 체리빛 볼터치"),
    ("nanashi", "(artist:ratatata74:0.8), (artist:nanashi_(774):0.8)", "나가토로 특유의 앙큼한 눈매와 장난기 어린 도발"),
    ("asanagi", "(artist:ratatata74:0.8), (artist:asanagi:0.8)", "탄탄하고 묵직한 골반과 육덕 하체 실루엣"),
    ("mizuryu_kei", "(artist:ratatata74:0.8), (artist:mizuryu_kei:0.8)", "달아오른 절정 얼굴, 혀 내밀기, 하트눈 표정"),
    ("kappe", "(artist:ratatata74:0.8), (artist:kappe:0.8)", "반짝이는 애니메이션 셀 채색과 도회적 인상"),
    ("guira", "(artist:ratatata74:0.8), (artist:guira:0.8)", "오일을 바른 듯 촉촉한 글로시 립과 바디 광택"),
    ("cogecha", "(artist:ratatata74:0.8), (artist:cogecha:0.8)", "오묘한 보랏빛/핑크빛 잔선과 화려한 그러데이션"),
    ("wlop", "(artist:ratatata74:0.8), (artist:wlop:0.8)", "신비로운 반사광과 메탈릭한 장신구 텍스처"),
    ("mika_pikazo", "(artist:ratatata74:0.8), (artist:mika_pikazo:0.8)", "비비드한 원색과 보석처럼 빛나는 화려한 눈동자"),
    ("lam", "(artist:ratatata74:0.8), (artist:lam_(ramu):0.8)", "카리스마 있는 아이라인과 앙칼진 눈빛"),

    # [31~40] 역동적 텐션 / 일러스트 거장 / 인기 동인지풍
    ("yoneyama_mai", "(artist:ratatata74:0.8), (artist:yoneyama_mai:0.8)", "유리 같은 굴절과 역동적인 포즈 텐션"),
    ("redrop", "(artist:ratatata74:0.8), (artist:redrop:0.8)", "FGO 공식 일러스트급 화려함과 레이스 디테일"),
    ("cutesexyrobutts", "(artist:ratatata74:0.8), (artist:cutesexyrobutts:0.8)", "탄력 넘치는 힙/허벅지와 과감한 앵글"),
    ("waterkuma", "(artist:ratatata74:0.8), (artist:waterkuma:0.8)", "투명한 물방울과 촉촉한 피부 하이라이트"),
    ("infinote", "(artist:ratatata74:0.8), (artist:infinote:0.8)", "또렷하고 샤프한 디지털 채색과 이목구비"),
    ("shindol", "(artist:ratatata74:0.8), (artist:shindol:0.8)", "하드코어 동인지 선화와 강렬한 쾌락 표정"),
    ("kuroda_bb", "(artist:ratatata74:0.8), (artist:kuroda_bb:0.8)", "동글동글 귀여운 눈망울과 부드러운 라인"),
    ("derpys", "(artist:ratatata74:0.8), (artist:derpys:0.8)", "풍만한 골반 볼륨과 매력적인 하체 라인"),
    ("towa", "(artist:ratatata74:0.8), (artist:towa:0.8)", "자연스러운 채색과 따스한 감성 일러스트"),
    ("reina", "(artist:ratatata74:0.8), (artist:reina:0.8)", "세련된 흑백 명암과 날카로운 시선 처리"),
]


def generate_html_viewer(benchmark_dir: Path, tasks: List[Dict]) -> Path:
    """오토코노코 벤치마크 전용 모던 반응형 인터랙티브 HTML 뷰어 생성."""
    html_path = benchmark_dir / "index.html"

    cards_json = json.dumps(tasks, ensure_ascii=False)

    html_content = f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>PLEPA 오토코노코 40인 화풍 H씬 벤치마크</title>
  <style>
    :root {{
      --bg: #0f1117;
      --card-bg: #1a1d27;
      --border: #2e3446;
      --accent: #ec4899;
      --accent-glow: rgba(236, 72, 153, 0.35);
      --text: #f3f4f6;
      --text-muted: #9ca3af;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Pretendard", sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
      padding-bottom: 60px;
    }}
    header {{
      background: linear-gradient(180deg, #1f1b2e 0%, var(--bg) 100%);
      padding: 24px 16px;
      text-align: center;
      border-bottom: 1px solid var(--border);
      position: sticky;
      top: 0;
      z-index: 50;
      backdrop-filter: blur(8px);
    }}
    h1 {{
      font-size: 1.3rem;
      font-weight: 800;
      background: linear-gradient(90deg, #f472b6, #ec4899, #a855f7);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      margin-bottom: 6px;
    }}
    .subtitle {{
      font-size: 0.82rem;
      color: var(--text-muted);
    }}
    .tabs {{
      display: flex;
      justify-content: center;
      gap: 8px;
      margin-top: 14px;
    }}
    .tab-btn {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      color: var(--text-muted);
      padding: 6px 16px;
      border-radius: 20px;
      font-size: 0.85rem;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s;
    }}
    .tab-btn.active {{
      background: var(--accent);
      color: white;
      border-color: var(--accent);
      box-shadow: 0 0 12px var(--accent-glow);
    }}
    .container {{
      max-width: 1400px;
      margin: 20px auto;
      padding: 0 12px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
      gap: 16px;
    }}
    .card {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      overflow: hidden;
      display: flex;
      flex-direction: column;
    }}
    .card-header {{
      padding: 10px 14px;
      background: rgba(0,0,0,0.25);
      border-bottom: 1px solid var(--border);
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    .artist-name {{
      font-weight: 700;
      font-size: 0.95rem;
      color: #fbcfe8;
    }}
    .combo-desc {{
      font-size: 0.75rem;
      color: var(--text-muted);
      margin-top: 2px;
    }}
    .poses-row {{
      display: grid;
      grid-template-columns: repeat(5, 1fr);
      gap: 4px;
      padding: 8px;
    }}
    .pose-item {{
      text-align: center;
      cursor: pointer;
    }}
    .pose-thumb {{
      width: 100%;
      aspect-ratio: 832 / 1216;
      object-fit: cover;
      border-radius: 6px;
      background: #111;
      border: 1px solid rgba(255,255,255,0.05);
      transition: transform 0.2s;
    }}
    .pose-thumb:hover {{
      transform: scale(1.04);
      border-color: var(--accent);
    }}
    .pose-title {{
      font-size: 0.65rem;
      color: var(--text-muted);
      margin-top: 3px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    /* Modal Lightbox */
    #lightbox {{
      display: none;
      position: fixed;
      inset: 0;
      background: rgba(0,0,0,0.92);
      z-index: 100;
      align-items: center;
      justify-content: center;
      flex-direction: column;
      padding: 16px;
    }}
    #lightbox img {{
      max-width: 95vw;
      max-height: 85vh;
      object-fit: contain;
      border-radius: 8px;
      box-shadow: 0 0 30px rgba(0,0,0,0.8);
    }}
    #lb-caption {{
      color: white;
      margin-top: 12px;
      font-size: 0.9rem;
      text-align: center;
    }}
  </style>
</head>
<body>
  <header>
    <h1>💋 PLEPA 오토코노코 40인 화풍 5대 H씬 벤치마크</h1>
    <div class="subtitle">Ratatata74 하이브리드 조합 × 메이드 3인방 (아오이 / 렌 / 유키)</div>
    <div class="tabs">
      <button class="tab-btn active" onclick="filterChar('all')">전체보기</button>
      <button class="tab-btn" onclick="filterChar('aoi')">아오이 (Aoi)</button>
      <button class="tab-btn" onclick="filterChar('ren')">렌 (Ren)</button>
      <button class="tab-btn" onclick="filterChar('yuk')">유키 (Yuki)</button>
    </div>
  </header>

  <div class="container">
    <div id="grid" class="grid"></div>
  </div>

  <div id="lightbox" onclick="closeLightbox()">
    <img id="lb-img" src="" alt="preview">
    <div id="lb-caption"></div>
  </div>

  <script>
    const data = {cards_json};
    let currentChar = 'all';

    function render() {{
      const grid = document.getElementById('grid');
      grid.innerHTML = '';
      const filtered = currentChar === 'all' ? data : data.filter(d => d.char === currentChar);

      filtered.forEach(item => {{
        const card = document.createElement('div');
        card.className = 'card';
        card.innerHTML = `
          <div class="card-header">
            <div>
              <div class="artist-name">#${{item.combo_id}} · ${{item.char_name}} × ${{item.partner}}</div>
              <div class="combo-desc">${{item.desc}}</div>
            </div>
          </div>
          <div class="poses-row">
            ${{item.poses.map(p => `
              <div class="pose-item" onclick="openLightbox('${{p.url}}', '${{item.char_name}} [${{item.partner}}] #${{p.code}} ${{p.label}}')">
                <img class="pose-thumb" src="${{p.url}}" loading="lazy" alt="${{p.label}}">
                <div class="pose-title">${{p.label}}</div>
              </div>
            `).join('')}}
          </div>
        `;
        grid.appendChild(card);
      }});
    }}

    function filterChar(c) {{
      currentChar = c;
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      event.target.classList.add('active');
      render();
    }}

    function openLightbox(url, caption) {{
      document.getElementById('lb-img').src = url;
      document.getElementById('lb-caption').textContent = caption;
      document.getElementById('lightbox').style.display = 'flex';
    }}

    function closeLightbox() {{
      document.getElementById('lightbox').style.display = 'none';
    }}

    render();
  </script>
</body>
</html>
"""
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    return html_path


def main():
    parser = argparse.ArgumentParser(description="오토코노코 40인 화풍 5대 H씬 벤치마크")
    parser.add_argument("--char", choices=["aoi", "ren", "yuk", "all"], default="all", help="대상 캐릭터 (기본: all)")
    parser.add_argument("--artist", type=str, default=None, help="특정 작가 ID 단독 실행 (예: hiten)")
    parser.add_argument("--mock", action="store_true", help="더미 이미지 초고속 생성으로 파이프라인/HTML 검증")
    parser.add_argument("--dry-run", action="store_true", help="생성 없이 프롬프트 조립 점검")
    parser.add_argument("--overwrite", action="store_true", help="기존 벤치마크 결과물 덮어쓰기")
    parser.add_argument("--limit", type=int, default=None, help="실행할 작가 수 제한 (테스트용)")
    parser.add_argument("--pose", type=str, default=None, help="특정 포즈 코드 단독 실행 (예: 151)")
    args = parser.parse_args()

    roster = "maid"
    bench_dir = PROJECTS_DIR / roster / "otoko_benchmark"
    bench_dir.mkdir(parents=True, exist_ok=True)

    target_chars = ["aoi", "ren", "yuk"] if args.char == "all" else [args.char]
    char_names = {"aoi": "아오이", "ren": "렌", "yuk": "유키"}

    artists = ARTISTS_40
    if args.artist:
        artists = [a for a in artists if a[0].lower() == args.artist.lower()]
        if not artists:
            print(f"[오류] 일치하는 작가를 찾을 수 없습니다: {args.artist}")
            return
    if args.limit:
        artists = artists[:args.limit]

    benchmark_poses = [args.pose] if args.pose else BENCHMARK_POSES
    total_tasks = len(target_chars) * len(artists) * len(benchmark_poses)
    print("=" * 70)
    print(f"  [플에파] 오토코노코 40인 화풍 5대 H씬 벤치마크 (mock={args.mock}, dry_run={args.dry_run})")
    print(f"• 대상 캐릭터: {', '.join(target_chars)} (총 {len(target_chars)}명)")
    print(f"• 작가 화풍: 총 {len(artists)}개 조합")
    print(f"• 5대 H씬 포즈: {', '.join(f'#{k} {v}' for k, v in POSE_LABELS.items())}")
    print(f"• 총 렌더링 예정: {total_tasks}장 ({len(target_chars)}명 × {len(artists)}작가 × 5포즈)")
    print(f"• 저장 경로: {bench_dir}")
    print("=" * 70)

    gen_svc = GenerationService()
    cards_data = []

    for char_code in target_chars:
        c_name = char_names.get(char_code, char_code)
        for idx, (a_id, a_tag, a_desc) in enumerate(artists, 1):
            combo_folder_name = f"{char_code}_{a_id}"
            out_combo_dir = bench_dir / combo_folder_name
            out_combo_dir.mkdir(parents=True, exist_ok=True)

            print(f"\n▶ [{char_code.upper()} {idx:02d}/{len(artists):02d}] {c_name} × {a_id} ({a_desc})")

            poses_list = []
            for p_code in benchmark_poses:
                p_label = POSE_LABELS[p_code]
                fname = f"{char_code}_{p_code}_{p_label}.webp"
                fpath = out_combo_dir / fname

                if args.mock:
                    if not fpath.exists():
                        from PIL import Image, ImageDraw
                        im = Image.new("RGB", (832, 1216), color=(40, 30, 50))
                        draw = ImageDraw.Draw(im)
                        draw.text((40, 60), f"Mock Otoko Benchmark", fill=(255, 255, 255))
                        draw.text((40, 100), f"Char: {c_name} ({char_code})", fill=(240, 180, 220))
                        draw.text((40, 140), f"Artist: {a_id}", fill=(200, 220, 255))
                        draw.text((40, 180), f"Pose: #{p_code} {p_label}", fill=(255, 255, 100))
                        im.save(fpath, "WEBP", quality=85)
                    print(f"  - #{p_code} {p_label:<10} -> {fname} [MOCK 완료]")
                elif not args.dry_run and fpath.exists() and not args.overwrite:
                    print(f"  - #{p_code} {p_label:<10} -> {fname} [SKIP: 이미 존재함]")
                elif not args.dry_run:
                    # 실 생성 호출
                    params = GenerationParams(
                        character_expr=char_code,
                        pose_expr=p_code,
                        roster=roster,
                        engine="sdxl",
                        overwrite=True,
                        custom_pos=a_tag,
                        ckpt_tag=f"otoko_tmp_{char_code}",
                        censor=True,
                    )
                    res = gen_svc.run_batch(params=params, quiet=True)
                    # 생성된 결과물을 벤치마크 디렉터리로 복사 이동
                    tmp_created = list((PROJECTS_DIR / roster / "assets" / char_code / f"ckpt_otoko_tmp_{char_code}").rglob(f"*{p_code}*.webp"))
                    if tmp_created:
                        shutil.copy2(tmp_created[0], fpath)
                    print(f"  - #{p_code} {p_label:<10} -> {fname} [생성 완료]" if tmp_created else f"  - #{p_code} {p_label:<10} -> {fname} [생성 실패]")
                else:
                    print(f"  - #{p_code} {p_label:<10} -> {fname} [DRY-RUN]")

                poses_list.append({
                    "code": p_code,
                    "label": p_label,
                    "filename": fname,
                    "url": f"{combo_folder_name}/{fname}",
                })

            cards_data.append({
                "combo_id": f"{char_code}_{a_id}",
                "char": char_code,
                "char_name": c_name,
                "partner": a_id,
                "tag": a_tag,
                "desc": a_desc,
                "poses": poses_list,
            })

    html_file = generate_html_viewer(bench_dir, cards_data)
    print("\n" + "=" * 70)
    print(f"✨ 오토코노코 벤치마크 완료! HTML 뷰어가 성공적으로 생성되었습니다.")
    print(f"• 인터랙티브 뷰어 경로: {html_file}")
    print("=" * 70)


if __name__ == "__main__":
    main()
