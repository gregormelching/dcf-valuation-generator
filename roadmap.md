# DCF-Valuation-Generator — Projektkontext für Claude Code

## Über dieses Projekt

Drittes Vibecoding-Projekt (nach Budget-Tracker und Trading-Backtester) im Rahmen der
Finance-Karriere-Vorbereitung für IB/Consulting-Bewerbungen. Ziel: ein automatisierter
DCF-Valuation-Generator, der Finanzdaten direkt aus der SEC EDGAR API zieht und daraus
FCF-Projektion, WACC, Terminal Value und Sensitivitätsanalyse berechnet.

**Wichtig für die Zusammenarbeit: Dies ist primär ein Lernprojekt, kein reines
Liefer-Projekt.** Das Ziel ist nicht nur ein funktionierendes Tool, sondern dass ich
(Gregor) die fachliche und technische Substanz dahinter wirklich verstehe — insbesondere
Financial-Modeling-Grundlagen (CAPM, WACC, DCF-Mechanik), die ich sonst über BIWS gelernt
hätte, aber bisher nicht gemacht habe.

## Arbeitsweise / Anweisungen an Claude Code

- **Nicht einfach fertige Lösungen liefern, wenn eine Phase explizit ein Lernziel hat**
  (siehe Roadmap unten). Stattdessen: Ansatz erklären, kleine Schritte vorschlagen, mich
  Kernlogik (v.a. Finanzformeln) selbst schreiben/nachvollziehen lassen.
- Bei Architekturentscheidungen (z.B. Datenmodell, Modulstruktur) kurz Optionen mit
  Trade-offs nennen, nicht stillschweigend die "beste" Lösung durchziehen.
- Wenn eine Finanzannahme (Wachstumsrate, WACC-Komponenten, Terminal Growth) getroffen
  wird: immer explizit machen und begründen, nicht in Code verstecken.
- Bei Unklarheiten in den Daten (fehlende Tags, N/A-Werte) lieber nachfragen bzw. als
  offenen Punkt markieren, statt stillschweigend mit Platzhaltern/Annahmen aufzufüllen.
- Direktes, ehrliches Feedback zu Code und Modellierungslogik — keine beschönigenden
  Bewertungen. Schwächen, Risiken und mögliche Fehler explizit benennen.
- Kein Copy-Paste-Boilerplate ohne Erklärung, vor allem nicht bei der DCF-Kernlogik
  (Phase 2) — das ist der Teil, der im Interview verteidigt werden muss.

## Tech-Stack (Konvention aus Vorprojekten)

- Python, pandas, SQLite
- Dashboard: Flask + Bootstrap 5, **"Trading Terminal"-Dark-Theme**:
  - Background `#0d1117`, Panel `#151b23`, Border `#2a3138`, Text `#c9d1d9`
  - Akzent `#58a6ff`, Gain-Grün `#3fb950`, Loss-Rot `#f85149`
  - Fonts: JetBrains Mono (Zahlen/Monospace), Inter (Fließtext), beide via Google Fonts
  - Abgerundete Panel-Cards (border-radius 8px), dünner Border statt Shadow
  - Uppercase-Labels mit Letter-Spacing für Formularfelder/Metric-Labels
  - Große Monospace-Zahlen für KPIs, grün/rot je nach Vorzeichen
- pytest für Tests, GitHub Actions für CI

## Roadmap mit Lernzielen

### Phase 0 — Scope & Datenexploration ✅ ABGESCHLOSSEN
Manuell SEC EDGAR API erkundet (companyfacts-Endpoint), 4 Unternehmen unterschiedlicher
Branchen verglichen: Apple, JPMorgan, Boeing, Tesla.

**Befunde:**
- Apple nutzt `RevenueFromContractWithCustomerExcludingAssessedTax` als Revenue-Tag,
  nicht das naheliegende `Revenues`.
- JPMorgan liefert vermutlich `N/A` für klassisches "Operating Income" — Banken haben
  unter US-GAAP kein Opex/COGS-Modell wie Industrieunternehmen, sondern
  Nettozinsertrag + Provisionsüberschuss als separate Linien. **Konsequenz: klassisches
  DCF ist für Finanzinstitute ungeeignet — eigenes Thema (Dividend-Discount- oder
  Excess-Return-Modelle). Banken vermutlich explizit aus dem Tool-Scope ausschließen
  oder mit Warnhinweis versehen.**
- Boeing ggf. mit getrennten Tags für Produkt-/Service-Revenue
  (`SalesRevenueGoodsNet`/`SalesRevenueServicesNet`) statt einem Gesamt-Tag — noch zu
  verifizieren.

**Lernziel erreicht:** REST-API-Dokumentation selbstständig erschlossen, Verständnis für
strukturelle Inkonsistenz von XBRL-Taxonomien zwischen Branchen.

**Aktueller Code-Stand** (Explorations-Script, noch nicht Teil der finalen Pipeline):

