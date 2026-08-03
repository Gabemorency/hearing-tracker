"""
Temporary diagnostic: what does a docs.house.gov/Committee/Calendar/ByEvent.aspx
page actually look like? Need this to know how to scrape the real committee
name (and title/witnesses if available) for each meeting DomeWatch gives us,
since DomeWatch's own API doesn't include a committee name field.

Not part of the regular pipeline — delete after use.
"""
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
            print("status:", r.status_code)
            print("length:", len(r.text))
            print(r.text[:6000])
        except requests.exceptions.RequestException as e:
            print("FAILED:", e)
        print()
