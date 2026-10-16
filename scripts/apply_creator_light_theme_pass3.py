"""Third pass: opacity whites, dark borders/bgs, settings accents → light Signal theme."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "frontend" / "apps" / "creator"
SKIP = {"node_modules", ".next"}

# Safe bulk replacements (order matters — longer / more specific first)
REPLS = [
    # Opacity text
    ("text-white/90", "text-slate-800"),
    ("text-white/80", "text-slate-700"),
    ("text-white/70", "text-slate-600"),
    ("text-white/62", "text-slate-500"),
    ("text-white/60", "text-slate-500"),
    ("text-white/58", "text-slate-500"),
    ("text-white/55", "text-slate-500"),
    ("text-white/50", "text-slate-500"),
    ("text-white/45", "text-slate-400"),
    ("text-white/40", "text-slate-400"),
    ("text-white/38", "text-slate-400"),
    ("placeholder:text-white/40", "placeholder:text-slate-400"),
    ("placeholder:text-white/38", "placeholder:text-slate-400"),
    # Borders
    ("border-white/[0.14]", "border-slate-300"),
    ("border-white/[0.12]", "border-slate-200"),
    ("border-white/[0.1]", "border-slate-200"),
    ("border-white/[0.10]", "border-slate-200"),
    ("border-white/[0.07]", "border-slate-200"),
    ("border-white/[0.04]", "border-slate-100"),
    ("border-b border-white/[0.04]", "border-b border-slate-100"),
    # Soft white fills used as dark-mode chips
    ("bg-white/[0.10]", "bg-slate-100"),
    ("bg-white/[0.05]", "bg-slate-50"),
    ("bg-white/10", "bg-slate-100"),
    ("hover:bg-white/[0.10]", "hover:bg-slate-100"),
    ("hover:bg-white/10", "hover:bg-slate-100"),
    # Dark panel hex leftovers
    ("bg-[#0b0e16]", "bg-white"),
    ("bg-[#0a0d15]", "bg-white"),
    ("bg-[#0f131d]", "bg-white"),
    ("bg-slate-950", "bg-white"),
    # Active chips / tabs still on dark cyan
    ('border-cyan-500/30 bg-cyan-500/10 text-white', "border-indigo-200 bg-indigo-50 text-indigo-800"),
    ('border-cyan-400/40 bg-cyan-500/10 text-white', "border-indigo-200 bg-indigo-50 text-indigo-800"),
    ('border-indigo-500/30 bg-indigo-500/10 text-white', "border-indigo-200 bg-indigo-50 text-indigo-800"),
    ('bg-indigo-500/20 text-white', "bg-indigo-50 text-indigo-800"),
    ('bg-indigo-500/10 text-white', "bg-indigo-50 text-indigo-800"),
    ('bg-indigo-500/15 text-white', "bg-indigo-50 text-indigo-800"),
    ('border-indigo-500/50 bg-indigo-500/15 text-white', "border-indigo-300 bg-indigo-50 text-indigo-800"),
    ('border-b-2 border-indigo-400 text-white', "border-b-2 border-indigo-500 text-foreground"),
    ('border-primary text-white', "border-indigo-500 text-foreground"),
    ('border-primary/50 bg-primary/10 text-white', "border-indigo-300 bg-indigo-50 text-indigo-800"),
    ('border-border bg-white/10 text-white', "border-border bg-slate-100 text-foreground"),
    ('border-border bg-slate-100 text-white', "border-border bg-slate-100 text-foreground"),
    ('bg-muted text-white', "bg-muted text-foreground"),
    # Common heading leftovers
    ("tracking-[-0.03em] text-white", "tracking-[-0.03em] text-foreground"),
    ("tracking-[-0.02em] text-white", "tracking-[-0.02em] text-foreground"),
    ("leading-snug text-white", "leading-snug text-foreground"),
    ("leading-tight text-white", "leading-tight text-foreground"),
    ("font-bold tracking-tight text-white", "font-bold tracking-tight text-foreground"),
    ("font-semibold text-white", "font-semibold text-foreground"),
    ("font-medium text-white", "font-medium text-foreground"),
    ("font-medium leading-snug text-white", "font-medium leading-snug text-foreground"),
    ('className="text-sm text-white"', 'className="text-sm text-foreground"'),
    ('className="text-[13px] text-white"', 'className="text-[13px] text-foreground"'),
    ('className="mt-1 text-sm text-white"', 'className="mt-1 text-sm text-foreground"'),
    ('className="mt-1 text-[13px] text-white"', 'className="mt-1 text-[13px] text-foreground"'),
    ('className="text-white"', 'className="text-foreground"'),
    ('section className="text-white"', 'section className="text-foreground"'),
    ('p className="text-white"', 'p className="text-foreground"'),
    ('span className="text-white"', 'span className="text-foreground"'),
    ('dd className="text-white"', 'dd className="text-foreground"'),
    ("text-slate-400 hover:text-foreground", "text-slate-500 hover:text-foreground"),
    ("text-slate-300 hover:bg-muted hover:text-foreground", "text-slate-500 hover:bg-slate-100 hover:text-foreground"),
    ("focus-visible:ring-cyan-400/60", "focus-visible:ring-indigo-300"),
    ("focus-visible:ring-cyan-400", "focus-visible:ring-indigo-300"),
    ("text-cyan-400", "text-indigo-600"),
    ("text-cyan-200", "text-indigo-700"),
    ("border-cyan-400", "border-indigo-400"),
    ("ring-cyan-400/40", "ring-indigo-300"),
    ("ring-cyan-500", "ring-indigo-300"),
]


def should_skip_text_white_on_line(line: str) -> bool:
    """Keep text-white when it's on a solid colored / gradient control."""
    markers = (
        "bg-primary",
        "bg-indigo-",
        "bg-emerald-",
        "bg-violet-",
        "bg-blue-",
        "bg-rose-",
        "bg-amber-",
        "bg-red-",
        "bg-green-",
        "from-indigo",
        "from-blue",
        "from-violet",
        "from-cyan",
        "to-indigo",
        "to-violet",
        "gradient",
        "bg-slate-900",
    )
    return any(m in line for m in markers)


def fix_bare_text_white(text: str) -> str:
    out_lines = []
    for line in text.splitlines(keepends=True):
        if "text-white" in line and not should_skip_text_white_on_line(line):
            # Avoid replacing partials already handled (text-white/xx gone)
            if "text-white/" not in line:
                line = line.replace("text-white", "text-foreground")
        out_lines.append(line)
    return "".join(out_lines)


def main() -> None:
    updated = 0
    for path in ROOT.rglob("*"):
        if any(part in SKIP for part in path.parts):
            continue
        if path.suffix not in {".tsx", ".ts", ".css"}:
            continue
        text = path.read_text(encoding="utf-8")
        orig = text
        for old, new in REPLS:
            text = text.replace(old, new)
        text = fix_bare_text_white(text)
        if text != orig:
            path.write_text(text, encoding="utf-8")
            updated += 1
            print(path.relative_to(ROOT))
    print(f"updated_files={updated}")


if __name__ == "__main__":
    main()
