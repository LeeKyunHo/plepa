---
status: template
version: template-v2.2-master
purpose: Gen-IT 다테마 신규 로스터 마스터 패키지 표준 청사진 (공식 JSX 3종 · 동적 CHAR_META · 12변수 · D20 · 탈 얀데레 1:1 DM)
---

# 🧩 Gen-IT 다테마 캐릭터 채팅 마스터 패키지 템플릿 (v2.2 Master Blueprint)

> **문서 목적**: 신규 로스터(캠퍼스, 오피스, 스파이, 오토코노코 마을 등)의 Gen-IT 5탭 작품을 제작할 때 **복제 즉시 프로덕션 규격을 충족하도록 표준화한 마스터 청사진**입니다.
> * **공식 SSOT**: [`docs/젠잇_캐릭터채팅_제작법.md`](../%EC%A0%A0%EC%9E%87_%EC%BA%90%EB%A6%AD%ED%84%B0%EC%B1%84%ED%8C%85_%EC%A0%9C%EC%9E%91%EB%B2%95.md) | **참고 구현본**: [`캠퍼스_완성본`](%EC%BA%A0%ED%8D%BC%EC%8A%A4_%EC%A0%A0%EC%9E%87_%EC%BA%90%EB%A6%AD%ED%84%B0_%EC%B1%84%ED%8C%85_v2.2_%EC%99%84%EC%84%B1%EB%B3%B8.md) · [`오토코노코_마스터(frozen)`](oto_v2_2.md)

---

## 1. 신규 작품 제작 5단계 표준 워크플로우

1. **에셋 통일 내보내기**: `832×1216` 생성 후 웹 GUI `📦 Genit 내보내기` ➔ `로스터 전체 일괄 내보내기` + `폴더/원본파일명 유지` + `1024×1536 통일`.
2. **문서 복제 및 Frontmatter 설정**: `docs/genit/{테마}_젠잇_캐릭터_채팅_v2.2_완성본.md` 생성 (`roster: {로스터명}`, `status: active`).
3. **고정 인원수 배제 & 동적 확장 설계**: 프롬프트·설정집·HTML·JSX 어디에도 `"N인방"`, `"N명 전원"`을 하드코딩하지 않고 **`CHAR_META` 1줄 추가 + `roster_stats` 동적 파싱**으로 설계.
4. **CDN URL 확보 & JSX 3종 탑재**: 본문 정상 이미지에서 `ASSET_BASE_URL` 추출 ➔ `Status` · `Talk` · `Board` 3종 JSX에 붙여넣고 `failedUrls` 모노그램 폴백 동작 확인.
5. **검증 및 실전 점검**: `.\.venv\Scripts\python.exe scripts/validate_genit_work.py --force` 실행 후 인트로 HTML·4탭 `Status`·D20·1:1 `Talk`·`Board` 동작 점검.

---

## 2. 8~12대 전역 변수 (Variables) 표준 슬롯

> `[에셋]` 탭 전역 변수에 등록합니다. `roster_stats`와 `items` 같은 장문 문자열은 절대 `setReturnValue`에 넣지 않고 전역 변수로만 관리합니다.

| 구분 | Key | 초기값 예시 | 역할 |
| :---: | :--- | :--- | :--- |
| **필수 8종** | `turn` | `1` | 누적 대화 턴 수 (`1, 2, 3...`) |
| **필수 8종** | `time` | `낮` | 시간대 (`아침` / `낮` / `저녁` / `밤`) |
| **필수 8종** | `location` | `{{START_SPOT}}` | 직관적 한글 거점명 |
| **필수 8종** | `char_name` | `{{MAIN_CHAR}}` | 현재 대화 중인 주 화자 |
| **필수 8종** | `affection` | `20` | 호감도 (**`0~100` 정수, `%` 기호 절대 생략**) |
| **필수 8종** | `submissiveness` / `stress` | `10` | 굴복·피로 텐션 (**`0~100` 정수**) |
| **필수 8종** | `tension` | `15` | 현장 열기·질투 텐션 (**`70+` 고조/합류**) |
| **필수 8종** | `roster_stats` | `캐릭터A:20/10,...` | 동적 주민 호감/보조 영구 기록장 (신규 추가 자동 확장) |
| **확장 4종** | `day` / `weather` | `1일차 (월)` / `맑음` | 요일별 이벤트·날씨별 복장(`attire`) 연출 |
| **확장 4종** | `trust` / `items` | `20` / `선물A:2,선물B:1` | 평판/신뢰도(`50+` 비밀 거점 해금) 및 선물함 소지품 |

---

## 3. 탭 1 `[설명]` 0칸 정렬 확장형 HTML 표준 템플릿

