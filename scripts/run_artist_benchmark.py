"""
scripts/run_artist_benchmark.py
YKN 로스터 (hay 20명 + yua 20명 = 총 40명 작가) × 5대 대표 포즈 (000, 028, 076, 095, 106)
총 200장 작가 화풍 스트레스 벤치마크 일괄 생성 및 인터랙티브 HTML 뷰어 자동 생성 스크립트.

사용법:
  python scripts/run_artist_benchmark.py --mock         # 0.1초 파이프라인 및 HTML 뷰어 검증
  python scripts/run_artist_benchmark.py --dry-run      # 프롬프트 및 설정 사전 점검
  python scripts/run_artist_benchmark.py                # 200장 본 생성 실행
  python scripts/run_artist_benchmark.py --char hay     # 하율(hay) 20명(100장)만 실행
  python scripts/run_artist_benchmark.py --char yua     # 유아(yua) 20명(100장)만 실행
  python scripts/run_artist_benchmark.py --artist tiv   # 특정 작가 1명(5장)만 단독 실행
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

# 하율(hay) 20인 작가 매핑: 쿨시크 / 흑발세미롱 / 샤프한 선화 / 글래머 셰이딩 특화
HAY_ARTISTS: List[Tuple[str, str, str]] = [
    ("tiv", "(artist:tiv:1.15)", "마사무네군의 리벤지 원화 / 맑고 정갈한 선화, 실패율 0% 미소녀"),
    ("hiten", "(artist:hiten:1.15)", "서정적인 빛과 차분한 공기감, 흑발 쿨뷰티 최적화"),
    ("rurudo", "(artist:rurudo:1.15)", "핑크/자색 계열의 몽환적 음영, 요염한 미소녀 셰이딩"),
    ("kurehito_misaki", "(artist:kurehito_misaki:1.15)", "사에카노 원화 / 정교한 펜선과 세련된 명암"),
    ("fly", "(artist:fly_(flyfly):1.15)", "약캐 토모자키군 / 차분하고 서정적인 감성 일러스트"),
    ("ciloranko", "(artist:ciloranko:1.15)", "수채화풍 몽환적 조명과 섬세하게 반짝이는 눈망울"),
    ("atdan", "(artist:atdan:1.15)", "깊이 있는 공기감과 섬세한 의상/천 질감 묘사"),
    ("ask", "(artist:ask_(askzy):1.15)", "극도로 정밀한 명암비와 깊고 그윽한 눈매"),
    ("sho", "(artist:sho_(sho_lwlw):1.15)", "모던하고 감각적인 컬러링과 세련된 패션"),
    ("asagi_syun", "(artist:asagi_syun:1.15)", "부드러운 살결 셰이딩과 풍만한 볼륨감 묘사"),
    ("kurogane_ken", "(artist:kurogane_ken:1.15)", "탄력 넘치는 바디라인과 광택 있는 피부 표현"),
    ("mignon", "(artist:mignon:1.15)", "매끄럽고 윤기 나는 살결, 요염한 인체 곡선"),
    ("hisasi", "(artist:hisasi:1.15)", "탄탄하고 매력적인 인체 비례, 몰입감 높은 표정"),
    ("urushihara_satoshi", "(artist:urushihara_satoshi:1.15)", "극상의 피부 광택 하이라이트와 클래식 글래머"),
    ("tony_taka", "(artist:tony_taka:1.15)", "샤이닝 시리즈 / 클래식 미소녀 일러스트의 정석"),
    ("magicians", "(artist:magicians:1.15)", "단정하면서도 세련된 현대 미소녀 셀화"),
    ("range_murata", "(artist:range_murata:1.15)", "레트로 모던, 독특한 의상 질감과 입체감"),
    ("shunya_yamashita", "(artist:shunya_yamashita:1.15)", "피규어 조형미와 매혹적인 눈빛 묘사"),
    ("popman3580", "(artist:popman3580:1.15)", "감각적인 색감과 트렌디한 일러스트 감성"),
    ("blade", "(artist:blade_(blade4649):1.15)", "샤프한 펜선과 건강미 넘치는 바디 실루엣"),
]

# 유아(yua) 20인 작가 매핑: 메가데레 / 사이드테일 / 따뜻한 파스텔 채색 / 풍만 볼륨 특화
YUA_ARTISTS: List[Tuple[str, str, str]] = [
    ("anmi", "(artist:anmi:1.15)", "소녀전선 수오미 / 부드러운 파스텔톤, 투명한 피부 질감"),
    ("kantoku", "(artist:kantoku:1.15)", "변웃고 / 정교한 역광 표현, 미려한 각선미와 옷 주름"),
    ("morikura_en", "(artist:morikura_en:1.15)", "키즈나 아이 원화 / 자연스럽고 사랑스러운 데일리 룩"),
    ("kappe", "(artist:kappe:1.15)", "렌탈여친 작화감독 / 생동감 넘치는 최신 TV 애니 셀화"),
    ("fuzichoco", "(artist:fuzichoco:1.15)", "화려한 색채감, 압도적인 디테일과 몽환적인 조명"),
    ("necomi", "(artist:necömi:1.15)", "풍부한 채도와 부드럽게 감싸는 따뜻한 빛 연출"),
    ("ogipote", "(artist:ogipote:1.15)", "드라마틱한 역광과 바람에 흩날리는 머리카락 결"),
    ("homunculus", "(artist:homunculus:1.15)", "묵직한 가슴/골반 음영, 육감적인 성인 체형의 교과서"),
    ("marushin", "(artist:marushin:1.15)", "쫀득하고 부드러운 질감의 살결과 글래머 체형"),
    ("reia", "(artist:reia_(r-e-i-a):1.15)", "풍만한 볼륨감과 청초하면서도 에로틱한 얼굴선"),
    ("yabuki_kentaro", "(artist:yabuki_kentaro:1.15)", "투러브트러블 / 완벽한 선화와 매혹적인 앵글"),
    ("alchemaniac", "(artist:alchemaniac:1.15)", "벽람항로 등 / 풍만한 곡선과 화려한 바디 조화"),
    ("ui_shigure", "(artist:ui_shigure:1.15)", "특유의 따뜻하고 정갈한 미소녀 감성, 단정한 톤"),
    ("fukahire", "(artist:fukahire:1.15)", "둥글고 부드러운 볼선, 포근한 파스텔 채색"),
    ("kakao", "(artist:kakao_(kakao_lanthanum):1.15)", "쫀득한 피부 표현과 귀엽고 요염한 이목구비"),
    ("momoko", "(artist:momoko_(momopoco):1.15)", "서정적이고 맑은 미소녀 채색, 섬세한 감정"),
    ("torino", "(artist:torino_(torinone):1.15)", "극상의 완성도와 디테일한 조명, 세련된 화풍"),
    ("nanashi", "(artist:nanashi_(774):1.15)", "나가토로 작가 / 생생한 표정 변화와 매력적인 체형"),
    ("crimson", "(artist:crimson:1.15)", "직관적이고 강렬한 성인 체위 묘사와 표정"),
    ("mika_pikazo", "(artist:mika_pikazo:1.15)", "눈에 확 띄는 화려한 비비드 컬러와 에너지 넘치는 채색"),
]


def generate_html_viewer(benchmark_dir: Path, tasks: List[Dict]) -> Path:
    """작가별, 포즈별로 한눈에 비교할 수 있는 모던 인터랙티브 HTML 뷰어 생성."""
    html_path = benchmark_dir / "index.html"
    
    # 작업 데이터 구성
    cards_data = []
    for t in tasks:
        char = t["char"]
        artist_id = t["artist_id"]
        artist_desc = t["desc"]
        artist_tag = t["tag"]
        pose_imgs = {}
        for p in BENCHMARK_POSES:
            img_rel = f"{char}_{artist_id}/{char}_{p}_{artist_id}.webp"
            img_full = benchmark_dir / img_rel
            pose_imgs[p] = img_rel if img_full.exists() else ""
        cards_data.append({
            "char": char,
            "char_name": "설하율 (hay)" if char == "hay" else "설유아 (yua)",
            "artist_id": artist_id,
            "artist_desc": artist_desc,
            "artist_tag": artist_tag,
            "poses": pose_imgs,
        })

    json_str = json.dumps(cards_data, ensure_ascii=False)

    html_content = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PLEPA YKN 작가 화풍 벤치마크 (200장)</title>
<style>
  :root {{
    --bg-color: #0f1117;
    --card-bg: #1a1d27;
    --accent: #8b5cf6;
    --accent-hover: #7c3aed;
    --text: #e2e8f0;
    --text-muted: #94a3b8;
    --border: #2d3748;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: var(--bg-color);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    padding: 20px;
    line-height: 1.5;
  }}
  header {{
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: center;
    padding-bottom: 20px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 20px;
    gap: 15px;
  }}
  h1 {{ font-size: 1.5rem; color: #fff; display: flex; align-items: center; gap: 10px; }}
  .badge {{ background: var(--accent); color: #fff; font-size: 0.8rem; padding: 3px 8px; border-radius: 9999px; }}
  .controls {{ display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }}
  button, select {{
    background: #242938;
    color: var(--text);
    border: 1px solid var(--border);
    padding: 8px 14px;
    border-radius: 8px;
    font-size: 0.9rem;
    cursor: pointer;
    transition: all 0.2s;
  }}
  button:hover, select:hover {{ background: #2e3547; border-color: var(--accent); }}
  button.active {{ background: var(--accent); color: #fff; border-color: var(--accent); }}
  .grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
    gap: 20px;
  }}
  .card {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    transition: transform 0.2s, border-color 0.2s;
  }}
  .card:hover {{ transform: translateY(-4px); border-color: var(--accent); }}
  .card-header {{
    padding: 12px 15px;
    border-bottom: 1px solid var(--border);
    display: flex;
    justify-content: space-between;
    align-items: baseline;
  }}
  .card-title {{ font-size: 1.1rem; font-weight: bold; color: #fff; }}
  .card-char {{ font-size: 0.85rem; color: var(--text-muted); }}
  .card-desc {{
    font-size: 0.82rem;
    color: var(--text-muted);
    padding: 8px 15px;
    background: rgba(0,0,0,0.2);
    border-bottom: 1px solid var(--border);
  }}
  .img-container {{
    position: relative;
    width: 100%;
    aspect-ratio: 832 / 1216;
    background: #141722;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
  }}
  .img-container img {{
    width: 100%;
    height: 100%;
    object-fit: contain;
    cursor: pointer;
  }}
  .pose-nav {{
    display: flex;
    overflow-x: auto;
    padding: 8px;
    background: #151824;
    gap: 6px;
    border-top: 1px solid var(--border);
  }}
  .pose-btn {{
    flex: 1;
    padding: 6px 4px;
    font-size: 0.75rem;
    text-align: center;
    background: #1e2230;
    border: 1px solid var(--border);
    border-radius: 6px;
    white-space: nowrap;
  }}
  .pose-btn.active {{
    background: var(--accent);
    color: #fff;
    border-color: var(--accent);
  }}
  /* Modal */
  .modal {{
    display: none;
    position: fixed;
    top: 0; left: 0; width: 100%; height: 100%;
    background: rgba(0,0,0,0.85);
    z-index: 1000;
    align-items: center;
    justify-content: center;
    cursor: pointer;
  }}
  .modal img {{
    max-width: 90vw;
    max-height: 90vh;
    border-radius: 8px;
    box-shadow: 0 10px 30px rgba(0,0,0,0.5);
  }}
</style>
</head>
<body>

<header>
  <div>
    <h1>🎨 YKN 작가 화풍 벤치마크 <span class="badge">40인 × 5포즈 = 200장</span></h1>
    <p style="color: var(--text-muted); font-size: 0.85rem; margin-top: 4px;">
      쿨뷰티 하율 (20인) · 메가데레 유아 (20인) | 포즈: 000(평상), 028(엉덩이애무), 076(수유대딸), 095(웨딩섹스), 106(샤워섹스강)
    </p>
  </div>
  <div class="controls">
    <button class="active" onclick="filterChar('all')">전체보기 (40명)</button>
    <button onclick="filterChar('hay')">하율 hay (20명)</button>
    <button onclick="filterChar('yua')">유아 yua (20명)</button>
    <select onchange="changeGlobalPose(this.value)">
      <option value="000">전체 포즈: 000_평상 (기준)</option>
      <option value="028">전체 포즈: 028_엉덩이애무</option>
      <option value="076">전체 포즈: 076_수유대딸</option>
      <option value="095">전체 포즈: 095_웨딩섹스</option>
      <option value="106">전체 포즈: 106_샤워섹스강</option>
    </select>
  </div>
</header>

<div class="grid" id="cardGrid"></div>

<div class="modal" id="imageModal" onclick="this.style.display='none'">
  <img id="modalImg" src="">
</div>

<script>
const data = {json_str};
let activeCharFilter = 'all';
let currentGlobalPose = '000';
const activePosesPerCard = {{}};

// 초기화
data.forEach((item, idx) => {{
  activePosesPerCard[idx] = '000';
}});

const poseLabels = {{
  '000': '000 평상',
  '028': '028 엉덩이',
  '076': '076 수유대딸',
  '095': '095 웨딩',
  '106': '106 샤워강'
}};

function render() {{
  const grid = document.getElementById('cardGrid');
  grid.innerHTML = '';

  data.forEach((item, idx) => {{
    if (activeCharFilter !== 'all' && item.char !== activeCharFilter) return;

    const currentPose = activePosesPerCard[idx] || currentGlobalPose;
    const imgSrc = item.poses[currentPose] || '';

    const card = document.createElement('div');
    card.className = 'card';
    card.innerHTML = `
      <div class="card-header">
        <span class="card-title">${{item.artist_id}}</span>
        <span class="card-char">${{item.char_name}}</span>
      </div>
      <div class="card-desc">${{item.artist_desc}} <br><code style="color:#a78bfa">${{item.artist_tag}}</code></div>
      <div class="img-container">
        ${{imgSrc ? `<img src="${{imgSrc}}" alt="${{item.artist_id}}" onclick="openModal('${{imgSrc}}')">` : '<div style="color:var(--text-muted);font-size:0.85rem">생성 대기 중...</div>'}}
      </div>
      <div class="pose-nav">
        ${{['000', '028', '076', '095', '106'].map(p => `
          <button class="pose-btn ${{p === currentPose ? 'active' : ''}}" onclick="setCardPose(${{idx}}, '${{p}}')">
            ${{poseLabels[p]}}
          </button>
        `).join('')}}
      </div>
    `;
    grid.appendChild(card);
  }});
}}

function filterChar(char) {{
  activeCharFilter = char;
  document.querySelectorAll('.controls button').forEach(b => b.classList.remove('active'));
  event.target.classList.add('active');
  render();
}}

function setCardPose(cardIdx, pose) {{
  activePosesPerCard[cardIdx] = pose;
  render();
}}

function changeGlobalPose(pose) {{
  currentGlobalPose = pose;
  data.forEach((_, idx) => {{
    activePosesPerCard[idx] = pose;
  }});
  render();
}}

function openModal(src) {{
  if (!src) return;
  document.getElementById('modalImg').src = src;
  document.getElementById('imageModal').style.display = 'flex';
}}

render();
</script>
</body>
</html>
"""
    html_path.write_text(html_content, encoding="utf-8")
    return html_path


