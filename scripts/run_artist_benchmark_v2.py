"""
scripts/run_artist_benchmark_v2.py
YKN 2차 벤치마크: 망가·동인지·성인지(R-18)·성인웹툰 특화 40인 작가 × 5대 대표 포즈
대상 캐릭터:
  - 설세린 (ser, 2녀 - 히메컷 & 쿨뷰티 & 힙라인): 14인 (70장)
  - 설시아 (sia, 3녀 - 하이 포니테일 & 츤데레 & 슬렌더): 13인 (65장)
  - 유키노시타 유키노 (ykn, 원본 - 소부고 교복 & 적색 리본 & 청초 쿨뷰티): 13인 (65장)
총 40인 × 5포즈 = 정확히 200장 일괄 생성 및 모던 인터랙티브 HTML 뷰어 자동 생성.
"""

from __future__ import annotations

import argparse
import json
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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from plepa_engine.config import PROJECTS_DIR
from plepa_engine.services.generation_service import GenerationParams, GenerationService

BENCHMARK_POSES = ["000", "028", "076", "095", "106"]
POSE_LABELS = {
    "000": "평상",
    "028": "엉덩이애무",
    "076": "수유대딸",
    "095": "웨딩섹스",
    "106": "샤워섹스강",
}

# 1. 설세린 (ser, 14인): 정통 히메컷 & 쿨뷰티 & 매혹적인 골반/힙라인
SER_ARTISTS: List[Tuple[str, str, str]] = [
    ("yd", "(artist:yd:1.15)", "한국 픽시브의 전설 / 매끄러운 힙과 각선미, 고급스러운 윤기"),
    ("shal_e", "(artist:shal.e:1.15)", "정갈한 쿨뷰티 반실사 / 성인웹툰 메인 표지 감성"),
    ("hews", "(artist:hews:1.15)", "픽시브 1티어 핀업 / 세련되고 뇌쇄적인 눈빛과 깔끔한 명암"),
    ("kisaragi_gunma", "(artist:kisaragi_gunma:1.15)", "키사라기 군마 / 청초하면서도 에로틱한 바디라인"),
    ("bokuboy", "(artist:bokuboy:1.15)", "보쿠보이 / 탄력 있는 허벅지와 골반 굴곡"),
    ("alp", "(artist:alp:1.15)", "알프 / 묵직하고 농밀한 성인 체위 셰이딩"),
    ("hirame", "(artist:hirame_(hirame99):1.15)", "히라메 / 쫀득하고 말랑한 살결 표현, 부드러운 라인"),
    ("distance", "(artist:distance:1.15)", "디스턴스 / 상업지 1티어, 농밀한 체위와 질척한 묘사"),
    ("shirabii", "(artist:shirabii:1.15)", "시라비 / 날카롭고 도도한 쿨뷰티 눈매"),
    ("morii_shizuki", "(artist:morii_shizuki:1.15)", "모리이 시즈키 / 페이트 시리즈, 기품 있는 음영"),
    ("qun", "(artist:qun:1.15)", "qun / 요염한 픽시브 핀업 셰이딩"),
    ("tamano_kedama", "(artist:tamano_kedama:1.15)", "타마노 케다마 / 옥구슬 같은 눈동자와 찰진 피부"),
    ("maruma", "(artist:maruma_(marumag):1.15)", "마루마 / 모던하고 세련된 성인 작화"),
    ("tsukaco", "(artist:tsukaco:1.15)", "츠카코 / 맑고 화사한 미소녀 핀업"),
]

# 2. 설시아 (sia, 13인): 하이 포니테일 & 츤데레 & 요염한 슬렌더
SIA_ARTISTS: List[Tuple[str, str, str]] = [
    ("ratatatat74", "(artist:ratatatat74:1.15)", "라타타타 / 도발적 표정, 타액, 타이트 의상, 에로티시즘의 정점"),
    ("asanagi", "(artist:asanagi:1.15)", "아사나기 / 매운맛 츤데레, 도발적 눈빛과 대담한 체위"),
    ("waterkuma", "(artist:waterkuma:1.15)", "워터쿠마 / 물광, 땀방울, 수중 샤워씬 광택 셰이딩"),
    ("cutesexyrobutts", "(artist:cutesexyrobutts:1.15)", "큐트섹시로봇 / 탄탄한 슬렌더 힙과 감각적 명암"),
    ("shindol", "(artist:shindol:1.15)", "신도엘 / 거친 펜선과 강렬한 현실적 인체 라인"),
    ("akitsuki_ryou", "(artist:akitsuki_ryou:1.15)", "아키츠키 료 / 메다카 박스, 샤프하고 날카로운 슬렌더 바디"),
    ("derpys", "(artist:derpys:1.15)", "더피스 / 감각적인 서양풍 성인 핀업"),
    ("reina", "(artist:reina:1.15)", "레이나 / 찰진 성인물 음영과 표정"),
    ("pochami", "(artist:pochami:1.15)", "포차미 / 슬렌더하면서도 쫀득한 살결"),
    ("kuroda_bb", "(artist:kuroda_bb:1.15)", "쿠로다 bb / 찰진 선화와 귀여운 도발"),
    ("towa", "(artist:towa:1.15)", "토와 / 트렌디하고 감각적인 픽시브 일러스트"),
    ("infinote", "(artist:infinote:1.15)", "인피노트 / 매끄러운 2D 애니메 셀 셰이딩"),
    ("kurot", "(artist:kurot:1.15)", "쿠롯 / 성인 웹툰/망가 스타일 특화"),
]

