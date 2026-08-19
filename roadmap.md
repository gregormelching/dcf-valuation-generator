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

#### Step 2a — driver ratios — DONE

`driver_ratio(data, metric)` in `logic/model.py` returns the median of `metric / Revenue`
over the usable years, as `{Ratio, n, Source}`. Feeds the EBIT margin, D&A, CapEx and dNWC
legs of `FCF = EBIT x (1 - t) + D&A - CapEx - dNWC`. Window is 2016+.

| | EBIT margin | D&A | CapEx | dNWC |
|---|---|---|---|---|
| Apple | 28.81% (n=10) | 3.56% (n=10) | 3.04% (n=10) | -0.34% (n=7) |
| Microsoft | 41.59% (n=9) | 6.34% (n=10) | 11.56% (n=10) | -1.59% (n=8) |
| P&G | 22.09% (n=8) | 3.88% (n=10) | 4.40% (n=10) | -0.97% (n=7) |
| Tesla | 6.32% (n=7) | 5.08% (n=10) | 9.90% (n=10) | -4.04% (n=7) |
| Boeing | 6.98% (n=5) | 2.58% (n=10) | 2.10% (n=10) | -0.30% (n=4) |

**An `outlier` flag does not mean the same thing under every rule — reusing the flags as a
driver filter needed that distinction.** The flags were designed to find data errors, not to
select driver years. Under `yoy` (D&A, CapEx) an `outlier` means "grew by more than the
threshold", which is normal for a growing company and says nothing about the *ratio* to
revenue: Tesla's flagged D&A years sit at 5-7% of revenue, Microsoft's at 6-8%, i.e. dead
normal levels. Excluding them cost Tesla 4 of 10 years and Microsoft 3, and biased the driver
toward slow-growth years. Under `margin_change_pp` (OperatingIncome) and `pct_of_revenue`
(WorkingCapital) an `outlier` means the ratio itself jumped — exactly what has to go. So the
filter drops every flag except `outlier` on a `yoy` metric. Same category mismatch as the
global 50% YoY threshold in Phase 1, one level up.

Writing that filter as a list of flag names to exclude was the wrong shape and `recon_gap`
was promptly forgotten, silently putting the reconciliation-gap years back into the dNWC
driver (Apple -0.47% instead of -0.34%, Boeing -2.26% instead of -0.30%). Inverted now: any
remaining flag disqualifies, with the single named exception. A new flag type costs no code
change.

**No fallback value, unlike the tax rate.** Below `MIN_YEARS` the function returns
`Ratio: None` with `Source: "Insufficient"` rather than a substitute. The tax rate can fall
back on the marginal rate because a statutory rate is a real external anchor; there is no
statutory CapEx ratio, so inventing one would be fiction. Returning `0` was the first version
and is worse than useless: `0` is a legitimate dNWC value (a company tying up no working
capital), so the consumer cannot tell it apart from "no data" — the same distinction the
`unchecked` flag exists for in Phase 1b. The projection must refuse to run on a `None` driver
rather than substitute silently.

Currently the guard never fires — the thinnest sample is Boeing dNWC at n=4. It is insurance.
Verified against a case that does trip it: Boeing from 2019 returns `None` for both EBIT
margin and dNWC at n=2, where the old version reported a -3.14% EBIT margin as a driver. That
number is wrong but not obviously wrong, which is why the function has to be loud there.

**Assumptions to carry into the projection, not code:**
- Boeing's EBIT margin of 6.98% rests on 5 years, all pre-737-MAX-crisis (2007-2016 ran a
  steady 7-8%). Unfiltered the median is -1.79%. Using the filtered figure asserts Boeing
  returns to its structural normal — a judgment call, not a measurement.
- Tesla's median revenue growth is 28.31% on the 2016+ window. (An earlier note here said
  39.8% — that figure came from a 2015 start, where the extra year makes the sample even and
  shifts the median. Corrected, and a reminder that every ratio in this file is only defined
  together with its window.) Not projectable as a constant: it needs a fade from the measured
  starting growth to the terminal growth rate over the projection horizon. That is step 2b.

#### Step 2b — revenue growth and FCF projection — DONE

Three functions in `logic/model.py`. `growth_rate(data)` measures YoY revenue growth over the
usable year pairs and returns median, mean, mean of the last three, `n` and `Source`.
`project_revenue(data, years)` fades from the measured growth to `TERMINAL_GROWTH = 0.025`.
`project_fcf(data, years)` applies the step-2a drivers to the projected revenue and returns
`years + 1` rows — the extra one is the terminal-year cashflow, marked `Flag: "TV"`.

| | Median | Mean | Last three | n |
|---|---|---|---|---|
| Apple | 6.30% | 8.04% | 1.88% | 9 |
| Microsoft | 14.28% | 13.43% | 12.49% | 9 |
| P&G | 2.48% | 2.90% | 1.68% | 9 |
| Tesla | 28.31% | 36.91% | 5.60% | 9 |
| Boeing | 6.94% | 1.18% | 12.26% | 9 |

**Why median, and why all three are reported.** CAGR was rejected: it reads only the two
endpoints, and Boeing's window starts pre-737-MAX-crisis and ends mid-recovery, so the CAGR
describes the two chosen years rather than the business. The mean is dragged by single
outlier years (Boeing 1.18% vs. 6.94% median — one crisis year does that). The median is the
base case; mean and last-three are carried along because step 2c has to choose between them,
and a function that silently returns only its own preferred answer hides that decision.

**Linear fade:** `g_t = g0 + (g_terminal - g0) * i/N`, so terminal growth is reached exactly
in year N, not one year early and not one year late. That matters because the terminal value
in step 4 assumes the company has *already arrived* at steady state — if the last projected
year still grows at 8%, the Gordon formula is applied to a company that isn't in perpetuity
yet, and the error lands in the 60-80% of enterprise value that TV represents.

**The terminal year uses `MARGINAL_TAX_RATE`, not the measured ETR.** Apple's measured 15.78%
comes from deferral, IP structures and foreign mix — all finite, and all under pressure from
Pillar Two's 15% global minimum and the Irish State Aid ruling. In perpetuity the statutory
rate is the honest assumption. Effect: `(1 - 0.25) / (1 - 0.1578) = 0.89`, terminal NOPAT
-11%, roughly 7-9% of total value. Visible in the verification below as the FCF drop from
157.83 to 144.68 while revenue still grows.

**Verified — Apple, `project_fcf(get_data("apple", 2016), 10)`, in bn:**

| Year | Revenue | FCF | |
|---|---|---|---|
| 2026 | 440.80 | 110.75 | first projected year |
| 2035 | 628.23 | 157.83 | `Growth_Rate` exactly 0.025 |
| 2036 | 643.93 | 144.68 | `Flag: "TV"`, marginal tax rate |

**Four bugs worth keeping, all of the silent kind:**
- The horizon was tied to the wall clock (`datetime.now().year + years`). It produced exactly
  10 years in 2026 by coincidence and would have quietly become 9 in 2027. Projection lengths
  must come from the data's last year, never from today's date.
- The terminal row was written by a branch that never fired — first comparing a projected year
  against the last *historical* year, then against a year one past the range end. No row ever
  carried `Flag`, and nothing raised. Only counting the returned rows exposed it.
- The terminal revenue was first taken from `project_revenue(data, years + 1)`. That re-lays
  the whole fade over 11 years and changes *every* growth rate: 2035 becomes 639.84 instead of
  628.23. The terminal year is one step of `TERMINAL_GROWTH` past the last projected year, not
  a re-projection.
- `if any([...]) is None` as the missing-driver guard: `any()` returns a bool, never `None`,
  so the guard was constantly false and step 2a's deliberate `None` would have propagated into
  the arithmetic as a `TypeError` deep in the loop. Now `if None in [...]: raise ValueError`.
  Same family as the `or`-short-circuit bug from step 1 — a guard that reads correctly in
  English but evaluates to a constant.

Also found while filtering flags: `flags = data[year][metric]["Flag"]` binds a reference, so
`flags.remove("outlier")` edited the caller's data in place. Verified on Tesla: five Revenue
years carried `outlier` before the call and zero after it. Any later consumer would have seen
silently cleaned data. Copy via list comprehension.

#### Step 2c — the three modelling decisions left in the projection — ALL DONE

The projection runs; what it assumes is not yet decided. In order:

**1. Which growth rate is the base.** The median is a statement about the past nine years, not
about next year, while the fade needs the *current* level to fade down from. Tesla: 28.31%
median vs. 5.60% over the last three years — a factor of 2.50 in year-10 revenue (347.7 vs.
138.9bn). Boeing inverts it: 6.94% median off a crisis-depressed base vs. 12.26% recently,
which is recovery, not a steady state (138.8 vs. 173.6bn). Apple 1.21x, Microsoft 1.08x,
P&G 1.04x — for the stable three it barely matters, for the two interesting ones it decides
the valuation. No single rule is right for all five, so: `project_revenue(data, years, base)`
with `"median"` as the default, the choice reported in the output the way `effective_tax_rate`
reports Median vs. Fallback, and the per-company deviation written down here as a judgment
call. Phase 3's sensitivity table is where this uncertainty gets shown, not resolved.
**Decided in step 4b** — median for Apple, Microsoft and P&G, `Mean_Last_Three` for Tesla and
Boeing, with the per-company reasoning and the measured spread in that entry.

**2. The EBIT margin is flat from year one — DONE.** Boeing actually earned 4.79% in 2025 while
the driver is 6.98%, so the old version booked the entire turnaround in the first projected
year and then held it forever. `project_fcf` now fades linearly from the last actual margin to
the driver over the horizon, same shape as the growth fade:
`m_t = m_last + (m_driver - m_last) * i/N`. The per-year margin is carried in the output as
`EBIT_Margin` rather than only implied by `EBIT / Revenue`, so the trajectory is auditable
without back-computing it.

| | last actual | driver | projected year 1 |
|---|---|---|---|
| Apple | 31.97% | 28.81% | 31.65% |
| Microsoft | 45.62% | 41.59% | 45.22% |
| P&G | 24.26% | 22.09% | 24.05% |
| Tesla | 4.59% | 6.32% | 4.77% |
| Boeing | 4.79% | 6.98% | 5.00% |

