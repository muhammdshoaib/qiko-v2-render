from pathlib import Path

files = [
    Path("frontend/apps/creator/app/knowledge/investors/page.tsx"),
    Path("frontend/apps/creator/app/knowledge/portfolio-reporter/page.tsx"),
    Path("frontend/apps/creator/components/knowledge/investors-chat.tsx"),
    Path("frontend/apps/creator/components/knowledge/portfolio-reporter-chat.tsx"),
    Path("frontend/apps/creator/components/worker-cockpit-tabs.tsx"),
]

repls = {
    "Â·": "·",
    "â€¦": "…",
    "â€™": "'",
    "â€”": "—",
    "â€“": "–",
    "Ã—": "×",
}

for path in files:
    text = path.read_text(encoding="utf-8")
    orig = text
    for bad, good in repls.items():
        text = text.replace(bad, good)
    if text != orig:
        path.write_text(text, encoding="utf-8", newline="\n")
        print("FIXED", path)
    else:
        print("CLEAN", path)
