# -*- coding: utf-8 -*-
"""
batch_murim_runner.py
1단계: 백설아(aa) 102종 풀패키지 생성
2단계: 나머지 9인(bb~jj) 무협 전용 10종 팩(C01~C10) 순차 생성
기존 생성된 파일은 스마트 스킵되어 누락분만 안전하게 채웁니다.
"""
import subprocess
import sys
import time

P_CODES = (
    "A00,A01,A02,A03,A04,A05,A06,A07,A08,A09,A10,A11,A12,A13,A14,A15,A16,A17,A18,A19,A20,A21,A22,A23,"
    "B01,B02,B03,B04,B05,B06,B07,B08,B09,B10,B11,B12,B13,B14,B15,B16,B17,B18,B19,B20,B21,B22,"
    "N01,N02,N03,N04,N05,N06,N07,N08,N09,N10,N11,N12,N13,N14,N15,N16,N17,N18,N19,N20,N24,N25,N26,N27,"
    "N28,N29,N30,N31,N32,N33,N34,N35,N36,N37,N38,N39,N40,N41,N42,N43,N44,N45,N46,N47,N48,N49,N50,N51,"
    "N57,N58,N59,N60,N61,N62,N63,N64,N65,N66,N67,N68,N69,N70,N71,N72,N73,N74,"
    "C01,C02,C03,C04,C05,C06,C07,C08,C09,C10"
)

C_CODES = "C01,C02,C03,C04,C05,C06,C07,C08,C09,C10"
OTHER_CHARS = ["bb", "cc", "dd", "ee", "ff", "gg", "hh", "ii", "jj"]


def main():
    print("=" * 65)
    print("  [무협 아포칼립스] 일괄 연속 배치 생성 파이프라인 가동")
    print("  1단계: 화산 대사저 백설아(aa) 102종 풀패키지")
    print("  2단계: 나머지 9인(bb~jj) 무협 전용 10종 팩(C01~C10)")
    print("=" * 65)

    start_total = time.time()

    # 1단계: 백설아(aa) 풀패키지
    print("\n▶ [1단계 시작] 화산 대사저 백설아(aa) 풀패키지 생성 (누락분 자동 채우기)")
    cmd_aa = [sys.executable, "flux_batch_generator.py", "-r", "murim", "-c", "aa", "-p", P_CODES]
    res_aa = subprocess.run(cmd_aa)
    if res_aa.returncode != 0:
        print("[오류] 백설아 생성 중 문제가 발생했습니다. 종료 코드:", res_aa.returncode)

    # 2단계: 나머지 9인 C팩 일괄
    for idx, ch in enumerate(OTHER_CHARS, 1):
        print(f"\n▶ [2단계 {idx}/9] 캐릭터 '{ch}' 무협 C팩(C01~C10) 생성 시작")
        cmd_ch = [sys.executable, "flux_batch_generator.py", "-r", "murim", "-c", ch, "-p", C_CODES]
        res_ch = subprocess.run(cmd_ch)
        if res_ch.returncode != 0:
            print(f"[경고] 캐릭터 {ch} 생성 중 오류 발생 (종료 코드: {res_ch.returncode}), 다음으로 진행합니다.")

    elapsed = time.time() - start_total
    print("\n" + "=" * 65)
    print(f"  [완료] 모든 지정 배치 생성이 종료되었습니다! (총 소요 시간: {elapsed:.1f}초)")
    print("=" * 65)


if __name__ == "__main__":
    main()