Not cosmetic: Apple's first projected FCF moves from 110.75 to 121.31bn (+9.5%), because the
three high-margin companies were previously marked down to their ten-year median immediately.
The direction differs by company — Apple, Microsoft and P&G start *above* their driver and
fade down, Tesla and Boeing start below and fade up. The terminal row keeps the driver margin,
which is exactly what the fade arrives at in year N, so the two are consistent by construction
rather than by coincidence.

The guard on the last actual margin raises rather than falling back on the driver. A missing
last actual year means the anchor for the whole trajectory is unknown, and silently starting
the fade at the driver would be indistinguishable from the old flat behaviour.

**3. Terminal reinvestment is pinned by `g / ROIC` — DONE.** CapEx and D&A used to inherit the
horizon driver ratios into perpetuity; a company growing at 2.5% forever cannot keep spending
3.04% of revenue on CapEx just because it did during the growth phase. The TV row now sets
`Reinvestment_Rate = TERMINAL_GROWTH / terminal_roic` and `FCF = NOPAT - NOPAT × rate`, with
`D&A`, `CapEx` and `dNWC` left at `None` — in steady state only the net figure is defined, and
writing a plausible CapEx/D&A pair there would invent two numbers to express one.

`terminal_roic` is a required parameter of `project_fcf`, not computed inside it, so `model.py`
stays independent of the discount rate (step 3c). `dcf_value` passes the scenario WACC, which
makes perpetual growth value-neutral and is the conservative default. The guard raises when
`terminal_roic <= TERMINAL_GROWTH`, because the reinvestment rate would exceed 100% and the FCF
would flip sign silently.

**This pin is consistent in the terminal year and inconsistent against the explicit period** —
three of five companies run negative net reinvestment before it. That is the open half, and it
sits in step 4b rather than here.

#### Step 3a — price data and the risk-free rate — DONE

WACC needs a beta, and beta needs price series. New module `logic/prices.py` with `SYMBOLS`
(the five companies plus `"market": "^GSPC"`) and `fetch_prices(symbol, freq)`. The market
index is a sixth entry in the same dict rather than a special case, so it runs through the
identical calendar and adjustment path — otherwise the two return series drift apart and the
covariance is measured against a different grid.

**First external dependency.** Everything in `logic/` ran on the standard library until now.
`requirements.txt` pins the full `pip freeze`, not just the three direct packages — the
transitive tree matters here because the behaviour depends on it. Current: `yfinance==1.5.2`,
`pandas==3.0.5`. Two traps on the way in: `pip freeze > requirements.txt` under PowerShell
writes UTF-16LE, which git treats as binary and `pip install -r` cannot read (use
`Out-File -Encoding utf8`), and `raise_errors` is deprecated in yfinance 1.5.2 in favour of
`yf.config.debug.hide_exceptions`.

**The split assumption was wrong, and it was the entire premise of this step.** The stated
risk was that unadjusted prices silently destroy beta, because Apple (4:1, 2020-08-31) and
Tesla (5:1, 2020-08-31 and 3:1, 2022-08-25) split inside the window and would show as
phantom crashes of 75-80%. Measured, that cannot happen: Yahoo's `Close` is *always*
split-adjusted, whatever `auto_adjust` is set to. `auto_adjust` controls the **dividend**
adjustment only. AAPL 2019-08-30 reads 50.08 adjusted vs 52.19 raw — a 4% level difference
that decays to 0.09% by 2026 — while TSLA is bit-identical in both modes because it pays no
dividend. So the real exposure is a systematic understatement of returns in ex-dividend
months for AAPL, MSFT and PG, worth roughly 0.15-0.25pp per quarter. That biases beta
slightly; it does not wreck it.

Consequence for the code: `MAX_SPLIT_DROP = -0.60` stays, but demoted to a plausibility
tripwire rather than the thing that catches the failure. It has never fired and cannot fire
via `auto_adjust` — the worst genuine month in the window is Boeing at -45.8% (2020-03).
The check that actually detects an unadjusted pull is the **presence of an `Adj Close`
column**: yfinance only emits it when `auto_adjust` was off. One-sided (`returns.min()`,
not `abs().max()`) because a 3:1 split is -66.7% while Tesla legitimately gained +74.1% in
a single month — a two-sided threshold would have raised on clean data.

**Why a daily pull plus own resampling, not `interval="1mo"`.** Yahoo's monthly bars are
labelled with the month *start* and the final bar is the partial current month, so neither
"61 rows" nor "last row on a month end" is obtainable from them. `Ticker.history` is used
over `yf.download` because the latter still defaults to `multi_level_index=True`, where
`df["Close"]` returns a DataFrame rather than a Series and everything downstream computes
silently wrong. Pull is `period="7y"` daily; six years would put the 2020 splits inside the
first, partial bucket where no prior month exists to compare against. Order matters: the
return check runs on the full ~84-month series, the trim to `N_MONTHS`/`N_WEEKS` happens
after.

**Two non-obvious mechanics, both silent if missed:** `resample("ME")` labels on the
calendar month end even when the data stops mid-month, so the newest row looks complete
while holding a shorter return period — it has to be dropped by comparing its label against
the last actual trading day, or the row count depends on which weekday the script runs.
And sqlite3 refuses to bind `numpy.float64`, so the values need an explicit `float()`.

**Cache layer.** Two tables, `prices` and `raw_downloads`, and `insert_prices` /
`get_prices` / `insert_raw_download` in `database.py` — same split as Phase 1, network in
its own module, DB access in `database.py`. `symbol` stores the project key (`"apple"`,
`"market"`), not the Yahoo ticker; the ticker is an external identifier like the CIK and
never enters the DB.

The `adjusted` column needed a second half to be worth anything. `UNIQUE(symbol, date, freq)`
does not include it, so an unadjusted comparison run would overwrite the clean rows at the
same keys and the column would document the damage instead of preventing it. The upsert
therefore carries `WHERE EXCLUDED.adjusted >= prices.adjusted`, and `get_prices` filters
`adjusted = 1` — a symbol present only in raw form then falls into the length guard and
raises, rather than quietly returning prices. `get_prices(symbol, freq, n)` takes `n` as a
required parameter for the same reason `get_data` takes `start_year`: the window is a
modelling assumption and does not belong in the data layer. It raises instead of returning
`None` because a covariance over 40 months instead of 61 computes fine and produces a
plausible number.

`raw_downloads` stores `df.to_csv()` of the daily frame with the yfinance version, always
tagged `freq = "1d"` regardless of what the caller asked for, since that is what the body
contains. Honest limitation: this is not the HTTP response. yfinance parses Yahoo's JSON
internally and only hands out a DataFrame, so the CSV is the earliest point the code sees
the data — the wire body would require bypassing yfinance and reimplementing the adjustment.

**Verified (dry run, inserts patched out):** all six symbols land on an identical grid,
monthly 61 rows `2021-07-31` to `2026-07-31`, weekly 105 rows `2024-08-09` to `2026-08-07`.

**Open:** `^GSPC` is a price index without dividends while the stock series are
dividend-adjusted total-return series. Immaterial for beta, but a historical ERP measured
from it understates by roughly 2pp — `^SP500TR` is the alternative, with shorter history.
Boeing's 2024 capital raise is in the window; `auto_adjust` correctly does not touch
dilution, so Boeing's beta partly measures a financing event.

**Part 2 — `risk_free_rate()`, also in `prices.py` — DONE.** FRED series DGS10, the keyless
CSV endpoint, no API key. Returns `{Risk_Free_Rate, Date, Source}`, same shape as
`effective_tax_rate` and `cost_of_debt`, so a later valuation can be traced back to which
observation it used. Current reading: 0.0472 as of 2026-08-10.

Four things about that file that are not guessable and cost a debugging round each:

- **Holidays are empty fields, not `"."`.** The premise going in was that FRED writes a dot
  for non-trading days; measured, it writes nothing at all — 719 empty values out of 16,855
  observations, e.g. `2025-12-25,`. A guard on `== "."` catches none of them and fails later
  inside `float('')`, at a place that looks like a network error.
- **Read the columns by position, not by name.** FRED renamed the header from `DATE` to
  `observation_date`; it currently reads `observation_date,DGS10`. Indexing by name works
  until the next rename, and then only in production.
- **Search backwards, don't take the last line.** The final rows are regularly weekends,
  holidays or simply not published yet — today the newest observation is 2026-08-10 while the
  11th and 12th do not exist. Normal publication lag is one to two business days.
- **FRED delivers percentage points.** `4.72` means 4.72%, and the rest of the model works in
  decimals. Same class as the step 1 bug where `0.25` and `16.6` shared a field; in CAPM it is
  a factor of 100 on the discount rate, not a rounding issue.

`RF_MAX_AGE_DAYS = 10` guards staleness, because a frozen series looks exactly like a valid
rate — without it a valuation six months from now silently uses a six-month-old yield. Ten
days lets holiday weeks through and still catches a genuinely dead feed. The first version
compared `datetime.now().day` against `date.day`, i.e. day-of-month against day-of-month,
which returns a negative number across a month boundary and never fires.

#### Cost of debt (`logic/wacc_calculation.py`) — DONE

`cost_of_debt(data, start_year)` returns `{Cost_of_Debt, n, Source}`, computed as
`InterestExpense / average(Debt_t, Debt_t-1)`, median over the usable years. The average is
used because interest accrues over the year while debt is a balance-sheet instant — using the
closing balance alone overstates the rate for a company that borrowed late in the year. The
flag filter is the same rule-aware one as `driver_ratio`: an `outlier` under a `yoy` rule is
dropped from consideration because it only means the position grew, while any other flag
disqualifies the year. Below `MIN_YEARS` it returns `None` with `Source: "Insufficient"`, no
substitute — same argument as the driver ratios, there is no statutory cost of debt to fall
back on.

| | from 2018 | n | from 2023 | n |
|---|---|---|---|---|
| Apple | 2.71% | 6 | **None** | 1 |
| Microsoft | 3.84% | 8 | 5.03% | 3 |
| P&G | 1.63% | 8 | 2.71% | 3 |
| Tesla | 5.38% | 8 | 4.66% | 3 |
| Boeing | 4.30% | 8 | 4.73% | 3 |

