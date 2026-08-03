"""
Temporary diagnostic round 4: search the full docs.house.gov event page for
the actual committee name / title, skipping past the New Relic boilerplate
that ate the whole first 6000 chars of round 3's dump.

Not part of the regular pipeline — delete after use.
"""
import re
import requests

URLS = [
    "http://docs.house.gov/Committee/Calendar/ByEvent.aspx?EventId=119443",
    "http://docs.house.gov/Committee/Calendar/ByEvent.aspx?EventId=118854",
]

if __name__ == "__main__":
    for url in URLS:
        print(f"=== {url} ===")
        try:
            r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            html = r.text
            print("status:", r.status_code, "length:", len(html))

            title = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
            print("title tag:", title.group(1).strip() if title else None)

            h1 = re.findall(r"<h1[^>]*>(.*?)</h1>", html, re.S | re.I)
            print("h1 tags:", h1)
            h2 = re.findall(r"<h2[^>]*>(.*?)</h2>", html, re.S | re.I)
            print("h2 tags:", h2)
            h3 = re.findall(r"<h3[^>]*>(.*?)</h3>", html, re.S | re.I)
            print("h3 tags:", h3)

            # Look for any element with id/class containing "committee" or "title"
            candidates = re.findall(
                r'<[a-z0-9]+[^>]*(?:id|class)="[^"]*(?:[Cc]ommittee|[Tt]itle|[Mm]eeting)[^"]*"[^>]*>(.*?)</[a-z0-9]+>',
                html, re.S)
            print("committee/title/meeting-class elements (first 10):", candidates[:10])

            # Print the <body> tag's first 4000 chars, stripped of script/style blocks
            body_match = re.search(r"<body[^>]*>(.*?)</body>", html, re.S | re.I)
            if body_match:
                body = body_match.group(1)
                body = re.sub(r"<script.*?</script>", "", body, flags=re.S | re.I)
                body = re.sub(r"<style.*?</style>", "", body, flags=re.S | re.I)
                print("body (scripts/styles stripped), first 4000 chars:")
                print(body[:4000])
        except requests.exceptions.RequestException as e:
            print("FAILED:", e)
        print()
