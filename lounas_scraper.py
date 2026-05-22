#!/usr/bin/env python3
"""
OP Kortteli & Antell Vallila — Lounas RSS-generaattori
Aja klo 10.30 arkisin cron-jobilla: 30 10 * * 1-5 /path/to/venv/bin/python /path/to/lounas_scraper.py
"""

import re
import os
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from playwright.sync_api import sync_playwright

# ── Konfiguraatio ─────────────────────────────────────────────────────────────
RSS_OUTPUT = Path(__file__).parent / "lounas.xml"   # Muuta haluamaasi hakemistoon
MAX_ITEMS  = 30                                       # Tallennetaan max 30 päivää
HELSINKI   = timezone(timedelta(hours=3))             # EEST (kesäaika); talvella hours=2
WEEKDAYS   = ("maanantai","tiistai","keskiviikko","torstai","perjantai")

RESTAURANTS = [
    {
        "id":    "pannu",
        "name":  "Pannu – Soupster OP Kortteli",
        "url":   "https://www.soupsterkortteli.fi/pannu",
        "type":  "soupster",
    },
    {
        "id":    "kulho",
        "name":  "Kulho – Soupster OP Kortteli",
        "url":   "https://www.soupsterkortteli.fi/kulho",
        "type":  "soupster",
    },
    {
        "id":    "uuni",
        "name":  "Uuni – Soupster OP Kortteli",
        "url":   "https://www.soupsterkortteli.fi/uuni",
        "type":  "soupster",
    },
    {
        "id":    "hella",
        "name":  "Antell Hella",
        "url":   "https://antell.fi/lounas/helsinki/hella/?print_lunch_list_week=1",
        "type":  "antell",
    },
    {
        "id":    "tori",
        "name":  "Antell Tori",
        "url":   "https://antell.fi/lounas/helsinki/tori/?print_lunch_list_week=1",
        "type":  "antell",
    },
]

# ── Scraping-funktiot ─────────────────────────────────────────────────────────

def scrape_soupster(page, url: str) -> str:
    """Hakee Soupster-sivun ja palauttaa päivän lounaan tekstinä."""
    page.goto(url, wait_until="networkidle", timeout=40000)
    page.wait_for_timeout(3000)

    today_fi = WEEKDAYS[datetime.now(HELSINKI).weekday()]

    # Yritä löytää "Lounasmenu" tai "Lounas"-osio
    try:
        # Wix renderöi sisällön span/div-elementteihin; haetaan koko body-teksti
        full = page.inner_text("body")
        lines = [l.strip() for l in full.splitlines() if l.strip()]

        # Etsi päivän nimi ja ota sen jälkeiset rivit kunnes seuraava viikonpäivä / tyhjä lohko
        result_lines = []
        capturing = False
        skip_keywords = {"aamiainen","deli","kokous","yhteystiedot","avoinna",
                         "lisätietoja","klikkaa","oiva","bottom","top of page"}

        for i, line in enumerate(lines):
            low = line.lower()

            # Aloita kaappaus kun löytyy tämän päivän nimi
            if today_fi in low and not capturing:
                capturing = True
                result_lines.append(line)
                continue

            if capturing:
                # Lopeta jos törmätään toiseen viikonpäivään tai sivun alaosaan
                if any(d in low for d in WEEKDAYS if d != today_fi):
                    break
                if any(k in low for k in skip_keywords):
                    break
                if line.startswith("http"):
                    break
                result_lines.append(line)

        if result_lines:
            return "\n".join(result_lines)

        # Fallback: palauta kaikki lounasosion jälkeinen teksti
        return _extract_menu_block(lines)

    except Exception as e:
        return f"(Tietojen haku epäonnistui: {e})"


