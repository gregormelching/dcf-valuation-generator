# DCF Valuation Generator — Project Context for Claude Code

## About this project

Third vibecoding project (after Budget Tracker and Trading Backtester), part of finance
career prep for IB/consulting applications. Goal: an automated DCF valuation generator
that pulls financial data from the SEC EDGAR API and computes FCF projection, WACC,
terminal value, and sensitivity analysis.

**This is primarily a learning project, not a pure delivery project.** The goal isn't
just a working tool — I (Gregor) need to actually understand the finance and technical
substance behind it, especially financial modeling fundamentals (CAPM, WACC, DCF
mechanics) that I'd otherwise have covered via BIWS but haven't yet.

## Working style / instructions for Claude Code

- Don't hand over finished solutions when a phase has an explicit learning goal (see
  roadmap below). Instead: explain the approach, suggest small steps, let me write the
  core logic myself (especially financial formulas).
- For architecture decisions (data model, module structure): briefly present options
  with trade-offs, don't silently pick the "best" one.
- Any financial assumption (growth rate, WACC components, terminal growth) must be
  explicit and justified, not hidden in code.
- When data is unclear (missing tags, N/A values): ask or flag as an open issue rather
  than silently filling in placeholders/assumptions.
- Direct, honest feedback on code and modeling logic — no sugar-coating. Call out
  weaknesses, risks, and mistakes explicitly.
- No copy-paste boilerplate without explanation, especially not for the DCF core logic
  (Phase 2) — that's the part that has to hold up in an interview.

## Tech stack (convention from prior projects)

- Python, pandas, SQLite
- Dashboard: Flask + Bootstrap 5, "Trading Terminal" dark theme:
  - Background `#0d1117`, panel `#151b23`, border `#2a3138`, text `#c9d1d9`
  - Accent `#58a6ff`, gain green `#3fb950`, loss red `#f85149`
  - Fonts: JetBrains Mono (numbers), Inter (body text), both via Google Fonts
  - Rounded panel cards (border-radius 8px), thin border instead of shadow
  - Uppercase labels with letter-spacing for form fields/metric labels
  - Large monospace KPI numbers, green/red by sign
- pytest for tests, GitHub Actions for CI

## Roadmap with learning goals

### Phase 0 — Scope & data exploration ✅ DONE
Manually explored the SEC EDGAR API (companyfacts endpoint), compared 4 companies
across industries: Apple, JPMorgan, Boeing, Tesla.

**Findings:**
- Apple's revenue tag migrated over time: `SalesRevenueNet` → `Revenues` (~2015-17) →
  `RevenueFromContractWithCustomerExcludingAssessedTax` (~2018+). A plain fallback list
  isn't enough — without sorting by recency, the last-processed tag wins regardless of
  whether it's actually the latest value.
- JPMorgan: `OperatingIncomeLoss` is missing entirely from the raw data (verified
  against raw JSON). Confirms banks don't fit a classic opex/COGS model under US-GAAP.
  **Decision needed: exclude banks from scope or handle separately (see Open
  Questions).**
- Boeing: Revenue and operating income are cleanly available via standard tags. No
  separate product/service tags needed, contrary to initial assumption.
- Two real bug classes hit while picking "correct latest value per tag/year": (1)
  cross-tag priority inversion — without a date comparison the last-iterated tag wins;
  (2) a "burn" bug where quarterly entries advance the yearly tracker prematurely,
  blocking the correct annual value. Lesson for Phase 1: this selection logic needs to
  be robust and explicitly tested, not written ad-hoc.

**Learning goal achieved:** navigated REST API docs independently, understood the
structural inconsistency of XBRL taxonomies across industries, hands-on experience with
common bug classes in "pick latest value per tag/year" logic.

### Phase 1 — Data pipeline (3–5 days) IN PROGRESS
- Structure the SEC EDGAR API integration cleanly (companyfacts/companyconcept)
- Parser for core line items (Revenue, EBIT, D&A, CapEx, Working Capital, Shares
  Outstanding) with fallback logic for differing tag names (based on Phase 0 findings)
- Data validation: sanity checks (negative revenue, missing years, outliers)
- Cache in SQLite
- **Risk:** typically takes longer than estimated — budget 1.5x the first estimate

**Learning goals:** design robust error handling and fallback logic for messy external
data; treat data validation as its own architectural component, not an afterthought.

### Phase 2 — Modeling core (3–4 days)
- FCF projection (revenue growth assumptions, margin trajectory)
- WACC (cost of equity via CAPM: beta, risk-free rate, equity risk premium from
  external sources; cost of debt from financial data)
- Terminal value (Gordon Growth vs. exit multiple, offer both)
- Discounting → enterprise value → equity value → fair value per share

**Learning goals:** understand CAPM, WACC, and DCF mechanics deeply enough to derive
them from scratch and translate into code without a template. Before closing the
phase: cross-check own derivation against a credible source (e.g. Damodaran).

### Phase 3 — Sensitivity & scenarios (2–3 days)
- Sensitivity table (WACC vs. terminal growth rate — football field matrix)
- Optional: Monte Carlo simulation over uncertain inputs for a valuation range

**Learning goals:** master sensitivity analysis as a valuation tool; for Monte Carlo,
understand random distributions and sampling, not just call a library function.

### Phase 4 — Output/interface (2–3 days)
- Dashboard in Trading Terminal style, or a structured PDF/Excel report
- Show assumptions and data sources transparently in the output

**Learning goals:** present complex, multi-dimensional results understandably, not
just impressively.

### Phase 5 — Validation (1–2 days, don't skip)
- Compare DCF outputs against real analyst price targets/consensus for 3–5 companies
- A 40%+ deviation signals a logic error or unrealistic assumptions — don't ignore it

**Learning goals:** actively check model results against external benchmarks,
systematically trace discrepancies to root causes.

### Phase 6 — Tests & CI (1–2 days)
- pytest for calculation logic (WACC, DCF formula in isolation, not just end-to-end)
- GitHub Actions CI, same pattern as the backtester

**Learning goals:** test financial formulas in isolation; design edge cases (negative
values, missing years, extreme assumptions).

### Phase 7 — Documentation
- README with an explicit limitations section: which assumptions are judgment calls,
  where the model can be wrong, what it doesn't cover (no M&A adjustments, no one-off
  item cleanup, no bank support)

**Learning goals:** precisely articulate technical limits and assumptions for a
critical audience (interviewer).

## Open questions / next steps

- **Decided:** banks excluded from scope. JPMorgan's `OperatingIncomeLoss`, CapEx tags,
  and all WorkingCapital component tags are missing entirely — a classic opex/COGS/
  working-capital DCF isn't buildable for a bank under US-GAAP, independent of parser
  robustness. The parser stays crash-safe for missing data generally, but banks are
  simply not on the target company list.
- Target company list finalized: Apple (tech hardware), Boeing (industrials/aerospace),
  Tesla (auto/EV), Microsoft (software), Procter & Gamble (consumer staples). CIKs
  verified against SEC's official company_tickers.json, not from memory.