**The window choice is unresolved and it matters.** A short window (2023+) measures today's
rate environment, which is what a forward-looking WACC wants; a long one (2018+) averages in
the zero-rate years and understates the cost of debt by 100-200bp for Microsoft and P&G. But
the short window breaks Apple outright: interest expense is untaggable from EDGAR for
2024-2025 (the Step 0 finding — Apple reports interest only inside "Other income/(expense),
net" from FY2024), so `n = 1` and the function correctly refuses. Options are a longer window
for Apple only, a synthetic rating-based spread over the risk-free rate à la Damodaran, or
accepting a stale rate. Decide before assembling WACC, and write down which one, because it
is a per-company judgment call and not a measurement.

Boeing's figure is additionally overstated: it uses `InterestAndDebtExpense`, which includes
non-interest financing cost. Known since Step 0, unfixable from EDGAR.

#### Step 3b — beta — DONE

`raw_beta(symbol, freq, n)` in `logic/wacc_calculation.py` regresses the symbol's returns on `^GSPC`'s and
returns `{Beta, n, Correlation, Std_Error, Source}`, where `Source` is the frequency. Both
series come from `get_prices`, which guarantees the identical date grid by construction; the
function still asserts it element-wise, because a silent misalignment shifts one series by a
period and produces a beta that looks entirely normal.

**Measured, five years monthly (60 returns) against two years weekly (104 returns):**

| | beta 1mo | corr | SE | 95% CI (1mo) | beta 1wk | corr |
|---|---|---|---|---|---|---|
| Apple | 1.089 | 0.690 | 0.150 | 0.80 – 1.38 | 1.048 | 0.571 |
| Microsoft | 1.107 | 0.640 | 0.174 | 0.77 – 1.45 | 1.111 | 0.566 |
| P&G | 0.386 | 0.333 | 0.144 | 0.10 – 0.67 | 0.189 | 0.179 |
| Tesla | 1.830 | 0.477 | 0.443 | 0.96 – 2.70 | 1.817 | 0.527 |
| Boeing | 1.212 | 0.538 | 0.249 | 0.72 – 1.70 | 1.483 | 0.616 |

**The standard error is the whole point of the step, and it is uncomfortable.** The CIs are
not a formality: Tesla's spans 0.96 to 2.70, which at `rf = 4.72%` and a 4.5% ERP is a cost of
equity between 9.1% and 16.9% — a factor of roughly 2.5 on the discounted value of a long-dated
cash flow. Reporting beta as a single number without it would present the least certain input
in the model as if it were measured. `R^2 = corr^2` puts numbers on how much of each stock is
even explained by the market: Apple 0.48, Microsoft 0.41, Boeing 0.29, Tesla 0.23, P&G 0.11.

**The weekly cross-check does not confirm the monthly estimate; it contradicts it twice.** P&G
reads 0.386 monthly vs 0.189 weekly, a factor of two, and Boeing 1.212 vs 1.483. Apple,
Microsoft and Tesla agree within 0.04. The two windows are not the same experiment — the weekly
series covers two years and the monthly five — so the disagreement is partly a window effect
and partly noise, and both candidates sit inside the other's confidence interval. The honest
reading is that P&G's beta is not identified by this method at all (R^2 of 0.11), not that one
frequency is right. It is a diagnostic, not a tiebreaker.

**Standard error is computed by hand because the stdlib does not have it.**
`statistics.linear_regression` returns slope and intercept only, so
`SE = sqrt(SSR / (n - 2) / Sxx)` is written out. The `n - 2` is not cosmetic: two parameters
are estimated, and using `n` understates the SE by ~2% at n=60 — small here, but wrong in a
way that always points the same direction.

**Inconsistent with the rest of the module, deliberately noted rather than fixed:**
`effective_tax_rate`, `driver_ratio` and `cost_of_debt` all signal insufficiency through
`Source` and return `None`. `raw_beta` has no such path — `get_prices` raises when fewer than
`n` rows carry `adjusted = 1`, so a thin series surfaces as an exception rather than as a
value. That is defensible (a beta over 40 months would compute fine and look plausible, the
same argument that put the guard in `get_prices`), but it means the consumer has to handle two
different absence conventions in one module.

**Part 2 — the adjustment chain — DONE.** `debt_to_equity(data, symbol, year)` returns gross
debt over market cap, where `year = None` means "today" (newest monthly close against the
latest fiscal year) and an explicit year means that year's December close.
`adjusted_beta(data, symbol, freq, n)` runs raw -> unlevered -> relevered -> Blume and keeps
every stage plus `DE_Window` and `DE_Current` in the return value.

- **Unlever/relever is a no-op unless the two D/E ratios differ, and that is a real trap.**
  Verified: unlevering at today's D/E and relevering at today's D/E returns the raw beta to the
  third decimal for all five companies. The chain only means something if the beta is unlevered
  at the *average* D/E over the regression window and relevered at *today's*. Measured (gross
  debt / market cap, calendar year-end closes):

  | | avg D/E 2021-25 | D/E today | raw | unlev | relev | Blume |
  |---|---|---|---|---|---|---|
  | Apple | 0.038 | 0.021 | 1.089 | 1.059 | 1.076 | 1.051 |
  | Microsoft | 0.020 | 0.012 | 1.107 | 1.091 | 1.101 | 1.068 |
  | P&G | 0.092 | 0.097 | 0.386 | 0.361 | 0.387 | 0.590 |
  | Tesla | 0.005 | 0.007 | 1.830 | 1.823 | 1.833 | 1.558 |
  | Boeing | 0.453 | 0.378 | 1.212 | 0.905 | 1.161 | 1.108 |

  Four of five move by less than 0.02, i.e. inside a tenth of their own standard error. Only
  Boeing moves materially (1.212 to 1.161, -4.2%), which is exactly the company whose capital
  structure changed in the window — the 2024 capital raise. So the chain earns its complexity
  on one company out of five. **Decided: carried for all**, because the alternative is asserting
  a stable capital structure, which is exactly the assumption Boeing violates and the one a
  future leveraged company would violate harder.
- **Blume dominates everything the relevering does, and it does the most damage where the
  estimate is weakest.** P&G goes 0.387 to 0.590, +52%, on a regression with an R^2 of 0.11.
  Tesla goes 1.833 to 1.558, -15%. The shrink toward 1.0 is defensible precisely because those
  estimates are noisy, but it is an assumption about mean reversion, not a measurement, and it
  moves the valuation more than the leverage adjustment does.
- **Market cap rests on an approximation that has to be recorded.** The only equity count is
  `SharesOutstanding` from EDGAR — a weighted average of diluted shares over the fiscal year —
  multiplied by a spot close. For Apple, with continuous buybacks, that is a 2-3% error on
  market cap. It barely propagates at D/E ratios of 0.02, but it is the same number that will
  later divide equity value into a per-share figure, where it matters directly.
- **Which tax rate unlevers — decided: `MARGINAL_TAX_RATE`.** The Hamada relation assumes the
  marginal rate; Apple's 15.8% effective rate would understate the tax shield. At these D/E
  levels the choice is worth <0.01 of beta for everyone except Boeing.
- **The D/E series above uses calendar year-end closes against fiscal-year debt.** Correct only
  for Boeing and Tesla; Apple's fiscal year ends in September, Microsoft's and P&G's in June.
  Immaterial at the current ratios, but it is a mismatch and would not stay immaterial for a
  leveraged company. `debt_to_equity` also always reads the monthly grid regardless of the
  `freq` the beta was measured on — deliberate, since the December closes it needs exist there
  for every window and an annual balance sheet does not need a weekly price.

**Two bugs from this step, both invisible on the frequency actually being tested:**
- The window years were derived with `"12" in date`, a substring test against the full date
  string. It survives on `"1mo"` by accident — month-end labels fall on days 28-31, so "12"
  can only ever be the month — and breaks on `"1wk"`, where `2024-03-12` matches. Same family
  as every other "reads correctly in English, evaluates to something else" guard in this file.
- Even after fixing the match, the weekly path produced `[2024, 2024, 2024, 2024, 2025, 2025,
  2025, 2025]`: December has four to five Fridays, so each one contributed a window year and
  the mean silently weighted years by how many Fridays they happened to contain. Invisible
  monthly (exactly one December per year), and invisible weekly whenever the counts happen to
  match. Fixed with `sorted(set(...))`.

#### Step 3c — cost of equity and WACC — DONE

`cost_of_equity(beta, rf, erp)` and `calc_wacc(data, symbol, freq, n, erp)` in
`logic/wacc_calculation.py`. Both take the *dicts* of the upstream functions rather than bare
floats, so `Source`, `n` and `Std_Error` propagate instead of being re-derived at the call site.

The module was split off under its own name rather than `wacc.py` so the module and the function
inside it do not share an identifier. `model.py` deliberately does **not** import from it: the
FCF series must not depend on the discount rate, which is why `project_fcf` takes `terminal_roic`
as a required parameter (step 2c-3) instead of computing it. The dependency runs
`wacc_calculation → model` only; wiring both together is the job of the step 4 module.

Measured at `rf = 4.68%` (DGS10, 2026-08-12), `EQUITY_RISK_PREMIUM = 0.0428`, monthly beta over
61 closes, `MARGINAL_TAX_RATE = 0.25`:

| | β_adj | Cost of equity | 95% CI |
|---|---|---|---|
| Apple | 1.051 | 9.18% | 8.34 – 10.01% |
| Microsoft | 1.068 | 9.25% | 8.28 – 10.22% |
| P&G | 0.590 | 7.20% | 6.39 – 8.02% |
| Tesla | 1.558 | 11.35% | 8.86 – 13.84% |
| Boeing | 1.108 | 9.42% | 8.08 – 10.76% |

| | W_e | W_d | Kd | Kd after tax | COD window | **WACC** | 95% CI |
|---|---|---|---|---|---|---|---|
| Apple | 97.91% | 2.09% | 2.71% | 2.03% | 2018 | **9.03%** | 8.21 – 9.84% |
| Microsoft | 98.77% | 1.23% | 5.03% | 3.77% | 2023 | **9.18%** | 8.22 – 10.14% |
| P&G | 91.13% | 8.87% | 2.71% | 2.03% | 2023 | **6.74%** | 6.00 – 7.49% |
| Tesla | 99.26% | 0.74% | 4.66% | 3.49% | 2023 | **11.29%** | 8.82 – 13.77% |
| Boeing | 72.56% | 27.44% | 4.73% | 3.55% | 2023 | **7.81%** | 6.84 – 8.78% |

