#!/usr/bin/env python3
"""
OP Kortteli & Antell Vallila — Lounas RSS-generaattori v6b (debug)
"""

import re
import json
import os
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

HELSINKI     = timezone(timedelta(hours=3))
WEEKDAYS     = ("maanantai","tiistai","keskiviikko","torstai","perjantai")
RSS_OUTPUT   = Path(__file__).parent / "lounas.xml"
HISTORY_FILE = Path(__file__).parent / "lounas_history.json"
MAX_ITEMS    = 30

RESTAURANTS = [
    {"id": "pannu", "name": "Pannu – Soupster OP Kortteli",
     "url": "https://www.soupsterkortteli.fi/pannu", "type": "soupster"},
    {"id": "kulho", "name": "Kulho – Soupster OP Kortteli",
     "url": "https://www.soupsterkortteli.fi/kulho", "type": "soupster"},
    {"id": "uuni",  "name": "Uuni – Soupster OP Kortteli",
     "url": "https://www.soupsterkortteli.fi/uuni",  "type": "soupster"},
    {"id": "hella", "name": "Antell Hella",
     "url": "https://antell.fi/lounas/helsinki/hella/?print_lunch_list_week=1", "type": "antell"},
    {"id": "tori",  "name": "Antell Tori",
     "url": "https://antell.fi/lounas/helsinki/tori/?print_lunch_list_week=1",  "type": "antell"},
]

ANTELL_DAYS = {
    "maanantai":   "M A A N A N T A I",
    "tiistai":     "T I I S T A I",
    "keskiviikko": "K E S K I V I I K K O",
    "torstai":     "T O R S T A I",
    "perjantai":   "P E R J A N T A I",
}

HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept":          "text/html,application/xhtml+xml",
    "Accept-Language": "fi-FI,fi;q=0.9",
    "Referer":         "https://www.google.com/",
}

# ── Browserless ───────────────────────────────────────────────────────────────

def fetch_browserless(url: str) -> str:
    api_key = os.environ.get("BROWSERLESS_API_KEY", "")
    endpoint = f"https://production-sfo.browserless.io/content?token={api_key}"

    # Käytetään waitForSelector joka odottaa kunnes menu-elementti on renderöity
    # Lisätään myös pidempi timeout
    payload = json.dumps({
        "url": url,
        "waitForTimeout": 8000,
        "gotoOptions": {
            "waitUntil": "networkidle2",
            "timeout": 45000
        }
    }).encode("utf-8")

    req = urllib.request.Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8", errors="replace")


def scrape_soupster_browserless(restaurant_id: str, url: str, today_fi: str) -> str:
    html = fetch_browserless(url)

    # Poista script/style
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
    html = re.sub(r'<style[^>]*>.*?</style>',  '', html, flags=re.DOTALL)

    # Muunna tekstiksi
    text = re.sub(r'<[^>]+>', '\n', html)
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # DEBUG: tulosta 3000 merkkiä puhdistettua tekstiä — vain Pannulle
    if restaurant_id == "pannu":
        print(f"\n===== DEBUG Pannu tekstisisältö =====")
        print("\n".join(lines)[:3000])
        print(f"===== DEBUG loppu =====\n")

    return parse_soupster(lines, today_fi)


def parse_soupster(lines: list, today_fi: str) -> str:
    paiva_lyhenne = {"maanantai": "Ma", "tiistai": "Ti", "keskiviikko": "Ke",
                     "torstai": "To", "perjantai": "Pe"}
    muut = [v for k, v in paiva_lyhenne.items() if k != today_fi]
    today_short = paiva_lyhenne[today_fi]

    result, capturing = [], False
    for line in lines:
        if re.match(rf'^{today_short}\b', line) and not capturing:
            capturing = True
            result.append(line)
            continue
        if capturing:
            if any(re.match(rf'^{d}\b', line) for d in muut):
                break
            skip = ["aamiainen","deli","kokous","yhteystiedot","avoinna",
                    "bottom of page","top of page","tietosuoja","hävikki"]
            if any(s in line.lower() for s in skip):
                break
            result.append(line)

    # Kokeile myös koko päivänimellä
    if not result:
        for line in lines:
            if today_fi in line.lower() and not capturing:
                capturing = True
                result.append(line)
                continue
            if capturing:
                if any(p in line.lower() for p in
                       [d for d in WEEKDAYS if d != today_fi]):
                    break
                result.append(line)
                if len(result) > 20:
                    break

    return "\n".join(result) if result else "(Päivän menu ei löytynyt)"