def run_benchmark(
    char_filter: str = "all",
    artist_filter: str = "",
    mock: bool = False,
    dry_run: bool = False,
    censor: bool = False,
) -> None:
    benchmark_dir = PROJECTS_DIR / "ykn" / "artist_benchmark"
    benchmark_dir.mkdir(parents=True, exist_ok=True)

    tasks = []
    if char_filter in ("all", "hay"):
        for a_id, a_tag, a_desc in HAY_ARTISTS:
            if artist_filter and a_id != artist_filter:
                continue
            tasks.append({
                "char": "hay",
                "artist_id": a_id,
                "tag": a_tag,
                "desc": a_desc,
            })

    if char_filter in ("all", "yua"):
        for a_id, a_tag, a_desc in YUA_ARTISTS:
            if artist_filter and a_id != artist_filter:
                continue
            tasks.append({
                "char": "yua",
                "artist_id": a_id,
                "tag": a_tag,
                "desc": a_desc,
            })

    print("=" * 65)
    print("  [ARTIST BENCHMARK] PLEPA YKN 작가 화풍 200장 벤치마크 러너")
    print("=" * 65)
    print(f"  대상 캐릭터: {char_filter.upper()} (총 {len(tasks)}명 작가 등록)")
    print(f"  대상 포즈 5종: {', '.join(BENCHMARK_POSES)} ({', '.join(POSE_LABELS[p] for p in BENCHMARK_POSES)})")
    print(f"  총 생성 목표: {len(tasks) * len(BENCHMARK_POSES)}장")
    print(f"  저장 루트: {benchmark_dir}")
    print(f"  모드: {'[시뮬레이션: MOCK]' if mock else '[DRY-RUN]' if dry_run else '[실제 ComfyUI 생성]'}")
    print("=" * 65)

    svc = GenerationService()
    total_images = len(tasks) * len(BENCHMARK_POSES)
    completed_images = 0
    start_time = time.time()

    for idx, t in enumerate(tasks, 1):
        char = t["char"]
        artist_id = t["artist_id"]
        artist_tag = t["tag"]
        artist_desc = t["desc"]

        artist_out_dir = benchmark_dir / f"{char}_{artist_id}"
        artist_out_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n▶ [{idx}/{len(tasks)}] {char.upper()} × {artist_id} ({artist_desc})")
        print(f"   태그: {artist_tag}")

        for p_code in BENCHMARK_POSES:
            target_file = artist_out_dir / f"{char}_{p_code}_{artist_id}.webp"
            if target_file.exists():
                print(f"   - 포즈 {p_code}_{POSE_LABELS[p_code]}: 이미 존재하여 건너뜀")
                completed_images += 1
                continue

            params = GenerationParams(
                character_expr=char,
                pose_expr=p_code,
                roster="ykn",
                custom_pos=artist_tag,
                ckpt_tag=f"art_{artist_id}",
                overwrite=True,
                engine="sdxl",
                censor=censor,
                mock=mock,
                dry_run=dry_run,
                no_ref=True,  # 순수 화풍 영향력을 위해 IP-Adapter 비활성화
            )

            # 생성 실행
            res = svc.run_batch(params, quiet=True)
            if res and res[0].success:
                # 생성된 이미지를 benchmark 폴더로 복사/저장
                gen_path = res[0].image_path
                if gen_path and Path(gen_path).exists():
                    shutil.copy2(gen_path, target_file)
                elif mock:
                    target_file.write_bytes(b"mock_webp_data")
                print(f"   ✓ 포즈 {p_code}_{POSE_LABELS[p_code]}: 완료 ({target_file.name})")
            else:
                err_msg = res[0].error_message if res else "Unknown Error"
                print(f"   ✗ 포즈 {p_code}_{POSE_LABELS[p_code]}: 실패 ({err_msg})")

            # 임시 ckpt 서브폴더 정리 (assets 폴더 무결성 유지)
            temp_ckpt_dir = PROJECTS_DIR / "ykn" / "assets" / char / f"ckpt_art_{artist_id}"
            if temp_ckpt_dir.exists():
                shutil.rmtree(temp_ckpt_dir, ignore_errors=True)
            temp_origin_dir = PROJECTS_DIR / "ykn" / "assets" / f"{char}_origin" / f"ckpt_art_{artist_id}"
            if temp_origin_dir.exists():
                shutil.rmtree(temp_origin_dir, ignore_errors=True)

            completed_images += 1

    # HTML 뷰어 자동 생성
    html_file = generate_html_viewer(benchmark_dir, tasks)
    elapsed = time.time() - start_time
    print("\n" + "=" * 65)
    print(f"  [완료] 벤치마크 완료! ({completed_images}/{total_images}장 처리 완료, 소요 시간: {elapsed:.1f}초)")
    print(f"  [뷰어] 인터랙티브 HTML 뷰어: {html_file}")
    print("=" * 65)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PLEPA YKN 작가 화풍 벤치마크 러너")
    parser.add_argument("--char", choices=["all", "hay", "yua"], default="all", help="생성할 캐릭터 (기본: all)")
    parser.add_argument("--artist", default="", help="특정 작가 1명만 단독 실행")
    parser.add_argument("--mock", action="store_true", help="ComfyUI 호출 없이 초고속 파이프라인 무결성 검증")
    parser.add_argument("--dry-run", action="store_true", help="프롬프트 확인만 수행")
    parser.add_argument("--censor", action="store_true", help="실루엣 검열 적용 (기본: 화풍 살결 보존을 위해 무검열 원본)")
    args = parser.parse_args()

    run_benchmark(
        char_filter=args.char,
        artist_filter=args.artist,
        mock=args.mock,
        dry_run=args.dry_run,
        censor=args.censor,
    )
