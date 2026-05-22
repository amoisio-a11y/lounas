#!/usr/bin/env python3
"""
OP Kortteli & Antell Vallila — Lounas sähköpostilähetin v10
Lähettää päivän lounasmenun HTML-sähköpostina Gmail SMTP:n kautta.
"""

import re
import json
import html as htmllib
import smtplib
import urllib.request
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import os

HELSINKI  = timezone(timedelta(hours=3))
WEEKDAYS  = ("maanantai", "tiistai", "keskiviikko", "torstai", "perjantai")
WEEKDAYS_CAP = ("Maanantai", "Tiistai", "Keskiviikko", "Torstai", "Perjantai")

RECIPIENTS = [
    "aleksi.moisio@op.fi",
    "ab5c3eef.oppalvelutO365.onmicrosoft.com@emea.teams.ms",
]

PANNU_RSS_URL = (
    "https://lounastaja.app/api/v1/rss/week/"
    "8fa7279e-8ff8-4275-a7ae-d52f7f12d369/current?days=current&language=fi"
)

RESTAURANTS = [
    {"id": "pannu", "name": "Pannu",
     "subtitle": "Soupster OP Kortteli",
     "url": "https://www.soupsterkortteli.fi/pannu",
     "type": "pannu_rss"},
    {"id": "kulho", "name": "Kulho",
     "subtitle": "Soupster OP Kortteli",
     "url": "https://www.soupsterkortteli.fi/kulho",
     "type": "soupster_html"},
    {"id": "uuni",  "name": "Uuni",
     "subtitle": "Soupster OP Kortteli",
     "url": "https://www.soupsterkortteli.fi/uuni",
     "type": "soupster_html"},
    {"id": "hella", "name": "Hella",
     "subtitle": "Antell",
     "url": "https://antell.fi/lounas/helsinki/hella/?print_lunch_list_week=1",
     "type": "antell"},
    {"id": "tori",  "name": "Tori",
     "subtitle": "Antell",
     "url": "https://antell.fi/lounas/helsinki/tori/?print_lunch_list_week=1",
     "type": "antell"},
]

ANTELL_DAYS = {
    "maanantai":   "M A A N A N T A I",
    "tiistai":     "T I I S T A I",
    "keskiviikko": "K E S K I V I I K K O",
    "torstai":     "T O R S T A I",
    "perjantai":   "P E R J A N T A I",
}

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
    text = htmllib.unescape(inner_html)
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('\u00a0', ' ')
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return "\n".join(lines)

# ── Scrapperit ────────────────────────────────────────────────────────────────

def scrape_pannu_rss() -> str:
    xml = http_get(PANNU_RSS_URL)
    m = re.search(
        r'<item>.*?<description><!\[CDATA\[(.*?)\]\]></description>',
        xml, re.DOTALL
    )
    if not m:
        return "(Pannun RSS ei palauttanut menua)"
    return html_to_text(m.group(1))


def scrape_soupster_html(url: str) -> str:
    raw_html = http_get(url)
    html = re.sub(r'<script[^>]*>.*?</script>', '', raw_html, flags=re.DOTALL)
    html = re.sub(r'<style[^>]*>.*?</style>',   '', html,     flags=re.DOTALL)

    idx = html.lower().find("lounasmenu")
    if idx < 0:
        return "(Lounasmenu-otsikkoa ei löydy sivulta)"

    after  = html[idx:]
    chunks = re.split(r'<!--/\$-->', after)

    result_lines = []
    for chunk in chunks[1:]:
        text = html_to_text(chunk)
        if not text:
            continue
        if any(fw in text.splitlines()[0].lower() for fw in SOUPSTER_FOOTER_WORDS):
            break
        result_lines.extend(text.splitlines())

    if not result_lines:
        return "(Menusisältöä ei löydy)"

    seen, deduped = set(), []
    for line in result_lines:
        if line not in seen:
            seen.add(line)
            deduped.append(line)
    return "\n".join(deduped)


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
            continue                        # ei lisätä päivän nimeä itse
        if capturing:
            if any(m in line for m in other_markers):
                break
            if "Pidätämme oikeuden" in line or "ainesosatiedot" in line:
                break
            result.append(line)

    return "\n".join(result) if result else "(Päivän menu ei löytynyt)"

# ── Sähköpostin HTML-rakenne ──────────────────────────────────────────────────

# Väripaletti: OP:n oranssi otsikoihin, neutraalit harmaat rakenteeseen
COLORS = {
    "bg":          "#f5f5f5",
    "card":        "#ffffff",
    "name":        "#ff6600",   # ravintolan nimi
    "subtitle":    "#888888",   # "Soupster OP Kortteli" / "Antell"
    "menu_text":   "#333333",
    "divider":     "#eeeeee",
    "header_bg":   "#ff6600",
    "header_text": "#ffffff",
    "footer_text": "#aaaaaa",
}

# Tunnetut kategoriaotsikot — nämä lihavoidaan ja kirjoitetaan isolla
CATEGORY_HEADERS = {
    "lämpimät ruoat", "lisukkeet", "salaattipöytä", "jälkiruoka",
    "nigirit", "rullat", "dumplingit", "alkuruoat", "keitot",
    "pääruoat", "kasvisruoat", "lisukkeina", "juomat", "salaatit",
}

