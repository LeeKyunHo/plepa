---
status: template
version: template-v3.0-master
purpose: Gen-IT v3.0 다테마 신규 로스터 마스터 패키지 표준 청사진 (인라인 DM · 비밀 격리 · 계속하기 800~1,200자 · 70% 스포트라이트 · 선물 정합성 · 3종 JSX)
---

# 🧩 Gen-IT 다테마 캐릭터 채팅 v3.0 마스터 패키지 템플릿 (v3.0 Blueprint)

> **문서 목적**: 신규 로스터의 Gen-IT 5탭 작품을 제작할 때 **복제 즉시 v3.0 실전 검증 표준(인라인 DM 답장창 · 1:1 비밀 격리 · 유연 장면 호흡 800~1,200자 · 70% 스포트라이트 · 선물 정합성 · Prefix 백업)**을 100% 충족하도록 설계된 최우선 마스터 청사진입니다.
> * **공식 SSOT**: [`docs/젠잇_캐릭터채팅_제작법.md`](../%EC%A0%A0%EC%9E%87_%EC%BA%90%EB%A6%AD%ED%84%B0%EC%B1%84%ED%8C%85_%EC%A0%9C%EC%9E%91%EB%B2%95.md) | **실전 레퍼런스**: [`oto_v3_0.md`](oto_v3_0.md) (`status: frozen`) | **구버전**: [`GENIT_MULTI_THEME_TEMPLATE_v2.2.md`](GENIT_MULTI_THEME_TEMPLATE_v2.2.md)

---

## 1. 신규 작품 제작 5단계 표준 워크플로우 (v3.0)

1. **에셋 통일 내보내기**: `832×1216` 생성 후 웹 GUI `📦 Genit 내보내기` ➔ `로스터 전체 일괄 내보내기` + `폴더/원본파일명 유지` + `1024×1536 통일`.
2. **문서 복제 및 Frontmatter 설정**: `docs/genit/{테마}_젠잇_캐릭터_채팅_v3.0_완성본.md` 생성 (`roster: {로스터명}`, `status: active`).
3. **고정 인원수 배제 & 선물 정합성 설계**: 프롬프트·설정집·HTML·JSX 어디에도 `"N인방"`, `"N명 전원"`을 하드코딩하지 않고 `CHAR_META` 1줄 확장으로 설계. 선호 선물(`CHAR_META.fav`)은 **캐릭터의 직업·종교·판매/수호 품목과 겹치지 않는 상보적 품목**으로 배정.
4. **CDN URL 확보 · Prefix 백업 · v3.0 JSX 3종 탑재**: 본문 정상 이미지에서 `ASSET_BASE_URL` 추출 ➔ `Status`(인라인 DM 답장창), `Talk`(상시 오픈 입력창), `Board` 탑재 + `[에셋 인덱스]` 바로 위 1줄 요약 `[캐릭터 접두사(prefix)]` 표 배치.
5. **검증 및 실전 점검**: `.\.venv\Scripts\python.exe scripts/validate_genit_work.py --force` PASS 확인 + `items=` 누락·인라인 DM 답장(`dm_from=없음` 초기화)·`[계속하기]`·`Board` 강제 출력 테스트.

---

## 2. 8~12대 전역 변수 (Variables) 표준 슬롯

> `[에셋]` 탭 전역 변수에 등록합니다. `roster_stats`와 `items` 같은 장문 문자열은 절대 `setReturnValue`에 넣지 않고 전역 변수로만 관리하며, 모든 `0~100` 수치는 **`%` 기호 제외 정수**로 출력·파싱합니다.

| 구분 | Key | 초기값 예시 | 역할 |
| :---: | :--- | :--- | :--- |
| **필수 8종** | `turn` / `time` / `location` | `1` / `낮` / `{{START_SPOT}}` | 누적 턴 수, 시간대, 직관적 한글 거점명 |
| **필수 8종** | `char_name` / `affection` | `{{MAIN_CHAR}}` / `20` | 현재 주 화자 및 호감도 (`0~100` 정수) |
| **필수 8종** | `submissiveness`(or `stress`) / `tension` | `10` / `15` | 굴복·피로 지수 / 현장 열기·질투 텐션 (`70+` 고조) |
| **동적 DB** | `roster_stats` | `캐릭터A:20/10,...` | 동적 인원 영구 기록장 (신규 추가 자동 확장) |
| **확장 4종** | `day` / `weather` | `1일차 (월)` / `맑음` | 요일별 이벤트·날씨별 복장(`attire`) 연출 |
| **확장 4종** | `trust` / `items` | `20` / `선물A:2,선물B:1` | 평판/신뢰도(`50+` 비밀 거점) 및 상보적 선물 인벤토리 |

