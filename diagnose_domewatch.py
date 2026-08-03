"""
TEMPORARY diagnostic script — to be deleted after use.
Round 4: found the real URL — majorityleader.gov/house-legislative-calendar-2026/.
Check whether it's server-rendered with real forward-looking session-day
content (not a JS widget shell like /calendar was).
"""
import re
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
}

URL = "https://www.majorityleader.gov/house-legislative-calendar-2026/"

def main():
    r = requests.get(URL, timeout=20, headers=HEADERS)
    print(f"{URL} -> HTTP {r.status_code}, {len(r.text)} bytes")
    if r.status_code != 200:
        print(r.text[:500])
        return

    text = r.text
    title_m = re.search(r"<title[^>]*>(.*?)</title>", text, re.S | re.I)
    print(f"title: {title_m.group(1).strip() if title_m else '(none)'}")

    # Strip scripts/styles, collapse tags to see real visible text content
    stripped = re.sub(r"<script.*?</script>|<style.*?</style>", "", text, flags=re.S | re.I)
    stripped_text = re.sub(r"<[^>]+>", " ", stripped)
    stripped_text = re.sub(r"\s+", " ", stripped_text).strip()
    print(f"\nFull visible text length: {len(stripped_text)} chars")
    print(f"First 3000 chars:\n{stripped_text[:3000]}")

    # Look for month names + day patterns suggesting a real calendar grid
    months = re.findall(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}", stripped_text)
    print(f"\nMonth/year mentions found: {months}")

    # Look for "session" / "district work period" / "recess" keywords with context
    for kw in ["district work period", "in session", "session day", "recess", "legislative day"]:
        idx = stripped_text.lower().find(kw)
        if idx >= 0:
            print(f"\n'{kw}' found at {idx}: ...{stripped_text[max(0,idx-100):idx+200]}...")

    # Dump any embedded JSON (common for calendar widgets: a JS var with events array)
    json_like = re.findall(r'(\[\s*\{\s*"[a-zA-Z_]+"\s*:.{0,300})', text)
    print(f"\nEmbedded JSON-like blobs found: {len(json_like)}")
    for j in json_like[:3]:
        print(f"  {j[:300]}")

if __name__ == "__main__":
    main()
