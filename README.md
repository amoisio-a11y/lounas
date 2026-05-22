# 🍽️ OP Kortteli Lounas RSS

Hakee automaattisesti päivän lounasmenut OP Korttelissa Vallilassa ja julkaisee ne RSS-feedinä.

## Ravintolat

| Ravintola | Sivu |
|---|---|
| Pannu – Soupster OP Kortteli | [soupsterkortteli.fi/pannu](https://www.soupsterkortteli.fi/pannu) |
| Kulho – Soupster OP Kortteli | [soupsterkortteli.fi/kulho](https://www.soupsterkortteli.fi/kulho) |
| Uuni – Soupster OP Kortteli | [soupsterkortteli.fi/uuni](https://www.soupsterkortteli.fi/uuni) |
| Antell Hella | [antell.fi/lounas/helsinki/hella](https://antell.fi/lounas/helsinki/hella/) |
| Antell Tori | [antell.fi/lounas/helsinki/tori](https://antell.fi/lounas/helsinki/tori/) |

## RSS-feedin URL

```
https://amoisio-a11y.github.io/lounas/lounas.xml
```

Liitä tämä URL Microsoft Teamsin RSS-konnektoriin.

## Miten se toimii

1. **GitHub Actions** ajaa `lounas_scraper.py`:n joka arkipäivä klo 10.30 (Helsinki)
2. Skripti käyttää **Playwright**ia JavaScript-renderöintiin (Soupster) ja suoraa HTTP-pyyntöä (Antell)
3. Tuloksena syntyy `lounas.xml` — standardi RSS 2.0 -tiedosto
4. Skripti commitoi `lounas.xml`:n ja `lounas_history.json`:n takaisin repoon
5. **GitHub Pages** julkaisee tiedoston julkisesti

## Teams-integraatio

1. Avaa Teams-kanava → `···` → **Konnektorit**
2. Etsi **RSS** → **Lisää**
3. Liitä RSS-URL: `https://amoisio-a11y.github.io/lounas/lounas.xml`
4. Päivitysväli: **1 päivä**
5. Tallenna

## Käyttöönotto (GitHub Pages)

1. Luo repo GitHubissa nimellä `lounas`
2. Lisää tiedostot (tämä paketti)
3. Mene **Settings → Pages → Source: Deploy from branch → main / (root)**
4. Odota ensimmäinen automaattinen ajo klo 10.30

## Tiedostorakenne

```
lounas-rss/
├── .github/
│   └── workflows/
│       └── lounas.yml        # GitHub Actions -ajastus
├── lounas_scraper.py         # Pääskripti
├── lounas.xml                # Generoituva RSS (älä muokkaa käsin)
├── lounas_history.json       # 30 päivän historia
├── index.html                # GitHub Pages -sivu
├── requirements.txt
└── .gitignore
```

## Vianmääritys

**Actions-ajo epäonnistuu** → Katso Actions-välilehden loki. Yleisimmät syyt: sivuston rakenne muuttunut tai bot-esto.

**Antell ei vastaa** → Kokeile manuaalisesti: `curl -A "Mozilla/5.0" "https://antell.fi/lounas/helsinki/hella/?print_lunch_list_week=1"`

**Teams ei näytä uutta sisältöä** → Teams lukee feedin noin kerran tunnissa; odota hetki commitin jälkeen.
