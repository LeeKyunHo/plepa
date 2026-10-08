"""
037번 포즈의 색조 문제 원인 태그 찾기
각 태그를 하나씩 제거하면서 WAI로 테스트
"""

import subprocess
import sys

# 원본 프롬프트
original = "kiss, french kiss, faceless male, deep passionate kiss, messy saliva trail, parted lips, heavy blush, flushed skin, trembling with pleasure, upper body"

# 의심 태그 목록
suspects = [
    ("flushed skin 제거", "kiss, french kiss, faceless male, deep passionate kiss, messy saliva trail, parted lips, heavy blush, trembling with pleasure, upper body"),
    ("heavy blush 제거", "kiss, french kiss, faceless male, deep passionate kiss, messy saliva trail, parted lips, flushed skin, trembling with pleasure, upper body"),
    ("passionate 제거", "kiss, french kiss, faceless male, deep kiss, messy saliva trail, parted lips, heavy blush, flushed skin, trembling with pleasure, upper body"),
    ("trembling 제거", "kiss, french kiss, faceless male, deep passionate kiss, messy saliva trail, parted lips, heavy blush, flushed skin, upper body"),
    ("saliva 제거", "kiss, french kiss, faceless male, deep passionate kiss, parted lips, heavy blush, flushed skin, trembling with pleasure, upper body"),
]

print("=" * 70)
print("  037번 색조 문제 원인 태그 찾기")
print("=" * 70)
print("\n각 테스트마다 약 17초 소요 예상\n")

# SDXL 포즈 DB를 임시로 수정해서 테스트하는 대신
# custom_pos로 오버라이드해서 테스트
for idx, (name, modified_prompt) in enumerate(suspects, 1):
    print(f"\n[테스트 {idx}/{len(suspects)}] {name}")
    print(f"  프롬프트: {modified_prompt[:80]}...")
    
    # 실제로는 SDXL DB를 수정해야 하지만, 지금은 분석만
    print(f"  → 이 테스트를 하려면 sdxl_pose_database.json에서 037의 prompt를 수정해야 함")
    print()

print("\n" + "=" * 70)
print("결론:")
print("  1. Unholy 037이 정상 색상이면 → Illustrious 계열 문제 확정")
print("  2. Unholy도 색조 문제 있으면 → 037 프롬프트 자체 문제")
print("  3. 해결: 문제 태그 제거 또는 Illustrious 계열 체크포인트는 037 회피")
print("=" * 70)
