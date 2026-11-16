import json
import html
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from PIL import Image

from plepa_engine.qa_validator import (
    configure_qa_runtime,
    detect_faces,
    detect_hands,
    detect_heads,
    detect_person,
)
from plepa_engine.services.pose_service import default_pose_service

ROOT = Path(__file__).resolve().parent.parent
OUT_ROOT = ROOT / "output" / "overnight_full_audit"


def _measure_image(path: Path) -> Dict:
    img = Image.open(path).convert("RGB")
    _, h = img.size
    persons = [p for p in detect_person(img) if p[2] >= 0.45]
    heads = [hd for hd in detect_heads(img) if hd[2] >= 0.50]
    faces = [fc for fc in detect_faces(img) if fc[2] >= 0.50]
    hands = [hn for hn in detect_hands(img) if hn[2] >= 0.60]
    fr = 0.0
    if faces:
        fr = max((f[0][3] - f[0][1]) / h for f in faces)
    elif heads:
        fr = max((hd[0][3] - hd[0][1]) / h for hd in heads)
    return {
        "persons": len(persons),
        "heads": len(heads),
        "faces": len(faces),
        "hands": len(hands),
        "fr": round(fr, 4),
    }


def _find_origin(after_path: Path, roster_dir: Path, char_pfx: str) -> Optional[Path]:
    rel = after_path.relative_to(roster_dir / char_pfx)
    cand = roster_dir / f"{char_pfx}_origin" / rel
    if cand.exists():
        return cand
    return None


def _compute_censor_pct(after_path: Path, origin_path: Optional[Path]) -> float:
    if not origin_path or not origin_path.exists():
        return 0.0
    a_arr = np.asarray(Image.open(after_path).convert("RGB"), dtype=np.int16)
    o_arr = np.asarray(Image.open(origin_path).convert("RGB"), dtype=np.int16)
    if a_arr.shape != o_arr.shape:
        return 0.0
    diff = np.abs(a_arr - o_arr).max(axis=2) > 15
    return round(float(diff.mean()) * 100.0, 3)


def _find_before_asset(roster: str, char_pfx: str, code: str) -> Optional[Path]:
    char_dir = ROOT / "projects" / roster / "assets" / char_pfx
    if not char_dir.exists():
        return None
    matches = [p for p in char_dir.rglob(f"{char_pfx}_{code}_*.webp") if "_origin" not in str(p)]
    return matches[0] if matches else None


