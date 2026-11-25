"""
plepa_gui.components.option_controls
GENERATION_OPTION_SPECS 단일 레지스트리 기반 NiceGUI 동적 옵션 위젯 렌더러 및 값 정규화기.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List

from nicegui import ui


def normalize_option_values(specs: List[Dict[str, Any]], state: Dict[str, Any]) -> Dict[str, Any]:
    """GUI 폼 상태 값을 GenerationParams 호환 파이썬 타입으로 정규화합니다."""
    resolved: Dict[str, Any] = {}
    for spec in specs:
        field = spec["field"]
        widget = spec.get("widget", "checkbox")
        default = spec.get("default")
        raw = state.get(field, default)

        if widget == "text":
            text = str(raw or "").strip()
            resolved[field] = text if text else None
        elif widget == "int":
            if raw is None or (isinstance(raw, str) and not raw.strip()):
                resolved[field] = default
            else:
                resolved[field] = int(float(raw))
        elif widget == "float":
            if raw is None or (isinstance(raw, str) and not raw.strip()):
                resolved[field] = default
            else:
                resolved[field] = float(raw)
        elif widget == "select":
            resolved[field] = raw if raw is not None else default
        else:
            resolved[field] = bool(raw)
    return resolved


def render_option_controls(
    specs: List[Dict[str, Any]],
    state: Dict[str, Any],
    on_change: Callable[[str, Any, bool], None],
) -> None:
    """GENERATION_OPTION_SPECS의 위젯 유형(checkbox/select/int/float/text)에 맞춰 옵션을 렌더링합니다."""
    checkbox_specs = [s for s in specs if s.get("widget") in (None, "checkbox")]
    select_specs = [s for s in specs if s.get("widget") == "select"]
    numeric_specs = [s for s in specs if s.get("widget") in ("int", "float")]
    text_specs = [s for s in specs if s.get("widget") == "text"]

    with ui.row().classes("w-full items-center gap-3 p-3 bg-slate-800/40 rounded-lg border border-slate-700/50 mb-3 flex-wrap"):
        for spec in checkbox_specs:
            f = spec["field"]
            ui.checkbox(
                spec["label"],
                value=bool(state.get(f, spec["default"])),
                on_change=lambda e, field=f: on_change(field, e.value, False),
            ).props("dark dense").tooltip(spec["tooltip"])

    if select_specs or numeric_specs:
        with ui.row().classes("w-full items-center gap-3 p-2.5 bg-slate-800/30 rounded-lg border border-slate-700/40 mb-3 flex-wrap"):
            for spec in select_specs:
                f = spec["field"]
                ui.select(
                    options=spec["choices"],
                    value=state.get(f, spec["default"]),
                    label=spec["label"],
                    on_change=lambda e, field=f: on_change(field, e.value, True),
                ).props("dense outlined dark options-dense").classes("w-44 text-xs").tooltip(spec["tooltip"])

            for spec in numeric_specs:
                f = spec["field"]
                widget_kind = spec.get("widget")
                step = spec.get("step", 1 if widget_kind == "int" else 0.05)
                ui.number(
                    label=spec["label"],
                    value=state.get(f, spec["default"]),
                    min=spec.get("min"),
                    max=spec.get("max"),
                    step=step,
                    placeholder="자동/미지정",
                    on_change=lambda e, field=f: on_change(field, e.value, False),
                ).props("dense outlined dark clearable").classes("w-36 text-xs").tooltip(spec["tooltip"])

    if text_specs:
        with ui.expansion("고급 프롬프트 · LoRA · 태그 오버라이드", icon="tune").classes(
            "w-full bg-slate-800/30 rounded-lg border border-slate-700/40 mb-6 text-xs text-slate-300"
        ):
            with ui.row().classes("w-full gap-3 p-2 flex-wrap"):
                for spec in text_specs:
                    f = spec["field"]
                    ui.input(
                        label=spec["label"],
                        value=state.get(f) or "",
                        placeholder=spec.get("placeholder", ""),
                        on_change=lambda e, field=f: on_change(field, e.value or None, False),
                    ).props("dense outlined dark clearable").classes("w-56 text-xs").tooltip(spec["tooltip"])