> CommonMark+HTML 파서 깨짐 방지를 위해 **모든 줄 선행 공백 0칸**, `{{파일명.webp}}` 매크로 **위·아래만 빈 줄 1줄씩**, 다인 명부는 `<details>` 아코디언 + `[NEW RESIDENTS]` 카드로 구성합니다.

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

## 4. 탭 2 `[프롬프트]` — 12,000자 공식 · `ambient` / `dm_from` · D20 & 충돌 방지

* **합산 한도**: `메인 프롬프트 + max(루트별 추가 프롬프트) <= 12,000자` (권장 배분: 메인 `9,000~9,800자` + 추가 `1,800~2,500자`, 프롤로그 `<= 2,000자`, 히든 `<= 2,000자` 독립 버퍼). 장식 문구 증량 대신 개조식 압축을 유지한 채 Few-shot·다인 관계성·분기 정밀도 강화에 활용합니다.
* **분량 지침 단일화**: 시작 설정별 히든 프롬프트에 출력 글자 수·이미지 수를 따로 적지 않고 **"출력 분량·이미지 규격은 메인 프롬프트를 준수한다"**로 단일 위임합니다.
* **이미지 출력 공식**: `{{url}}{prefix}/{prefix}_{code}.webp` (슬래시 누락 `{{url}}/xxx_000.webp` 엄금).
* **탈 얀데레 1:1 DM & `ambient` 지시문 (메인 프롬프트 복붙용)**:
  ```text
  [상태창·메신저·반환변수 지시]
  - 수치(affection, submissiveness, tension, trust)는 % 기호 없이 0~100 정수만 기입한다.
  - 평소 턴의 70~80%는 dm_from=없음|dm_preview= 로 비우고 ambient에 고요한 풍경·소리 1줄만 적는다.
  - 개인톡(dm_from)은 최소 3~4턴 쿨타임 후 시간대 전환·헤어진 직후·이벤트 후 [일상·나눔 / 가벼운 부탁 / 수줍은 여운] 위주로 1건만 보낸다. (질투 톡은 호감 75+ & tension 75+ 이상 예외 허용)
  - [@id=Talk]는 유저가 [1:1 톡 확인/선톡/답장]을 보냈을 때만 Status 윗줄에 출력한다([톡 종료] 시 중단).
  - [@id=Board]는 새 아침·거점 방문·[알림판 확인] 시에만 Status 윗줄에 출력한다.
  - 반환변수(tone, event[합계|등급|상황], gift, dm_reply, quest) 수신 시 이번 턴 서사에 즉시 반영하되 D20 낮은 눈금에도 호감도 페널티는 금지한다.
  ```
* **3종 상태창 호출 시그니처**:
  - `[@id=Status|turn=...|day=...|time=...|weather=...|location=...|char_name=...|affection=...|submissiveness=...|tension=...|trust=...|roster_stats=...|items=...|ambient=...|dm_from=...|dm_preview=...|attire=...|reaction=...]`
  - `[@id=Talk|room={상대이름}|time={HH:MM}|log={상대:내용;;나:내답장;;상대:후속답장}]`
  - `[@id=Board|day=...|weather=...|notice={공지1줄}|q1={인물:제목:장소:보상}|q2={...}|q3={...}]`

---

## 5. 탭 5 `[에셋]` — 공식 JSX 3종 (`Status` · `Talk` · `Board`) 스켈레톤 & D20 `EVENT_POOL`

### 공식 샌드박스 준수 불변식
1. **React 훅**: 반드시 `React.useState(...)` 접두 사용.
2. **리터럴 `setReturnValue` 200자 제한**: 반드시 `setReturnValue('tone', ...)`, `setReturnValue('event', ...)`, `setReturnValue('gift', ...)`, `setReturnValue('dm_reply', ...)`, `setReturnValue('quest', ...)`처럼 **문자열 리터럴 키로 직접 호출**(루프 호출 금지, 합계 200자 이하).
3. **클릭 핸들러 전용 호출**: 렌더 본문 호출 절대 금지, `onClick` 내부에서만 동기 실행.
4. **`fillInput` vs `sendMessage(..., false)`**: 이동·선물·수락·톡 전송은 `sendMessage(..., false)` 즉시 실행, 어프로치·케어 초안은 `fillInput(text, false)`.
5. **테마 안전 & 폴백**: `light-dark(...)` 또는 CSS 변수 사용, 이미지 `onError` 시 `failedUrls` 모노그램 폴백 렌더링.