**The ERP is a constant, and that is the honest option rather than a shortcut.**
`EQUITY_RISK_PREMIUM = 0.0428` is Damodaran's implied ERP for the US
(pages.stern.nyu.edu/~adamodar/), pulled 2026-08-14. Two alternatives rejected:

- *Historical excess return over the existing 7-year price window.* Seven years of realised
  excess return over 2019-2026 prints double digits — that is a bull market, not a premium. A
  historical ERP needs 50+ years of history and still carries a standard error around 2pp. The
  `^GSPC` variant was already rejected in step 3a for being a price index without dividends.
- *Computing the implied ERP ourselves.* Requires aggregate S&P 500 dividends plus buybacks and
  a growth estimate. Neither EDGAR nor yfinance delivers that cleanly. Phase 7 at the earliest.

Sensitivity: `d(WACC)/d(ERP) ≈ W_e × β`, so roughly 1.0 for Apple and Microsoft, 1.55 for Tesla,
0.80 for Boeing, 0.54 for P&G. A 50bp error in the ERP moves Apple's WACC by 49bp — an order of
magnitude more than the cost-of-debt window decision below is worth.

**The cost-of-debt window question from the previous section is decided, and it turned out to be
nearly irrelevant.** `COD_START_YEAR = 2023` with `COD_FALLBACK_START_YEAR = 2018` when the short
window returns `Insufficient`. Only Apple falls back — interest expense is untaggable from
FY2024, the step 0 finding. Measured against using 2018 for everyone: Microsoft -1bp, Tesla +1bp,
P&G -7bp, Boeing -9bp. At equity weights of 73-99% the debt leg simply cannot move the result.
Worth writing down because the reasoning does not survive a leveraged company — same shape as the
argument that kept the unlever/relever chain in step 3b. `COD_Source` carries the window that
actually applied, so Apple's zero-rate-era figure stays visible instead of blending in.

**Weights on gross debt and market cap, never net debt.** Cash is added back in the equity
bridge; netting it in the weights counts it twice. Harder still: Apple, Microsoft and Tesla are
net cash, so a net-debt weight would go negative and the WACC formula would stop meaning
anything. Book debt stands in for the market value of debt — acceptable near par, wrong for
Boeing (see below).

**`(1 - t)` uses `MARGINAL_TAX_RATE`, matching the Hamada unlevering in step 3b.** Apple's 15.8%
effective rate would put two different tax rates on the same deductibility inside one model, and
would set the after-tax cost of debt 0.24pp too high.

**The beta confidence interval propagates through to `WACC_Low`/`WACC_High`.** The standard error
belongs to the *raw* beta, but the adjustment chain is affine in it —
`β_adj = k·β_raw + 0.33` with `k = 0.67·(1+(1-t)·DE_Current)/(1+(1-t)·DE_Window)` — so the error
scales by `k` and the Blume intercept carries none of it. Applying `k` twice, which the first
version did, narrows Apple's band from 8.34-10.01% to 8.63-9.73%, a third of its width, in the
direction that makes the model look more certain than it is. Only the equity leg gets a band: the
cost of debt is a median of measured values, not a regression estimate, and giving it an interval
would invent uncertainty that was never measured.

**Boeing at 7.81% is wrong and the model cannot see it.** Consensus runs 9-10%. Three causes,
none fixable from EDGAR: beta 1.108 out of a regression with R² = 0.29; cost of debt from accrued
interest expense rather than today's marginal borrowing rate, on an issuer whose bonds trade
below par; and a 27% debt weight built on book debt, which mechanically drags the average down.
Expect this to surface in Phase 5 as an overvaluation — it is an input problem, not a discounting
bug, so do not go looking in the DCF mechanics.

**P&G at 6.74% is the weakest number in the model.** Its cost of equity rests on beta 0.590,
which is Blume shrinkage applied to a regression with R² = 0.11. The raw beta of 0.386 would give
6.33% cost of equity and a 5.95% WACC. The shrinkage is defensible precisely because the estimate
is noisy, but it is an assumption doing more work than the measurement underneath it.

**Two bugs from this step, both of the type-drift kind:**
- The `erp` parameter of `wacc` was accepted and then ignored in favour of the module constant.
  Nothing raised; a scenario ERP silently produced the base case. That is exactly the failure
  that flattens Phase 3's sensitivity axis while every cell still looks like a real number.
- A refactor left `cost_debt` bound to a dict on one branch and to a float on the other. It
  crashed on all five companies but at two different lines, so the first traceback pointed at the
  fallback path rather than at the type.

#### Step 4 — the bridge from projected FCF to value per share — DONE

`terminal_value(fcf, wacc, method, exit_multiple)` and `dcf_value(symbol, start_year, years,
freq, n, base, method, exit_multiple, as_of)` in `logic/valuation.py`. This is the module step 3c
anticipated: it is the only place that imports from both `model.py` and `wacc_calculation.py`,
and the dependency between those two still runs one way only.

**The terminal value is discounted at exponent N, not N+1.** The Gordon formula
`FCF_{N+1} / (WACC - g)` already produces a value standing as of the *end* of year N, so
discounting the TV row by its own year index would lose one full year. `project_fcf` returns
`years + 1` rows and the last one carries `Flag: "TV"`, which is why the explicit loop iterates
`sorted(fcf)[:-1]` and the TV is handled separately rather than falling out of the same loop.

**`method` offers Gordon and exit multiple, but the implied multiple is always reported.**
`Implied_Multiple` is computed as `gordon_tv / EBITDA_N` regardless of which method was selected,
so the Gordon result can be sanity-checked against comparable trading multiples without a second
run. EBITDA is taken from the *last explicit* year, not the TV row, because the TV row has
`D&A` set to `None` by construction — the terminal reinvestment is a single netted figure, not
a CapEx/D&A pair.

**The equity bridge subtracts gross debt and adds cash, never net debt.** This is the same
argument as the WACC weights in step 3c: the weights are already built on gross debt, so netting
cash here would count it twice. The guard rejects `0` and `None` for `Debt`, `Cash` and
`SharesOutstanding` alike — a zero share count is a parser failure, not a company without shares.

**All three WACC scenarios re-project the FCF, they do not merely re-discount it.** Since step
2c-3 pins `terminal_roic = WACC`, changing the discount rate changes the terminal reinvestment
rate `g / ROIC` and therefore the terminal FCF. Calling `project_fcf` once outside the loop would
silently hold the base-case reinvestment while varying only the denominator, which is a different
and much narrower band than the one reported.

**Four bugs from this step, all mechanical:**
- The discount loop was nested (`for row: for i in range(1, years)`), applying every exponent to
  every cashflow — roughly a factor of ten on the explicit period. `range(1, years)` additionally
  dropped the last year, and an `i += 1` inside the `range` loop was a no-op.
- `PV_tv` was named as a present value but never divided by `(1 + WACC) ** years`. Apple came out
  at 1549.50bn instead of 655.76bn, i.e. a year-N value added to year-0 present values.
- `terminal_value = terminal_value(...)` shadowed the function. Assigning to the name makes it
  local for the entire function scope, so the read on the right-hand side failed on the *first*
  iteration with `UnboundLocalError` — the traceback points at the call, not at the shadowing.
- The `exit_multiple is None` guard sat before the method branch instead of inside the
  `"multiple"` branch, so the ordinary Gordon call with `exit_multiple=None` raised.

#### Step 4a — mechanical corrections to the bridge — DONE

Phase 5 exists to catch a 40%+ deviation from market and trace it to a cause. The first run did
that on all five companies at once (-30% to -88%), so the diagnosis was pulled forward. It splits
cleanly into corrections that are simply errors — this step — and modelling assumptions that need
a decision, which is step 4b.

Measured cumulatively, value per share at base WACC, `as_of = 2026-08-16`:

| | step 4 | + tax fade | + mid-year | + stub | + dated shares | market | delta |
|---|---|---|---|---|---|---|---|
| Apple | 105.51 | 102.33 | 106.73 | 114.98 | **116.80** | 308.64 | -62.2% |
| Microsoft | 251.20 | 243.68 | 254.16 | 279.57 | **280.78** | 464.72 | -39.6% |
| P&G | 100.41 | 98.86 | 102.45 | 111.00 | **116.66** | 144.49 | -19.3% |
| Tesla | 38.34 | 37.79 | 39.30 | 41.30 | **38.86** | 311.21 | -87.5% |
| Boeing | 71.53 | 71.53 | 75.85 | 81.48 | **78.47** | 216.14 | -63.7% |

**1. The tax rate now fades, and it fades the value down.** `project_fcf` used the effective
median for the explicit years and switched to `MARGINAL_TAX_RATE` in the TV row — a discontinuity
of 9.2pp for Apple at exactly the seam that carries 44% of the value. Resolved with
`t_t = t + (MARGINAL_TAX_RATE - t) * i/N`, the same shape already used for `g_t` and `m_t`, so
year N arrives at 25.0% and the TV row continues it rather than jumping to it. Apple's path runs
16.7 → 25.0%. Costs 1.4-3.0%, and Boeing is unaffected because `effective_tax_rate` already falls
back to the marginal rate there (`Source: "Fallback"`).

The alternative — pulling the effective rate *into* the TV instead — was rejected: it is worth
+2 to +5% but hangs 84% of Apple's value on a 15.8% tax rate holding in perpetuity, against
Pillar Two and against any plausible IP-regime change. The per-year rate is carried as `Tax_Rate`
in the output so the trajectory is auditable, same reasoning as `EBIT_Margin` in step 2c-2.

**2. Mid-year convention.** Cashflows arrive across the year, not on the last day of it, so the
exponent is `i - 0.5` and the TV discount is `years - 0.5`. Worth a uniform +4.3% on all five —
the factor is `(1+WACC)^0.5` and cancels against the WACC, so any company deviating from +4.3%
means the TV exponent was missed.

**3. The valuation date is now a parameter, not the last balance sheet date.** The model
discounted to the fiscal year end, which for Microsoft and P&G is 2025-06-30 — 1.128 years before
the market price it was being compared against. `as_of` defaults to `datetime.now()` but accepts
`"%Y-%m-%d"`, because otherwise every verification table written into this file is wrong the day
after it is written.

| | FYE | stub (years) | compounding factor |
|---|---|---|---|
| Apple | 2025-09-27 | 0.884 | 1.0790 |
| Microsoft | 2025-06-30 | 1.128 | 1.1036 |
| P&G | 2025-06-30 | 1.128 | 1.0759 |
| Tesla | 2025-12-31 | 0.624 | 1.0688 |
| Boeing | 2025-12-31 | 0.624 | 1.0478 |

