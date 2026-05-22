#!/usr/bin/env python3
"""
OP Kortteli & Antell Vallila — Lounas RSS-generaattori v9
- Pannu:       lounastaja.app RSS-feedi
- Kulho, Uuni: HTTP-haku + "Lounasmenu"-ankkurihaku HTML:stä
- Antell:      print-URL HTTP-haku + M A A N A N T A I -logiikka
"""

import re
import json
import html as htmllib
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

HELSINKI     = timezone(timedelta(hours=3))
WEEKDAYS     = ("maanantai","tiistai","keskiviikko","torstai","perjantai")
RSS_OUTPUT   = Path(__file__).parent / "lounas.xml"
HISTORY_FILE = Path(__file__).parent / "lounas_history.json"
MAX_ITEMS    = 30

PANNU_RSS_URL = (
    "https://lounastaja.app/api/v1/rss/week/"
    "8fa7279e-8ff8-4275-a7ae-d52f7f12d369/current?days=current&language=fi"
)

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

# Merkit joiden jälkeen Soupster-sivun footer alkaa
SOUPSTER_FOOTER_WORDS = [
    "yhteystiedot", "avoinna", "gebhardinaukio",
    "tietosuojaseloste", "kokouspalvelut", "oiva-raporttiin",
    "pannussa, uunissa",
]

HEADERS = {
    "User-Agent":      ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"),
    "Accept":          "text/html,application/xhtml+xml",
    "Accept-Language": "fi-FI,fi;q=0.9",
    "Referer":         "https://www.google.com/",
}

# ── HTTP ──────────────────────────────────────────────────────────────────────

def http_get(url: str) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="replace")

# ── HTML → teksti ─────────────────────────────────────────────────────────────

def html_to_text(inner_html: str) -> str:
    """Muuntaa HTML-snippetin siistiksi tekstiksi."""
    text = htmllib.unescape(inner_html)
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('\u00a0', ' ')   # &nbsp; → välilyönti
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return "\n".join(lines)

# ── Pannu: lounastaja.app RSS ─────────────────────────────────────────────────

def scrape_pannu_rss() -> str:
    xml = http_get(PANNU_RSS_URL)
    m = re.search(
        r'<item>.*?<description><!\[CDATA\[(.*?)\]\]></description>',
        xml, re.DOTALL
    )
    if not m:
        return "(Pannun RSS ei palauttanut menua)"
    return html_to_text(m.group(1))

# ── Kulho ja Uuni: Wix HTML + Lounasmenu-ankkuri ─────────────────────────────

def scrape_soupster_html(url: str) -> str:
    """
    Wixin SSR-HTML sisältää menun suoraan sivun rakenteessa.
    Elementtien id:t vaihtelevat sivuittain, joten ei käytetä id-hakua.

    Strategia:
    1. Löydä "Lounasmenu"-otsikko HTML:stä
    2. Ota kaikki <!--/$-->-blokit sen jälkeen
    3. Lopeta kun kohdataan footerin tunnistesana
    """
    raw_html = http_get(url)

    # Poista script ja style
    html = re.sub(r'<script[^>]*>.*?</script>', '', raw_html, flags=re.DOTALL)
    html = re.sub(r'<style[^>]*>.*?</style>',   '', html,     flags=re.DOTALL)

    # Etsi Lounasmenu-otsikon sijainti
    idx = html.lower().find("lounasmenu")
    if idx < 0:
        return "(Lounasmenu-otsikkoa ei löydy sivulta)"

    after = html[idx:]

    # Jaa Wixin <!--/$--> -kommenttimerkintöjen kohdalta
    chunks = re.split(r'<!--/\$-->', after)

    result_lines = []
    for chunk in chunks[1:]:   # Ohita ensimmäinen (Lounasmenu-otsikko itse)
        text = html_to_text(chunk)
        if not text:
            continue
        # Tarkista onko footer alkanut
        first_lower = text.splitlines()[0].lower()
        if any(fw in first_lower for fw in SOUPSTER_FOOTER_WORDS):
            break
        result_lines.extend(text.splitlines())

    if not result_lines:
        return "(Menusisältöä ei löydy Lounasmenu-otsikon jälkeen)"

    # Poista duplikaattirivit säilyttäen järjestys
    seen = set()
    deduped = []
    for line in result_lines:
        if line not in seen:
            seen.add(line)
            deduped.append(line)

    return "\n".join(deduped)

# ── Antell ────────────────────────────────────────────────────────────────────

def scrape_antell(url: str, today_fi: str) -> str:
    html = http_get(url)
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
    html = re.sub(r'<style[^>]*>.*?</style>',   '', html, flags=re.DOTALL)
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
    return (t.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;"))

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
            print(f"OK ({len(menu.splitlines())} riviä)")
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

    # Historia
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