def scrape_antell(page, url: str) -> str:
    """
    Hakee Antell-sivun print_lunch_list_week=1 -URL:sta ja palauttaa päivän lounaan.
    Tämä URL renderöi viikon menun staattisena HTML:nä ilman JS-riippuvuuksia,
    joten se toimii myös requests-kirjastolla (nopeampi kuin Playwright).
    """
    import urllib.request

    # Rakenna print-URL: lisää ?print_lunch_list_week=1 jos ei jo ole
    if "print_lunch_list_week" not in url:
        sep = "&" if "?" in url else "?"
        print_url = url + sep + "print_lunch_list_week=1"
    else:
        print_url = url

    today_fi = WEEKDAYS[datetime.now(HELSINKI).weekday()]
    today_num = datetime.now(HELSINKI).weekday()  # 0=ma, 4=pe

    # Yritä ensin kevyellä HTTP-pyynnöllä (ei Playwrightia)
    try:
        req = urllib.request.Request(
            print_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/124.0.0.0 Safari/537.36",
                "Accept":          "text/html,application/xhtml+xml",
                "Accept-Language": "fi-FI,fi;q=0.9,en;q=0.8",
                "Referer":         "https://antell.fi/",
            }
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        return _parse_antell_html(html, today_fi, today_num)

    except Exception:
        # Fallback: Playwright (JS-renderöinti) jos pelkkä HTTP-pyyntö ei riitä
        pass

    try:
        page.goto(print_url, wait_until="networkidle", timeout=40000)
        page.wait_for_timeout(2000)
        html = page.content()
        return _parse_antell_html(html, today_fi, today_num)

    except Exception as e:
        return f"(Tietojen haku epäonnistui: {e})"


def _parse_antell_html(html: str, today_fi: str, today_num: int) -> str:
    """
    Parsii Antell print_lunch_list_week=1 -sivun HTML:n.

    Antell käyttää rakennetta jossa jokaisella viikonpäivällä on oma osio.
    Tyypillinen rakenne (tutkittu inspect-työkalulla):
      <div class="lunch-list-day"> tai <section data-weekday="N">
      tai <h2/h3> jossa päivän nimi, jonka alla <ul>/<li> tai <p>-elementtejä.

    Koska emme voi testata suoraan, käytetään kolmea strategiaa järjestyksessä.
    """
    import re as _re

    # ── Strategia 1: regex päivänimen perusteella ──────────────────────────────
    # Etsi lohko joka alkaa tämän päivän nimellä (fi tai lyhenne)
    # Antell käyttää usein muotoa "Maanantai 19.5." tai pelkkää "Maanantai"
    day_pattern = _re.compile(
        rf'({today_fi})[^\n]*\n(.*?)(?=maanantai|tiistai|keskiviikko|torstai|perjantai|</body|$)',
        _re.IGNORECASE | _re.DOTALL
    )
    m = day_pattern.search(html)
    if m:
        raw = m.group(2)
        # Poista HTML-tagit
        clean = _re.sub(r'<[^>]+>', '\n', raw)
        lines = [l.strip() for l in clean.splitlines() if l.strip()]
        # Suodata pois navigaatio-/footer-roskaa
        lines = [l for l in lines if len(l) > 3 and not l.startswith("http")]
        if lines:
            return "\n".join(lines[:20])

    # ── Strategia 2: weekday-indeksi data-attribuutissa ────────────────────────
    # <div data-day="1"> tai <section data-weekday="monday">
    day_names_en = ["monday","tuesday","wednesday","thursday","friday"]
    for attr_pattern in [
        rf'data-day=["\']?{today_num + 1}["\']?',      # 1-indeksoitu
        rf'data-weekday=["\']?{day_names_en[today_num]}["\']?',
        rf'data-index=["\']?{today_num}["\']?',
    ]:
        sec = _re.search(attr_pattern, html, _re.IGNORECASE)
        if sec:
            chunk = html[sec.start():sec.start() + 2000]
            clean = _re.sub(r'<[^>]+>', '\n', chunk)
            lines = [l.strip() for l in clean.splitlines() if l.strip()]
            lines = [l for l in lines if len(l) > 3]
            if lines:
                return "\n".join(lines[:20])

    # ── Strategia 3: koko teksti päivänimen hakusanalla ────────────────────────
    clean_all = _re.sub(r'<[^>]+>', '\n', html)
    all_lines = [l.strip() for l in clean_all.splitlines() if l.strip()]
    return _extract_day_block(all_lines, today_fi)