def main() -> None:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    configure_qa_runtime(True)

    run_results_path = OUT_ROOT / "run_results.json"
    run_records: Dict[str, Dict] = {}
    if run_results_path.exists():
        for rec in json.loads(run_results_path.read_text(encoding="utf-8")):
            key = f"{rec['roster']}:{rec['char']}:{rec['code']}"
            run_records[key] = rec

    pose_dbs = {
        "campus": default_pose_service.load_pose_db(engine="sdxl", roster="campus"),
        "oto": default_pose_service.load_pose_db(engine="sdxl", roster="oto"),
    }

    rows: List[Dict] = []
    for roster in ("campus", "oto"):
        roster_dir = OUT_ROOT / roster / roster
        if not roster_dir.exists():
            roster_dir = OUT_ROOT / roster
        if not roster_dir.exists():
            continue
        db = pose_dbs[roster]
        for char_dir in sorted(roster_dir.iterdir()):
            if not char_dir.is_dir() or char_dir.name.endswith("_origin"):
                continue
            char_pfx = char_dir.name
            for fpath in sorted(char_dir.rglob("*.webp")):
                parts = fpath.stem.split("_")
                if len(parts) < 3:
                    continue
                code = parts[1]
                pose = db.get(code)
                section = pose.section if pose else "unknown"
                mob_tier = getattr(pose, "mob_tier", None) if pose else None
                label = pose.label if pose else "_".join(parts[2:])

                after_m = _measure_image(fpath)
                before_path = _find_before_asset(roster, char_pfx, code)
                before_m = _measure_image(before_path) if before_path else None
                origin_path = _find_origin(fpath, roster_dir, char_pfx)
                censor_pct = _compute_censor_pct(fpath, origin_path)

                rec = run_records.get(f"{roster}:{char_pfx}:{code}", {})
                retries = int(rec.get("retries", 0))
                qc_passed = rec.get("qc_passed", True)
                duration_sec = float(rec.get("duration_sec", 0.0))

                flags = []
                if retries >= 3:
                    flags.append("MAX_RETRIES_3")
                if not qc_passed:
                    flags.append("QC_FAILED_FALLBACK")
                if after_m["faces"] >= 2:
                    flags.append("FACES>=2")
                if censor_pct > 8.0:
                    flags.append("CENSOR>8%")
                if (mob_tier == 3 or section in ("scenes_otokonoko", "special_otokonoko_h")) and censor_pct == 0.0:
                    flags.append("ZERO_CENSOR_EXPECT_PENIS")

                rows.append({
                    "roster": roster,
                    "char": char_pfx,
                    "code": code,
                    "label": label,
                    "section": section,
                    "mob_tier": mob_tier,
                    "before_fr": before_m["fr"] if before_m else None,
                    "after_fr": after_m["fr"],
                    "persons": after_m["persons"],
                    "heads": after_m["heads"],
                    "faces": after_m["faces"],
                    "hands": after_m["hands"],
                    "censor_pct": censor_pct,
                    "retries": retries,
                    "qc_passed": qc_passed,
                    "duration_sec": round(duration_sec, 2),
                    "flags": flags,
                    "after_rel": fpath.relative_to(OUT_ROOT).as_posix(),
                    "before_rel": f"projects/{roster}/assets/{before_path.relative_to(ROOT / 'projects' / roster / 'assets').as_posix()}" if before_path else None,
                })

    # Aggregate by section
    by_section: Dict[str, List[Dict]] = defaultdict(list)
    for r in rows:
        by_section[r["section"]].append(r)

    sec_order = [
        "emotions", "poses", "daily_events", "romance",
        "h_scenes", "special_female_h", "scenes_otokonoko", "special_otokonoko_h",
    ]
    all_sections = [s for s in sec_order if s in by_section] + [
        s for s in sorted(by_section) if s not in sec_order
    ]

    sec_stats = []
    for sec in all_sections:
        items = by_section[sec]
        n = len(items)
        first_pass = sum(1 for x in items if x["retries"] == 0 and x["qc_passed"])
        final_pass = sum(1 for x in items if x["qc_passed"])
        avg_retries = sum(x["retries"] for x in items) / n
        b_frs = [x["before_fr"] for x in items if x["before_fr"] is not None]
        a_frs = [x["after_fr"] for x in items]
        c_pos = [x["censor_pct"] for x in items if x["censor_pct"] > 0]
        sec_stats.append({
            "section": sec,
            "count": n,
            "first_pass_pct": round(first_pass / n * 100, 1),
            "final_pass_pct": round(final_pass / n * 100, 1),
            "avg_retries": round(avg_retries, 2),
            "before_avg_fr": round(sum(b_frs) / len(b_frs), 4) if b_frs else None,
            "after_avg_fr": round(sum(a_frs) / n, 4),
            "persons_ge_2": sum(1 for x in items if x["persons"] >= 2),
            "heads_ge_2": sum(1 for x in items if x["heads"] >= 2),
            "faces_ge_2": sum(1 for x in items if x["faces"] >= 2),
            "hands_ge_3": sum(1 for x in items if x["hands"] >= 3),
            "censor_detect_pct": round(len(c_pos) / n * 100, 1),
            "censor_avg_pct": round(sum(c_pos) / len(c_pos), 3) if c_pos else 0.0,
        })

    outliers = [r for r in rows if r["flags"]]
    summary = {
        "total_images": len(rows),
        "total_duration_sec": round(sum(r["duration_sec"] for r in rows), 1),
        "section_stats": sec_stats,
        "outlier_count": len(outliers),
        "outliers": outliers,
        "rows": rows,
    }
    (OUT_ROOT / "overnight_audit_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Write REPORT.md
    md = [
        "# Overnight Full-Pose Audit Report",
        "",
        f"- **Total Images Evaluated:** {len(rows)}",
        f"- **Total Recorded Generation Time:** {summary['total_duration_sec']}s",
        f"- **Flagged Outliers:** {len(outliers)}",
        "",
        "## 1. Section-by-Section Quantitative Summary",
        "",
        "| Section | N | 1st Pass % | Final Pass % | Avg Retries | Before FR | After FR | P>=2 | Hd>=2 | Fc>=2 | Hnd>=3 | Censor Det % | Avg Mask % |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]
    for s in sec_stats:
        bfr = f"{s['before_avg_fr']:.4f}" if s["before_avg_fr"] is not None else "-"
        md.append(
            f"| `{s['section']}` | {s['count']} | {s['first_pass_pct']}% | {s['final_pass_pct']}% | "
            f"{s['avg_retries']} | {bfr} | {s['after_avg_fr']:.4f} | "
            f"{s['persons_ge_2']} | {s['heads_ge_2']} | {s['faces_ge_2']} | {s['hands_ge_3']} | "
            f"{s['censor_detect_pct']}% | {s['censor_avg_pct']}% |"
        )
    md.extend(["", "## 2. Flagged Outliers", ""])
    if not outliers:
        md.append("- None (0 outliers)")
    else:
        md.append("| Char | Code | Section | Tier | Flags | Retries | Faces | Censor % |")
        md.append("| :--- | :---: | :--- | :---: | :--- | :---: | :---: | :---: |")
        for o in outliers:
            md.append(
                f"| `{o['char']}` | `{o['code']}` | `{o['section']}` | {o['mob_tier']} | "
                f"`{', '.join(o['flags'])}` | {o['retries']} | {o['faces']} | {o['censor_pct']}% |"
            )
    (OUT_ROOT / "REPORT.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    # Write Comparison Gallery index.html
    cards = []
    for r in sorted(rows, key=lambda x: (x["code"], x["char"])):
        b_img = (
            f'<img src="/{html.escape(r["before_rel"])}" loading="lazy" alt="Before">'
            if r["before_rel"]
            else '<div class="empty">No Before</div>'
        )
        a_img = f'<img src="{html.escape(r["after_rel"])}" loading="lazy" alt="After">'
        flag_badge = f'<span class="flag">{html.escape(", ".join(r["flags"]))}</span>' if r["flags"] else ""
        cards.append(
            f'<div class="card" data-char="{html.escape(r["char"])}" data-sec="{html.escape(r["section"])}" data-flag="{1 if r["flags"] else 0}">'
            f'<div class="hdr"><b>{html.escape(r["char"])} #{html.escape(r["code"])}</b> ({html.escape(r["section"])}) {flag_badge}</div>'
            f'<div class="meta">FR: {r["before_fr"]} → {r["after_fr"]} | P:{r["persons"]} Hd:{r["heads"]} Fc:{r["faces"]} Hn:{r["hands"]} | Retries:{r["retries"]} | Censor:{r["censor_pct"]}%</div>'
            f'<div class="pair"><div><small>Before</small>{b_img}</div><div><small>After</small>{a_img}</div></div>'
            f'</div>'
        )

    gallery_html = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PLEPA Overnight Full-Pose Audit</title>
<style>
body{{background:#111318;color:#e6e9ef;font-family:system-ui,sans-serif;margin:0;padding:12px}}
.bar{{position:sticky;top:0;background:#1a1d24;padding:10px;border-radius:8px;margin-bottom:12px;display:flex;gap:8px;flex-wrap:wrap;z-index:10}}
select,button{{background:#252a34;color:#fff;border:1px solid #3a4150;padding:6px 10px;border-radius:6px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:12px}}
.card{{background:#181b22;border:1px solid #2b3140;border-radius:8px;padding:8px}}
.hdr{{font-size:14px;margin-bottom:4px}}
.meta{{font-size:11px;color:#9aa4b2;margin-bottom:6px}}
.flag{{background:#7f1d1d;color:#fecaca;padding:2px 6px;border-radius:4px;font-size:11px;margin-left:4px}}
.pair{{display:grid;grid-template-columns:1fr 1fr;gap:6px}}
.pair img{{width:100%;border-radius:4px;display:block}}
.empty{{height:200px;display:flex;align-items:center;justify-content:center;background:#101217;color:#666;border-radius:4px;font-size:12px}}
</style></head><body>
<div class="bar">
  <strong>Overnight Audit ({len(rows)}장 | Outliers: {len(outliers)})</strong>
  <select id="fChar" onchange="flt()"><option value="">All Chars</option><option value="aya">aya</option><option value="kei">kei</option><option value="shz">shz</option></select>
  <select id="fFlag" onchange="flt()"><option value="">All</option><option value="1">Outliers Only</option></select>
</div>
<div class="grid">{"".join(cards)}</div>
<script>
function flt(){{
  const c=document.getElementById('fChar').value, f=document.getElementById('fFlag').value;
  document.querySelectorAll('.card').forEach(el=>{{
    const okC=!c||el.dataset.char===c, okF=!f||el.dataset.flag===f;
    el.style.display=(okC&&okF)?'':'none';
  }});
}}
</script></body></html>"""
    (OUT_ROOT / "index.html").write_text(gallery_html, encoding="utf-8")
    print(f"Evaluated {len(rows)} images, {len(outliers)} outliers -> {OUT_ROOT / 'REPORT.md'}")


if __name__ == "__main__":
    main()
