#!/usr/bin/env python3
"""
Soupster Kortteli & Antell Vallila — Lounas sähköpostilähetin v11
"""

import re
import html as htmllib
import smtplib
import urllib.request
import os
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

HELSINKI     = timezone(timedelta(hours=3))
WEEKDAYS     = ("maanantai", "tiistai", "keskiviikko", "torstai", "perjantai")

RECIPIENTS   = ["aleksi.moisio@op.fi"]
SENDER       = "postimestari777@gmail.com"

PANNU_RSS_URL = (
    "https://lounastaja.app/api/v1/rss/week/"
    "8fa7279e-8ff8-4275-a7ae-d52f7f12d369/current?days=current&language=fi"
)

RESTAURANTS = [
    {"id": "pannu", "name": "Pannu",  "subtitle": "Soupster Kortteli",
     "url": "https://www.soupsterkortteli.fi/pannu",  "type": "pannu_rss"},
    {"id": "kulho", "name": "Kulho",  "subtitle": "Soupster Kortteli",
     "url": "https://www.soupsterkortteli.fi/kulho",  "type": "soupster_html"},
    {"id": "uuni",  "name": "Uuni",   "subtitle": "Soupster Kortteli",
     "url": "https://www.soupsterkortteli.fi/uuni",   "type": "soupster_html"},
    {"id": "hella", "name": "Hella",  "subtitle": "Antell",
     "url": "https://antell.fi/lounas/helsinki/hella/?print_lunch_list_week=1",
     "type": "antell"},
    {"id": "tori",  "name": "Tori",   "subtitle": "Antell",
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

CATEGORY_HEADERS = {
    "lämpimät ruoat", "lisukkeet", "salaattipöytä", "jälkiruoka",
    "nigirit", "rullat", "dumplingit", "alkuruoat", "keitot",
    "pääruoat", "kasvisruoat", "lisukkeina", "juomat", "salaatit",
}

COLORS = {
    "bg":          "#f5f5f5",
    "card":        "#ffffff",
    "name":        "#ff6600",
    "subtitle":    "#888888",
    "menu_text":   "#333333",
    "header_bg":   "#ff6600",
    "header_text": "#ffffff",
    "footer_text": "#aaaaaa",
}

HTTP_HEADERS = {
    "User-Agent":      ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"),
    "Accept":          "text/html,application/xhtml+xml",
    "Accept-Language": "fi-FI,fi;q=0.9",
    "Referer":         "https://www.google.com/",
}

# ── HTTP ──────────────────────────────────────────────────────────────────────

def http_get(url):
    req = urllib.request.Request(url, headers=HTTP_HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="replace")

# ── HTML → teksti ─────────────────────────────────────────────────────────────

def html_to_text(inner_html):
    text = htmllib.unescape(inner_html)
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('\u00a0', ' ')
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return "\n".join(lines)

# ── Scrapperit ────────────────────────────────────────────────────────────────

def scrape_pannu_rss():
    xml = http_get(PANNU_RSS_URL)
    m = re.search(
        r'<item>.*?<description><!\[CDATA\[(.*?)\]\]></description>',
        xml, re.DOTALL
    )
    if not m:
        return "(Pannun RSS ei palauttanut menua)"
    return html_to_text(m.group(1))


def scrape_soupster_html(url):
    raw = http_get(url)
    html = re.sub(r'<script[^>]*>.*?</script>', '', raw,  flags=re.DOTALL)
    html = re.sub(r'<style[^>]*>.*?</style>',   '', html, flags=re.DOTALL)

    idx = html.lower().find("lounasmenu")
    if idx < 0:
        return "(Lounasmenu-otsikkoa ei löydy sivulta)"

    chunks = re.split(r'<!--/\$-->', html[idx:])
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


def scrape_antell(url, today_fi):
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
            continue
        if capturing:
            if any(m in line for m in other_markers):
                break
            if "Pidätämme oikeuden" in line or "ainesosatiedot" in line:
                break
            result.append(line)

    return "\n".join(result) if result else "(Päivän menu ei löytynyt)"

# ── Sähköpostin HTML ──────────────────────────────────────────────────────────

def menu_to_html_rows(menu):
    rows = []
    for line in menu.splitlines():
        line = line.strip()
        if not line:
            continue
        if re.match(r'^\d+[\.\-]', line):
            rows.append(
                f'<tr><td style="padding:8px 0 2px 0;font-weight:600;'
                f'color:{COLORS["menu_text"]};font-size:14px;'
                f'font-family:Arial,sans-serif;">'
                f'{htmllib.escape(line)}</td></tr>'
            )
        elif line.lower().rstrip(":") in CATEGORY_HEADERS:
            rows.append(
                f'<tr><td style="padding:10px 0 3px 0;font-weight:700;'
                f'color:{COLORS["menu_text"]};font-size:13px;'
                f'text-transform:uppercase;letter-spacing:0.05em;'
                f'font-family:Arial,sans-serif;">'
                f'{htmllib.escape(line)}</td></tr>'
            )
        else:
            rows.append(
                f'<tr><td style="padding:3px 0;color:{COLORS["menu_text"]};'
                f'font-size:14px;line-height:1.5;font-family:Arial,sans-serif;">'
                f'{htmllib.escape(line)}</td></tr>'
            )
    return "\n".join(rows)


def build_restaurant_card(r, menu):
    return f"""
<table width="100%" cellpadding="0" cellspacing="0" border="0"
       style="background:{COLORS['card']};border-radius:8px;
              margin-bottom:20px;
              box-shadow:0 1px 4px rgba(0,0,0,0.08);">
  <tr>
    <td style="padding:16px 24px 6px 24px;
               border-left:4px solid {COLORS['name']};">
      <div style="font-size:22px;font-weight:700;color:{COLORS['name']};
                  font-family:Arial,sans-serif;">
        {htmllib.escape(r['name'])}
      </div>
      <div style="font-size:12px;color:{COLORS['subtitle']};margin-top:2px;
                  font-family:Arial,sans-serif;text-transform:uppercase;
                  letter-spacing:0.08em;">
        {htmllib.escape(r['subtitle'])}
      </div>
    </td>
  </tr>
  <tr>
    <td style="padding:10px 24px 20px 28px;">
      <table width="100%" cellpadding="0" cellspacing="0" border="0">
        {menu_to_html_rows(menu)}
      </table>
    </td>
  </tr>
</table>"""


def build_email_html(today, restaurants_menus):
    day_name = WEEKDAYS[today.weekday()].capitalize()
    date_str = today.strftime("%-d.%-m.%Y")
    cards    = "\n".join(build_restaurant_card(r, m) for r, m in restaurants_menus)

    return f"""<!DOCTYPE html>
<html lang="fi">
<head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
</head>
<body style="margin:0;padding:0;background:{COLORS['bg']};
             font-family:Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" border="0"
       style="background:{COLORS['bg']};">
  <tr>
    <td align="center" style="padding:24px 16px 32px 16px;">
      <table width="600" cellpadding="0" cellspacing="0" border="0"
             style="max-width:600px;width:100%;">

        <!-- Otsikko -->
        <tr>
          <td style="background:{COLORS['header_bg']};
                     border-radius:8px 8px 0 0;
                     padding:20px 24px 18px 24px;">
            <div style="color:{COLORS['header_text']};font-size:11px;
                        text-transform:uppercase;letter-spacing:0.12em;
                        margin-bottom:4px;font-family:Arial,sans-serif;">
              Soupster Kortteli &amp; Antell Vallila
            </div>
            <div style="color:{COLORS['header_text']};font-size:24px;
                        font-weight:700;font-family:Arial,sans-serif;">
              {day_name}in lounas &mdash; {date_str}
            </div>
          </td>
        </tr>

        <!-- Ravintolakortit -->
        <tr>
          <td style="padding:20px 0 0 0;">
            {cards}
          </td>
        </tr>

        <!-- Alatunniste -->
        <tr>
          <td style="padding:8px 0 0 0;text-align:center;">
            <div style="font-size:11px;color:{COLORS['footer_text']};
                        font-family:Arial,sans-serif;">
              Automaattinen viesti &middot; Kortteli Vallila &middot;
              <a href="https://www.soupsterkortteli.fi"
                 style="color:{COLORS['footer_text']};">
                soupsterkortteli.fi
              </a>
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

def send_email(subject, html_body, app_password):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"Lounaslista <{SENDER}>"
    msg["To"]      = ", ".join(RECIPIENTS)
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    print(f"  Yhdistetaan smtp.gmail.com:465 ...")
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            print(f"  Kirjaudutaan tilille {SENDER} ...")
            smtp.login(SENDER, app_password)
            print(f"  Lahetetaan -> {RECIPIENTS} ...")
            smtp.sendmail(SENDER, RECIPIENTS, msg.as_string())
    except smtplib.SMTPAuthenticationError as e:
        print(f"SMTP-kirjautuminen epaonnistui: {e}")
        print("Tarkista: 1) App Password on oikein GitHubin secretissa GMAIL_APP_PASSWORD")
        print("          2) Kaksivaiheinen tunnistus on paalla tililla postimestari777@gmail.com")
        print("          3) App Password on luotu juuri tälle tilille (ei muulle)")
        raise
    except Exception as e:
        print(f"SMTP-virhe: {e}")
        raise

# ── Pääohjelma ────────────────────────────────────────────────────────────────

def main():
    today    = datetime.now(HELSINKI)
    today_fi = WEEKDAYS[today.weekday()]

    if today.weekday() >= 5:
        print("Viikonloppu — ei ajeta.")
        return

    # Aikaikkunatarkistus: ohitetaan jos manuaalinen ajo (workflow_dispatch)
    is_manual = os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
    utc_now     = datetime.now(timezone.utc)
    utc_minutes = utc_now.hour * 60 + utc_now.minute
    window_start = 7 * 60        # 07:00 UTC = 10:00 Helsinki EEST
    window_end   = 8 * 60 + 29   # 08:29 UTC = 11:29 Helsinki EEST
    if not is_manual and not (window_start <= utc_minutes <= window_end):
        print(f"Ajo UTC {utc_now.strftime('%H:%M')} on aikaikkunan ulkopuolella "
              f"(07:00-08:29 UTC). Skipataan.")
        return
    if is_manual:
        print(f"Manuaalinen ajo — aikaikkunatarkistus ohitetaan.")


    print(f"Haetaan lounaat: {today.strftime('%d.%m.%Y')} ({today_fi})")

    restaurants_menus = []
    for r in RESTAURANTS:
        print(f"  -> {r['name']} ({r['subtitle']}) ...", end=" ", flush=True)
        try:
            if r["type"] == "pannu_rss":
                menu = scrape_pannu_rss()
            elif r["type"] == "soupster_html":
                menu = scrape_soupster_html(r["url"])
            else:
                menu = scrape_antell(r["url"], today_fi)
            print(f"OK ({len(menu.splitlines())} rivia)")
        except Exception as e:
            menu = f"(Virhe: {e})"
            print(f"VIRHE: {e}")
        restaurants_menus.append((r, menu))

    day_name = WEEKDAYS[today.weekday()].capitalize()
    date_str = today.strftime("%-d.%-m.%Y")
    subject  = f"Lounaat {date_str} ({day_name})"
    html_body = build_email_html(today, restaurants_menus)

    app_password = os.environ["GMAIL_APP_PASSWORD"]

    print(f"\nLahetetaan sahkopostiviesti -> {RECIPIENTS} ...")
    send_email(subject, html_body, app_password)
    print("Sahkoposti lahetetty.")



if __name__ == "__main__":
    main()
