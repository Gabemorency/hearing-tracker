"""
Temporary diagnostic round 2: check ALL 21 Senate + 15 House committee
hearing-listing pages for a per-hearing detail link, not just the 5 sampled
in round 1. Round 1 confirmed a working pattern for Aging/HELP
(`.LegislationList__link`) but the naive "any link with >15 chars text"
heuristic got drowned out by nav-menu junk on other sites. This version:
  1. Checks the confirmed-good selector directly (fast yes/no per site).
  2. Falls back to a nav-junk-filtered generic scan for sites where it
     doesn't match, to see if there's a different-but-usable pattern.

Not part of the regular pipeline — delete after use.
"""
from playwright.sync_api import sync_playwright

SENATE_COMMITTEE_PAGES = [
    ("Armed Services",             "https://www.armed-services.senate.gov/hearings"),
    ("Agriculture",                "https://www.agriculture.senate.gov/hearings"),
    ("Aging",                      "https://www.aging.senate.gov/hearings"),
    ("Appropriations",             "https://www.appropriations.senate.gov/hearings"),
    ("Banking",                    "https://www.banking.senate.gov/hearings"),
    ("Budget",                     "https://www.budget.senate.gov/hearings"),
    ("Commerce",                   "https://www.commerce.senate.gov/hearings"),
    ("Energy & Natural Resources", "https://www.energy.senate.gov/hearings"),
    ("Environment & Public Works", "https://www.epw.senate.gov/public/index.cfm/hearings"),
    ("Finance",                    "https://www.finance.senate.gov/hearings"),
    ("Foreign Relations",          "https://www.foreign.senate.gov/hearings"),
    ("Health HELP",                "https://www.help.senate.gov/hearings"),
    ("Homeland Security",          "https://www.hsgac.senate.gov/hearings"),
    ("Indian Affairs",             "https://www.indian.senate.gov/hearings"),
    ("Intelligence",               "https://www.intelligence.senate.gov/hearings"),
    ("Judiciary",                  "https://www.judiciary.senate.gov/committee-activity/hearings"),
    ("Rules",                      "https://www.rules.senate.gov/hearings"),
    ("Small Business",             "https://www.sbc.senate.gov/public/index.cfm/hearings"),
    ("Veterans Affairs",           "https://www.veterans.senate.gov/hearings"),
    ("Joint Economic",             "https://www.jec.senate.gov/public/index.cfm/hearings-calendar"),
    ("Narcotics Control",          "https://www.drugcaucus.senate.gov/"),
]

HOUSE_COMMITTEE_PAGES = [
    ("Agriculture",               "https://agriculture.house.gov/calendar/"),
    ("Appropriations",            "https://appropriations.house.gov/events/hearings"),
    ("Armed Services",            "https://armedservices.house.gov/hearings"),
    ("Education & Workforce",     "https://edworkforce.house.gov/hearings/"),
    ("Energy & Commerce",         "https://energycommerce.house.gov/hearings"),
    ("Financial Services",        "https://financialservices.house.gov/calendar/"),
    ("Foreign Affairs",           "https://foreignaffairs.house.gov/hearings/"),
    ("Homeland Security",         "https://homeland.house.gov/hearings/"),
    ("Judiciary",                 "https://judiciary.house.gov/hearings/"),
    ("Natural Resources",         "https://naturalresources.house.gov/hearings/"),
    ("Oversight",                 "https://oversight.house.gov/hearings/"),
    ("Science Space Technology",  "https://science.house.gov/hearings"),
    ("Transportation",            "https://transportation.house.gov/hearings/"),
    ("Veterans Affairs",          "https://veterans.house.gov/hearings/"),
    ("Ways & Means",              "https://waysandmeans.house.gov/hearings/"),
]

JUNK_HINTS = ["menu", "nav", "dropdown", "footer", "sr-only", "skip",
              "sitenav", "site-header", "siteheader", "breadcrumb",
              "social", "login", "search"]

def is_junk(cls, parent_cls):
    blob = (cls + " " + parent_cls).lower()
    return any(h in blob for h in JUNK_HINTS)

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()

    for chamber, pages_list in [("SENATE", SENATE_COMMITTEE_PAGES), ("HOUSE", HOUSE_COMMITTEE_PAGES)]:
        for name, url in pages_list:
            print(f"=== {chamber} {name}: {url} ===")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(1200)

                known_good = page.eval_on_selector_all(
                    ".LegislationList__link",
                    "els => els.map(e => ({text: e.innerText.trim().slice(0,70), href: e.href}))"
                )
                if known_good:
                    print(f"  MATCH (.LegislationList__link): {len(known_good)} found")
                    for l in known_good[:2]:
                        print("   -", l)
                else:
                    candidates = page.eval_on_selector_all(
                        "a[href]",
                        """els => els.map(e => ({
                            text: e.innerText.trim().slice(0, 90),
                            href: e.href,
                            cls: e.className || '',
                            parentCls: e.parentElement ? (e.parentElement.className || '') : ''
                        })).filter(l => l.text.length > 20)"""
                    )
                    filtered = [c for c in candidates if not is_junk(c["cls"], c["parentCls"])]
                    print(f"  no .LegislationList__link — {len(candidates)} long-text links, "
                          f"{len(filtered)} after junk filter")
                    for l in filtered[:4]:
                        print("   -", l)
            except Exception as e:
                print("  FAILED:", repr(e))
            print()

    browser.close()
