# 📂 PLEPA `scripts/` 디렉토리 안내 (Wave 5-B 계층 정리)

## 1. 루트 활성 운영 CLI (Production CLIs — 전 모듈 `<=350L` / `<=120L`)
| 스크립트 | 역할 |
| :--- | :--- |
| `export_context.py` + `context_exporter/` | Gemini 노트북·인계용 `context_snapshot/` 5종 번들 추출기 |
| `start_remote.py` | 8080 NiceGUI 웹 스튜디오 + Cloudflared 보안 원격 터널 기동 |
| `validate_genit_work.py` + `validate_genit_rules.py` | Gen-IT v2.2 5탭 완성본 스마트 해시·에셋 정합성 검증기 |
| `validate_novelchat_work.py` + `novelchat_asset_mapper.py` | 노벨챗 6탭 원고·500장 에셋 매핑 검증/매핑 CLI |
| `audit_asset_alignment.py` + `audit_alignment_helpers.py` | 포즈 DB ↔ 에셋 라벨·누락·고아 전수 정합성 감사 CLI |
| `audit_sector_assets.py` | 6대 섹터별 검열·`_origin` 백업·Auto-QC 감사 CLI |
| `plepa_upscaler.py` | 단독 4x AI 업스케일 CLI 래퍼 |
| `sync_to_kiro.py` | 레거시 `kiro` 덮어쓰기 브릿지 (**기본 `exit 2` 차단, `--force-unsafe` 전용**) |

## 2. 목적별 격리 하위 디렉토리 (활성 AST 부채 래칫 제외)
- **`scripts/ml/`**: YOLO11s-seg 검열 모델 학습/데이터셋 추출/정량 평가 (`extract_censor_seg_dataset.py`, `train_censor_seg.py`, `benchmark_censor_metrics.py`)
- **`scripts/benchmarks/`**: 화풍·검열·야간감사 일회성 실험 및 HTML 갤러리 생성기 10종
- **`scripts/archive/`**: 은퇴한 구형 `:8085` 뷰어·마이그레이션 스크립트 (`generate_inspection_viewer.py`, `serve_benchmark_mobile.py`, `mobile_gallery.py` 등 — 현역 대체: `plepa_gui/pages/mobile_viewer.py` + `scripts/start_remote.py`)