# 3. 유키노시타 유키노 (ykn, 13인): 원본 소부고 교복 & 적색 리본 & 청초 쿨뷰티
YKN_ARTISTS: List[Tuple[str, str, str]] = [
    ("dooky", "(artist:dooky:1.15)", "두키 / 청초한 얼굴과 반전의 육감적 셰이딩"),
    ("kimsan", "(artist:kimsan:1.15)", "김산 / 한국형 성인웹툰의 매끄러운 피부 질감"),
    ("inu_toushirou", "(artist:inu_(toushirou):1.15)", "이누 토시로 / 상업지 전설, 매력적인 표정과 체위"),
    ("nagishiro_mito", "(artist:nagishiro_mito:1.15)", "나기시로 미토 / 몽환적이고 섬세한 흑발 텍스처"),
    ("fukuro_daikokuten", "(artist:fukuro_daikokuten:1.15)", "후쿠로 다이코쿠텐 / 매력적인 피부 광택"),
    ("refeia", "(artist:refeia:1.15)", "레페이아 / 부드럽고 섬세한 미소녀 원화"),
    ("citemer", "(artist:citemer:1.15)", "시트머 / 스타일리시한 선화와 명암"),
    ("sakimichan", "(artist:sakimichan:1.15)", "사키미찬 / 입체적인 라이팅과 화려한 핀업"),
    ("dishwasher1910", "(artist:dishwasher1910:1.15)", "디시워셔 / 날카로운 선화와 역동적 구도"),
    ("z_ton", "(artist:z-ton:1.15)", "Z-TON / 독특하고 육감적인 실루엣"),
    ("parno", "(artist:parno:1.15)", "파르노 / 쫀득한 피부 질감"),
    ("hizuki_yeo", "(artist:hizuki_yeo:1.15)", "히즈키 여 / 부드럽고 투명한 셰이딩"),
    ("tsunako", "(artist:tsunako:1.15)", "츠나코 / 데이트 어 라이브 원화, 화려한 미소녀 감성"),
]


