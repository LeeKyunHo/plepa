"""체크포인트 매칭 디버그"""
from plepa_engine.checkpoint_service import CheckpointService

service = CheckpointService()

test_names = [
    "WAI-NSFW-illustrious-v7.safetensors",
    "unholy_desire_mix_v5.0.safetensors",
    "pony_diffusion_v6.safetensors",
    "unknown_model.safetensors"
]

for name in test_names:
    profile = service.get_profile_for_checkpoint(name)
    print(f"{name}")
    print(f"  → 프로필: {profile.name}")
    print(f"  → 품질 태그: {profile.quality_positive[:60]}...")
    print()