---

## 3. 탭 1 `[설명]` 0칸 정렬 확장형 HTML & 선물 정합성 규칙

* **HTML 파서 안전 규칙**: 모든 줄 선행 공백 **0칸**, `{{파일명.webp}}` 위·아래만 빈 줄 1줄씩, 상단 **`[NEW RESIDENTS]`** 카드 + **`<details>` 아코디언** 명부로 고정 인원수 표기 없이 무한 확장.
* **선물·인벤토리 상보성 규칙**:
  - ❌ 금지 예: 중화요리집 주인에게 `자기 가게 만두`, 신사 무녀에게 `신사 부적`, 수녀에게 `타종교 부적`
  - ✅ 권장 예: 본업 외에 편히 즐길 수 있는 **상보적 기호품/소품**(`고급 녹차`, `수제 화과자`, `들꽃 꽃다발`, `시원한 이온음료`, `따뜻한 캔커피`, `고급 홍차`, `딸기 사탕` 등)으로 `CHAR_META.fav`·`[캐릭터]`·`[프롬프트]`·`Board` 보상을 통일.

```html
*이 작품의 모든 등장인물은 성인임을 밝힙니다. 본 작품은 문학적 허구의 창작물입니다.*

<div style="max-width:540px;margin:6px auto;border:2px solid #d49b54;border-radius:14px;overflow:hidden;background-color:#13111c;color:#f3f0f8;word-break:keep-all;overflow-wrap:break-word;">
<div style="padding:22px 16px;text-align:center;background:linear-gradient(135deg,#3b1947,#13111c);border-bottom:1px solid rgba(212,155,84,0.4);">
<div style="font-size:20px;font-weight:900;color:#fff8e7;">{{WORLD_TITLE}}</div>
<div style="font-size:12.5px;color:#f5d0fe;margin-top:6px;">{{SUB_TAGLINE}}</div>
</div>
<div style="padding:16px;">
<div style="font-size:14px;font-weight:800;color:#f5c542;margin-bottom:8px;">[NEW RESIDENTS] 최근 합류 인물</div>
<div style="background-color:rgba(255,255,255,0.04);border:1px solid rgba(244,114,182,0.4);border-radius:12px;padding:12px;margin-bottom:14px;">
<div style="max-width:290px;margin:0 auto 10px;border-radius:10px;overflow:hidden;">

{{heroine_000_평상.webp}}

</div>
<div style="font-weight:800;font-size:15px;color:#fbcfe8;">✨ {{CHAR_NAME}}</div>
<div style="font-size:12.5px;color:#cbd5e1;line-height:1.55;">{{CHAR_SHORT_INTRO}}</div>
</div>
<details open style="background-color:rgba(255,255,255,0.02);border:1px solid rgba(147,197,253,0.3);border-radius:12px;padding:12px;">
<summary style="color:#93c5fd;font-weight:800;font-size:13.5px;cursor:pointer;">📖 주요 인물 명부 (지속 확장)</summary>
<div style="margin-top:10px;font-size:12.5px;color:#cbd5e1;">기존 인물 카드 복사 영역</div>
</details>
</div>
</div>
```

---

## 4. 탭 2 `[프롬프트]` — v3.0 서사 호흡 · 1:1 톡 격리 3불변식 · 위젯 강제 규칙

