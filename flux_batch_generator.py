#!/usr/bin/env python3
"""
flux_batch_generator.py
하위 호환성을 위한 CLI 진입점 래퍼 (단일 진실 공급원: batch_generator.py).
모든 배치 생성 기능과 최신 옵션(--censor-only, white_silhouette, Auto-QC 등)은
batch_generator.py에서 단일 관리됩니다.
"""

from __future__ import annotations

import sys

from batch_generator import *  # noqa: F401, F403
from batch_generator import main

if __name__ == "__main__":
    sys.exit(main())