```python
import requests
import json
from prettytable import PrettyTable

table = PrettyTable()
table.field_names = ["Company", "Revenue", "Rev. Tag", "Operating Income", "OpInc Tag"]

companies = {
    "apple": "0000320193",
    "jpmorgan": "0000019617",
    "boeing": "0000012927",
    "tesla": "0001318605",
}

REVENUE_TAGS = ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"]
OPERATING_INCOME_TAGS = ["OperatingIncomeLoss"]


def get_response(cik):
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    response = requests.get(url, headers={"User-Agent": "Gregor Melching gregor.melching.2401@gmail.com"})
    response.raise_for_status()
    return response.json()


def _to_days(end, start):
    from datetime import date
    e = date.fromisoformat(end)
    s = date.fromisoformat(start)
    return (e - s).days


def latest_annual_value(facts, tags):
    gaap = facts.get("facts", {}).get("us-gaap", {})
    candidates = []
    for tag in tags:
        entries = gaap.get(tag, {}).get("units", {}).get("USD", [])
        annual = [
            e for e in entries
            if e.get("form") == "10-K"
            and e.get("start") and e.get("end")
            and _to_days(e["end"], e["start"]) >= 300
        ]
        if annual:
            best = max(annual, key=lambda e: e["end"])
            candidates.append((best["end"], best["val"], tag))
    if not candidates:
        return None, None, None
    end, val, tag = max(candidates, key=lambda c: c[0])
    return val, tag, end


for company, cik in companies.items():
    data = get_response(cik)
    with open(f"data_{company}.json", "w") as f:
        json.dump(data, f, indent=4)

    revenue, rev_tag, rev_end = latest_annual_value(data, REVENUE_TAGS)
    op_income, op_tag, op_end = latest_annual_value(data, OPERATING_INCOME_TAGS)

    revenue_str = f"{revenue:,} ({rev_end})" if revenue is not None else "N/A"
    op_income_str = f"{op_income:,} ({op_end})" if op_income is not None else "N/A"

    table.add_row([company, revenue_str, rev_tag or "–", op_income_str, op_tag or "–"])

print(table)
```

### Phase 1 — Datenpipeline (3–5 Tage) ⏳ NÄCHSTER SCHRITT
- SEC EDGAR API-Anbindung sauber strukturieren (companyfacts/companyconcept)
- Parser für Kernposten (Revenue, EBIT, D&A, CapEx, Working Capital, Shares Outstanding)
  mit Fallback-Logik für unterschiedliche Tag-Namen (Basis: Phase-0-Befunde oben)
- Datenvalidierung: Plausibilitätschecks (negative Umsätze, fehlende Jahre, Ausreißer)
- Zwischenspeicherung in SQLite
- **Risiko:** dauert erfahrungsgemäß länger als geschätzt — mit 1,5x der ersten
  Schätzung rechnen

**Lernziele:** robuste Fehlerbehandlung und Fallback-Logik für unsaubere externe Daten
designen; Datenvalidierung als eigenständigen Architektur-Baustein behandeln, nicht als
Nachgedanken.

### Phase 2 — Modellierungskern (3–4 Tage)
- FCF-Projektion (Umsatzwachstum-Annahmen, Margen-Entwicklung)
- WACC-Berechnung (Cost of Equity via CAPM: Beta, Risk-Free Rate, Equity Risk Premium
  aus externen Quellen; Cost of Debt aus Finanzdaten)
- Terminal Value (Gordon Growth vs. Exit Multiple, beide anbieten)
- Diskontierung → Enterprise Value → Equity Value → Fair Value pro Aktie

**Lernziele:** CAPM, WACC und DCF-Mechanik so tief verstehen, dass ich sie ohne Template
selbst herleiten und in Code übersetzen kann. Vor Phasenabschluss: Cross-Check der
eigenen Herleitung gegen eine seriöse Quelle (z.B. Damodaran), nicht nur eigene
Herleitung vertrauen.

### Phase 3 — Sensitivität & Szenarien (2–3 Tage)
- Sensitivitätstabelle (WACC vs. Terminal Growth Rate — Football-Field-Matrix)
- Optional: Monte-Carlo-Simulation über unsichere Inputs für Bewertungsspanne

**Lernziele:** Sensitivitätsanalyse als Bewertungswerkzeug beherrschen; bei Monte-Carlo
Grundlagen von Zufallsverteilungen und Sampling-Methoden verstehen, nicht nur eine
Bibliotheksfunktion aufrufen.

### Phase 4 — Output/Interface (2–3 Tage)
- Dashboard im Trading-Terminal-Stil (siehe Tech-Stack oben) oder strukturierter
  PDF/Excel-Report
- Annahmen und Datenquellen transparent im Output zeigen

**Lernziele:** komplexe, mehrdimensionale Ergebnisse nachvollziehbar statt nur
beeindruckend aufbereiten.

### Phase 5 — Validierung (1–2 Tage, nicht überspringen)
- Vergleich der DCF-Outputs mit echten Analysten-Kurszielen/Consensus-Bewertungen für
  3–5 Unternehmen
- Abweichung von 40%+ = Hinweis auf Logikfehler oder unrealistische Annahmen, nicht
  ignorieren

**Lernziele:** eigene Modellergebnisse aktiv gegen externe Benchmarks prüfen,
Diskrepanzen systematisch auf Ursachen zurückführen.

### Phase 6 — Tests & CI (1–2 Tage)
- pytest für Berechnungslogik (WACC, DCF-Formel isoliert testen, nicht nur
  End-to-End)
- GitHub Actions CI, analog zum Backtester

**Lernziele:** Finanzformeln gezielt isoliert testen; Testfälle für Grenzfälle
entwerfen (negative Werte, fehlende Jahre, Extremannahmen).

### Phase 7 — Dokumentation
- README mit expliziter Grenzen-Sektion: welche Annahmen sind Judgment Calls, wo kann
  das Modell falsch liegen, was deckt es nicht ab (z.B. keine M&A-Adjustments, keine
  Sonderposten-Bereinigung, kein Banken-Support)

**Lernziele:** technische Grenzen und Annahmen präzise für ein kritisches Publikum
(Interviewer) formulieren.

## Offene Fragen / Nächste Schritte

- Boeing-Tags für Revenue noch verifizieren (getrennte Produkt-/Service-Linien?)
- Banken (JPMorgan-Fall) explizit aus Scope nehmen oder gesondert behandeln — Entscheidung
  zu Beginn von Phase 1 treffen
- Liste der finalen Ziel-Unternehmen für die Pipeline festlegen (aktuell nur
  Explorations-Sample)
