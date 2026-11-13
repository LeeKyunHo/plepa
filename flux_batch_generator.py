#!/usr/bin/env python3
"""
[DEPRECATED / LEGACY] flux_batch_generator.py
플에파는 SDXL 단일 파이프라인으로 영구 일원화되었습니다 (GEMINI.md 제3조).
하위 호환성을 유지하기 위한 CLI 진입점 래퍼이며, 실제 모든 기능은 batch_generator.py에서 단일 관리됩니다.
"""

from __future__ import annotations

import sys

from batch_generator import *  # noqa: F401, F403
from batch_generator import main

if __name__ == "__main__":
    print(
        "[DEPRECATED] flux_batch_generator.py는 하위 호환 래퍼입니다. "
        "'python batch_generator.py' 사용을 적극 권장합니다.",
        file=sys.stderr,
    )
    sys.exit(main())