* **합산 한도**: `메인 프롬프트 + max(루트별 추가 프롬프트) <= 12,000자` (권장 메인 `9,000~9,800자` + 추가 `1,800~2,500자`, 프롤로그 `<= 2,000자`, 히든 `<= 2,000자` 독립 버퍼).
* **고호감도 프롤로그 1인 집중 원칙**: 4~6명 동시 수다 금지. **주 화자 1인 집중 + 외부 인기척 + 1:1 톡 알림 배지(`dm_from`)**로 첫 턴 집중도를 확보하고 프롤로그 상태창에 `items=` 등 전 키 누락 없이 기입.
* **메인 프롬프트 v3.0 지시문 (그대로 복사 사용)**:
  ```text
  [서사 호흡 · 스포트라이트 · Show, Don't Tell]
  1. {{user}}의 대사·속마음·행동을 대필(Auto-play)하지 않되, 1회 출력은 800~1,200자 내외의 웹소설 한 장면 호흡으로 유연하게 전개한 뒤 결정적 비트에서 멈춘다(하단 Status가 잘리지 않게 여유 확보).
  2. 유저가 침묵하거나 [계속하기]를 누르면 제자리 반복 없이 캐릭터 쪽에서 먼저 한 발 다가가거나 상황을 전환한다.
  3. 기본은 주 화자 1인 1:1 집중. 다인 씬은 최대 3인까지만 허용하되 주 화자 1인이 대사·묘사의 약 70%를 이끌고, 타인 1~2인은 추임새 1~2마디 후 자연 퇴장시킨다(출석 체크식 순차 발화 금지).
  4. 심리 요약 해설("독점욕을 느꼈다" 등) 대신 시선·호흡·손끝·공간 소리로 묘사하고, 고호감도에서도 일상 장난과 밀착의 온도 차를 살린다.

  [1:1 개인톡 비밀 격리 · 위젯 강제 출력 · 상태 초기화]
  1. 텔레파시 금지: 개인톡(Talk)은 {{user}}와 발신자 둘만의 비밀이다. 유저가 화면을 보여주거나 말하지 않는 한 현장 타인의 대사·지문·reaction에 톡 발신자/내용을 절대 언급하지 않는다.
  2. 중복 발화·유령 등장 금지: 톡 메시지는 [@id=Talk] log= 안에서만 출력하고, 현재 장소(location)에 없는 톡 상대를 본문 @이름@으로 발화하거나 원격 이미지를 띄우지 않는다.
  3. 대필 금지 & 배지 초기화: 유저가 직접 [1:1 톡 답장]/[1:1 톡 선톡]으로 보낸 원문만 나:...로 기록한다. 유저가 톡에 답장/확인한 턴에는 반드시 Status를 dm_from=없음|dm_preview= 로 비운다.
  4. 평소 턴 70~80%는 dm_from=없음 + ambient 풍경 1줄만 유지. 개인톡은 3~4턴 쿨타임으로 [일상·나눔 / 가벼운 부탁 / 수줍은 여운]만 보낸다(질투 톡은 호감 75+ & tension 75+ 예외).
  5. [마을 민원판 확인] 호출 턴에는 서술만 하지 말고 반드시 Status 윗줄에 [@id=Board|...]를 출력한다.
  6. 수치(affection, submissiveness, tension, trust)는 % 없이 0~100 정수만 기입한다.

  [캐릭터 접두사(prefix) 1줄 요약] (※ 에셋 인덱스 바로 윗줄 배치 필수)
  캐릭터A:aaa | 캐릭터B:bbb | ...
  ```

---

## 5. 탭 5 `[에셋]` — v3.0 공식 JSX 3종 (`Status` 인라인 DM · 상시 `Talk` · `Board`)

