from pathlib import Path

p = Path(__file__).resolve().parents[1] / "frontend" / "apps" / "creator" / "app" / "workers" / "[id]" / "page.tsx"
t = p.read_text(encoding="utf-8")
old = 'Card className="border-amber-500/30 bg-amber-500/5"'
new = 'Card className="border-indigo-200 bg-indigo-50/60"'
count = t.count(old)
p.write_text(t.replace(old, new), encoding="utf-8")
print(f"replaced={count}")