Implemented as a single factor on EV rather than as `i - 0.5 - stub` in the exponent. The two are
algebraically identical, but the exponent form goes negative for Microsoft and P&G, and a
negative exponent is indistinguishable from a sign error when reading the code later. Debt and
cash are deliberately *not* rolled forward: they are point-in-time figures from the FYE, and the
cashflows generated since then are already inside `PV_Explicit` — estimating and adding the
accumulated cash on top would double-count it. Conservative, and standard.

**4. `SharesOutstanding` was a weighted average, and the bridge needs a point-in-time count.**
`WeightedAverageNumberOfDilutedSharesOutstanding` is the right denominator for EPS and the wrong
one for an equity bridge. This is the smallest lever of the four and the only one that points
*down* for two companies:

| | weighted diluted | dated | delta |
|---|---|---|---|
| Apple | 15.005 | 14.776 | -1.5% |
| Microsoft | 7.465 | 7.433 | -0.4% |
| P&G | 2.454 | 2.342 | -4.6% |
| Tesla | 3.528 | 3.752 | **+6.4%** |
| Boeing | 0.762 | 0.785 | **+3.0%** |

**`dei:EntityCommonStockSharesOutstanding` beats the us-gaap alternative on data, not on
principle.** `us-gaap:CommonStockSharesOutstanding` sits exactly on the balance sheet date, which
is the theoretically cleaner instant, but it is absent for P&G (only `CommonStockSharesIssued` =
4.009bn including treasury, against 2.34bn real) and wrong for Boeing (1.012bn, tagged identically
to Issued, against 0.785bn). Two of five unusable. The dei cover-page figure is clean for all
five and dated a few weeks *after* FYE, which for a valuation as of today is closer, not further.

**Two structural obstacles in `parser.py`, both worth knowing before touching that function
again.** First, `get_values` iterates `for sec_layer in sec_layers` as the outermost loop with
`sec_layers = ["us-gaap", "dei"]`, and the update condition `slot["Tag"] == tag` prevents any
other tag from taking a slot that is already filled. A dei tag appended to an existing tag list
is therefore *unreachable* — it needs its own slot, which is why `SharesDated` exists and
`select_shares` sits in `SLOT_SELECTORS`. Second, the year filter runs on the fact end date, and
Tesla's and Boeing's cover pages for FY2025 are dated 2026-01-23, which lands outside the data
window entirely. That one slot keys on `entry["fy"]` instead; this is admissible only because
fact and filing belong to the same 10-K, and it would be wrong globally — for us-gaap comparative
periods `fy` is the filing year, not the fact year.

**Three bugs from this step:**
- The `fy` switch was applied to the filter but not to the write, leaving `values[end.year]` two
  lines below. Filtering on one key and writing on another produced `KeyError: 2026`.
- `select_shares` returned `["SharesOutstanding"]` unconditionally when `SharesDated` was empty,
  including for pre-2010 years where neither slot is filled. `clean_values` then dereferenced
  `slots[s]["Value"]` on an empty dict. The other selectors all have an empty-list third case;
  this one needed the same.
- Before that, `select_shares` was written but never registered in `SLOT_SELECTORS`. With two
  slots the `elif len(...) == 1` branch in `clean_values` no longer fires, the metric is never
  flattened, `validate_values` flags every year as `missing`, and `insert_data` writes `None` for
  all five companies and all years. The failure surfaced three call levels away in
  `debt_to_equity`, not in the parser.

**What is left is not a discounting error.** A reverse DCF — solving for the constant revenue
growth that reproduces today's price, everything else held at the measured values — puts the
market's implied assumption at 20.2% for Apple (measured median 6.30%), 17.5% for Microsoft
(14.28%), 15.0% for Boeing (6.94%) and 49.3% for Tesla (28.31%). P&G needs 7.2% against 2.48%,
which is why it is the one case that nearly closes. Tesla at -87.5% is the model's output, not
its defect: 49% growth for a decade at a 6.3% EBIT margin is not an assumption anyone should
write down. The remaining structural gap belongs to step 4b, and tuning WACC, growth or the
terminal multiple until the market price falls out is explicitly rejected — it would discard the
only statement a DCF makes.

#### Step 4b — terminal ROIC and the growth base — DONE

**The plan this step started with was wrong, and measuring it is what showed that.** The previous
version of this entry called a measured `NOPAT / Invested Capital` the clean fix. It is not. With
`Equity` added to the parser and `IC = Debt + Equity - Cash&Investments`, `ROIC_t = NOPAT_t /
IC_{t-1}` over 2016-2025:

| | IC 2025 | IC 2016 | ROIC range | median | usable |
|---|---|---|---|---|---|
| Apple | 39.97 | **-22.30** | -3716% to +5899% | -311.5% | no |
| Microsoft | 276.66 | 12.88 | 46.7% to 188.2% | 109.1% | with reservation |
| P&G | 77.24 | 80.48 | 5.4% to 22.2% | **20.1%** | yes |
| Tesla | 46.90 | 9.15 | -14.2% to 58.3% | 12.2% | with reservation |
| Boeing | 37.32 | **0.52** | -110% to +1483% | -9.7% | no |

Apple carries *negative* invested capital in nine of ten years — buybacks pushed equity to ~57bn
while cash and investments sit above it, so the denominator is negative or near zero and the
quotient is an artefact, not a return. Boeing starts at 0.52bn IC and goes through the 737 MAX
years. Two of five unmeasurable, and they are the two with the largest gap to market. The
distinction matters for Boeing specifically: its denominator is fine from 2019 on, the *numerator*
is negative — that is a correct measurement of a company that earned nothing for six years, not a
broken ratio, and it is still useless as a terminal assumption.

**The second finding corrected an error in the step 4a diagnosis.** That entry claimed the
explicit period implies infinite ROIC. Measured as `ΔNOPAT_t / net reinvestment_{t-1}`:

| | net reinv. % revenue | implied ROIC yr 2 | implied ROIC yr 10 | WACC |
|---|---|---|---|---|
| Apple | -0.86% | -102% | -4% | 8.98% |
| Microsoft | +3.63% | 101% | 3% | 9.13% |
| P&G | -0.45% | -40% | -32% | 6.68% |
| Tesla | +0.78% | 130% | 28% | 11.23% |
| Boeing | -0.78% | -51% | -38% | 7.81% |

The explicit phase is not too generous, it is *incoherent*: reinvestment runs as a fixed share of
revenue while `ΔNOPAT` decays with the growth fade, so the implied return collapses toward year
10. Microsoft falls from 101% to 3%, below its own WACC. The terminal value at `ROIC = WACC` is
therefore not the conservative end of the model — by year 10 it is the optimistic one.

**Decision: `terminal_roic` becomes an explicit per-company parameter, and the measured ROIC is
built as a diagnostic rather than as an input.** `roic(data)` in `model.py` returns
`ROIC_Median`, `ROIC_Last`, `IC_Last`, `n` and `Source`, and reports `Insufficient` where the
capital base is not defined. `dcf_value` takes `terminal_roic` with `None` defaulting to the
scenario WACC, so every number from step 4a stays reproducible, and carries `ROIC_Source`
(`"WACC"` or `"Assumption"`) into the output.

Two alternatives rejected:

- *Coupling reinvestment to ROIC across the whole projection* (`Reinvestment_t = ΔNOPAT_t /
  ROIC`). Internally consistent, and it would fix the incoherence above at the root. It also
  discards the D&A, CapEx and dNWC driver ratios built in step 2a from ten years of filings and
  replaces three measured quantities with one assumed one. In an interview "my capex ratio is the
  ten-year median of actuals" survives a follow-up question; "I assumed a return on capital" does
  not.
- *Wiring `roic()` directly into `project_fcf`.* Apple and Boeing would hit a `None` path in the
  middle of the valuation, or a silent fallback. A visibly set number is worse in theory and
  better in practice than a fallback nobody sees.

Value per share against terminal ROIC, base WACC, `as_of = 2026-08-16`, median growth:

| | ROIC=WACC | 10% | 15% | 20% | 30% | ∞ |
|---|---|---|---|---|---|---|
| Apple | 116.80 | 118.78 | 124.55 | 127.44 | 130.33 | 136.11 |
| Microsoft | 280.78 | 285.18 | 300.63 | 308.35 | 316.08 | 331.52 |
| P&G | 116.66 | 130.18 | 139.25 | **143.79** | 148.32 | 157.39 |
| Tesla | 38.86 | 38.30 | 39.97 | 40.81 | 41.64 | 43.31 |
| Boeing | 78.47 | 84.87 | 92.50 | 96.32 | 100.13 | 107.76 |

**The coupling to WACC was also hiding a second effect in the scenario band.** While
`terminal_roic = WACC`, the low/base/high band moved the discount rate *and* the terminal
reinvestment rate at once, which is why Apple's band looked wider than discount-rate uncertainty
alone justifies. With `terminal_roic` set, the band measures what it claims to measure.

#### Step 2c-1 — the growth base, decided per company — DONE

| | median | Mean_Last_Three | mean | chosen |
|---|---|---|---|---|
| Apple | 116.80 | 100.20 | 124.02 | median |
| Microsoft | 280.78 | 264.34 | 272.85 | median |
| P&G | 116.66 | 112.88 | 118.68 | median |
| Tesla | 38.86 | **22.79** | 48.53 | Mean_Last_Three |
| Boeing | 78.47 | **104.28** | 55.26 | Mean_Last_Three |

Apple, Microsoft and P&G keep the median: the spread across the three bases is 3-15% and none of
them has a structural break inside the window. Boeing moves to `Mean_Last_Three` because its
6.94% median is drawn from a window containing the 737 MAX grounding and the pandemic — a median
across a crisis is not a statement about the normal state. Tesla moves to `Mean_Last_Three` as
well, and this **lowers** its valuation from 38.86 to 22.79: growth genuinely collapsed from 28%
to 5.6%, and 2016-2019 Tesla is not evidence about 2026 Tesla. That direction is the point. The
base is a judgment about the business, not a dial pointed at the market price, and the one case
where the honest choice hurts is the case that proves the rule.