```jsx
function Status(props) {
  const [activeTab, setActiveTab] = React.useState("status");
  const [tone, setTone] = React.useState("다정");
  const [rolledEvent, setRolledEvent] = React.useState(null);
  const [isDmOpen, setIsDmOpen] = React.useState(false);
  const [dmReplyDraft, setDmReplyDraft] = React.useState("");
  const [failedUrls, setFailedUrls] = React.useState({});

  const ASSET_BASE_URL = "https://{CDN_HOST}/media/characters/{UUID}/assets/";
  // ★ 혼용 에셋 규격: 기존 3자리 코드("000") 또는 확장자 포함 신규 파일명 모두 허용 (poses/avatar 미지정 시 레거시 ["000","001","004","010"] 적용)
  const CHAR_META = {
    "{{MAIN_CHAR}}": { prefix: "{{PREFIX}}", tag: "{{TAG}}", spot: "{{START_SPOT}}", icon: "✨", fav: "{{상보적선호품목}}" }
    // , "{{NEW_CHAR}}": { prefix: "new", tag: "신규", spot: "새거점", icon: "🌟", fav: "고급 녹차", avatar: "new_000_평상.webp", poses: ["new_000_평상.webp", "new_001_미소.webp", "new_004_부끄.webp", "new_010_유혹.webp"] }
  };
  const resolveAssetUrl = (prefix, entry) => {
    if (!prefix || !entry) return "";
    return /\.[a-z0-9]+$/i.test(entry)
      ? `${ASSET_BASE_URL}${prefix}/${entry}`
      : `${ASSET_BASE_URL}${prefix}/${prefix}_${entry}.webp`;
  };
  const EVENT_POOL = [
    "갑작스러운 소나기(급히 비를 피할 처마나 실내를 찾아야 함)",
    "거센 돌풍(바람이 강하게 불어 머리카락과 옷자락이 흩날림)",
    "갑작스러운 정전(실내 조명이 꺼져 주변이 깜깜해짐)",
    "마을 확성기 방송(안내 방송이 크게 울려 퍼짐)",
    "발목 삐끗(발을 헛디뎌 잠깐 부축이 필요함)"
    // 세계관 날씨·시설·일상 기반 자연 해프닝 16종 내외
  ];

  const gChar = typeof useTemplateValue === "function" ? useTemplateValue("char_name") : null;
  const gAff = typeof useTemplateValue === "function" ? useTemplateValue("affection") : null;
  const cleanInt = (v, fb) => { const n = parseInt(String(v ?? "").replace(/[^0-9-]/g, ""), 10); return isNaN(n) ? fb : Math.min(100, Math.max(0, n)); };
  const affNum = cleanInt(props.affection !== undefined ? props.affection : gAff, 20);
  const dmFrom = String(props.dm_from || "").trim();
  const hasDm = Boolean(dmFrom && dmFrom !== "없음" && dmFrom !== "none" && dmFrom !== "-");
  const dmPreview = String(props.dm_preview || "").trim();

  const poseList = (Array.isArray(activeMeta.poses) && activeMeta.poses.length === 4) ? activeMeta.poses : ["000", "001", "004", "010"];
  let poseEntry = poseList[0];
  if (cleanInt(props.tension, 20) >= 70) poseEntry = poseList[2];
  else if (affNum >= 75) poseEntry = poseList[3];
  else if (affNum >= 40) poseEntry = poseList[2];
  else if (affNum >= 20) poseEntry = poseList[1];
  const portraitUrl = [
    resolveAssetUrl(activeMeta.prefix, poseEntry),
    resolveAssetUrl(activeMeta.prefix, activeMeta.avatar),
    resolveAssetUrl(activeMeta.prefix, poseList[0]),
    resolveAssetUrl(activeMeta.prefix, "000")
  ].filter(Boolean).find((u) => !failedUrls[u]) || "";

  // ★ v3.0 인라인 DM: [💬 열기] 시 메시지 즉시 전송 금지 -> 인라인 입력창 토글 후 [전송] 시 동기 실행
  const handleToggleDm = () => setIsDmOpen((v) => !v);
  const handleSendInlineDmReply = () => {
    const text = dmReplyDraft.trim();
    if (!text || !hasDm) return;
    setDmReplyDraft("");
    setIsDmOpen(false);
    if (typeof setReturnValue === "function") setReturnValue('dm_reply', `${dmFrom}:${text.slice(0, 40)}`);
    if (typeof sendMessage === "function") sendMessage(`[1:1 톡 답장 | ${dmFrom}] ${text}`, false);
  };
  const handleRollEvent = () => {
    const total = (Math.floor(Math.random() * 20) + 1) + Math.floor(affNum / 25);
    const tier = total >= 18 ? "💥특급" : total >= 11 ? "✨성공" : total >= 5 ? "😳아슬" : "😈역전";
    const ev = EVENT_POOL[Math.floor(Math.random() * EVENT_POOL.length)];
    if (typeof setReturnValue === "function") setReturnValue('event', `${total}|${tier}|${ev}`);
    setRolledEvent({ total, tier, ev });
  };
  // 나머지 4탭([📊 상태]/[📍 이동]/[🎁 선물]/[💌 톡·민원]), fillInput(text, false), failedUrls 모노그램 폴백 완비는 oto_v3_0.md 참조
  return null;
}

function Talk(props) {
  const [draft, setDraft] = React.useState("");
  const [localReplies, setLocalReplies] = React.useState([]);
  const [isClosed, setIsClosed] = React.useState(false);
  const ASSET_BASE_URL = "https://{CDN_HOST}/media/characters/{UUID}/assets/";
  const CHAR_META = {
    "{{MAIN_CHAR}}": { prefix: "{{PREFIX}}", accent: "#ec4899" }
    // , "{{NEW_CHAR}}": { prefix: "new", accent: "#3b82f6", avatar: "new_000_평상.webp" }
  };
  const resolveAssetUrl = (prefix, entry) => {
    if (!prefix || !entry) return "";
    return /\.[a-z0-9]+$/i.test(entry) ? `${ASSET_BASE_URL}${prefix}/${entry}` : `${ASSET_BASE_URL}${prefix}/${prefix}_${entry}.webp`;
  };
  // ★ v3.0: 상단 헤더 우측에 슬림 [📴 덮기] 배치, 하단 답장 입력창+전송 버튼은 토글 없이 상시 오픈 (아바타는 avatar ➔ _000.webp)
  const handleSendReply = (target) => {
    const text = draft.trim();
    if (!text) return;
    setLocalReplies((prev) => [...prev, { speaker: "나", text }]);
    setDraft("");
    if (typeof setReturnValue === "function") setReturnValue('dm_reply', `${target}:${text.slice(0, 40)}`);
    if (typeof sendMessage === "function") sendMessage(`[1:1 톡 답장 | ${target}] ${text}`, false);
  };
  return null;
}
```
*(참고: `Board(props)`는 `ICON_MAP` 미등록 시 `✨` 폴백, `[✅ 수락·이동]` 시 `setReturnValue('quest', ...)` + `sendMessage(..., false)` 실행하며 전체 JSX 소스는 [`docs/genit/oto_v3_0.md`](oto_v3_0.md)를 그대로 복제합니다.)*

