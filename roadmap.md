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
absolute and as % of revenue.

**Residuum interpreted and tolerance band set — DONE.** Two decisions, both non-obvious.

*The residuum is an exclusion criterion, not a correction term.* The `implicit` formula
assumes OCF consists solely of the four listed addbacks plus dNWC. Every other non-cash item
— impairments, pensions, provisions, disposal gains, equity-method results — therefore lands
in the residuum as well. It measures "missing working capital **plus** unlisted addbacks", not
missing working capital. Boeing proves the point: negative in 8 of 10 recent years, median
-3.95% of revenue. That is 737 MAX provisions and pension, not a working-capital gap. Adding
the residuum back onto dNWC would import provisions into working capital.

*The band is 3% of revenue (`RECON_TOLERANCE`), not 5%.* 5% was the first choice and was
wrong, because the denominator is revenue while the validated quantity is dNWC. For Apple,
dNWC runs 1-10bn against 416bn revenue, so a 5% band tolerates a residuum several times the
size of the thing it checks. Concretely: Apple FY2025 has a 19.4bn residuum = 4.65% of
revenue, which passes at 5% — while being ~19% of FCF and 4.4x the reported dNWC. At 3% the
flag counts are Apple 3/10, Boeing 6/10, Tesla 3/10, Microsoft 2/10, P&G 3/10. Boeing losing
6 of 10 years is uncomfortable but is the honest reading of its data quality, not a reason to
loosen the band.

`check_recon_tolerance` emits `recon_gap` above the band and `recon_unchecked` when the recon
inputs are incomplete — the second is essential, otherwise a year with missing inputs is
indistinguishable from a clean one. Same lesson as the `unchecked` flag in Phase 1b.

**Still open:** Apple FY2025's 19.4bn residuum is flagged but unexplained. OCF (111.5bn) sits
implausibly close to net income (112.0bn) despite 12.9bn SBC and 11.7bn D&A as addbacks, so
there is a large cash outflow outside the four working-capital slots. Suspected cause is the
Irish State Aid payment following the 2024 ECJ ruling — unverified, needs a look at the 10-K.

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

**Closed during Phase 2 step 0:** the `form`/`end` last-slot-wins issue. Root cause was that
`insert_data` re-derived which slots contributed to a multi-slot metric, duplicating a
decision `clean_values` had already made. `clean_values` now records `Tag`/`Form`/`End`
alongside `Value` while it sums, so provenance can no longer drift from the number, and the
multi-slot branch in `insert_data` became dead code and was removed.

### Phase 2 — Modeling core (3–4 days)
- FCF projection (revenue growth assumptions, margin trajectory)
- WACC (cost of equity via CAPM: beta, risk-free rate, equity risk premium from
  external sources; cost of debt from financial data)
- Terminal value (Gordon Growth vs. exit multiple, offer both)
- Discounting → enterprise value → equity value → fair value per share

**Learning goals:** understand CAPM, WACC, and DCF mechanics deeply enough to derive
them from scratch and translate into code without a template. Before closing the
phase: cross-check own derivation against a credible source (e.g. Damodaran).

#### Step 0 — data the model needs but the pipeline didn't have — DONE

Phase 1 pulled six income-statement and cash-flow items. The DCF also needs an effective tax
rate, a cost of debt, and the enterprise-value-to-equity bridge, so five metrics were added:
`Tax`, `PretaxIncome`, `InterestExpense`, `Debt`, `Cash`. Doing this before the modelling
avoided discovering the gaps halfway through the projection.

**Parser had to learn instant facts.** All six original metrics are *duration* facts with
`start` and `end`; the `diff.days > 350` filter separated annual from quarterly values. Cash
and debt are *instant* facts — balance-sheet positions with only an `end`. `get_values` read
`entry["start"]` unconditionally. A first fix branched on `"start" in entry` but left `end`
computed only inside the duration branch, which did not crash (a previous iteration's `end`
was still bound) and instead silently returned empty slots. Lesson repeated from Phase 0:
the dangerous version of a bug is the one that returns nothing rather than raising.

**Restatements: newest filing wins.** The old guard "first match wins" picked whichever entry
came first in the JSON, i.e. the *originally reported* value. Tesla's FY2016 10-K tagged long
term debt as `5892016` — reported in thousands, a filer scaling error — and corrected it to
`5892016000` in the FY2017 10-K. Off by three orders of magnitude, and it would not have been
visible in any single number, only in the net-debt series looking wrong.

The fix needs two levels, not one, or it reintroduces the Phase 0 cross-tag priority
inversion: **different tags** are ranked by fallback-list order, **the same tag** by newest
`filed`. Verified across all five companies and ten years: zero priority violations. Side
effect worth knowing: the parser now returns restated figures, not as-originally-reported.
For a DCF that is the right choice, but it is a choice — P&G's FY2016 cash moved from 7.102
to 8.098bn because of the ASU 2016-18 restricted-cash restatement.

