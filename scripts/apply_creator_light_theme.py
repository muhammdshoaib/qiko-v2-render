"""Bulk-replace hardcoded dark Creator surfaces with light theme tokens."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "frontend" / "apps" / "creator"
SKIP = {"node_modules", ".next"}

REPLS = [
    ("bg-[#05070d]", "bg-background"),
    ("bg-[#050810]", "bg-background"),
    ("bg-[#070a12]/95", "bg-card/95"),
    ("bg-[#070a12]/80", "bg-card/95"),
    ("bg-[#070a12]", "bg-card"),
    ("bg-[#0b0f18]", "bg-card"),
    ("bg-[#0a0f1a]/80", "bg-card"),
    ("bg-[#0a0f1a]/60", "bg-card"),
    ("bg-[#0a0f1a]/40", "bg-muted"),
    ("bg-[#0a0f1a]", "bg-card"),
    ("bg-[#0c111c]/95", "bg-card"),
    ("bg-[#0c111c]", "bg-card"),
    ("bg-[#111827]", "bg-card"),
    ("hover:bg-[#1f2937]", "hover:bg-muted"),
    ("border-white/[0.06]", "border-border"),
    ("border-white/[0.08]", "border-border"),
    ("border-white/[0.05]", "border-border"),
    ("border-white/10", "border-border"),
    ("border-white/15", "border-border"),
    ("border-white/20", "border-border"),
    ("border-white/5", "border-border"),
    ("border-white/25", "border-border"),
    ("border-white/30", "border-border"),
    ("divide-white/[0.06]", "divide-border"),
    ("divide-white/[0.05]", "divide-border"),
    ("bg-white/[0.015]", "bg-muted/40"),
    ("bg-white/[0.02]", "bg-muted/50"),
    ("bg-white/[0.03]", "bg-muted"),
    ("bg-white/[0.04]", "bg-muted"),
    ("bg-white/[0.06]", "bg-muted"),
    ("bg-white/[0.08]", "bg-muted"),
    ("hover:bg-white/[0.03]", "hover:bg-muted"),
    ("hover:bg-white/[0.04]", "hover:bg-muted"),
    ("hover:bg-white/[0.08]", "hover:bg-muted"),
    ("hover:bg-white/5", "hover:bg-muted"),
    ("hover:bg-white/10", "hover:bg-muted"),
    ("bg-white/5", "bg-muted"),
    ("text-[#05070d]", "text-foreground"),
    ("font-bold text-white", "font-bold text-foreground"),
    ("font-semibold text-white", "font-semibold text-foreground"),
    ("font-extrabold text-white", "font-extrabold text-foreground"),
    ("font-medium text-white", "font-medium text-foreground"),
    ("text-lg font-semibold text-white", "text-lg font-semibold text-foreground"),
    ("text-xl font-bold text-white", "text-xl font-bold text-foreground"),
    ("text-2xl font-bold text-white", "text-2xl font-bold text-foreground"),
    ("text-sm font-semibold text-white", "text-sm font-semibold text-foreground"),
    ("text-sm font-medium text-white", "text-sm font-medium text-foreground"),
    ("text-[15px] font-semibold text-white", "text-[15px] font-semibold text-foreground"),
    ("text-[13.5px] font-semibold text-white", "text-[13.5px] font-semibold text-foreground"),
    ("truncate text-white", "truncate text-foreground"),
    ("hover:text-white", "hover:text-foreground"),
    (
        'rounded-2xl border border-white/[0.08] bg-[#0b0f18]',
        "rounded-2xl border border-border bg-card",
    ),
    (
        'const CARD = "rounded-2xl border border-border bg-card"',
        'const CARD = "rounded-2xl border border-border bg-card"',
    ),
]


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
        # Remaining CARD constants that used #0b0f18 already swapped via bg replace
        text = text.replace(
            'const CARD = "rounded-2xl border border-border bg-card"',
            'const CARD = "rounded-2xl border border-border bg-card"',
        )
        if text != orig:
            path.write_text(text, encoding="utf-8")
            updated += 1
            print(path.relative_to(ROOT))
    print(f"updated_files={updated}")


if __name__ == "__main__":
    main()
