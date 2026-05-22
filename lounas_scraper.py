#!/usr/bin/env python3
"""
OP Kortteli & Antell Vallila — Lounas RSS-generaattori v3b (debug)
"""

import re
import json
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

HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept":          "text/html,application/xhtml+xml",
    "Accept-Language": "fi-FI,fi;q=0.9",
    "Referer":         "https://www.google.com/",
}

def http_get(url: str) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="replace")

def scrape_antell(restaurant_id: str, url: str, today_fi: str, today_num: int) -> str:
    html = http_get(url)

    # Poista skriptit ja tyylit
    clean = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
    clean = re.sub(r'<style[^>]*>.*?</style>',  '', clean, flags=re.DOTALL)
    text  = re.sub(r'<[^>]+>', '\n', clean)
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # DEBUG: tulosta 3000 merkkiä tekstisisältöä lokkiin
    print(f"\n    ===== DEBUG {restaurant_id} tekstisisältö (3000 merkkiä) =====")
    print("\n".join(lines)[:3000])
    print(f"    ===== DEBUG loppu =====\n")

    return "(debug-ajo — ei parsita vielä)"

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

def main():
    today     = datetime.now(HELSINKI)
    today_fi  = WEEKDAYS[today.weekday()]
    today_num = today.weekday()

    if today.weekday() >= 5:
        print("Viikonloppu — ei ajeta.")
        return

    print(f"Haetaan lounaat: {today.strftime('%d.%m.%Y')} ({today_fi})")

    new_items = []
    for r in RESTAURANTS:
        print(f"  → {r['name']} ...", end=" ", flush=True)
        try:
            if r["type"] == "antell":
                menu = scrape_antell(r["id"], r["url"], today_fi, today_num)
                print("OK")
            else:
                menu = f"Katso päivän menu: {r['url']}"
                print("(ohitettu)")
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
            "link":        r["url"].split("?")[0],
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