**Tag findings (each verified against the raw JSON, not assumed):**
- `InterestExpense` is deprecated. It ends 2023 for Apple/Tesla/P&G and 2024 for Microsoft;
  successor is `InterestExpenseNonoperating`. Values are identical in overlap years, so it is
  a pure rename. Boeing uses `InterestAndDebtExpense` throughout — not the same concept, it
  includes non-interest financing cost, so Boeing's cost of debt will be overstated.
- **Apple has no successor tag at all.** From FY2024 it reports interest only inside "Other
  income/(expense), net". No interest expense is obtainable from EDGAR for 2024-2025.
- `LongTermDebt` means different things per filer: total debt including the current portion
  at Apple and Microsoft, non-current only at Boeing and Tesla. The fallback order happens to
  resolve this correctly because Apple/Microsoft/P&G all have `LongTermDebtNoncurrent` — but
  by ordering, not by design. Same pattern as the Tesla payables case in Phase 1.
- Boeing has neither `LongTermDebtNoncurrent` nor `LongTermDebt` before 2019, only
  `LongTermDebtAndCapitalLeaseObligations`. Including capital leases is correct for net debt
  under ASC 842 anyway.
- `DebtCurrent` already contains commercial paper; `LongTermDebtCurrent` does not. So
  `CommercialPaper` is a conditional slot — added only when the current-debt slot was filled
  from the narrow tag. Verified: P&G `DebtCurrent` 7.19 = `LongTermDebtCurrent` 3.84 +
  `CommercialPaper` 3.33. Without the condition, P&G double-counts every year.
- Microsoft used `AvailableForSaleSecuritiesCurrent` until 2018, `ShortTermInvestments` after.
  Missing the old tag left a 106bn hole in FY2016 — the difference between 47bn net debt and
  60bn net cash, i.e. a sign flip on the single most important balance-sheet input to the
  equity bridge.
- P&G stopped tagging `CashAndCashEquivalentsAtCarryingValue` after 2019; the successor is
  `CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents`, which is a superset. It has
  to be used or P&G has no cash at all from 2020. Restricted cash is immaterial at P&G, but
  the series has a definitional break at 2019/2020.

**Decision: long-term marketable securities count as cash.** Apple holds 91.5bn (FY2024) and
up to 170bn (FY2018) in `MarketableSecuritiesNoncurrent`. These are government and corporate
bonds held because the cash is not needed — non-operating assets, classified as non-current
only because of residual maturity. Excluding them puts Apple at +41.5bn net debt instead of
-50bn net cash, a 132bn swing straight into equity value. Added as a third `Cash` slot.
Caveat: Microsoft's `LongTermInvestments` (14.6bn) also contains equity stakes that are not
liquid securities — tolerable at that size, but not clean.

**New validation rules.** `Tax` and `PretaxIncome` initially got `yoy` rules and immediately
reproduced the Phase 1 category mismatch: Boeing flagged in 8 of 10 years, Tesla 7 of 10,
because both are result figures that flip sign in loss years. Replaced by:
- `PretaxIncome` → `margin_change_pp` at 10pp (7pp would flag Tesla's normal growth; pretax
  margin is structurally more volatile than operating margin because it carries interest,
  equity-method results and one-offs). Flags 6 of 39: Boeing 2019-2021, 2024, 2025 and Tesla
  2018 — exactly the years to exclude from driver averaging.
- `Tax` → new rule type `effective_rate`, checking `Tax / PretaxIncome` against a band rather
  than an upper bound. The lower bound matters more: negative effective rates are the real
  anomalies. Tesla 2023 at -50% is the valuation-allowance release on loss carryforwards, a
  ~5bn one-off; Microsoft 2018 at 55% is the TCJA repatriation charge, the same root cause as
  the 38.5bn working-capital outlier excluded in Phase 1.

The band alone is not enough: with negative pretax income *and* a tax benefit the ratio comes
out positive and looks normal. Boeing 2020 (-14.5bn pretax) passes at 17.5%, indistinguishable
from Apple. The effective rate is simply not interpretable on a loss, so `PretaxIncome < 0`
now yields `unchecked`. A first attempt tested the sign of `Tax` instead of `PretaxIncome`,
which inverted the result in both directions — it dismissed Tesla 2023 (profitable, tax
benefit) as unchecked and flagged Boeing's loss years as outliers.

**Verified end-to-end:** 550 rows (5 x 10 x 11 metrics), 85 flags, two consecutive runs
identical. Net debt series plausible across all five: Boeing ~0 in 2016 rising to 43bn in
2022, Tesla crossing into net cash in 2020, P&G stable at 22-28bn.

**Multi-slot summation refactored (`SLOT_SELECTORS`).** The three near-identical blocks in
`clean_values` are replaced by one loop plus a selector function per multi-slot metric. Which
slots contribute is now the selector's only job; summing, provenance and sign handling live in
one place. Verified as a pure refactor: old vs. new over all 5 companies x 10 years x
WorkingCapital/Cash/Debt gives zero differences in Value, Tag and Form.