Combined result, terminal ROIC 20% for Apple/Microsoft/P&G, 12% for Tesla, 15% for Boeing:

| | step 4a | + ROIC | + base | both | TV share | market | delta |
|---|---|---|---|---|---|---|---|
| Apple | 116.80 | 127.44 | 116.80 | **127.44** | 48.5% | 308.64 | -58.7% |
| Microsoft | 280.78 | 308.35 | 280.78 | **308.35** | 54.2% | 464.72 | -33.6% |
| P&G | 116.66 | 143.79 | 116.66 | **143.79** | 61.7% | 144.49 | **-0.5%** |
| Tesla | 38.86 | 39.14 | 22.79 | **22.91** | 47.5% | 311.21 | -92.6% |
| Boeing | 78.47 | 92.50 | 104.28 | **121.83** | 58.8% | 216.14 | -43.6% |

**The terminal ROIC per company is an assumption and has to be written down before the run, not
after.** 20% for P&G is the measured median and the only one resting on data. 20% for Apple and
Microsoft is a judgment that both defend a durable spread over their cost of capital, taken
against an unmeasurable denominator for Apple and a sharply falling series for Microsoft (188% to
46.7%). 15% for Boeing and 12% for Tesla are set below their pre-crisis levels. This parameter is
the single easiest place in the model to reverse-engineer a desired answer, which is exactly why
the numbers live here rather than in the code.

**Two risks this step creates.** The TV share rises to 48-62%; at P&G two thirds of the value now
sit beyond year 10, and hitting the market within 0.5% at that weighting is closer to coincidence
than to confirmation. And Gruppe 2 does not close the remaining gap for anyone else: even at
infinite terminal ROIC Apple reaches 136.11 against 308.64. The reverse DCF from step 4a already
named the reason — the market prices 20.2% revenue growth for a decade against a measured 6.30%.
That is no longer a modelling gap; it is the model's statement.

#### Step 4c — the EBIT margin fade target, decided per company — DONE

**The margin was the last fade target nobody had decided.** `m_t` runs from the last actual EBIT
margin to `EBIT_MARGIN`, and that was the ten-year median out of `driver_ratio` — inherited from
step 2a, where the median is the right tool for CapEx and D&A ratios, and never examined for the
margin. The TV then runs on the same number in perpetuity, so it carries the same weight as the
tax rate corrected in step 4a, at 48-62% of value.

Measured over 2016-2025, base WACC, `as_of = 2026-08-17`:

| | last actual | 10y median | mean of last three clean | clean years (n) |
|---|---|---|---|---|
| Apple | 31.97% | 28.81% | 31.10% | 2016-2025 (10) |
| Microsoft | 45.62% | 41.59% | 44.01% | 2017-2025 (9) |
| P&G | 24.26% | 22.09% | 22.81% | 2016-2018, 2021-2025 (8) |
| Tesla | 4.59% | 6.32% | 9.53% | 2017, 2019-2022, 2024, 2025 (7) |
| Boeing | 4.79% | 6.98% | 1.86% | 2016-2018, 2022, 2023 (5) |

| | `Driver_Ratio` | TV share | `Mean_Last_Three` | TV share | `Last` | TV share |
|---|---|---|---|---|---|---|
| Apple | 127.47 | 48.5% | **134.66** | 49.5% | 137.39 | 49.8% |
| Microsoft | 308.42 | 54.2% | **322.36** | 54.8% | 331.65 | 55.2% |
| P&G | 143.82 | 61.7% | **147.84** | 62.1% | 155.97 | 62.8% |
| Tesla | 22.91 | 47.5% | 28.61 | 50.2% | **19.84** | 44.8% |
| Boeing | 121.87 | 58.8% | 25.47 | 38.5% | **80.54** | 54.0% |

**A string selector, not a float.** `terminal_roic` is a float because ROIC is unmeasurable for
two of five. The margin is measurable for all five, so the choice is a selection among measured
statistics — a free float would be the single easiest place in the model to reverse-engineer the
market price, which step 4a explicitly rejected.

**`"Last"` resolves to `LAST_EBIT_MARGIN`, not to a key in `driver_ratio`.** That function's last
year is the last *clean* one, and for Boeing that is 2023 at -0.99% against a 2025 actual of 4.79%
(flagged `outlier`). A `Last` key taken from there would fade 4.79% down to -0.99% — the most
aggressive of the three options, under the label "no change". With target equal to start, `m_t`
collapses to a constant and needs no branch in the fade itself.

**`driver_ratio` now returns `Years`, and it had to start sorting.** Boeing's "last three" are
2018, 2022 and 2023; without the window in the return value the number reads as a statement about
2023-2025 and is not one. The loop ran on `for year in data` while `get_data` has no `ORDER BY` —
the median is order-invariant so this was inert, `ratios[-3:]` is not.

**Decision per company.** Apple, Microsoft and P&G take `Mean_Last_Three`: their last three clean
years are 2023-2025 in all three cases, a genuinely contiguous window, and the ten-year median
reaches back past the mix shift — Services at Apple, Azure scale at Microsoft. The margin still
fades down from the last actual, just not to the pre-shift level.

Tesla and Boeing take `Last`, and both times it **lowers** the valuation. Tesla's
`Mean_Last_Three` of 9.53% comes from 2022, 2024 and 2025 and would claim the margin more than
doubles over the fade; the median of 6.32% is also above the current 4.59%. Boeing has five clean
years and none of them is 2024 or 2025 — `Mean_Last_Three` averages 2018, 2022 and 2023 into
1.86%, the median of 6.98% assumes a return to pre-MAX profitability. `Last` is the least bad
because it at least stands on the current state. Same reasoning as the growth base in step 2c-1,
and the same direction: 22.91 → 19.84 and 121.87 → 80.54.

Combined result:

| | step 2c-1 | + margin base | chosen | market | delta |
|---|---|---|---|---|---|
| Apple | 127.44 | **134.66** | `Mean_Last_Three` | 308.64 | -56.4% |
| Microsoft | 308.35 | **322.36** | `Mean_Last_Three` | 464.72 | -30.6% |
| P&G | 143.79 | **147.84** | `Mean_Last_Three` | 144.49 | **+2.3%** |
| Tesla | 22.91 | **19.84** | `Last` | 311.21 | -93.6% |
| Boeing | 121.83 | **80.54** | `Last` | 216.14 | -62.7% |

P&G flips from -0.5% to +2.3%, which confirms the risk noted in step 2c-1: at a 62% TV share that
hit was coincidence, not confirmation. Nothing here closes the remaining gap — with every open
lever pushed to the most value-friendly defensible setting at once (margin flat, dNWC on the
delta basis, terminal ROIC 30%) Apple reaches 142.53 against 308.64, and Tesla gets *worse* at
13.53. The reverse DCF from step 4a stands.

**Three defects cleared in the same pass.** The `__main__` in `valuation.py` passed
`roic(...)["ROIC_Median"]` positionally into `exit_multiple`, where it was inert and would have
raised `TypeError` on Apple's `None` as a keyword. `"SharesDated"` sat in `OUTLIER_RULES` but is
never looked up, because `validate_values` iterates metric names and the metric is called
`SharesOutstanding` after `clean_values`. `"Equity"` was missing from the `exceptions` list, so
Boeing's correctly measured negative equity from 2019 to 2024 was flagged `negative` six times —
the cached flags in `storage/values.db` still carry it until the next ingest.

**Three items deliberately left open.**

- *The fade start is unfiltered, the fade target is not.* `LAST_EBIT_MARGIN` comes straight from
  `data[last_year]` with no flag check, while the target skips flagged years. For Boeing 2025 is
  good enough as a starting point and discarded from the statistic. Unifying them is its own step
  and not obviously right — a flag-checked start would no longer mean "where the company is".
- *`dNWC` is dimensionally wrong.* Resolved in step 4d below.
- *The same statistics now exist for D&A, CapEx and `WorkingCapital` but are not wired.* Microsoft
  is the reason to look: CapEx runs at a 11.56% ten-year median against 18.11% over the last three
  clean years — the AI build — and switching all drivers to the three-year window costs it 12.0%.

#### Step 4d — dNWC on the balance-sheet NWC level — DONE

**The open item from step 4c, closed at the parser.** `WORKING_CAPITAL_TAGS` only ever collected
the cash-flow-statement *deltas*, so the driver was a median of a change over a revenue level and
`dnwc = cur_rev * DNWC_MARGIN` multiplied it by a level again. New metric `NWC` in `parser.py`,
built from balance-sheet instants: `NWC_LEVEL_TAGS` with `Receivables`, `Inventory`, `Payables`,
`DeferredRev`, signs `+1/+1/-1/-1` in `NWC_LEVEL_SIGNS`. `project_fcf` now computes
`dnwc = (cur_rev - prev_rev) * NWC_INTENSITY`, with `prev_rev` seeded from the last actual revenue
and advanced at the end of the loop. At 2.5% terminal growth the flow now scales with the growth
increment instead of the whole revenue base.

**`select_nwc_level` sums, it does not choose.** Every other multi-slot metric picks one variant by
priority — `select_cash`, `select_debt`, `select_shares` are all "first filled slot wins". NWC is a
sum of four independent positions, so the selector returns *all* filled slots. Reusing the priority
shape here would have returned receivables alone and called it working capital.

**`WC_SIGNS` had to become a per-metric dispatch.** `clean_values` applied `WC_SIGNS.get(s, 1)` to
every multi-slot metric, not just `WorkingCapital`. That was inert only because no `Cash`, `Debt`
or `PretaxIncome` slot happens to be named `Receivables`, `Inventory`, `Payables` or
`DeferredRevenue`. A second signed metric makes the shared map a name collision waiting to happen,
so it is now `SLOT_SIGNS[metric_name]` with `{}` as the default for unsigned metrics.

Measured 2016-2025, `NWC / Revenue`:

| | median | mean last three | 2016 | 2025 | range | components found |
|---|---|---|---|---|---|---|
| Apple | -9.68% | -8.82% | -12.75% | -8.03% | -13.07 .. -8.03 | all four |
| Microsoft | -8.37% | -8.25% | -15.18% | -7.61% | -15.18 .. -7.03 | all four |
| P&G | -2.21% | -2.31% | -0.36% | -1.77% | -3.96 .. -0.36 | no `DeferredRev` |
| Tesla | -0.52% | +0.28% | -0.81% | +0.18% | -7.06 .. +0.81 | all four |
| Boeing | +22.11% | +20.92% | +43.68% | +16.86% | +2.82 .. +43.68 | all four |