def menu_to_html_rows(menu: str) -> str:
    """Muuntaa rivimuotoisen menun HTML-riveiksi."""
    rows = []
    for line in menu.splitlines():
        line = line.strip()
        if not line:
            continue
        # Päivämäärärivit: "25.-28.5." tai "29.5. BURGERIPERJANTAI"
        if re.match(r'^\d+[\.\-]', line):  # esim. 25.-28.5. tai 29.5.
            rows.append(
                f'<tr><td style="padding:8px 0 2px 0; font-weight:600; '
                f'color:{COLORS["menu_text"]}; font-size:14px;">{htmllib.escape(line)}</td></tr>'
            )
        # Kategoriaotsikot: tunnettu lista tai pelkkiä isoja kirjaimia
        elif line.lower().rstrip(":") in CATEGORY_HEADERS:
            rows.append(
                f'<tr><td style="padding:10px 0 3px 0; font-weight:700; '
                f'color:{COLORS["menu_text"]}; font-size:13px; '
                f'text-transform:uppercase; letter-spacing:0.05em;">'
                f'{htmllib.escape(line)}</td></tr>'
            )
        else:
            rows.append(
                f'<tr><td style="padding:3px 0; color:{COLORS["menu_text"]}; '
                f'font-size:14px; line-height:1.5;">{htmllib.escape(line)}</td></tr>'
            )
    return "\n".join(rows)


def build_restaurant_card(r: dict, menu: str) -> str:
    menu_rows = menu_to_html_rows(menu)
    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" border="0"
           style="background:{COLORS['card']}; border-radius:8px;
                  margin-bottom:20px; overflow:hidden;
                  box-shadow:0 1px 4px rgba(0,0,0,0.08);">
      <tr>
        <td style="padding:16px 24px 6px 24px; border-left:4px solid {COLORS['name']};">
          <div style="font-size:22px; font-weight:700; color:{COLORS['name']};
                      font-family:Arial,sans-serif; letter-spacing:-0.3px;">
            {htmllib.escape(r['name'])}
          </div>
          <div style="font-size:12px; color:{COLORS['subtitle']}; margin-top:2px;
                      font-family:Arial,sans-serif; text-transform:uppercase;
                      letter-spacing:0.08em;">
            {htmllib.escape(r['subtitle'])}
          </div>
        </td>
      </tr>
      <tr>
        <td style="padding:10px 24px 20px 28px;">
          <table width="100%" cellpadding="0" cellspacing="0" border="0"
                 style="font-family:Arial,sans-serif;">
            {menu_rows}
          </table>
        </td>
      </tr>
    </table>"""


def build_email_html(today: datetime, restaurants_menus: list) -> str:
    today_cap = WEEKDAYS_CAP[today.weekday()]
    date_str  = today.strftime("%-d.%-m.%Y")

    cards = "\n".join(
        build_restaurant_card(r, menu)
        for r, menu in restaurants_menus
    )

    return f"""<!DOCTYPE html>
<html lang="fi">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0; padding:0; background:{COLORS['bg']}; font-family:Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" border="0"
       style="background:{COLORS['bg']};">
  <tr>
    <td align="center" style="padding:24px 16px 32px 16px;">
      <table width="600" cellpadding="0" cellspacing="0" border="0"
             style="max-width:600px; width:100%;">

        <!-- Otsikko -->
        <tr>
          <td style="background:{COLORS['header_bg']}; border-radius:8px 8px 0 0;
                     padding:20px 24px 18px 24px;">
            <div style="color:{COLORS['header_text']}; font-size:11px;
                        text-transform:uppercase; letter-spacing:0.12em;
                        margin-bottom:4px;">
              OP Kortteli &amp; Antell Vallila
            </div>
            <div style="color:{COLORS['header_text']}; font-size:24px;
                        font-weight:700; letter-spacing:-0.3px;">
              {today_cap}in lounas — {date_str}
            </div>
          </td>
        </tr>

        <!-- Ravintolakorti-alue -->
        <tr>
          <td style="padding:20px 0 0 0;">
            {cards}
          </td>
        </tr>

        <!-- Alatunniste -->
        <tr>
          <td style="padding:8px 0 0 0; text-align:center;">
            <div style="font-size:11px; color:{COLORS['footer_text']};
                        font-family:Arial,sans-serif;">
              Automaattinen viesti · OP Kortteli Vallila ·
              <a href="https://www.soupsterkortteli.fi"
                 style="color:{COLORS['footer_text']};">soupsterkortteli.fi</a>
            </div>
          </td>
        </tr>

      </table>
    </td>
  </tr>
</table>
</body>
</html>"""

# ── Sähköpostin lähetys ───────────────────────────────────────────────────────

def send_email(subject: str, html_body: str,
               sender_email: str, app_password: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"Lounas OP Kortteli <{sender_email}>"
    msg["To"]      = ", ".join(RECIPIENTS)
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(sender_email, app_password)
        smtp.sendmail(sender_email, RECIPIENTS, msg.as_string())

# ── Pääohjelma ────────────────────────────────────────────────────────────────

def main():
    today    = datetime.now(HELSINKI)
    today_fi = WEEKDAYS[today.weekday()]

    if today.weekday() >= 5:
        print("Viikonloppu — ei ajeta.")
        return

    print(f"Haetaan lounaat: {today.strftime('%d.%m.%Y')} ({today_fi})")

    restaurants_menus = []
    for r in RESTAURANTS:
        print(f"  → {r['name']} ({r['subtitle']}) ...", end=" ", flush=True)
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
        restaurants_menus.append((r, menu))

    today_cap = WEEKDAYS_CAP[today.weekday()]
    date_str  = today.strftime("%-d.%-m.%Y")
    subject   = f"🍽️ {today_cap}in lounas — {date_str}"
    html_body = build_email_html(today, restaurants_menus)

    sender_email = os.environ["GMAIL_SENDER"]
    app_password = os.environ["GMAIL_APP_PASSWORD"]

    print(f"\nLähetetään sähköposti → {RECIPIENTS} ...")
    send_email(subject, html_body, sender_email, app_password)
    print("✓ Sähköposti lähetetty.")

if __name__ == "__main__":
    main()