def generate_html_viewer_v2(benchmark_dir: Path, tasks: List[Dict]) -> Path:
    """작가별, 포즈별로 한눈에 비교할 수 있는 2차 모던 인터랙티브 HTML 뷰어 생성."""
    html_path = benchmark_dir / "index.html"
    
    cards_data = []
    for t in tasks:
        char = t["char"]
        artist_id = t["artist_id"]
        artist_desc = t["desc"]
        artist_tag = t["tag"]
        char_name_map = {
            "ser": "설세린 (ser - 2녀)",
            "sia": "설시아 (sia - 3녀)",
            "ykn": "유키노시타 유키노 (ykn - 원본)",
        }
        pose_imgs = {}
        for p in BENCHMARK_POSES:
            img_rel = f"{char}_{artist_id}/{char}_{p}_{artist_id}.webp"
            img_full = benchmark_dir / img_rel
            pose_imgs[p] = img_rel if img_full.exists() else ""
        cards_data.append({
            "char": char,
            "char_name": char_name_map.get(char, char),
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
<title>PLEPA YKN 성인지·동인지 40인 벤치마크 (200장)</title>
<style>
  :root {{
    --bg-color: #0d0f17;
    --card-bg: #161926;
    --accent: #ec4899;
    --accent-hover: #db2777;
    --text: #e2e8f0;
    --text-muted: #94a3b8;
    --border: #262b3d;
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
    background: #1f2438;
    color: var(--text);
    border: 1px solid var(--border);
    padding: 8px 14px;
    border-radius: 8px;
    font-size: 0.9rem;
    cursor: pointer;
    transition: all 0.2s;
  }}
  button:hover, select:hover {{ background: #2b324c; border-color: var(--accent); }}
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
  .card-char {{ font-size: 0.85rem; color: #f472b6; font-weight: 500; }}
  .card-desc {{
    font-size: 0.82rem;
    color: var(--text-muted);
    padding: 8px 15px;
    background: rgba(0,0,0,0.25);
    border-bottom: 1px solid var(--border);
  }}
  .img-container {{
    position: relative;
    width: 100%;
    aspect-ratio: 832 / 1216;
    background: #11131f;
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
    background: #141724;
    gap: 6px;
    border-top: 1px solid var(--border);
  }}
  .pose-btn {{
    flex: 1;
    padding: 6px 4px;
    font-size: 0.75rem;
    text-align: center;
    background: #1a1e2e;
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
    <h1>🔞 YKN 성인지·동인지 40인 벤치마크 <span class="badge">40인 × 5포즈 = 200장</span></h1>
    <p style="color: var(--text-muted); font-size: 0.85rem; margin-top: 4px;">
      설세린 (14인) · 설시아 (13인) · 유키노 원본 (13인) | 포즈: 000(평상), 028(엉덩이애무), 076(수유대딸), 095(웨딩섹스), 106(샤워섹스강)
    </p>
  </div>
  <div class="controls">
    <button class="active" onclick="filterChar('all')">전체보기 (40명)</button>
    <button onclick="filterChar('ser')">설세린 ser (14명)</button>
    <button onclick="filterChar('sia')">설시아 sia (13명)</button>
    <button onclick="filterChar('ykn')">유키노 ykn (13명)</button>
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
      <div class="card-desc">${{item.artist_desc}} <br><code style="color:#f472b6">${{item.artist_tag}}</code></div>
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


def run_benchmark_v2(
    char_filter: str = "all",
    artist_filter: str = "",
    mock: bool = False,
    dry_run: bool = False,
    censor: bool = False,
) -> None:
    benchmark_dir = PROJECTS_DIR / "ykn" / "artist_benchmark_v2"
    benchmark_dir.mkdir(parents=True, exist_ok=True)

    tasks = []
    # 1. 설세린 (ser)
    if char_filter in ("all", "ser"):
        for a_id, a_tag, a_desc in SER_ARTISTS:
            if artist_filter and a_id != artist_filter:
                continue
            tasks.append({"char": "ser", "artist_id": a_id, "tag": a_tag, "desc": a_desc})

    # 2. 설시아 (sia)
    if char_filter in ("all", "sia"):
        for a_id, a_tag, a_desc in SIA_ARTISTS:
            if artist_filter and a_id != artist_filter:
                continue
            tasks.append({"char": "sia", "artist_id": a_id, "tag": a_tag, "desc": a_desc})

    # 3. 유키노시타 유키노 (ykn)
    if char_filter in ("all", "ykn"):
        for a_id, a_tag, a_desc in YKN_ARTISTS:
            if artist_filter and a_id != artist_filter:
                continue
            tasks.append({"char": "ykn", "artist_id": a_id, "tag": a_tag, "desc": a_desc})

    print("=" * 65)
    print("  [BENCHMARK V2] PLEPA YKN 성인지·동인지 40인 화풍 200장 벤치마크 러너")
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

            actual_roster = "don" if char == "ykn" else "ykn"
            params = GenerationParams(
                character_expr=char,
                pose_expr=p_code,
                roster=actual_roster,
                custom_pos=artist_tag,
                ckpt_tag=f"art2_{artist_id}",
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
            temp_ckpt_dir = PROJECTS_DIR / "ykn" / "assets" / char / f"ckpt_art2_{artist_id}"
            if temp_ckpt_dir.exists():
                shutil.rmtree(temp_ckpt_dir, ignore_errors=True)
            temp_origin_dir = PROJECTS_DIR / "ykn" / "assets" / f"{char}_origin" / f"ckpt_art2_{artist_id}"
            if temp_origin_dir.exists():
                shutil.rmtree(temp_origin_dir, ignore_errors=True)

            completed_images += 1

    # HTML 뷰어 자동 생성
    html_file = generate_html_viewer_v2(benchmark_dir, tasks)
    elapsed = time.time() - start_time
    print("\n" + "=" * 65)
    print(f"  [완료] 벤치마크 완료! ({completed_images}/{total_images}장 처리 완료, 소요 시간: {elapsed:.1f}초)")
    print(f"  [뷰어] 인터랙티브 HTML 뷰어: {html_file}")
    print("=" * 65)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PLEPA YKN 성인지·동인지 40인 화풍 벤치마크 러너 V2")
    parser.add_argument("--char", choices=["all", "ser", "sia", "ykn"], default="all", help="생성할 캐릭터 (기본: all)")
    parser.add_argument("--artist", default="", help="특정 작가 1명만 단독 실행")
    parser.add_argument("--mock", action="store_true", help="ComfyUI 호출 없이 초고속 파이프라인 무결성 검증")
    parser.add_argument("--dry-run", action="store_true", help="프롬프트 확인만 수행")
    parser.add_argument("--censor", action="store_true", help="실루엣 검열 적용 (기본: 화풍 살결 보존을 위해 무검열 원본)")
    args = parser.parse_args()

    run_benchmark_v2(
        char_filter=args.char,
        artist_filter=args.artist,
        mock=args.mock,
        dry_run=args.dry_run,
        censor=args.censor,
    )
