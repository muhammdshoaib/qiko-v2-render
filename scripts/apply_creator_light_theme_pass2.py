"""Second pass: remaining heading text-white and tab active states."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "frontend" / "apps" / "creator"
SKIP = {"node_modules", ".next"}

REPLS = [
    ("text-[28px] font-bold tracking-[-0.02em] text-white", "text-[28px] font-bold tracking-[-0.02em] text-foreground"),
    ("text-[18px] font-extrabold tracking-[-0.02em] text-white", "text-[18px] font-extrabold tracking-[-0.02em] text-foreground"),
    ("text-[22px] font-extrabold tracking-[-0.02em] text-white", "text-[22px] font-extrabold tracking-[-0.02em] text-foreground"),
    ("text-2xl font-bold text-white", "text-2xl font-bold text-foreground"),
    ('active ? "border-cyan-400 text-white"', 'active ? "border-indigo-500 text-foreground"'),
    (
        'isActive ? "border-cyan-500/30 bg-cyan-500/10 text-white"',
        'isActive ? "border-indigo-300 bg-indigo-50 text-indigo-800"',
    ),
    ("border-transparent text-slate-300", "border-transparent text-slate-500"),
    ("hover:border-white/[0.14]", "hover:border-slate-300"),
    ('AlertDialogContent className="border-border bg-card text-white"', 'AlertDialogContent className="border-border bg-card text-foreground"'),
    ('<span className="text-white">', '<span className="text-foreground">'),
    ('BrainCircuit className="size-7 text-white', 'BrainCircuit className="size-7 text-indigo-600'),
    ('Bot className="size-4 text-white"', 'Bot className="size-4 text-indigo-600"'),
    ('Zap className="size-4 sm:size-5 text-white"', 'Zap className="size-4 sm:size-5 text-indigo-600"'),
    ('BrainCircuit className="size-4 sm:size-5 text-white"', 'BrainCircuit className="size-4 sm:size-5 text-indigo-600"'),
    ('font-semibold text-sm sm:text-base text-white', "font-semibold text-sm sm:text-base text-foreground"),
    ("group-hover:text-cyan-200", "group-hover:text-indigo-700"),
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