**Two fallbacks added on top, both by the same pattern:**
- `select_pretax` — P&G's missing `PretaxIncome` is rebuilt from the Domestic/Foreign split.
  Closes 2016-2019; **2020 and 2021 stay missing**, P&G tags neither the total nor the split
  there. `PretaxIncome = NetIncome + Tax` remains the fallback of last resort if those two
  years turn out to matter.
- `select_deferred_taxes` — `DeferredIncomeTaxExpenseBenefit` genuinely ends at Apple FY2022;
  the parser was not missing a tag. The successor is the tax-footnote jurisdiction split
  (`DeferredFederalIncomeTaxExpenseBenefit` + `-Foreign-` + `-StateAndLocal-`), verified
  identical to the total in all 15 overlap years, difference exactly 0. Setting the gap to 0
  would have been wrong: Apple's deferred taxes are -3.02 / -3.03 / -1.34bn in 2023-2025.
  Only Apple needs this fallback. All three components are required rather than "sum what
  exists" — a partial sum would understate silently instead of failing visibly.

**Open for later steps:**
- Apple has no interest expense for 2024-2025 (step 4, cost of debt).

#### Step 1 — effective tax rate — DONE

Feeds `NOPAT = EBIT x (1 - t)` in the FCF bridge. Data is in the cache (`Tax`,
`PretaxIncome`), so this step reads from `get_data`, not from the parser.

**The dominant fact is the TCJA break at 2018.** The federal rate dropped 35% -> 21%, so
pre-2018 effective rates carry no information about the future. Median ETR over unflagged
years, before vs. from 2018:

| | to 2017 | from 2018 |
|---|---|---|
| Apple | 26.1% (n=11) | 15.8% (n=8) |
| Microsoft | 22.2% (n=10) | 16.5% (n=7) |
| Boeing | 26.4% (n=11) | 12.5% (n=2) |
| Tesla | none | 20.4% (n=5) |
| P&G | 24.4% (n=10) | 20.3% (n=6) |

A 20-year average would overstate the forward tax rate by 5-14pp on every company. The
window therefore starts at 2018, which costs most of the history the 20-year pull just
bought — the long series stays useful for revenue and margin drivers, not for tax.

**Boeing is the problem case.** Six of eight post-2018 years are `unchecked` because pretax
income is negative and an effective rate is not interpretable on a loss. The remaining two
(2018: 9.9%, 2025: 15.1%) are a sample, not a signal.

**Decisions taken** (`effective_tax_rate` in `logic/model.py`, the first module that reads
from the cache rather than the parser):
- **Median, not mean**, over the unflagged years in the window. The flag filter removes the
  known one-offs, but not all of them; the median limits what a survivor can do. Not academic
  here — mean vs. median differs by 2.8pp on P&G and 2.0pp on Tesla.
- **Fallback to the marginal rate at n < 3.** Boeing is the case: six of eight post-2018 years
  are `unchecked` because pretax income is negative and an effective rate is not interpretable
  on a loss. The two survivors (2018: 9.9%, 2025: 15.1%) are a sample, not a signal.
- **The return value carries `Source` and `n`, not just the rate.** Otherwise a skewed
  valuation in Phase 5 cannot be traced back to whether the tax rate was measured or assumed.
- **Terminal-year rate is the marginal rate** (`MARGINAL_TAX_RATE = 0.25`, US federal plus
  state), not the historical ETR. Damodaran's argument: deferral and planning advantages do
  not persist in perpetuity.

| | rate | n | source |
|---|---|---|---|
| Apple | 15.8% | 8 | median |
| Microsoft | 16.5% | 7 | median |
| Tesla | 20.4% | 5 | median |
| P&G | 20.3% | 6 | median |
| Boeing | 25.0% | 2 | fallback |

**Known conceptual approximation, to document rather than fix:** the ETR is measured on
pretax income (i.e. after interest) but applied to EBIT (before interest). The interest tax
shield is already captured in WACC via the after-tax cost of debt, so this double-counts it
slightly. Standard practice, but it is an approximation and an interviewer may probe it.

**Bug classes worth remembering from this step:**
- The cache path and the parser path signal absence differently. Parser dicts leave `Value`
  out entirely; `get_data` always sets the key and puts `None` in it. A guard written as
  `"Value" not in ...` is therefore dead code against the DB and has to be `is None`. The
  same guard also chained two checks as `"Value" not in (a.keys() or b.keys())`, where the
  `or` short-circuits on the first non-empty view — the second operand was never checked.
- `sorted(rates)[len(rates) // 2]` is not the median for an even count; it takes the upper of
  the two middle values. Cost only 0.1pp on Apple by luck of the data.
- A percentage conversion applied in one branch and not the other put `0.25` and `16.6` into
  the same field. In `EBIT x (1 - t)` that is a sign flip, not a rounding error.
- `get_data` briefly carried `start_year = 2018` as a default. That puts a tax-regime
  assumption into the data layer, where the revenue and margin drivers would silently have
  inherited an 8-year window instead of 20. The parameter is now required and the constant
  lives in `model.py`.

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
