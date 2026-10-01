"""
plepa_engine
플에파(PLEPA: Flux Asset Pipeline) 핵심 파이프라인 엔진 패키지.
"""

__version__ = "1.0.0"

from plepa_engine.profile_resolver import (
    BUILTIN_PROFILES,
    apply_profile_to_prompt,
    load_global_profiles,
    resolve_character_profile,
)

__all__ = [
    "BUILTIN_PROFILES",
    "load_global_profiles",
    "resolve_character_profile",
    "apply_profile_to_prompt",
]
