"""
Temporary diagnostic round 3: continue the per-hearing-link investigation.
Round 2 confirmed 9 of 36 committees have a real, usable per-hearing link
pattern, but only printed the first 4 filtered candidates per site (missing
real hearing links buried further down the list) and used a fast
domcontentloaded wait that returned 0 candidates for 7 House committees
(likely just not fully rendered yet, not evidence those sites lack links).

This round: re-checks only the committees NOT already confirmed good,
using the slower/more reliable networkidle wait, prints up to 8 filtered
candidates instead of 4, and ranks candidates containing hearing-ish
keywords (Hearing, Markup, Business Meeting, Examine, Testimony,
Nomination, or a 4-digit year) first so real hearing links surface above
generic content links in the printed sample.

Not part of the regular pipeline — delete after use.
"""
from playwright.sync_api import sync_playwright

# Committees already confirmed to have a working per-hearing link pattern —
# skipped here, no need to re-check.
CONFIRMED_GOOD = {
    "Armed Services (Senate)", "Aging", "Health HELP", "Judiciary (Senate)",
    "Rules", "Foreign Relations", "Homeland Security (Senate)",
    "Indian Affairs", "Financial Services (House)",
}

SENATE_COMMITTEE_PAGES = [
    ("Appropriations",             "https://www.appropriations.senate.gov/hearings"),
    ("Banking",                    "https://www.banking.senate.gov/hearings"),
    ("Budget",                     "https://www.budget.senate.gov/hearings"),
    ("Commerce",                   "https://www.commerce.senate.gov/hearings"),
    ("Energy & Natural Resources", "https://www.energy.senate.gov/hearings"),
    ("Environment & Public Works", "https://www.epw.senate.gov/public/index.cfm/hearings"),
    ("Intelligence",               "https://www.intelligence.senate.gov/hearings"),
    ("Small Business",             "https://www.sbc.senate.gov/public/index.cfm/hearings"),
    ("Veterans Affairs (Senate)",  "https://www.veterans.senate.gov/hearings"),
    ("Joint Economic",             "https://www.jec.senate.gov/public/index.cfm/hearings-calendar"),
]

HOUSE_COMMITTEE_PAGES = [
    ("Agriculture (House)",       "https://agriculture.house.gov/calendar/"),
    ("Appropriations (House)",    "https://appropriations.house.gov/events/hearings"),
    ("Armed Services (House)",    "https://armedservices.house.gov/hearings"),
    ("Education & Workforce",     "https://edworkforce.house.gov/hearings/"),
    ("Energy & Commerce",         "https://energycommerce.house.gov/hearings"),
    ("Homeland Security (House)", "https://homeland.house.gov/hearings/"),
    ("Judiciary (House)",         "https://judiciary.house.gov/hearings/"),
    ("Natural Resources",         "https://naturalresources.house.gov/hearings/"),
    ("Science Space Technology",  "https://science.house.gov/hearings"),
    ("Transportation",            "https://transportation.house.gov/hearings/"),
    ("Veterans Affairs (House)",  "https://veterans.house.gov/hearings/"),
    ("Ways & Means",              "https://waysandmeans.house.gov/hearings/"),
]

JUNK_HINTS = ["menu", "nav", "dropdown", "footer", "sr-only", "skip",
              "sitenav", "site-header", "siteheader", "breadcrumb",
              "social", "login", "search", "subcommittee"]

HEARING_HINTS = ["hearing", "markup", "business meeting", "examine",
                  "testimony", "nomination", "20", "roundtable", "oversight of"]

def is_junk(cls, parent_cls):
    blob = (cls + " " + parent_cls).lower()
    return any(h in blob for h in JUNK_HINTS)

def hearing_score(text):
    t = text.lower()
    return sum(1 for h in HEARING_HINTS if h in t)

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()

    for chamber, pages_list in [("SENATE", SENATE_COMMITTEE_PAGES), ("HOUSE", HOUSE_COMMITTEE_PAGES)]:
        for name, url in pages_list:
            print(f"=== {chamber} {name}: {url} ===")
            try:
                page.goto(url, wait_until="networkidle", timeout=25000)
                page.wait_for_timeout(1000)

                known_good = page.eval_on_selector_all(
                    ".LegislationList__link",
                    "els => els.map(e => ({text: e.innerText.trim().slice(0,70), href: e.href}))"
                )
                if known_good:
                    print(f"  MATCH (.LegislationList__link): {len(known_good)} found")
                    for l in known_good[:2]:
                        print("   -", l)
                    print()
                    continue

                candidates = page.eval_on_selector_all(
                    "a[href]",
                    """els => els.map(e => ({
                        text: e.innerText.trim().slice(0, 100),
                        href: e.href,
                        cls: e.className || '',
                        parentCls: e.parentElement ? (e.parentElement.className || '') : ''
                    })).filter(l => l.text.length > 20)"""
                )
                filtered = [c for c in candidates if not is_junk(c["cls"], c["parentCls"])]
                filtered.sort(key=lambda c: -hearing_score(c["text"]))
                print(f"  no .LegislationList__link — {len(candidates)} long-text links, "
                      f"{len(filtered)} after junk filter")
                for l in filtered[:8]:
                    print("   -", l)
            except Exception as e:
                print("  FAILED:", repr(e))
            print()

    browser.close()
