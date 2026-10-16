"""Targeted UX polish for worker + knowledge headers/CTAs on light theme."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "frontend" / "apps" / "creator"

FILES = {
    ROOT / "app" / "workers" / "[id]" / "page.tsx": [
        ("bg-indigo-600 px-4 text-sm font-semibold text-slate-950", "bg-indigo-600 px-4 text-sm font-semibold text-white"),
        ("from-emerald-500 to-cyan-500", "from-emerald-500 to-teal-500"),
        ('Zap className="size-4 sm:size-5 text-indigo-600"', 'Zap className="size-4 sm:size-5 text-white"'),
        ('BrainCircuit className="size-4 sm:size-5 text-indigo-600"', 'BrainCircuit className="size-4 sm:size-5 text-slate-500"'),
        ('BrainCircuit className="size-7 text-indigo-600 sm:size-8"', 'BrainCircuit className="size-7 text-white sm:size-8"'),
        ("from-cyan-500/10 to-violet-500/[0.06]", "from-indigo-50 to-violet-50"),
        ("bg-white/[0.01]", "bg-slate-50"),
        ("bg-slate-200", "bg-slate-200"),  # noop placeholder kept for clarity
    ],
    ROOT / "app" / "knowledge" / "investors" / "page.tsx": [
        (
            "from-indigo-400 to-cyan-400 text-lg font-bold text-slate-950",
            "from-indigo-500 to-violet-600 text-lg font-bold text-white",
        ),
        ("from-cyan-500/10 to-violet-500/[0.06]", "from-indigo-50 to-violet-50"),
        ("bg-indigo-600 px-4 text-sm font-semibold text-slate-950", "bg-indigo-600 px-4 text-sm font-semibold text-white"),
    ],
    ROOT / "app" / "knowledge" / "portfolio-reporter" / "page.tsx": [
        (
            "from-cyan-400 to-indigo-400 text-lg font-bold text-slate-950",
            "from-indigo-500 to-violet-600 text-lg font-bold text-white",
        ),
        ("from-cyan-500/10 to-violet-500/[0.06]", "from-indigo-50 to-violet-50"),
        ("bg-indigo-600 px-4 text-sm font-semibold text-slate-950", "bg-indigo-600 px-4 text-sm font-semibold text-white"),
    ],
    ROOT / "components" / "knowledge" / "investors-chat.tsx": [
        ("bg-indigo-600 px-4 py-2 text-sm font-semibold text-slate-950", "bg-indigo-600 px-4 py-2 text-sm font-semibold text-white"),
    ],
    ROOT / "components" / "knowledge" / "portfolio-reporter-chat.tsx": [
        ("bg-indigo-600 px-4 py-2 text-sm font-semibold text-slate-950", "bg-indigo-600 px-4 py-2 text-sm font-semibold text-white"),
    ],
}

# Global safe CTA contrast: indigo solid + slate-950 text → white
GLOBAL = [
    ("bg-indigo-600 px-4 text-sm font-semibold text-slate-950", "bg-indigo-600 px-4 text-sm font-semibold text-white"),
    ("bg-indigo-600 px-4 py-2 text-sm font-semibold text-slate-950", "bg-indigo-600 px-4 py-2 text-sm font-semibold text-white"),
    ("rounded-lg bg-indigo-600 px-4 text-sm font-semibold text-slate-950", "rounded-lg bg-indigo-600 px-4 text-sm font-semibold text-white"),
]


def main() -> None:
    for path, repls in FILES.items():
        if not path.exists():
            print("missing", path)
            continue
        text = path.read_text(encoding="utf-8")
        orig = text
        for old, new in repls:
            if old == new:
                continue
            text = text.replace(old, new)
        if text != orig:
            path.write_text(text, encoding="utf-8")
            print("updated", path.relative_to(ROOT))

    # Sweep remaining indigo+slate-950 CTAs
    updated = 0
    for path in ROOT.rglob("*.tsx"):
        if any(p in path.parts for p in (".next", "node_modules")):
            continue
        text = path.read_text(encoding="utf-8")
        orig = text
        for old, new in GLOBAL:
            text = text.replace(old, new)
        # Common remaining dark-header cyan bands
        text = text.replace("from-cyan-500/10 to-violet-500/[0.06]", "from-indigo-50 to-violet-50")
        if text != orig:
            path.write_text(text, encoding="utf-8")
            updated += 1
            print("sweep", path.relative_to(ROOT))
    print(f"sweep_updated={updated}")


if __name__ == "__main__":
    main()
