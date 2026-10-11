# -*- coding: utf-8 -*-
"""
generate_all_murim_full.py
무협 아포칼립스 10인(aa~jj) 전원 풀패키지(102종) 일괄 생성 파이프라인.
- 모브 남성 파트너 무특징화(faceless/obscured face) 및 남성 얼굴 디테일 차단 네거티브 반영.
- aa: B팩(스킨십 22종) 및 N팩(성인 46종) 개선 모브 로직으로 강제 덮어쓰기(--overwrite) 갱신.
- bb~jj: wuxia_full 102종 전수 생성 (기존 C01~C10 및 A00은 자동 스마트 스킵).
"""
import subprocess
import sys
import time

# 무협 풀패키지 102종 포즈 코드
WUXIA_FULL_CODES = (
    "A00,A01,A02,A03,A04,A05,A06,A07,A08,A09,A10,A11,A12,A13,A14,A15,A16,A17,A18,A19,A20,A21,A22,A23,"
    "B01,B02,B03,B04,B05,B06,B07,B08,B09,B10,B11,B12,B13,B14,B15,B16,B17,B18,B19,B20,B21,B22,"
    "N01,N02,N03,N04,N05,N06,N07,N08,N09,N10,N11,N12,N13,N14,N15,N16,N17,N18,N19,N20,N24,N25,N26,N27,"
    "N28,N29,N30,N31,N32,N33,N34,N35,N36,N37,N38,N39,N40,N41,N42,N43,N44,N45,N46,N47,N48,N49,N50,N51,"
    "N57,N58,N59,N60,N61,N62,N63,N64,N65,N66,N67,N68,N69,N70,N71,N72,N73,N74,"
    "C01,C02,C03,C04,C05,C06,C07,C08,C09,C10"
)

# 모브 파트너 상호작용 씬 (B 스킨십 + N 성인 씬 = 68종)
MOB_INTERACTION_CODES = (
    "B01,B02,B03,B04,B05,B06,B07,B08,B09,B10,B11,B12,B13,B14,B15,B16,B17,B18,B19,B20,B21,B22,"
    "N01,N02,N03,N04,N05,N06,N07,N08,N09,N10,N11,N12,N13,N14,N15,N16,N17,N18,N19,N20,N24,N25,N26,N27,"
    "N28,N29,N30,N31,N32,N33,N34,N35,N36,N37,N38,N39,N40,N41,N42,N43,N44,N45,N46,N47,N48,N49,N50,N51,"
    "N57,N58,N59,N60,N61,N62,N63,N64,N65,N66,N67,N68,N69,N70,N71,N72,N73,N74"
)

ALL_CHARS = ["aa", "bb", "cc", "dd", "ee", "ff", "gg", "hh", "ii", "jj"]


def main():
    print("=" * 70)
    print("  [무협 아포칼립스] 10인 전원 풀패키지(102종) 연속 생성 시작")
    print("  - 개선 사항: 모브 남성 파트너 무특징(Faceless/Blank Face) 및 얼굴 차단 적용")
    print("=" * 70)

    start_total = time.time()

    # 1. 백설아(aa) B/N 상호작용 씬을 무특징 모브 로직으로 덮어쓰기 재생성
    print("\n▶ [1/10] 백설아(aa) 상호작용(B+N) 모브 개선 씬 재생성 (--overwrite)")
    cmd_aa = [
        sys.executable, "flux_batch_generator.py",
        "-r", "murim", "-c", "aa", "-p", MOB_INTERACTION_CODES, "--overwrite"
    ]
    res_aa = subprocess.run(cmd_aa)
    if res_aa.returncode != 0:
        print(f"[경고] 백설아 모브 씬 재생성 중 오류 코드 {res_aa.returncode}")

    # 2. 나머지 9인(bb~jj) 전원 풀패키지 순차 생성 (기존 파일은 자동 스킵)
    for idx, ch in enumerate(ALL_CHARS[1:], 2):
        print(f"\n▶ [{idx}/10] 캐릭터 '{ch}' 풀패키지 102종 생성 시작 (누락분 자동 채우기)")
        cmd_ch = [
            sys.executable, "flux_batch_generator.py",
            "-r", "murim", "-c", ch, "-p", WUXIA_FULL_CODES
        ]
        res_ch = subprocess.run(cmd_ch)
        if res_ch.returncode != 0:
            print(f"[경고] 캐릭터 {ch} 생성 중 오류 발생 (종료 코드: {res_ch.returncode}), 다음 캐릭터로 진행합니다.")

    elapsed = time.time() - start_total
    print("\n" + "=" * 70)
    print(f"  [축하합니다!] 10인 전원 풀패키지 배치가 완료되었습니다. (소요: {elapsed/60:.1f}분)")
    print("=" * 70)


if __name__ == "__main__":
    main()
