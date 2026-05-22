#!/usr/bin/env python3
"""
OP Kortteli & Antell Vallila — Lounas RSS-generaattori v7
- Pannu:       lounastaja.app RSS-feedi (luotettavin)
- Kulho, Uuni: suora HTTP-haku Wix-sivulta (menu on staattisessa HTML:ssä)
- Antell:      print-URL HTTP-haku
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

# Pannun lounastaja.app RSS-feedi
PANNU_RSS_URL = "https://lounastaja.app/api/v1/rss/week/8fa7279e-8ff8-4275-a7ae-d52f7f12d369/current?days=current&language=fi"

RESTAURANTS = [
    {"id": "pannu", "name": "Pannu – Soupster OP Kortteli",
     "url": "https://www.soupsterkortteli.fi/pannu", "type": "pannu_rss"},
    {"id": "kulho", "name": "Kulho – Soupster OP Kortteli",
     "url": "https://www.soupsterkortteli.fi/kulho", "type": "soupster_html"},
    {"id": "uuni",  "name": "Uuni – Soupster OP Kortteli",
     "url": "https://www.soupsterkortteli.fi/uuni",  "type": "soupster_html"},
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

def http_get(url: str) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="replace")

# ── Pannu: lounastaja.app RSS ─────────────────────────────────────────────────

def scrape_pannu_rss() -> str:
    """Hakee Pannun menun suoraan lounastaja.app RSS-feedistä."""
    xml = http_get(PANNU_RSS_URL)

    # Poimii <description> ensimmäisestä <item>-elementistä
    m = re.search(r'<item>.*?<description><!\[CDATA\[(.*?)\]\]></description>', xml, re.DOTALL)
    if not m:
        return "(Pannun RSS ei palauttanut menua)"

    # Muunna <br> rivinvaihdoiksi ja siivoa
    raw = m.group(1)
    text = re.sub(r'<br\s*/?>', '\n', raw, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return "\n".join(lines)

# ── Kulho ja Uuni: staattinen HTML ────────────────────────────────────────────

def scrape_soupster_html(url: str) -> str:
    """
    Hakee Kulhon tai Uunin menun suoraan HTML:stä.
    Menu on elementissä jonka id alkaa 'comp-m7ngbax' tai vastaava.
    Etsitään viimeisin pitkä rich-text-elementti jossa on ravintolatietoja.
    """
    html = http_get(url)

    # Etsi kaikki wixui-rich-text -elementtien sisällöt
    # Kulhossa menu on comp-m7ngbax61-elementissä
    # Poistetaan script/style ensin
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
    html = re.sub(r'<style[^>]*>.*?</style>',  '', html, flags=re.DOTALL)

    # Etsi kaikki comp-m7ngbax* -elementit
    blocks = re.findall(
        r'<div[^>]+id="comp-m7ngbax\w+"[^>]*>(.*?)</div>\s*<!--/\$-->',
        html, re.DOTALL
    )

    best = ""
    for block in blocks:
        text = re.sub(r'<[^>]+>', '\n', block)
        text = re.sub(r'&[a-z]+;', ' ', text)
        text = re.sub(r'\s+', '\n', text).strip()
        lines = [l.strip() for l in text.splitlines()
                 if l.strip() and len(l.strip()) > 2]
        # Valitse pisin lohko joka näyttää lounaslistalta
        food_keywords = ['sushi','nigiri','rulla','keitto','salaatti','pääruoka',
                         'lounas','buffet','tofu','lohi','kana','liha','kasvis',
                         'jälkiruoka','kahvi','riisi','pasta','keitto']
        joined = " ".join(lines).lower()
        if any(k in joined for k in food_keywords) and len(lines) > len(best.splitlines()):
            best = "\n".join(lines)

    if best:
        return best

    # Fallback: etsi "Lounasmenu" jälkeinen teksti
    idx = html.lower().find("lounasmenu")
    if idx > 0:
        chunk = html[idx:idx+5000]
        text = re.sub(r'<[^>]+>', '\n', chunk)
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        return "\n".join(lines[:30])

    return "(Menu ei löytynyt HTML:stä)"

# ── Antell ────────────────────────────────────────────────────────────────────

def scrape_antell(url: str, today_fi: str) -> str:
    html = http_get(url)
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
            if r["type"] == "pannu_rss":
                menu = scrape_pannu_rss()
            elif r["type"] == "soupster_html":
                menu = scrape_soupster_html(r["url"])
            else:
                menu = scrape_antell(r["url"], today_fi)
            print("OK")
        except Exception as e:
            menu = f"(Virhe: {e})"
            print(f"VIRHE: {e}")

        desc_html = "<br>".join(
            f"<b>{line}</b>" if i == 0 else line
            for i, line in enumerate(menu.splitlines()) if line.strip()
        )
        new_items.append({
            "title":    f"{today.strftime('%d.%m.%Y')} – {r['name']}",
            "description": desc_html,
            "link":     r["url"],
            "pub_date": today.isoformat(),
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
