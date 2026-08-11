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

### Phase 0 — Scope & data exploration — DONE
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

### Phase 1 — Data pipeline (3–5 days) — DONE
- Structure the SEC EDGAR API integration cleanly (companyfacts/companyconcept)
- Parser for core line items (Revenue, EBIT, D&A, CapEx, Working Capital, Shares
  Outstanding) with fallback logic for differing tag names (based on Phase 0 findings)
- Data validation: sanity checks (negative revenue, missing years, outliers)
- Cache in SQLite
- Verified end-to-end (parse → validate → cache) against all 5 target companies, no crashes

**Learning goals:** design robust error handling and fallback logic for messy external
data; treat data validation as its own architectural component, not an afterthought.

**Sign convention fixed (was a real bug).** The `IncreaseDecreaseIn*` elements carry the
*balance-sheet* direction of change, not the cash effect: a positive value means the
position increased. Verified empirically against balance-sheet levels rather than assumed
(Apple FY2021 Receivables: balance-sheet delta +10.158bn vs. flow element +10.125bn; holds
across all years and all slots). `clean_values` previously summed all components with `+`,
which treated a rise in payables as capital *tied up* instead of capital *provided*.
Correct definition, now in `WC_SIGNS`:

    dNWC = dReceivables + dInventory - dPayables - dDeferredRevenue

Impact was material, not cosmetic: Apple FY2021 went from +25.1bn to -1.2bn (factor ~20,
sign flip). Since `FCF = EBIT(1-t) + D&A - CapEx - dNWC`, the old value understated FY2021
FCF by ~26bn (~7% of revenue). Post-fix the series is economically plausible: Apple, Tesla
and P&G show structurally negative dNWC (supplier/customer financing), Boeing spikes to
+28% of revenue in 2020 and +13.7% in 2024 — the 737 MAX / 787 inventory builds, i.e. a
real economic outlier, not a data artifact.

**Deferred revenue added as a 4th working-capital slot** (`ContractWithCustomerLiability`
with the pre-ASC-606 `DeferredRevenue` as fallback). Material for Microsoft (~5bn/yr) and
Boeing (up to 4bn/yr). P&G doesn't tag it at all.

**Known limitations of the working-capital definition (for Phase 7):**
- Only AR, inventory, payables/accrued and deferred revenue are captured. The catch-all
  buckets (`IncreaseDecreaseInOtherOperatingAssets`/`-Liabilities`,
  `-OtherOperatingCapitalNet`, `-OtherCurrentAssets`/`-Liabilities`) are deliberately
  excluded: they mix deferred taxes, provisions and one-offs into working capital. Apple's
  largest such position is 38.5bn in FY2018 — essentially the TCJA repatriation tax
  liability, which is not working capital and must not be projected forward as a % of
  revenue in Phase 2. `-OtherOperatingCapitalNet` (Boeing, P&G) additionally carries a
  double-counting risk as a net residual.
- Apple stopped tagging deferred revenue separately from FY2023 (it moved into the
  excluded catch-all). So Apple's dNWC includes deferred revenue for 2019-2022 but not
  2023-2025 — a structural break in the series, magnitude 0.1-0.5% of revenue.
- Tesla reports `AccountsPayable` and `AccountsPayableAndAccruedLiabilities` in parallel;
  the fallback order picks the combined tag, which is correct here but by ordering rather
  than by design.

**Per-metric validation rules — DONE.** The single global 50% YoY threshold flagged
`WorkingCapital` in ~74% of comparable company-years. Not a threshold problem but a category
mismatch: `WorkingCapital` is already a *delta*, so a relative YoY change is a second
derivative that flips sign and explodes without anything being anomalous. `OperatingIncome`
had a weaker version of the same (13/40 flags, from sign flips in Boeing/Tesla loss years).
Now `OUTLIER_RULES`, one rule per metric: `yoy` for Revenue/D&A/CapEx/SharesOutstanding,
`margin_change_pp` (7pp) for OperatingIncome, `pct_of_revenue` (10%) for WorkingCapital.
Flags are a list per value, so `outlier` no longer overwrites `negative`.

**Working-capital reconciliation added** (`RECON_TAGS`, `reconcile_working_capital`). The
dNWC definition deliberately excludes the catch-all buckets, so the size of what's excluded
has to be measurable rather than assumed. Rebuilds dNWC from the cash flow statement as
`NetIncome + D&A + SBC + DeferredTaxes - OCF` and reports `residuum = implicit - own`,
absolute and as % of revenue. Still open: interpret the residuum per company and set a
tolerance band — matters for Phase 2, where dNWC gets projected as % of revenue.

### Phase 1b — cleanup before Phase 2 — DONE

**Fixed: DB insert path was broken.** `insert_data` still assumed a string flag after flags
became a list. `if not flag == "missing"` compared list to string, always True, so the
missing-branch was dead code and a missing metric would raise `KeyError` on `["Tag"]`. On the
happy path sqlite3 refuses to bind a list (`ProgrammingError`). Parse and validate worked,
cache did not — the "verified end-to-end" claim for Phase 1 did not hold until now.

**Flags moved into a separate 1:n table** rather than being flattened into a TEXT column.
Exact filtering instead of `LIKE '%outlier%'`, and doing it now avoided a schema migration on
a populated DB later. `values.db` was rebuilt from scratch; the old flag values came from the
single-string era and no longer matched the current rule set.

The non-obvious part is idempotency: `data` gets upserted, but the flags attached to a row
survive the upsert. Without deleting them first, a second run either accumulates duplicates
or — because of `UNIQUE(data_id, flag)` — fails outright with `IntegrityError`. Order per
value is therefore: upsert `data` with `RETURNING id`, delete that id's flags, insert the
current ones. Also worth remembering: `PRAGMA foreign_keys` is per *connection* and off by
default in sqlite, so setting it once in `init_db` does nothing for later connections.

**Fixed: validation assumed Revenue exists.** The `pct_of_revenue` and `margin_change_pp`
branches read `values[year]["Revenue"]["Value"]` unconditionally — `KeyError` if Revenue was
missing for a year, and no zero-denominator guard. A first fix wrapped the whole metric loop
in the Revenue guard, which was worse: a year without Revenue produced no flags at all, not
even `missing`, so it looked clean. The guard belongs on the two ratio checks only; `yoy`
divides by the metric's own prior-year value and needs no Revenue.

New flag `unchecked` for the three cases where a check cannot run (Revenue missing/zero for
the current year, for the prior year, or a zero prior-year value). Without it, "checked and
fine" and "not checkable" are indistinguishable in Phase 2.

**Verified end-to-end:** all five companies, 10 years, parse → validate → cache → read back.
300 rows in `data` (5 x 10 x 6), 35 flags, all `outlier`, no `missing` and no `unchecked` —
the guards are insurance, not a live data problem. Two consecutive runs produce identical
counts. Boeing 2020 dNWC is flagged at 28% of revenue, i.e. the rule catches the 737 MAX
inventory build it was designed for.

**Still open (minor):** in the WorkingCapital branch of `insert_data`, `form`/`end` are
overwritten by whichever slot comes last in dict order. Harmless today (all slots come from
the same 10-K) but it's an accident, not a decision.

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
