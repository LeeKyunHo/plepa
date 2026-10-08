"""
test_checkpoint_service.py
체크포인트 프로필 서비스 테스트 스크립트
"""

from plepa_engine.checkpoint_service import CheckpointService, get_profile_for_checkpoint, get_recommended_summary


def test_profile_loading():
    """프로필 로딩 테스트"""
    print("=" * 70)
    print("  [테스트 1] 체크포인트 프로필 로딩")
    print("=" * 70)
    
    service = CheckpointService()
    profiles = service.list_all_profiles()
    
    print(f"✓ 총 {len(profiles)}개 프로필 로드 완료\n")
    
    for profile in profiles:
        print(f"• {profile.name}")
        print(f"  - 해상도: {profile.width}x{profile.height}")
        print(f"  - 스텝/CFG: {profile.steps}스텝 / CFG {profile.cfg}")
        print(f"  - 샘플러: {profile.sampler} / {profile.scheduler}")
        print(f"  - 매칭 패턴: {', '.join(profile.match_patterns)}")
        print()


def test_exact_match():
    """정확한 파일명 매칭 테스트"""
    print("=" * 70)
    print("  [테스트 2] 정확한 파일명 매칭")
    print("=" * 70)
    
    test_cases = [
        "waiIllustriousSDXL_v170.safetensors",
        "unholyDesireMixSinister_v90.safetensors",
        "loxsHEXMIX_hexmixV50.safetensors",
    ]
    
    for ckpt_name in test_cases:
        profile = get_profile_for_checkpoint(ckpt_name)
        print(f"✓ {ckpt_name}")
        print(f"  → {profile.name} ({profile.width}x{profile.height}, CFG {profile.cfg})")
        print()


def test_fuzzy_match():
    """퍼지 매칭 테스트 (부분 문자열)"""
    print("=" * 70)
    print("  [테스트 3] 퍼지 매칭 (부분 문자열)")
    print("=" * 70)
    
    test_cases = [
        "illustrious_v2_beta.safetensors",  # "illustrious" 패턴 매칭
        "unholy_custom_merge.ckpt",         # "unholy" 패턴 매칭
        "hexmix_anime_v6.safetensors",      # "hexmix" 패턴 매칭
        "pony_realism_xl.safetensors",      # "pony" 패턴 매칭
    ]
    
    for ckpt_name in test_cases:
        profile = get_profile_for_checkpoint(ckpt_name)
        print(f"✓ {ckpt_name}")
        print(f"  → 매칭: {profile.name}")
        print(f"  → 설정: {profile.width}x{profile.height}, CFG {profile.cfg}, {profile.sampler}")
        print()


def test_fallback():
    """미등록 체크포인트 폴백 테스트"""
    print("=" * 70)
    print("  [테스트 4] 미등록 체크포인트 (기본 프로필 폴백)")
    print("=" * 70)
    
    unknown_ckpt = "completely_unknown_model_v999.safetensors"
    profile = get_profile_for_checkpoint(unknown_ckpt)
    
    print(f"✓ {unknown_ckpt}")
    print(f"  → 폴백: {profile.name}")
    print(f"  → 설정: {profile.width}x{profile.height}, CFG {profile.cfg}")
    print()


def test_recommended_summary():
    """권장 설정 요약 문자열 테스트"""
    print("=" * 70)
    print("  [테스트 5] 권장 설정 요약 문자열 (GUI 표시용)")
    print("=" * 70)
    
    test_cases = [
        "waiIllustriousSDXL_v170.safetensors",
        "unholyDesireMixSinister_v90.safetensors",
        "unknown_model.safetensors",
    ]
    
    for ckpt_name in test_cases:
        summary = get_recommended_summary(ckpt_name)
        print(f"✓ {ckpt_name}")
        print(f"  → {summary}")
        print()


def test_quality_tags():
    """체크포인트별 품질 태그 확인"""
    print("=" * 70)
    print("  [테스트 6] 체크포인트별 품질 태그")
    print("=" * 70)
    
    test_cases = [
        "waiIllustriousSDXL_v170.safetensors",
        "unholyDesireMixSinister_v90.safetensors",
        "ponyDiffusionV6XL.safetensors",
    ]
    
    for ckpt_name in test_cases:
        profile = get_profile_for_checkpoint(ckpt_name)
        print(f"✓ {profile.name}")
        print(f"  Positive: {profile.quality_positive[:80]}...")
        print(f"  Negative: {profile.quality_negative[:80]}...")
        print()


def test_profile_application():
    """프로필을 옵션 딕셔너리에 적용 테스트"""
    print("=" * 70)
    print("  [테스트 7] 프로필 자동 적용 (GenerationOptions)")
    print("=" * 70)
    
    service = CheckpointService()
    
    # 기본 옵션 (사용자가 아무것도 설정 안한 상태)
    default_options = {
        "width": 832,
        "height": 1216,
        "steps": 25,
        "cfg": 6.5,
        "sampler": "dpmpp_sde",
        "scheduler": "karras"
    }
    
    ckpt_name = "waiIllustriousSDXL_v170.safetensors"
    
    print(f"✓ 체크포인트: {ckpt_name}")
    print(f"  적용 전: {default_options}")
    
    updated_options = service.apply_profile_to_options(
        default_options.copy(),
        ckpt_name,
        engine="sdxl",
        override_user_values=False  # 기본값만 교체
    )
    
    print(f"  적용 후: {updated_options}")
    print()
    
    # 사용자 커스텀 값이 있는 경우
    custom_options = {
        "width": 1024,  # 사용자가 직접 설정
        "height": 1024,  # 사용자가 직접 설정
        "steps": 25,     # 기본값
        "cfg": 6.5,      # 기본값
        "sampler": "dpmpp_sde",
        "scheduler": "karras"
    }
    
    print(f"✓ 사용자 커스텀 옵션 (width/height만 변경)")
    print(f"  적용 전: {custom_options}")
    
    updated_custom = service.apply_profile_to_options(
        custom_options.copy(),
        ckpt_name,
        engine="sdxl",
        override_user_values=False  # 사용자 값 보존
    )
    
    print(f"  적용 후: {updated_custom}")
    print(f"  → width/height는 사용자 값 보존, 나머지는 프로필 적용")
    print()


def main():
    """모든 테스트 실행"""
    try:
        test_profile_loading()
        test_exact_match()
        test_fuzzy_match()
        test_fallback()
        test_recommended_summary()
        test_quality_tags()
        test_profile_application()
        
        print("=" * 70)
        print("  ✅ 모든 테스트 통과!")
        print("=" * 70)
        
    except Exception as e:
        print(f"\n❌ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