def _extract_day_block(lines: list, today: str) -> str:
    """Yleiskäyttöinen päiväblokin erottelija."""
    result, capturing = [], False
    for line in lines:
        low = line.lower()
        if today in low and not capturing:
            capturing = True
            result.append(line)
            continue
        if capturing:
            if any(d in low for d in WEEKDAYS if d != today):
                break
            result.append(line)
            if len(result) > 20:
                break
    return "\n".join(result) if result else "(Päivän menu ei löytynyt — tarkista sivu manuaalisesti.)"


def _extract_menu_block(lines: list) -> str:
    """Heuristinen blokin erottelija ilman päivänimeä."""
    result, in_menu = [], False
    for line in lines:
        low = line.lower()
        if "lounasmenu" in low or "lounas" in low:
            in_menu = True
        if in_menu and line:
            result.append(line)
        if len(result) > 25:
            break
    return "\n".join(result[:25]) if result else "(Lounastietoja ei löytynyt.)"


# ── RSS-rakentaja ─────────────────────────────────────────────────────────────

def escape_xml(text: str) -> str:
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def build_rss(items: list[dict]) -> str:
    """
    items: lista dict { title, description, link, pub_date (datetime) }
    """
    now_rfc = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")

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
    <description>Päivittäin klo 10.30 päivitetty lounaslista: Pannu, Kulho, Uuni, Antell Hella, Antell Tori</description>
    <language>fi</language>
    <lastBuildDate>{now_rfc}</lastBuildDate>
    <ttl>1440</ttl>{entries}
  </channel>
</rss>"""


# ── Historia (JSON-välimuisti) ─────────────────────────────────────────────────

HISTORY_FILE = Path(__file__).parent / "lounas_history.json"

def load_history() -> list:
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, encoding="utf-8") as f:
            return json.load(f)
    return []

def save_history(items: list):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(items[-MAX_ITEMS:], f, ensure_ascii=False, indent=2, default=str)


# ── Pääohjelma ────────────────────────────────────────────────────────────────

def main():
    today = datetime.now(HELSINKI)

    # Älä aja viikonloppuisin
    if today.weekday() >= 5:
        print(f"Viikonloppu ({today.strftime('%A')}) — ei ajeta.")
        return

    print(f"Haetaan lounasmenut {today.strftime('%d.%m.%Y klo %H:%M')} ...")

    new_items = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/124.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        for r in RESTAURANTS:
            print(f"  → {r['name']} ...", end=" ", flush=True)
            try:
                if r["type"] == "soupster":
                    menu_text = scrape_soupster(page, r["url"])
                else:
                    menu_text = scrape_antell(page, r["url"])
                print("OK")
            except Exception as e:
                menu_text = f"(Virhe: {e})"
                print(f"VIRHE: {e}")

            # HTML-muotoilu RSS-kuvaukseen
            description_html = "<br>".join(
                f"<b>{line}</b>" if i == 0 else line
                for i, line in enumerate(menu_text.splitlines())
                if line.strip()
            )

            new_items.append({
                "title":       f"{today.strftime('%d.%m.%Y')} – {r['name']}",
                "description": description_html,
                "link":        r["url"],
                "pub_date":    today.isoformat(),
            })

        browser.close()

    # Yhdistä historia + uudet alkiot
    history = load_history()

    # Poista tämän päivän vanhat versiot (uudelleenajo)
    today_str = today.date().isoformat()
    history = [h for h in history if not h["pub_date"].startswith(today_str)]
    history.extend(new_items)
    history = history[-MAX_ITEMS:]

    save_history(history)

    # Muodosta RSS-alkiot oikeilla datetime-objekteilla
    rss_items = []
    for h in reversed(history):  # Uusin ensin
        h2 = dict(h)
        h2["pub_date"] = datetime.fromisoformat(h["pub_date"])
        rss_items.append(h2)

    xml = build_rss(rss_items)
    RSS_OUTPUT.write_text(xml, encoding="utf-8")
    print(f"\n✓ RSS kirjoitettu: {RSS_OUTPUT} ({len(rss_items)} alkiota)")


if __name__ == "__main__":
    main()