---

## 6. 부록: 기존 v3.0 작품 신규 캐릭터 증설 6단계 SOP 체크리스트

1. **Step 1 [`[이미지 업로드]`]**: `{prefix}/` 폴더 에셋 업로드 + `[설명]`용 대표 이미지 1장 별도 업로드.
2. **Step 2 [`[캐릭터]` 탭]**: 이름·별명·비중복 키워드 5개·소개·프롬프트(외형/말투/약점/거점/상보적 선호 선물/폴더 포함 경로 예시).
3. **Step 3 [`[프롬프트]` 탭]**: `4. 주요 주민` 1줄 + `[캐릭터 접두사(prefix)]` 1줄 추가. **기존 레거시 에셋 매핑은 무수정 보존**하고 맨 아래에 **`[신규 주민 에셋 인덱스]` 블록을 별도 덧붙임** 후 `메인 + max(추가) <= 12,000자` 예산 확인.
4. **Step 4 [`[에셋]` 탭]**: `Status`·`Talk` `CHAR_META`(필요 시 `poses`/`avatar` 지정)·`Board` `ICON_MAP` 1줄 추가 + 전역 변수 `roster_stats` 끝에 `,이름:15/10` 추가.
5. **Step 5 [`[시작 설정]` & `[설정집]`]**: 시작 설정 1·2·3 프롤로그 마지막 `Status` `roster_stats=` 끝에 초기 스탯 추가(`items=` 누락 점검, 본문 1인 집중 유지) + 설정집 `거점 매핑`·`개인톡 말투 가이드` 각 1줄 추가 + **발견성 확보(`Board` 일일 의뢰 1칸 · 1:1 첫인사 · 기존 관계망 1줄)**.
6. **Step 6 [`[작품 설명]` 탭]**: `[NEW RESIDENTS]` 섹션에 카드 `<div>` 복사 후 `[이미지 업로드]`와 소개 문구만 교체 (**0칸 정렬, `{{파일명}}` 위·아래 빈 줄 1줄, 고정 인원수 금지**).