# ── Antell ────────────────────────────────────────────────────────────────────

def scrape_antell(url: str, today_fi: str) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        html = resp.read().decode("utf-8", errors="replace")

    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
    html = re.sub(r'<style[^>]*>.*?</style>',  '', html, flags=re.DOTALL)
    text = re.sub(r'<[^>]+>', '\n', html)
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    today_marker  = ANTELL_DAYS[today_fi]
    other_markers = [v for k, v in ANTELL_DAYS.items() if k != today_fi]

    result, capturing = [], False
    for line in lines:
        if today_marker in line and not capturing:
            capturing = True
            result.append(line)
            continue
        if capturing:
            if any(m in line for m in other_markers):
                break
            if "Pidätämme oikeuden" in line or "ainesosatiedot" in line:
                break
            result.append(line)

    return "\n".join(result) if result else "(Päivän menu ei löytynyt)"


# ── RSS ───────────────────────────────────────────────────────────────────────

def escape_xml(t: str) -> str:
    return t.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")

def build_rss(items: list) -> str:
    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    entries = ""
    for it in items:
        pub = it["pub_date"].strftime("%a, %d %b %Y %H:%M:%S +0000")
        entries += f"""
    <item>
      <title>{escape_xml(it['title'])}</title>
      <link>{escape_xml(it['link'])}</link>
      <description><![CDATA[{it['description']}]]></description>
      <pubDate>{pub}</pubDate>
      <guid isPermaLink="false">{it['link']}-{it['pub_date'].date()}</guid>
    </item>"""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>OP Kortteli &amp; Antell Vallila — Päivän lounaat</title>
    <link>https://www.soupsterkortteli.fi</link>
    <description>Päivittäin klo 10.30 päivitetty lounaslista</description>
    <language>fi</language>
    <lastBuildDate>{now}</lastBuildDate>
    <ttl>1440</ttl>{entries}
  </channel>
</rss>"""


# ── Pääohjelma ────────────────────────────────────────────────────────────────

def main():
    today    = datetime.now(HELSINKI)
    today_fi = WEEKDAYS[today.weekday()]

    if today.weekday() >= 5:
        print("Viikonloppu — ei ajeta.")
        return

    print(f"Haetaan lounaat: {today.strftime('%d.%m.%Y')} ({today_fi})")

    new_items = []
    for r in RESTAURANTS:
        print(f"  → {r['name']} ...", end=" ", flush=True)
        try:
            if r["type"] == "antell":
                menu = scrape_antell(r["url"], today_fi)
            else:
                menu = scrape_soupster_browserless(r["id"], r["url"], today_fi)
            print("OK")
        except Exception as e:
            menu = f"(Virhe: {e})"
            print(f"VIRHE: {e}")

        desc_html = "<br>".join(
            f"<b>{line}</b>" if i == 0 else line
            for i, line in enumerate(menu.splitlines()) if line.strip()
        )
        new_items.append({
            "title":       f"{today.strftime('%d.%m.%Y')} – {r['name']}",
            "description": desc_html,
            "link":        r["url"],
            "pub_date":    today.isoformat(),
        })

    history = []
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, encoding="utf-8") as f:
            history = json.load(f)

    today_str = today.date().isoformat()
    history = [h for h in history if not h["pub_date"].startswith(today_str)]
    history.extend(new_items)
    history = history[-MAX_ITEMS:]

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2, default=str)

    rss_items = []
    for h in reversed(history):
        h2 = dict(h)
        h2["pub_date"] = datetime.fromisoformat(h["pub_date"])
        rss_items.append(h2)

    RSS_OUTPUT.write_text(build_rss(rss_items), encoding="utf-8")
    print(f"\n✓ lounas.xml päivitetty ({len(rss_items)} alkiota)")

if __name__ == "__main__":
    main()
