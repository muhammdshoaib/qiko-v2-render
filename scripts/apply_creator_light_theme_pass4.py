"""Fourth pass: remaining dark-mode slate/cyan accents → light Signal palette."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "frontend" / "apps" / "creator"
SKIP = {"node_modules", ".next"}

REPLS = [
    # Body / muted text that was dark-theme light gray
    ("text-slate-200", "text-slate-700"),
    ("text-slate-300", "text-slate-600"),
    ("hover:text-slate-300", "hover:text-slate-700"),
    # Cyan link/accent → indigo
    ("text-cyan-300", "text-indigo-600"),
    ("text-cyan-400", "text-indigo-600"),
    ("hover:text-cyan-300", "hover:text-indigo-700"),
    ("bg-cyan-500/15 text-cyan-300", "bg-indigo-50 text-indigo-700"),
    ("bg-cyan-400", "bg-indigo-500"),
    ("bg-cyan-500", "bg-indigo-600"),
    ("hover:bg-cyan-400", "hover:bg-indigo-500"),
    ("hover:bg-cyan-500/20", "hover:bg-indigo-100"),
    ("border-cyan-500/40", "border-indigo-200"),
    ("bg-cyan-500/10", "bg-indigo-50"),
    ("from-cyan-500/10", "from-indigo-50"),
    ("from-cyan-500/10", "from-indigo-50"),
    ("to-violet-500/[0.06]", "to-violet-50"),
    ("from-cyan-400 to-blue-500", "from-indigo-500 to-violet-600"),
    ("shadow-cyan-500/20", "shadow-indigo-200"),
    ("focus-visible:border-cyan-500/60", "focus-visible:border-indigo-300"),
    ("focus-visible:ring-cyan-500", "focus-visible:ring-indigo-300"),
    ("focus-visible:ring-cyan-300", "focus-visible:ring-indigo-300"),
    ("focus-visible:ring-cyan-400/60", "focus-visible:ring-indigo-300"),
    ("ring-cyan-500", "ring-indigo-300"),
    # Status chips readable on light
    ("text-emerald-400", "text-emerald-700"),
    ("text-amber-400", "text-amber-700"),
    ("bg-emerald-500/15 text-emerald-400", "bg-emerald-50 text-emerald-700"),
    ("bg-emerald-500/15", "bg-emerald-50"),
    ("border-emerald-500/25", "border-emerald-200"),
    ("border-amber-500/25", "border-amber-200"),
    ("bg-amber-500/10", "bg-amber-50"),
    # Code blocks / dark leftover fills
    ("bg-black/40", "bg-slate-100"),
    ("bg-slate-700", "bg-slate-200"),
    ("via-white/[0.015]", "via-white"),
    # Indigo link contrast
    ("text-indigo-300", "text-indigo-600"),
    ("focus-visible:ring-indigo-400/60", "focus-visible:ring-indigo-300"),
]


def main() -> None:
    updated = 0
    for path in ROOT.rglob("*"):
        if any(part in SKIP for part in path.parts):
            continue
        if path.suffix not in {".tsx", ".ts"}:
            continue
        text = path.read_text(encoding="utf-8")
        orig = text
        for old, new in REPLS:
            text = text.replace(old, new)
        if text != orig:
            path.write_text(text, encoding="utf-8")
            updated += 1
            print(path.relative_to(ROOT))
    print(f"updated_files={updated}")


if __name__ == "__main__":
    main()
