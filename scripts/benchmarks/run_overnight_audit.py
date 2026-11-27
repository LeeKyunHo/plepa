import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from plepa_engine.services.generation_service import GenerationParams, GenerationService
from scripts.benchmarks.evaluate_overnight_audit import OUT_ROOT, main as evaluate_main


def _save_records(records: list) -> None:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    (OUT_ROOT / "run_results.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _run_stage(svc: GenerationService, roster: str, char_expr: str, pose_expr: str, out_sub: str, records: list) -> None:
    params = GenerationParams(
        character_expr=char_expr,
        pose_expr=pose_expr,
        roster=roster,
        overwrite=False,
        auto_qc=True,
        censor=True,
        max_retries=3,
        out_dir=f"output/overnight_full_audit/{out_sub}",
    )
    results = svc.run_batch(params, quiet=False)
    for r in results:
        records.append({
            "roster": roster,
            "char": r.target.character_prefix,
            "code": r.target.code,
            "section": r.target.section,
            "success": r.success,
            "qc_passed": r.qc_passed,
            "qc_reason": r.qc_reason,
            "retries": r.retries,
            "duration_sec": round(r.duration_sec, 2),
        })
    _save_records(records)


def main() -> None:
    svc = GenerationService()
    records = []

    print("=== [Stage 1A] campus / aya / all poses ===", flush=True)
    _run_stage(svc, "campus", "aya", "all", "campus", records)

    print("=== [Stage 1B] oto / kei / all poses ===", flush=True)
    _run_stage(svc, "oto", "kei", "all", "oto", records)

    print("=== [Stage 1 Eval] Generating Stage 1 REPORT.md & Gallery ===", flush=True)
    evaluate_main()

    print("=== [Stage 2] campus / shz / 060..132 ===", flush=True)
    _run_stage(svc, "campus", "shz", "060..132", "campus", records)

    print("=== [Final Eval] Updating REPORT.md & Gallery ===", flush=True)
    evaluate_main()


if __name__ == "__main__":
    main()
