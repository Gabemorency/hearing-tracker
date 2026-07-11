"""
inject_keys.py — called by update.yml and nightly.yml
Injects API keys into HTML and JS files.
"""
import os

dw = os.environ.get("DOMEWATCH_API_KEY", "")
cg = os.environ.get("CONGRESS_API_KEY", "")

if not dw:
    print("WARNING: DOMEWATCH_API_KEY is empty")
if not cg:
    print("WARNING: CONGRESS_API_KEY is empty")

files = ["index.html", "calendar.html", "members.html", "domewatch.js"]
for fname in files:
    if not os.path.exists(fname):
        print(f"Skipping {fname} — not found")
        continue
    with open(fname, "r", encoding="utf-8") as f:
        content = f.read()
    before = content.count("__DOMEWATCH_KEY__") + content.count("__CONGRESS_KEY__")
    content = content.replace("__DOMEWATCH_KEY__", dw)
    content = content.replace("__CONGRESS_KEY__", cg)
    after = content.count("__DOMEWATCH_KEY__") + content.count("__CONGRESS_KEY__")
    with open(fname, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"{fname}: replaced {before - after} placeholder(s)")

print("Done.")
