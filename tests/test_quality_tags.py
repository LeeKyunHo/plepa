"""
체크포인트별 품질 태그 자동 주입 테스트
각 체크포인트마다 다른 품질 태그가 프롬프트에 추가되는지 확인
"""

import sys
from plepa_engine.prompt_builder import assemble_sdxl_prompt
from plepa_engine.models import CharacterConfig, PoseEntry

def test_quality_tag_injection():
    """체크포인트별 품질 태그 주입 테스트"""
    
    print("=" * 70)
    print("  체크포인트별 품질 태그 자동 주입 테스트")
    print("=" * 70)
    
    # 테스트용 캐릭터 생성
    char = CharacterConfig.from_dict({
        "prefix": "test",
        "name": "테스트 캐릭터",
        "appearance": {
            "outfit": "blue dress",
            "face_and_hair": "long black hair, brown eyes",
            "physique": "slim body"
        }
    })
    
    # 테스트용 포즈 생성
    pose = PoseEntry(
        code="000",
        label="평상",
        section="emotions",
        prompt="1girl, standing, smile"
    )
    
    test_cases = [
        {
            "checkpoint": "WAI-NSFW-illustrious-v7.safetensors",
            "expected_quality": "amazing quality, very aesthetic",
            "description": "WAI-Illustrious (amazing quality)"
        },
        {
            "checkpoint": "unholy_desire_mix_v5.0.safetensors",
            "expected_quality": "amazing quality, very aesthetic, absurdres, newest, glossy skin",
            "description": "Unholy Mix (amazing quality + glossy skin)"
        },
        {
            "checkpoint": "pony_diffusion_v6.safetensors",
            "expected_quality": "score_9, score_8_up, score_7_up",
            "description": "Pony Diffusion (score_9)"
        },
        {
            "checkpoint": "unknown_model.safetensors",
            "expected_quality": "masterpiece, best quality",
            "description": "Unknown (기본값: masterpiece)"
        }
    ]
    
    passed = 0
    failed = 0
    
    for tc in test_cases:
        print(f"\n[테스트] {tc['description']}")
        print(f"  체크포인트: {tc['checkpoint']}")
        
        # 프롬프트 조립 (체크포인트 이름 전달)
        positive, negative, is_nude = assemble_sdxl_prompt(
            char, pose, checkpoint_name=tc["checkpoint"]
        )
        
        # 품질 태그 확인
        print(f"  실제 프롬프트: {positive[:200]}")
        
        if tc["expected_quality"] in positive:
            print(f"  ✅ 품질 태그 '{tc['expected_quality']}' 주입 확인")
            passed += 1
        else:
            print(f"  ❌ 품질 태그 미주입")
            print(f"     예상: {tc['expected_quality']}")
            failed += 1
    
    print("\n" + "=" * 70)
    print(f"  테스트 결과: {passed}개 통과, {failed}개 실패")
    print("=" * 70)
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(test_quality_tag_injection())