**The sign is the finding.** Four of five carry *negative* working capital — payables and deferred
revenue exceed receivables and inventory — so growth releases cash rather than consuming it, and
`dNWC` is a positive contribution to FCF. Under the old formula that release was booked against the
entire revenue base every single year, in perpetuity. Boeing is the only classical case: program
inventory against customer advances, +22% of revenue.

Effect in isolation, base WACC, `as_of = 2026-08-17`, per-company settings from steps 2c-1/4b/4c:

| | old (level basis) | new (delta basis) | change | TV share old | TV share new |
|---|---|---|---|---|---|
| Apple | 133.81 | **133.97** | +0.1% | 49.2% | 49.2% |
| Microsoft | 320.22 | **315.85** | -1.4% | 54.5% | 55.3% |
| P&G | 146.35 | **143.40** | -2.0% | 61.7% | 62.9% |
| Tesla | 19.79 | **11.58** | -41.5% | 44.6% | 226.9% |
| Boeing | 79.82 | **57.77** | -27.6% | 53.8% | 65.9% |

The three low-intensity names barely move, which is the expected result: a small ratio times a
small delta against a small ratio times a large level lands in the same neighbourhood once the
growth rate is low. Tesla and Boeing move hard because their old `WorkingCapital` deltas and their
new NWC levels disagree in both magnitude and sign.

**Two definitional breaks the sum papers over.** P&G has neither `ContractWithCustomerLiabilityCurrent`
nor `DeferredRevenueCurrent`, so its NWC is a three-component figure while everyone else's has four
— the selector takes what is there and the `Tag` string is the only place this is visible. And
Boeing's inventory tag is `InventoryNetOfAllowancesCustomerAdvancesAndProgressBillings`: customer
advances are already netted *inside* the inventory line, where every other filer would carry them as
a separate liability. Boeing's +22.11% is therefore not comparable to the other four as a ratio.

**Boeing's intensity is not stationary and the median hides it.** It falls from 43.68% to 16.86%
across the window — the median of 22.11% is a statement about 2019-2020, not about the current
balance sheet. `Mean_Last_Three` at 20.92% is barely different because `driver_ratio`'s clean years
for Boeing end in 2023. Same structural problem as the EBIT margin in step 4c, and it is not yet
decided.

**New defect this exposes: Tesla's explicit period has negative present value.**

| | WACC | PV explicit | PV TV | EV | value/share | TV share |
|---|---|---|---|---|---|---|
| Tesla low | 8.81% | -9.94bn | 27.57bn | 18.59bn | 14.52 | 156.4% |
| Tesla base | 11.28% | -8.95bn | 16.01bn | 7.54bn | 11.58 | 226.9% |
| Tesla high | 13.76% | -8.11bn | 10.14bn | 2.20bn | 10.15 | 500.3% |

FCF is negative in all ten explicit years, and the cause is not `dNWC` — it is CapEx at 9.90% of
revenue against D&A at 5.08% and a flat 4.59% EBIT margin. NOPAT of ~3.6bn cannot cover a ~4.8bn
net reinvestment. That is a coherent statement about the inputs, but `TV_Share = PV_TV /
(PV_Explicit + PV_TV)` stops meaning anything once the denominator is smaller than the numerator,
and it is printed as a headline diagnostic. It needs either a guard or a different definition
before Phase 3 puts it in a sensitivity grid.

**One inert oddity left in place.** `prev_rev = cur_rev` sits after the `if i == years` block, which
has already overwritten `cur_rev` with the *terminal* revenue. Harmless because that is the last
iteration, but it reads as a bug and will become one if anything is appended to the loop.

#### Step 4e — the driver window, decided per company — DONE

**The last inherited default.** D&A, CapEx and `NWC` all took the ten-year median out of
`driver_ratio`, chosen in step 2a for its robustness against a single bad year and never examined
per driver afterwards. `project_fcf` now takes `metrics`, a dict keyed by `"D&A"`, `"CapEx"` and
`"NWC"` with `"Driver_Ratio"` or `"Mean_Last_Three"` as values; a metric that is not named falls
back to the median, so every call written before this step returns the same number. The resolved
selection travels into every explicit year row and into the scenario dict as `Metrics`, in the
order D&A, CapEx, NWC.

**A dict per driver, not one shared string.** Microsoft is the reason: the structural break sits in
CapEx alone, while its D&A and NWC are stationary. A single switch would move all three at once and
the output could no longer say why D&A changed — the same traceability `ROIC_Source` was introduced
for in step 4b. `"Last"` is deliberately not offered here: for the EBIT margin it was needed because
the margin *starts* at the last actual, but a driver ratio has no fade, so a single year would run
in perpetuity.

Measured 2016-2025. All three drivers are clean in all ten years for all five companies, so the
three-year window is 2023-2025 everywhere — the note in step 4d that `driver_ratio`'s clean years
for Boeing end in 2023 applies to `OperatingIncome`, not to these three.

| | D&A median / last three | CapEx median / last three | NWC median / last three |
|---|---|---|---|
| Apple | 3.56% / 2.91% | 3.04% / 2.78% | -9.68% / -8.82% |
| Microsoft | 6.34% / 6.40% | 11.56% / **18.11%** | -8.37% / -8.25% |
| P&G | 3.88% / 3.38% | 4.40% / 4.05% | -2.21% / -2.31% |
| Tesla | 5.08% / 4.32% | 9.90% / 9.93% | -0.52% / +0.28% |
| Boeing | 2.58% / 2.45% | 2.10% / **2.87%** | 22.11% / 20.92% |

Effect in isolation, one driver switched at a time, base WACC, `as_of = 2026-08-19`, per-company
settings from steps 2c-1/4b/4c/4d:

| | median (today) | only D&A | only CapEx | only NWC | all three |
|---|---|---|---|---|---|
| Apple | 134.03 | 132.36 | 134.70 | 133.94 | **132.93** |
| Microsoft | 316.00 | 316.27 | **286.77** | 315.96 | 287.00 |
| P&G | 143.45 | 141.84 | 144.58 | 143.46 | **142.98** |
| Tesla | 11.58 | 10.03 | 11.52 | 11.52 | 9.90 |
| Boeing | 57.81 | 56.16 | **48.01** | 58.79 | 47.33 |

**Decision per company.**

*Microsoft takes the three-year window on CapEx alone.* The ratio runs 9.15% (2016), 13.26% (2023),
18.14% (2024), 22.91% (2025) — a seven-year ramp, not an outlier, and the 11.56% median describes a
company that no longer exists. D&A (5.19% to 7.81%, no trend) and NWC (-7.0% to -10.2% since 2017)
stay on the median because nothing broke there.

*The counterargument belongs in the same paragraph:* 18.11% CapEx now sits against 6.40% D&A for
all ten explicit years, so the model asserts that the AI build-out intensity is permanent. There is
no fade for driver ratios, so "elevated now, normalising later" cannot be expressed at all — that is
the honest limit of this decision, and the main reason Microsoft's -38.3% gap to market should not
be read as a precise number.

*Boeing takes the three-year window on CapEx as well*, 2.10% median against 3.35% (2024) and 3.29%
(2025). The evidence is thinner than Microsoft's — two years, not seven — and the effect is the
largest single move in the whole comparison at -17.0%. It is taken anyway because the alternative is
a 2.10% median drawn from the grounding and pandemic years, when Boeing was not investing.

*Boeing keeps the median on NWC, and the window does not fix the problem.* The ratio runs 43.68,
4.30, 2.82, 16.70, 34.83, 30.86, 26.10, 18.12, 27.79, 16.86 percent — it oscillates, it does not
drift, and neither 22.11% (median) nor 20.92% (last three) is a statement about the current balance
sheet. Choosing between them would dress up a driver that is not stationary; it stays on the median
and becomes a sensitivity axis in Phase 3.

*Apple and P&G take the three-year window on all three drivers.* Both have falling D&A and CapEx
ratios (Apple 4.87% to 2.81% and 5.91% to 3.06%; P&G 4.71% to 3.38% and 5.08% to 4.48%), the last
three clean years are contiguous 2023-2025, and the choice is consistent with their margin base from
step 4c. It decides nothing either way: every combination lands within 1.5%.

*Tesla stays on the median for all three.* Its D&A ratio falls from 6.82% to 2.97% (2022) and rises
back to 5.30% (2025); the three-year window would catch half of that rebound and sell it as a level,
costing -13.4% on no structural argument. CapEx is flat across both windows and NWC hovers around
zero.

Combined result, base WACC, `as_of = 2026-08-19`:

| | step 4d | + driver window | `Metrics` (D&A/CapEx/NWC) | TV share | market | delta |
|---|---|---|---|---|---|---|
| Apple | 134.03 | **132.93** | m3 / m3 / m3 | 49.6% | 308.64 | -56.9% |
| Microsoft | 316.00 | **286.77** | med / m3 / med | 61.1% | 464.72 | -38.3% |
| P&G | 143.45 | **142.98** | m3 / m3 / m3 | 63.1% | 144.49 | -1.0% |
| Tesla | 11.58 | **11.58** | med / med / med | 226.9% | 311.21 | -96.3% |
| Boeing | 57.81 | **48.01** | med / m3 / med | 73.2% | 216.14 | -77.8% |

Market prices are the last cached monthly close, 2026-07-31 — the price side is not yet pinned to
`as_of`, see the status block below.

**Every decision in this step lowered the valuation or left it flat**, and P&G's -1.0% moves it from
+2.3% back through the market price. Third step in a row where the defensible choice is the lower
one, and it is worth stating plainly: the model says all five names are expensive, and the two where
the gap is smallest (P&G, Microsoft) are the two carrying 61-63% of their value beyond year 10.

**Two things this step does not settle.** Microsoft's CapEx has no fade path, as above. And Boeing's
TV share rises to 73.2%, because the higher CapEx ratio pushes its explicit period toward zero — the
same failure mode as Tesla, one step earlier in its development.

#### Step 5 — the `TV_Share` guard — DONE

