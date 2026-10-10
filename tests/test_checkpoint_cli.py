"""
체크포인트 프로필 시스템 CLI 통합 테스트
실제 생성 없이 프로필 적용 여부만 검증 (--dry-run 모드)
"""

import subprocess
import sys

def test_checkpoint_profile_integration():
    """CLI에서 체크포인트 프로필이 제대로 적용되는지 테스트"""
    
    print("=" * 70)
    print("  체크포인트 프로필 CLI 통합 테스트")
    print("=" * 70)
    
    test_cases = [
        {
            "name": "WAI-Illustrious 프로필 (퍼지 매칭)",
            "ckpt": "WAI-NSFW-illustrious-v7.safetensors",
            "expected_resolution": "1024x1344",
            "expected_profile_contains": "WAI-Illustrious"  # 프로필 이름 일부만 확인
        },
        {
            "name": "Unholy Mix 프로필 (퍼지 매칭)",
            "ckpt": "unholy_desire_mix_v5.0.safetensors",
            "expected_resolution": "832x1216",
            "expected_profile_contains": "Unholy"
        },
        {
            "name": "알 수 없는 체크포인트 (기본 프로필)",
            "ckpt": "unknown_checkpoint_xyz.safetensors",
            "expected_resolution": "832x1216",
            "expected_profile_contains": None  # 기본 프로필은 명시적으로 출력 안함
        }
    ]
    
    passed = 0
    failed = 0
    
    for i, tc in enumerate(test_cases, 1):
        print(f"\n[테스트 {i}/{len(test_cases)}] {tc['name']}")
        print(f"  체크포인트: {tc['ckpt']}")
        
        # CLI 실행 (dry-run 모드로 실제 생성은 하지 않음)
        cmd = [
            sys.executable,
            "flux_batch_generator.py",
            "-c", "sample_character",
            "-p", "000",
            "--engine", "sdxl",
            "--ckpt", tc["ckpt"],
            "--dry-run"
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
                encoding='utf-8'
            )
            
            output = result.stdout
            
            # 프로필 적용 메시지 확인
            if tc["expected_profile_contains"]:
                if f"체크포인트 프로필:" in output and tc["expected_profile_contains"] in output:
                    # 실제 프로필 이름 추출
                    import re
                    match = re.search(r"체크포인트 프로필: '([^']+)' 자동 적용", output)
                    profile_name = match.group(1) if match else "알 수 없음"
                    print(f"  ✅ 프로필 '{profile_name}' 자동 적용 확인")
                else:
                    print(f"  ❌ 프로필 자동 적용 메시지 누락 또는 불일치")
                    print(f"     출력: {output[:300]}")
                    failed += 1
                    continue
            
            # 해상도 확인
            if tc["expected_resolution"] in output:
                print(f"  ✅ 해상도 {tc['expected_resolution']} 확인")
            else:
                print(f"  ❌ 예상 해상도 {tc['expected_resolution']} 미확인")
                print(f"     출력: {output[:200]}")
                failed += 1
                continue
            
            passed += 1
            print(f"  ✅ 테스트 통과")
            
        except subprocess.TimeoutExpired:
            print(f"  ❌ 타임아웃 (10초 초과)")
            failed += 1
        except Exception as e:
            print(f"  ❌ 예외 발생: {e}")
            failed += 1
    
    print("\n" + "=" * 70)
    print(f"  테스트 결과: {passed}개 통과, {failed}개 실패")
    print("=" * 70)
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(test_checkpoint_profile_integration())
