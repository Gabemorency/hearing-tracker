"""
inject_keys.py — called by update.yml and nightly.yml
Injects API keys into HTML and JS files.
"""
import glob
import os

dw = os.environ.get("DOMEWATCH_API_KEY", "")
cg = os.environ.get("CONGRESS_API_KEY", "")

if not dw:
    print("WARNING: DOMEWATCH_API_KEY is empty")
if not cg:
    print("WARNING: CONGRESS_API_KEY is empty")

# bios/*.html each embed __CONGRESS_KEY__ for their own client-side
# "Recent Sponsored Legislation" fetch (see build_members.py) — without this,
# that placeholder is never replaced and the fetch silently no-ops on every
# bio page (it explicitly bails out if key === "__CONGRESS_KEY__").
main_files = ["index.html", "calendar.html", "members.html"]
bio_files  = sorted(glob.glob("bios/*.html"))

def inject(fname):
    if not os.path.exists(fname):
        print(f"Skipping {fname} — not found")
        return 0
    with open(fname, "r", encoding="utf-8") as f:
        content = f.read()
    before = content.count("__DOMEWATCH_KEY__") + content.count("__CONGRESS_KEY__")
    content = content.replace("__DOMEWATCH_KEY__", dw)
    content = content.replace("__CONGRESS_KEY__", cg)
    after = content.count("__DOMEWATCH_KEY__") + content.count("__CONGRESS_KEY__")
    with open(fname, "w", encoding="utf-8") as f:
        f.write(content)
    return before - after

for fname in main_files:
    print(f"{fname}: replaced {inject(fname)} placeholder(s)")

bio_total = sum(inject(fname) for fname in bio_files)
print(f"bios/*.html: replaced {bio_total} placeholder(s) across {len(bio_files)} file(s)")

print("Done.")