**A ratio that was never a share.** `TV_Share` divides `PV_TV` by `PV_Explicit + PV_TV` and was
emitted unconditionally, so Tesla carried 226.9% into every table. `dcf_value` now computes it only
when `PV_Explicit` and `PV_tv` are both positive; otherwise it stays `None` and `TV_Share_Source`
names the side that failed, built from the same two conditions rather than enumerated per case.
`PV_Explicit` is no longer overwritten with `None` — the previous guard nulled the one number in
that block that was correctly measured.

**Why both sides are tested, not the denominator.** Tesla's base case is -8.95 + 16.01 = 7.06 bn,
a positive denominator. A check on the sum alone passes exactly the case that produced the 226.9%.

Base WACC, `as_of = 2026-08-19`, `start_year = 2016`, settings from `ASSUMPTIONS`. Billions USD:

| | PV_Explicit | PV_TV | TV_Share | TV_Share_Source | Value_Per_Share |
|---|---|---|---|---|---|
| Apple | 900.92 | 886.30 | 49.6% | Calculated | 132.93 |
| Microsoft | 726.09 | 1142.55 | 61.1% | Calculated | 286.77 |
| P&G | 123.22 | 210.98 | 63.1% | Calculated | 142.98 |
| Tesla | **-8.95** | 16.01 | **None** | **PV_Explicit <= 0** | 11.58 |
| Boeing | 17.79 | 48.53 | 73.2% | Calculated | 48.01 |

No valuation moved. `EV`, `Equity_Value` and `Value_Per_Share` are untouched by the guard, because
`TV_Share` is a diagnostic and not an input to the equity bridge — nulling Tesla's valuation over an
undefined diagnostic would have removed the most informative result in the set from every table.

**The number was not merely above 100%, it was diverging.** Across the WACC band Tesla's
`PV_Explicit` runs -9.94 / -8.95 / -8.11 and the old `TV_Share` ran 156.4% / 226.9% / 500.3%: the
denominator approaches zero as the discount rate rises, so the quantity has no bounded
interpretation at all. This matters for Phase 3, where the same function is swept over a WACC by
terminal-growth grid — without the guard a band of cells would have shown large finite numbers with
no meaning, and `TV_Share_Source` is what tells you per cell whether the explicit period or the
terminal value is the side that broke.

**What this does not fix.** Tesla's negative explicit PV is a statement of the model, not a defect:
at the last actual EBIT margin and the 4b terminal ROIC of 12%, ten years of reinvestment consume
more than NOPAT produces. The guard makes that visible instead of dressing it up as a share. The
`PV_TV <= 0` branch is unreachable for the current five — all carry positive EBIT margin targets —
and exists for a loss-making company under `margin_base = "Last"`, and to keep the division from
raising on an exactly zero denominator.

#### Step 6a — prices pinned to `as_of` — DONE

**The second of the two vintage leaks is closed.** `get_prices` takes `as_of` and bounds the window
with `date <= ?`, the same shape `get_rate` already used. The parameter is threaded through
`raw_beta` (both the stock and the market call, so the date-alignment check cannot pair different
days), `debt_to_equity`, `adjusted_beta` (including the December-year list that builds `DE_Window`)
and `calc_wacc`, which now owns the single `None` → today normalisation — `date <= NULL` returns no
rows rather than raising, so no downstream function may be handed `None`.

**No number moved, and that is the test.** The newest cached monthly close is 2026-07-31, below the
2026-08-19 stichtag, so the bound selects exactly the rows the unbounded query returned. Measured
before and after, base WACC, `start_year = 2016`, settings from `ASSUMPTIONS`:

| | Beta (adj.) | DE_Window | DE_Current | WACC | Value_Per_Share |
|---|---|---|---|---|---|
| Apple | 1.0506 | 0.0387 | 0.0216 | 9.025% | 132.93 |
| Microsoft | 1.0677 | 0.0197 | 0.0125 | 9.182% | 286.77 |
| P&G | 0.5895 | 0.0972 | 0.1020 | 6.724% | 142.98 |
| Tesla | 1.5558 | 0.0073 | 0.0070 | 11.284% | 11.58 |
| Boeing | 1.1098 | 0.4375 | 0.3671 | 7.850% | 48.01 |

That the bound actually binds is shown separately: `get_prices("apple", "1mo", 61, "2024-06-30")`
raises, and with `n = 36` returns the series ending 2024-06-30 at 208.63.

**Backward pinning does not work yet, and the cache is why.** `fetch_prices` truncates to
`N_MONTHS` before `insert_prices`, so each symbol holds exactly 61 monthly rows, 2021-07-31 to
2026-07-31. Any `as_of` more than a few months back starves the 61-month beta window and hits the
`Too few prices` raise. The interface is correct; the stored history is not deep enough to use it.
Widening it means keeping the full `PERIOD` download instead of the truncated slice.

**The bound is one-sided.** `get_prices` never fetches. If the cache ends well before `as_of`, the
valuation runs on stale prices without complaint — unlike the rate path, which `RF_MAX_AGE_DAYS`
guards. The asymmetry is deliberate for now, not resolved.

#### Step 6b — the filing vintage, recorded — DONE

**The database now knows which filing a number came from.** The parser has carried `Filed` per fact
since step 0 and threw it away at the database boundary. `clean_values` now also sets `Filed` for
the composed metrics, as the maximum over the slots the selector chose — a summed figure is only as
current as its newest component, so `min` or the first slot would understate its age. `data` gained
a `filed` column, `insert_data` writes it in both branches and in the `DO UPDATE SET`, `get_data`
returns it as `Filed`, and `dcf_value` reduces it to `Data_Filed`: the newest filing across every
year and metric the valuation stands on, `None` when nothing carries a date.

**Migrated with `ALTER TABLE`, not by rebuilding.** `CREATE TABLE IF NOT EXISTS` never alters an
existing table, so deleting `values.db` is the obvious shortcut and the wrong one — the same file
holds `prices`, `rates` and `raw_downloads`, and since `fetch_prices` truncates to `N_MONTHS` before
the insert, the 61-month price history that step 6a pins against would not come back from a
re-download either.

**Nothing moved, which is the point.** The re-ingest reads the JSONs in `storage/` from 2026-08-18,
the same source the previous database was built from:

| | Data_Filed | rows with `filed` | Value_Per_Share |
|---|---|---|---|
| Apple | 2025-10-31 | 237 | 132.93 |
| Microsoft | 2026-07-29 | 233 | 286.77 |
| P&G | 2026-08-04 | 232 | 142.98 |
| Tesla | 2026-01-29 | 219 | 11.58 |
| Boeing | 2026-01-30 | 246 | 48.01 |

1167 of 1850 rows carry a date; the rest are metrics flagged `missing`, which keep NULL rather than
a substituted one.

**Two things the column made visible immediately.** P&G's newest filing is 2026-08-04, four days
before the ingest that shifted the step 4d numbers — the same class of event, now dated instead of
reconstructed. And Microsoft's fiscal 2025 figures carry `filed = 2026-07-29`, so they come from the
FY2026 10-K's comparatives, not from the original FY2025 report. That is newest-filing-wins working
exactly as written in `parser.py`, and it was invisible until now.

**This labels the vintage, it does not pin it.** Nothing filters filings by `as_of`; a valuation can
state which filing it stands on but still cannot reproduce an earlier one. Doing that means moving
the selection out of `parser.py` into read time, keyed on `accn`, and re-running the ingest — the
SEC companyfacts response carries every vintage with its `filed` date, so the history is
recoverable, it is simply not kept. Deliberately deferred past Phase 2: it costs more than every
step so far and improves no valuation, it only protects future comparisons.

#### Phase 2 — status

Steps 0 through 6b are done. What is left before the phase closes:

- **The Damodaran cross-check named in the learning goals has not been done.** WACC, terminal value
  and the equity bridge were each derived and verified internally; none of them has been held
  against an external reference. This is the explicit exit condition of the phase.
- **The filing vintage is labelled but not pinned.** All three vintage leaks are now visible: the
  rate is served from the `rates` table under `as_of`, prices are bounded by `date <= as_of` (step
  6a), and every valuation reports the newest filing it stands on as `Data_Filed` (step 6b). Only
  the filings remain unpinned — `parser.py` still resolves newest-filing-wins at write time with no
  `as_of` bound, so a re-ingest can still move a past number. The measured case: the 2026-08-18
  re-ingest picked up restated balance-sheet figures and moved the equity weights — Boeing 72.56% →
  73.15%, P&G 91.13% → 90.75%, Apple 97.91% → 97.88%, Tesla 99.26% → 99.31%, Microsoft unchanged —
  taking Boeing's WACC 7.81% → 7.85% and its value per share 80.54 → 79.82. Full point-in-time is
  scoped and deferred past Phase 2 (step 6b).
- **The exit-multiple path is built and never used.** `terminal_value(method="multiple")` requires
  an `exit_multiple` the caller must supply, and no comparable-multiple source exists. Phase 2's
  scope says "offer both". Either wire a source or write down that Gordon is the only supported
  method and why.
- **The per-company settings are wired but not enforced.** `ASSUMPTIONS` in `valuation.py` now
  carries growth base, `terminal_roic`, `margin_base` and `metrics` for all five companies, and
  `__main__` unpacks it against `start_year = 2016` and an explicit `as_of`. What is missing is the
  link back to this file: nothing checks the dict against the tables in steps 2c-1, 4b, 4c and 4e,
  and `dcf_value`'s own defaults still describe the pre-4c model (`margin_base = "Driver_Ratio"`,
  `terminal_roic = None` falling back to WACC). A call that forgets to unpack `ASSUMPTIONS` returns
  a number that looks valid and is not the decided basis.
- **The cached price history is 61 monthly rows deep**, so `as_of` cannot be moved back more than a
  few months without starving the beta window (step 6a). `fetch_prices` truncates to `N_MONTHS`
  before the insert; keeping the full `PERIOD` download would fix it.
- **Prices have no staleness bound**, unlike the rate path with `RF_MAX_AGE_DAYS` (step 6a).
- **The rate-pinning work has no step section in this file.** `database.py`'s `rates` table,
  `get_rate`, `risk_free_rate(as_of)` and the `RF_MAX_AGE_DAYS` bound were built and committed
  without a write-up, so the only record of why the staleness bound is ten days is the code.
- **The fade start is unfiltered, the fade target is not** (step 4c, still open).
- **Boeing's NWC intensity is not stationary** (step 4d; step 4e could not fix it with a window
  choice, so it becomes a Phase 3 sensitivity axis).

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