```jsx
function Status(props) {
  const [activeTab, setActiveTab] = React.useState("status");
  const [tone, setTone] = React.useState("다정");
  const [rolledEvent, setRolledEvent] = React.useState(null);
  const [failedUrls, setFailedUrls] = React.useState({});

  // ★ 신규 캐릭터 추가 시 1줄 추가 (미등록 인원도 roster_stats/char_name에서 자동 인식·모노그램 폴백)
  const ASSET_BASE_URL = "https://{CDN_HOST}/media/characters/{UUID}/assets/";
  const CHAR_META = {
    "{{MAIN_CHAR}}": { prefix: "{{PREFIX}}", tag: "{{TAG}}", spot: "{{START_SPOT}}", icon: "✨", fav: "{{FAV_GIFT}}" }
  };

  // ★ EVENT_POOL 작성 원칙: 작위적 고백·억지 스킨십 배제, 세계관 날씨·시설·일상 기반 자연 상황 16종
  const EVENT_POOL = [
    "갑작스러운 소나기(급히 비를 피할 처마나 실내를 찾아야 함)",
    "거센 돌풍(바람에 머리카락·소지품이 날려 함께 붙잡아야 함)",
    "갑작스러운 정전(주변 조명이 꺼져 어둠 속 의지해야 함)",
    "확성기 안내 방송(근처 행사·긴급 공지가 크게 울려 퍼짐)",
    "발목 삐끗(발을 헛디뎌 잠깐 부축이 필요한 상황)"
    // ... 해당 로스터 세계관에 맞는 물리적 일상 해프닝 16종 내외 채우기
  ];

  const gChar = typeof useTemplateValue === "function" ? useTemplateValue("char_name") : null;
  const gAff = typeof useTemplateValue === "function" ? useTemplateValue("affection") : null;
  const cleanInt = (v, fb) => { const n = parseInt(String(v ?? "").replace(/[^0-9-]/g, ""), 10); return isNaN(n) ? fb : Math.min(100, Math.max(0, n)); };
  const affNum = cleanInt(props.affection !== undefined ? props.affection : gAff, 20);
  const markFailed = (u) => { if (u) setFailedUrls((p) => (p[u] ? p : { ...p, [u]: true })); };

  // 클릭 핸들러에서만 상태/반환변수 갱신 (리터럴 키 준수)
  const handleSelectTone = (next) => { setTone(next); if (typeof setReturnValue === "function") setReturnValue('tone', next); };
  const handleRollEvent = () => {
    const total = (Math.floor(Math.random() * 20) + 1) + Math.floor(affNum / 25);
    const tier = total >= 18 ? "💥특급" : total >= 11 ? "✨성공" : total >= 5 ? "😳아슬" : "😈역전";
    const ev = EVENT_POOL[Math.floor(Math.random() * EVENT_POOL.length)];
    const payload = `${total}|${tier}|${ev}`;
    if (typeof setReturnValue === "function") setReturnValue('event', payload);
    setRolledEvent({ total, tier, ev, payload });
  };
  const handleQuickApproach = () => {
    if (typeof setReturnValue === "function") setReturnValue('tone', tone);
    const draft = `${String(props.char_name || gChar || "{{MAIN_CHAR}}")} 곁으로 다가가 ${tone}하게 말을 건넨다.`;
    if (typeof fillInput === "function") fillInput(draft, false);
    else if (typeof sendMessage === "function") sendMessage(draft, true);
  };
  // 4탭 UI: [📊 상태 (+톤 토글/D20/fillInput)] [📍 이동(allCharNames.length)] [🎁 선물] [💌 톡·민원]
  return null;
}
```
*(참고: `Talk(props)`는 `setReturnValue('dm_reply', ...)` + `sendMessage(..., false)`, `Board(props)`는 `ICON_MAP` 미등록 시 `✨` 폴백 + `setReturnValue('quest', ...)` + `sendMessage(..., false)` 패턴을 동일 적용하며 상세 풀 코드는 `docs/genit/oto_v2_2.md`를 참조합니다.)*

---

## 6. 부록: 신규 캐릭터 추가 1분 체크리스트

1. **`[캐릭터]` 탭**: 신규 인물 등록 (이름 · 별명 · 키워드 5개 비중복 · 소개 · 프롬프트 · 경로 `{{url}}{prefix}/{prefix}_{code}.webp`).
2. **`[프롬프트]` 탭**: 하단 `[캐릭터 식별자(Prefix) 매핑 테이블]`에 1줄 추가.
3. **`[에셋]` 탭**: `Status`·`Talk` `CHAR_META` 및 `Board` `ICON_MAP`에 1줄 추가 + `roster_stats` 초기값 끝에 `,이름:초기값` 추가.
4. **`[설명]` 탭**: `[NEW RESIDENTS]` 섹션에 기존 카드 `<div>` 복사 후 `[이미지 업로드]`와 소개 문구만 교체.
