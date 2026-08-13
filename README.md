# Termister

Magister in je terminal. Rooster, cijfers en huiswerk & toetsen ophalen via de
**Magister API** en tonen in een eigen terminal-UI (gebouwd met [Textual](https://textual.textualize.io/)),
of in een eenvoudigere versie met [Rich](https://github.com/Textualize/rich).

> Geen scraping van de Magister-website: er wordt alleen gebruikgemaakt van de
> JSON-API's die Magister zelf gebruikt.

## Features

- **Home / dashboard** – grote live klok, datum en een grafiek van alle
  cijfers van het huidige schooljaar (met gemiddelde per vak).
- **Rooster** – weekoverzicht met dagen als kolommen; toetsen rood gemarkeerd,
  uitval doorgestreept, gewijzigde lessen geel.
- **Cijfers** – overzicht van de laatste cijfers plus gemiddelde per vak
  (groen = voldoende, rood = onvoldoende).
- **Huiswerk & toetsen** – openstaande opdrachten met inleverdatum en status.
- **Demo-modus** – draaien met voorbeelddata, zonder in te loggen.
- **Sessie-cache** – na inloggen wordt de token hergebruikt; opnieuw inloggen
  alleen wanneer nodig.
- **Login-UI** – schoolnaam, gebruikersnaam en wachtwoord direct in de app
  invoeren; wachtwoord wordt niet opgeslagen.

## Installatie

```bash
cd termister
python -m venv .venv
.venv/bin/pip install -e .
```

## Gebruik

```bash
# Demo-modus (geen inloggen nodig)
.venv/bin/termister --demo

# Normaal: login-UI in de app
.venv/bin/termister

# Of gegevens meegeven (schoolnaam van je school, bv. 'grotiuscollege')
.venv/bin/termister --school grotiuscollege --username jan
```

Environmentvariabelen: `MAGISTER_SCHOOL`, `MAGISTER_USERNAME`, `MAGISTER_PASSWORD`.

### Rich-versie

Dezelfde data, maar dan in een eenvoudigere terminal-GUI op basis van
[Rich](https://github.com/Textualize/rich) (geen tabbladen maar toetsen):

```bash
.venv/bin/termister --rich --demo     # demo
.venv/bin/termister --rich            # echte login
```

### Sneltoetsen

Textual-versie:

| Toets | Actie |
|-------|-------|
| `Tab` | Wisselen tussen tabbladen |
| `Ctrl+R` | Vernieuwen |
| `q` | Afsluiten |

Rich-versie:

| Toets | Actie |
|-------|-------|
| `0` | Home / dashboard (grote klok + cijfergrafiek) |
| `1` / `2` / `3` | Rooster / Cijfers / Huiswerk & toetsen |
| `[` / `]` of `←` / `→` | Vorige / volgende dag (rooster) |
| `t` | Terug naar vandaag (rooster) |
| `r` | Vernieuwen |
| `q` of `Esc` | Afsluiten |

## Configuratie en cache

- Sessietoken: `~/.config/termister/session.json` (alleen leesbaar voor de eigenaar, `chmod 600`).
- Laatst gebruikte schoolnaam/gebruikersnaam: `~/.config/termister/credentials.json`.
- Cache overslaan: `--no-cache`.
- Andere configmap: env `TERMISTER_CONFIG_DIR`.

## Projectstructuur

```
termister/
  auth.py          # Inloggen via accounts.magister.net (OIDC) + API-basics ontdekken
  client.py        # MagisterClient: afspraken, cijfers, opdrachten via de API
  models.py        # Lesson / Grade / Assignment met API-veld-mapping
  demo_data.py     # DemoClient met voorbeelddata
  config.py        # Sessie- en credentialcache
  rich_app.py      # Rich-versie (term toetsen, geen Textual)
  ui/              # Textual-app: app, login-view, main-view, tabbladen, thema
tests/
  test_app.py      # Headless Textual-UI-test (draait de hele app door)
  test_rich_app.py # Headless test van de Rich-versie
```

Testen:

```bash
cd /tmp && .venv/bin/python /Users/ebehoekema/termister/tests/test_app.py
cd /tmp && .venv/bin/python /Users/ebehoekema/termister/tests/test_rich_app.py
```

## Disclaimer

Unofficieel project, niet gelieerd aan Magister / Iddink Group. Gebruik op eigen
risico; de inlogstroom en API's kunnen wijzigen zonder voorafgaande kennisgeving.

## Acknowledgements
This project received assistance from GitHub Copilot during development.
