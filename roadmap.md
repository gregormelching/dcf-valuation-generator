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

### Phase 2 — Modeling core (3–4 days) — DONE
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

#### Step 3a-1 — the risk-free rate pinned to `as_of` — DONE

Built during the step 6a work and committed without a write-up (`c5011c3`); recorded here because
it belongs topically to step 3a, not to the price pinning.

**The rate is cached, not fetched per valuation.** `fetch_rates` pulls the full FRED `DGS10` series
(16,140 rows back to 1962-01-02) and writes it into a `rates` table keyed `UNIQUE(series, date)`
with a `fetched_at` column. `get_rate(series, as_of)` returns the newest row with `date <= as_of`,
the same shape `get_prices` later adopted. Without the cache every valuation hit FRED, and a rerun
of the same `as_of` could return a different number.

**Why `date <= as_of` and not the exact date.** `DGS10` has no row on weekends and holidays. An
exact-date lookup fails on roughly three days in ten, and the failure is not informative — the rate
simply was not published that day.

**`RF_MAX_AGE_DAYS = 10` is the staleness bound.** `risk_free_rate` computes the gap between
`as_of` and the returned row's date; if it exceeds ten days it refetches once, and if it still
exceeds ten days it raises rather than returning the stale number. Ten days covers the longest
gap the series actually produces — a weekend plus a holiday plus a missing print — while still
catching the real failure case, which is a cache that has not been refreshed in months. Measured
sensitivity at `as_of = 2026-08-19`: the rate moves 4.75% (2026-07-31) to 4.68% (2026-08-14), which
takes Boeing's WACC 7.90% to 7.85% and Apple's 9.09% to 9.03%. Three weeks of drift is worth about
5bp of WACC — small enough that a bound is a guard against neglect, large enough that silently
serving a year-old rate would not be acceptable.

**The refetch is unconditional on the miss, not incremental.** `fetch_rates` rewrites all 16,140
rows on every refresh. At this size that is cheaper than tracking a watermark, and it means a FRED
revision to a historical print propagates instead of being pinned to whatever was first cached.

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

#### Step 7 — the terminal value method, decided — DONE

Phase 2's scope line says "Terminal value (Gordon Growth vs. exit multiple, offer both)". This
records the decision not to deliver the second one, and why that is not a shortcut.

**Gordon Growth is the only supported method.** `terminal_value(method="multiple")` stays in the
code and stays reachable, but only when the caller supplies `exit_multiple` explicitly. No default
is provided and no comparable-multiple source is wired.

**There is no honest source for the multiple in this stack.** SEC EDGAR carries filings, not peer
market data — an exit multiple needs a peer set, each peer's enterprise value and each peer's
EBITDA on a comparable basis. yfinance could supply a per-ticker EV/EBITDA, but the peer set itself
would be a hand-picked judgment call sitting nowhere in this file, which is exactly the pattern the
project rules forbid. The alternative, a hardcoded constant, is not a second method at all: it is
the same terminal assumption with a different label and a worse audit trail, because Gordon at
least exposes `TERMINAL_GROWTH` and the terminal ROIC as named inputs that steps 4b and 5 argued
for.

**The deeper objection is circularity.** An exit multiple taken from today's market prices the
terminal year at today's sentiment. Phase 5 then compares the model's value per share against the
market price to look for a 40%+ deviation. A terminal value imported from the market cannot fail
that test in an informative way — the model would be checking the market against itself.

**`Implied_Multiple` is the inverse, and it is already built.** Rather than importing a multiple,
`terminal_value` reports what the Gordon terminal value implies against the last explicit year's
EBITDA (`EBIT + D&A` of year 10). That is the cross-check an interviewer actually asks for, and it
runs in every valuation without a peer set. Measured at `as_of = 2026-08-19`, `start_year = 2016`,
settings from `ASSUMPTIONS`, across the WACC band:

| | WACC low | WACC base | WACC high | base WACC |
|---|---|---|---|---|
| Apple | 10.77x | 9.43x | 8.38x | 9.03% |
| Microsoft | 10.28x | 8.80x | 7.69x | 9.18% |
| P&G | 16.80x | 13.87x | 11.81x | 6.72% |
| Boeing | 9.53x | 7.78x | 6.57x | 7.85% |
| Tesla | 4.58x | 3.29x | 2.57x | 11.28% |

**The ordering is right, the level is the open question.** P&G highest at the lowest WACC, Tesla
lowest because a 4.59% EBIT margin produces little EBITDA to capitalise — both are what the inputs
say. What has not been checked is whether 8-10x on Apple and Microsoft is defensible against where
comparable large-cap names actually trade. If the market clears materially higher, the model is
either conservative on the margin fade or the terminal growth of 2.5% is doing too little work, and
`Implied_Multiple` is the number that surfaces it. **This is carried into the Damodaran cross-check
as an explicit item**, not closed here — the cache holds no market multiples to test it against.

#### Step 8 — the Damodaran cross-check — DONE

The explicit exit condition of Phase 2. Every WACC component, the terminal multiple and the returns
assumptions are now held against an external reference instead of only against each other.

**The script sits in the root, not in `logic/`.** `2026-08-20-damodaran-check.py` imports from
`logic/` and writes nothing back. It is a report, not a model input: no function in `logic/` reads
`DAMODARAN`, and nothing in the valuation path changes because a row prints `GAP`. Keeping it
outside the package is what guarantees that — the check can never quietly become an assumption.

**The reference is pinned, both value and vintage.** `DAMODARAN` holds one row per company from the
US industry datasets, `REFERENCE_VINTAGE = "January 2026"`, `REFERENCE_PULLED = "2026-08-20"`, plus
`REFERENCE_SOURCES` with the six URLs the rows came from. Industry mapping: Apple →
Computers/Peripherals (36 firms), Microsoft → Software System & Application (309), P&G → Household
Products (110), Boeing → Aerospace/Defense (79), Tesla → Auto & Truck (33). `IMPLIED_ERP` carries
4.46% as of 2026-01-05 against our `EQUITY_RISK_PREMIUM = 0.0428` pulled 2026-08-14 — the same
series at two dates, so the 18bp is a vintage difference and not a disagreement.

**The synthetic rating is computed, not copied.** `SPREADS` is Damodaran's full interest-coverage
table for large caps; `interest_coverage` takes the newest year whose `OperatingIncome` and
`InterestExpense` both survive the flag filter (yoy outliers removed, same rule as `cost_of_debt`),
`synthetic_rating` maps it to a rating and `synthetic_cost_of_debt` returns `rf + spread`. That is
the only row where the reference is a per-company figure rather than a sector average, and it is the
one that found something.

**Tolerances are declared in `METRICS`, per row**: 0.30 on both betas, 10pp on D/E and E/(D+E),
200bp on cost of equity, cost of debt and WACC, 10pp on the effective tax rate, 15pp on ROIC, and 50%
relative on the multiple. They are wide on purpose — the reference is a sector aggregate, so a
narrow band would print `GAP` on every row and mean nothing. `NOTES` records the five
non-comparabilities in the output itself.

Measured at `as_of = 2026-08-19`, `start_year = 2016`, settings from `ASSUMPTIONS`:

| | beta ours/ref | Ke ours/ref | WACC ours/ref | ΔWACC | EV/EBITDA ours/ref |
|---|---|---|---|---|---|
| Apple | 1.051 / 1.35 | 9.18% / 9.97% | 9.03% / 9.71% | -68bp | 9.43x / 25.42x |
| Microsoft | 1.068 / 1.28 | 9.25% / 9.64% | 9.18% / 9.34% | -16bp | 8.80x / 24.48x |
| P&G | 0.589 / 0.82 | 7.20% / 7.59% | 6.72% / 7.03% | -31bp | 13.87x / 13.17x |
| Boeing | 1.110 / 0.95 | 9.43% / 8.17% | 7.85% / 7.60% | +25bp | 7.78x / 21.58x |
| Tesla | 1.556 / 1.46 | 11.34% / 10.45% | 11.28% / 9.38% | +190bp | 3.29x / 47.76x |

**The WACC machinery survives the check.** Four of five land within 70bp of the sector cost of
capital, and Tesla's +190bp is the beta doing exactly what CAPM says it should. This is the first
evidence that the CAPM path, the relevering and the weights are right rather than merely internally
consistent — every earlier verification compared the model against itself.

**Finding 1: the cost of debt is a legacy coupon, not a marginal rate.** Apple 2.71% and P&G 2.71%
against a synthetic AAA of 5.08% at coverage of 29.06x and 22.55x — both 237bp low. Microsoft
(+5bp) and Tesla (+42bp) agree, so this is not a broken function; it is a definitional gap.
`cost_of_debt` measures interest expense over average debt, i.e. what the existing stack costs,
while a forward-looking WACC wants what new debt would cost. Arithmetic on the printed weights, not
re-run: switching to the synthetic rate moves Apple +4bp, P&G +16bp, Boeing (at a BBB spread of
1.11%) +21bp. **Decide the basis or defer it explicitly; do not leave it undecided a second time
like the window question in step 3a.**

**Finding 2: Boeing's cost of debt is measured off a stale, unusable year.** The newest year with
both figures clean is 2023, and its EBIT is negative, so coverage is -0.31x → D2/D → a synthetic
23.68%. The number itself is nonsense as a forward rate, but the signal is not: Boeing carries the
highest debt weight of the five (26.85%) and is the one company whose cost of debt the model has no
usable evidence for. Its 4.73% is the least defensible input in the whole set.

**Finding 3: the terminal multiple gap is real and is not explained by the fade argument alone.**
Step 7 left this open. Apple 9.43x against 25.42x and Microsoft 8.80x against 24.48x are not
"somewhat below" a current market multiple, they are a third of it. Part of that is structural — the
Gordon terminal value prices a business already faded to 2.5% growth ten years out, so it must sit
below a trailing multiple on a still-growing company. But a factor of 2.5x is more than the fade
buys. P&G is the control case: at 13.87x against 13.17x it agrees almost exactly, and P&G is the
one company already close to mature. Tesla at 3.29x against 47.76x is the same effect at the
extreme, plus a 4.59% EBIT margin producing little EBITDA. **Read: the model is materially more
conservative than the market on companies still growing, and the terminal assumptions are where
that lives.** This is the input for the Phase 3 sensitivity axes, and the honest framing for Phase 5
— a 40%+ deviation from market price is close to guaranteed for Apple and Microsoft, and it will be
the terminal block producing it, not the explicit window.

**Rows that print `GAP` and should be ignored.** The effective tax rate on every company (the
reference averages loss-makers into the sector rate — 5.91% for Computers/Peripherals is not a
number any profitable large cap could match; `MARGINAL_TAX_RATE = 25%` is the comparable figure).
Boeing's D/E and E/(D+E) at 36.71% against 15.56% (a single distressed balance sheet against a
sector average). Tesla's unlevered beta at 1.820 against 1.310 (our 0.70% D/E barely unlevers, the
sector's 19.70% does). P&G's unlevered beta at 0.360 against 0.740, the same effect with the sign
reversed. Boeing's ROIC of -9.72% is a fact about Boeing, not about the function.

**One row could not be checked at all.** Apple's `ROIC_Median` returns `Insufficient` — invested
capital goes non-positive in the window, so the median is never formed and the script prints `n/a`
rather than a substitute. The terminal ROIC of 20% assumed for Apple therefore still stands on the
step 4b argument alone and has no measured company-level counterpart; the sector's 44.76% is the
only external anchor, and it is above the assumption, i.e. the assumption is the conservative side.

#### Phase 2 — CLOSED

Steps 0 through 8 are done, including the Damodaran cross-check that was the phase's stated exit
condition. The phase is closed as of 2026-08-20.

**The closing test was not "nothing is left open" — it was "nothing left open is structural."** Every
residual below is a numeric-value question with a measured size in basis points. None of them
changes a function signature, a return shape, or a dict key, so re-opening one later costs the same
as doing it now. That is the whole justification for moving on, and it is the reason the two items
that *were* structural (point-in-time filings, the exit multiple) were decided rather than deferred:
step 6b scoped and rejected the first, step 7 closed the second.

**Carried forward out of Phase 2, with a deadline.** All of these must be closed — resolved or
explicitly rejected in writing — **before Phase 4**, because a dashboard freezes the output format
and makes changes to `logic/` visible in a way that turns cheap edits expensive:

1. **CLOSED (step 14) — realised versus marginal cost of debt** (step 8, finding 1). Apple +4bp, P&G +16bp, Boeing
   +21bp on WACC if switched to the synthetic rate, arithmetic on the printed weights. Either wire
   `synthetic_cost_of_debt` into `wacc_calculation.py` as the basis, or record that the realised
   rate stays and why.
2. **CLOSED (step 15) — Boeing's cost of debt has no usable evidence** (step 8, finding 2). The
   year selection read 2023 (coverage -0.31x, D2/D) past the newest reading, and the fallback stood
   on the legacy coupon. Both fixed; Boeing 4.73% → 5.76%, WACC +21bp, value per share 48.42 → 44.68.
3. **CLOSED (step 16) — prices have no staleness bound** (below). `PRICE_MAX_AGE_DAYS` bounds both
   price reads, both dates are reported, and the bound is pinned by a test. The measured finding was
   not the stale price but the two prices: the weights stand on a 19-day-old close, the reference
   price on a 5-day-old one.
4. **CLOSED (step 17) — the fade start is unfiltered** (step 4c). Filtering it was measured and
   rejected: Boeing's last clean `OperatingIncome` year is 2023 at -0.99%, and because its
   `margin_base` is `Last` the filtered start drags the target with it, taking value per share
   44.68 → -84.60. The start is now reported instead — `EBIT_Margin_Start`, `Margin_Start_Year` and
   `Margin_Start_Source`, the last of which reads `Last_Actual_Flagged` for Boeing alone.

**The list is empty as of 2026-08-28.** All four are resolved in code and pinned by tests, none by
deferral. Phase 4 is unblocked by this list; what remains open before it is named in the block
directly above Phase 4.

- **CLOSED — the Damodaran cross-check** (step 8). WACC within 70bp of the sector cost of capital
  for four of five companies, ERP within 18bp of the same source at a different date, and three
  findings carried forward: the cost-of-debt basis, Boeing's unusable cost of debt, and the
  terminal multiple gap (into Phase 3).
- **The filing vintage is labelled but not pinned.** All three vintage leaks are now visible: the
  rate is served from the `rates` table under `as_of`, prices are bounded by `date <= as_of` (step
  6a), and every valuation reports the newest filing it stands on as `Data_Filed` (step 6b). Only
  the filings remain unpinned — `parser.py` still resolves newest-filing-wins at write time with no
  `as_of` bound, so a re-ingest can still move a past number. The measured case: the 2026-08-18
  re-ingest picked up restated balance-sheet figures and moved the equity weights — Boeing 72.56% →
  73.15%, P&G 91.13% → 90.75%, Apple 97.91% → 97.88%, Tesla 99.26% → 99.31%, Microsoft unchanged —
  taking Boeing's WACC 7.81% → 7.85% and its value per share 80.54 → 79.82. Full point-in-time is
  scoped and deferred past Phase 2 (step 6b).
- **CLOSED — Gordon is the only supported terminal value method** (step 7). No comparable-multiple
  source is wired, the reasoning is on record, and `Implied_Multiple` carries the cross-check
  instead. One item moves from here into the Damodaran step: whether the implied 8-10x on Apple and
  Microsoft is defensible against where those names actually trade.
- **CLOSED — the per-company settings are enforced.** Measured cost of the old hole, kept on record:
  calling `dcf_value` without `**ASSUMPTIONS[symbol]` returned Apple 116.48 against 132.93, P&G
  112.98 against 142.98, Boeing 64.17 against 48.01, Microsoft 275.16 against 286.77, and Tesla
  23.13 against 11.58 — a doubling, with no exception raised anywhere. `resolve_assumptions(symbol,
  base, terminal_roic, margin_base, metrics)` in `valuation.py` now copies the company entry,
  applies only the non-`None` overrides, copies the nested `metrics` dict afterwards so a caller
  cannot mutate `ASSUMPTIONS`, and validates the four value domains before returning. `dcf_value`
  calls it as its first statement and its four settings parameters default to `None`. Verified at
  `as_of = 2026-08-19` with no settings argument: Apple 132.93, Microsoft 286.77, P&G 142.98, Tesla
  11.58, Boeing 48.01 — the step 5 table reproduces exactly. Override path verified too:
  `margin_base = "Mean_Last_Three"` takes Tesla to 20.30 at an EBIT margin target of 9.53%.
  Rejected as expected: unknown symbol, `base = "Mean"`, `metrics = {"NWC": "Last"}` (value),
  `metrics = {"Foo": ...}` (key), `terminal_roic = 0.01` (below terminal growth).
  Two consequences worth knowing. `None` as "no override" makes `terminal_roic = None` unable to
  request the WACC fallback in `dcf_value`, so that branch is now unreachable for the five —
  acceptable because step 4b gave all of them an explicit ROIC; measured cost of that path for
  Apple would be 121.68 against 132.93. And `resolve_assumptions` validates domains, not decisions:
  it cannot check the values against the tables in steps 2c-1, 4b, 4c and 4e. `ASSUMPTIONS` staying
  the single source is the only guard against drift.
- **CLOSED — the price cache carries real `as_of` headroom.** The earlier note here said `as_of` could not move back
  "more than a few months". Measured, the headroom was zero: with exactly 61 monthly rows
  (2021-07-31 to 2026-07-31) `as_of = 2026-07-31` ran and `2026-07-30` already raised `Too few
  prices`. The two `closes.iloc[-N:]` lines are gone from `fetch_prices`, so the full
  `PERIOD = "7y"` download reaches `insert_prices` and `get_prices` does the cutting via `LIMIT`.
  Rerun for all six symbols in both frequencies: 84 monthly rows from 2019-08-31 and 365 weekly rows
  from 2019-08-23, against 61 and 105 before. `as_of` now carries back to 2024-08-31 on the monthly
  path, which is what `raw_beta` and `debt_to_equity` need, and the weekly path has the depth Phase
  3 wants for the robustness check against the monthly beta.
- **Prices have no staleness bound**, unlike the rate path with `RF_MAX_AGE_DAYS` (step 3a-1). The
  gap is live, not hypothetical: at `as_of = 2026-08-19` the newest close for all six symbols is
  2026-07-31, 19 days old, while the rate is held to ten — the valuation mixes an 2026-08-14 rate
  with a 2026-07-31 market cap and reports neither fact. Measured size before spending time on it:
  a full month of price staleness moves the equity weight by at most 30bp (Microsoft -29.9bp at a
  +24.6% monthly move, Tesla +17.9bp at -26.0%, Boeing +3.0bp), because the weights sit at 73-99%
  equity and barely respond. The value is closing the last hole in the vintage chain, not accuracy.
  The bound must be wider than the rate's ten days — monthly data needs roughly 45. Taken up in
  step 16, where the measured finding turned out to be the two prices, not the one stale price.
- **CLOSED — `prev_rev` in `project_fcf`** (step 4d). The assignment now sits immediately before the
  `if i == years` block, so it no longer picks up the terminal revenue. Worth keeping on record
  because the first attempt moved it one level in rather than one line up, which put it inside
  `if i == years`: every projected year then measured its revenue delta against the last actual
  year, `dNWC` compounded to -2.17 / -4.33 / -6.44 / -8.51 / -10.50bn at Apple, and value per share
  went Apple 132.93 to 136.75, Microsoft 286.77 to 298.08, Tesla 11.58 to 11.74, P&G 142.98 to
  143.67 and **Boeing 48.01 to -29.90**, a sign flip. Apple's `dNWC` now runs -2.17 / -2.15 / -2.12
  / -2.06 / -1.99bn and all five values reproduce the step 5 table.
- **CLOSED (step 17) — the fade start is unfiltered** (step 4c). Reported, not filtered; the
  filtered variant costs Boeing 129 per share in the wrong direction. `Last` as a `margin_base`
  leaves both ends of the fade unfiltered, which is now visible in the output.
- **Boeing's NWC intensity is not stationary** (step 4d; step 4e could not fix it with a window
  choice, so it becomes a Phase 3 sensitivity axis).

### Phase order from here — 3, 5, 6, 4, 7

Decided 2026-08-20, replacing the original numeric order. The numbering of the phases below stays
as written; only the sequence changes.

- **3 before 5, but 5 immediately after.** The football field needs the current market price as a
  reference bar anyway, and the prices are already in the cache — so Phase 5's core question falls
  out of Phase 3 at almost no extra cost. Step 8 already tells us what it will say: Apple and
  Microsoft will land far below market, and the terminal block will be the cause. The sensitivity
  is what distinguishes "reachable with plausible inputs" (adjust the assumption) from "only
  reachable with implausible ones" (a model statement worth defending).
- **6 before 4.** Step 4d is the argument: one line indented one level too far took Boeing from
  48.01 to -29.90, a sign flip, and it surfaced only through manual recomputation. Phase 3 iterates
  over `project_fcf` and `dcf_value` constantly — the two functions involved. Five golden-value
  tests at a fixed `as_of` (Apple 132.93, Microsoft 286.77, P&G 142.98, Tesla 11.58, Boeing 48.01)
  would have caught it on the spot.
- **4 last before the documentation.** A dashboard freezes the output format; if Phase 5 overturns
  an assumption, the presentation gets built twice. This is also the deadline for the four items
  carried out of Phase 2.

#### Step 9 — the golden-value tests — DONE

A slice of Phase 6 pulled forward, ahead of Phase 3. The argument is step 4d: one line indented one
level too far took Boeing from 48.01 to -29.90, a sign flip, and nothing raised — it surfaced only
through manual recomputation. Phase 3 iterates on `project_fcf` and `dcf_value` constantly, the two
functions involved. The rest of Phase 6 (formulas in isolation, edge cases, CI) stays where it is.

**What the test does and does not claim.** It freezes the output verified as correct today and
compares against it after every change. It does not say 132.93 is right; it says the last edit did
not move 132.93 unnoticed.

`tests/conftest.py` puts `logic/` on `sys.path` — absolute, built from `Path(__file__).resolve()`,
and passed as `str`. The modules import each other flat (`valuation.py` does `from model import
project_fcf`), so the repo root on the path is not enough: `logic/` itself has to be on it. A `Path`
object is silently ignored by the import machinery, which surfaces as `ModuleNotFoundError` rather
than as a type error.

`tests/test_golden_values.py` holds `GOLDEN` — five symbols against `Value_Per_Share`, `WACC`, `EV`,
`Low`, `High`, `Implied_Multiple`, `TV_Share`, `Data_Filed` at full float precision — and one
module-scoped fixture parametrised over the symbols, so `dcf_value` runs five times rather than 35.
Seven test functions, 35 cases, all green at `as_of = 2026-08-19`, `start_year = 2016`, `years = 10`,
`freq = "1mo"`, `n = N_MONTHS`, no settings argument. The values reproduce the step 5 table exactly.

Decisions worth keeping:

- **`AS_OF` is hard-wired, not `datetime.now()`.** Without it `dcf_value` takes the current date, the
  stub moves daily and the suite is red tomorrow with no code change. This is the single line that
  makes the test reproducible.
- **`rel = 1e-9`, not exact equality.** A real logic error moves percent, not the ninth decimal.
  Exact equality would go red on a harmless reordering of the summation in `project_fcf`.
- **`Data_Filed` is its own test.** The filings are still not point-in-time pinned. A re-ingest moves
  the numbers legitimately — measured, Boeing 80.54 to 79.82. If only this test fails, the data base
  moved and the golden values are to be reset; if it holds and others fail, it is code.
- **Tesla's `TV_Share` is asserted as `is None`, not with `approx`.** Its `PV_Explicit` is negative in
  all three WACC rows. `pytest.approx(None)` raises, so the test would break itself. If a number ever
  appears there, the FCF projection changed structurally — the step 4d error class, stop immediately.
- **`EV` is asserted on the base row only.** It is computed inside the WACC loop and differs per row
  by construction (Tesla `wacc_low` 18.60bn against `wacc` 7.55bn). `Value_Per_Share` already carries
  the band via `Low`/`High`; a second set of EV goldens would add maintenance, not signal.
  `Data_Filed` is the opposite case: computed once outside the loop, identical in all three rows.

**The rule for resetting the golden values: only together with a roadmap entry saying why.** Phase 3
will move them legitimately the moment an assumption changes. Without the rule, resetting becomes a
reflex and the test is dead.

**Two failure modes found while building it, both of which leave a suite that cannot fail.**
`pytest.approx` called as a statement rather than on the right-hand side of an `assert` asserts
nothing. And a golden value compared against the wrong dict key raises `KeyError`, which reads like a
broken test rather than a broken model. Both are why the mutation probe is part of the procedure:
change one digit in a golden value, confirm exactly one case goes red, revert. Verified on Tesla's
`Implied_Multiple`.

**Open, deliberately deferred to Phase 6.** Every test depends on `storage/values.db`, which is
gitignored — they will not run in GitHub Actions as they stand. Either a checked-in mini fixture
cache or a `skipif` on the database's existence; decide it in Phase 6, not before. Second, minor:
`requirements.txt` is UTF-16 from `pip freeze >` in PowerShell — harmless locally, a candidate for
`Invalid requirement` in CI, to be verified once in a fresh venv.


#### Step 10 — the two sensitivity axes, injectable — DONE

`TERMINAL_GROWTH` was a module constant read at five live sites across two modules, so `g` could not
be varied at all. It is now a parameter with `TERMINAL_GROWTH` as the default, threaded through
`project_revenue`, `project_fcf`, `terminal_value`, `resolve_assumptions` and `dcf_value`. A second
parameter `wacc_offset` (default `0.0`) is added to all three WACC rows in `dcf_value` right after
`calc_wacc`. Both are appended at the end of every signature, because the call chain passes
positionally — a parameter inserted in the middle silently shifts the meaning of existing arguments
without raising. All 35 golden-value tests stay green, which is what the parameters had to prove.

**Threading `g` fully rather than only into the Gordon denominator is a correctness decision, not a
magnitude one.** `g` enters at three places that pull in different directions: the revenue growth
fade target in `project_revenue`, the terminal revenue step, and `reinvestment_rate = g /
terminal_roic`. Measured at `g = 3.5%`, the shortcut of varying only the denominator gives Apple
144.66 against 146.27 fully threaded and Boeing 62.91 against 60.40 — single-digit percent, and the
sign of the error differs per company. Small, but wrong in a way no test would surface.

Measured `Value_Per_Share` on the `wacc` row, `as_of = 2026-08-19`, `wacc_offset = 0`:

| Symbol | g=1.5% | g=2.0% | g=2.5% (base) | g=3.0% | g=3.5% |
|---|---|---|---|---|---|
| apple | 122.62 | 127.48 | 132.93 | 139.13 | 146.27 |
| microsoft | 261.60 | 273.45 | 286.77 | 301.92 | 319.37 |
| procter_gamble | 122.69 | 131.85 | 142.98 | 156.85 | 174.73 |
| tesla | 11.31 | 11.44 | 11.58 | 11.73 | 11.88 |
| boeing | 39.38 | 43.34 | 48.01 | 53.59 | 60.40 |

**The grid design, decided.** `WACC_OFFSETS = (-0.02, -0.01, 0.0, 0.01, 0.02)` and
`TERMINAL_GROWTHS = (0.015, 0.02, 0.025, 0.03, 0.035)` as module constants in `valuation.py`, tuples
so a caller cannot mutate them. `sensitivity_grid` returns a flat dict keyed by the tuple
`(wacc_offset, terminal_growth)`; the nested `offset -> g -> cell` shape was rejected because every
consumer (rendering, Excel, dashboard) wants one row per cell, and the axes are already available as
the constants.

- **The WACC axis is absolute offsets, not percentage steps.** `calc_wacc` already produces a
  Low/High band in basis points; offsets stay comparable with it, relative steps do not.
- **The cell reads the `wacc` row only, not the band.** `wacc_low`/`wacc_high` are a second WACC axis
  and would measure the same thing twice in a matrix whose first axis is already the WACC. The
  side effect is that a cell dies if any of the three rows violates `wacc > g`, even when the row
  actually read is computable — P&G at `wacc_offset = -0.02` with `g = 4%` raises from the
  `wacc_low` row at 3.988% while the base row sits at 4.724%. Inside the chosen axes this never
  fires: zero dead cells across all five companies.
- **A dead cell keeps `Value_Per_Share = None` and carries the reason in `Status`.** No substitute
  value, in line with the project convention that absence stays visible. Only `ValueError` is caught;
  anything else is a bug and must propagate.
- **No settings overrides on the grid function.** `ASSUMPTIONS` stays the single source. An override
  parameter here would invite comparing cells computed under different assumptions inside one
  matrix. The third axis Phase 3 still needs — the EBIT margin fade, and NWC intensity for Boeing —
  gets its own function rather than more parameters on this one.
- **No caching of `calc_wacc` across cells.** Measured: 125 cells (5 companies x 5 x 5) in 0.8s,
  roughly 7ms per cell, because everything hits the SQLite cache. Hoisting `calc_wacc` out of
  `dcf_value` would be complexity for nothing.

**The grid answers the Phase 5 question before Phase 5 starts, and the answer is uncomfortable.**
Newest cached close at `as_of = 2026-08-19` is 2026-07-31 for all five. Against the best cell in the
whole matrix (`wacc_offset = -0.02`, `g = 3.5%`):

| Symbol | base 132.93-style value | best cell | market 2026-07-31 | closes? |
|---|---|---|---|---|
| apple | 132.93 | 215.44 | 308.64 | no |
| microsoft | 286.77 | 487.48 | 464.72 | only in the extreme corner |
| procter_gamble | 142.98 | 444.79 | 144.49 | already matches at base |
| tesla | 11.58 | 14.53 | 311.21 | no, by a factor of 21 |
| boeing | 48.01 | 155.17 | 216.14 | no |

Read: the sensitivity is not what closes the gap. P&G — the one mature company — matches the market
at the base assumptions with an implied multiple of 13.87x against a sector 13.17x, which says the
machinery is sound. Apple and Microsoft need the entire WACC and growth range exhausted at once and
still fall short or only just arrive, and the P&G corner at 444.79 with a 45.55x implied multiple is
numerically valid and economically meaningless — `wacc - g` collapses to 1.22% there. Corner cells of
this matrix are not scenarios; they are the boundary where Gordon stops behaving.

**Tesla's number is not a valuation.** 11.58 against a market of 311.21, with `PV_Explicit` negative
in all three WACC rows and a 4.59% EBIT margin producing almost no EBITDA. The grid moves it between
10.24 and 14.53 — the axes are irrelevant to it. The honest conclusion for Phase 5 and the README is
that a classic FCF DCF has nothing to say about this company at its current margin, not that Tesla is
overvalued by 96%.

**What this hands to the next step.** The gap sits where step 8 said it does, in the terminal block,
and neither WACC nor `g` reaches it. That points at the EBIT margin fade in `project_revenue` /
`project_fcf` and at the unfiltered fade start from step 4c — the last carried-forward item that
still moves a number rather than basis points.


#### Step 11 — the EBIT margin scenario table and the market price reference — DONE

The third axis from step 10's handover. `MARGIN_BASES = ("Driver_Ratio", "Mean_Last_Three", "Last")`
in `valuation.py`, swept by `sensitivity_table`, which returns a flat dict keyed by the margin base.
`margin_base` was already a `dcf_value` parameter from step 4c, so nothing had to be threaded — the
axis existed, it just had no sweep.

At the same time `dcf_value` gained the market reference in every WACC row: `Market_Price`,
`Price_Date`, `Price_Age_Days` and `Upside = value_per_share / market_price - 1`, pulled once
outside the WACC loop via `get_prices(symbol, MARKET_PRICE_FREQ, 1, as_of_key)[-1]`.

- **`MARKET_PRICE_FREQ = "1wk"`, not the `"1mo"` series the WACC regression runs on.** The monthly
  series only carries month-end closes (newest 2026-07-31), so at `as_of = 2026-08-19` the reference
  bar would be nineteen days stale while a weekly close from 2026-08-14 exists. The two series are
  used for different things — the regression needs a uniform grid, the reference bar needs
  recency — and `Price_Age_Days` keeps the remaining gap visible instead of hiding it.
- **The price is fetched once, outside the loop, but written into all three rows.** It is a property
  of the valuation date, not of the WACC scenario. Writing it per row costs nothing and means every
  row is self-contained for rendering in Phase 4; recomputing it per row would have been wrong.
- **`Upside` is not guarded against a zero price.** `get_prices` returning a 0 close would raise
  `ZeroDivisionError` rather than produce a silent infinity. Left deliberate: a zero close is a data
  defect, not a valuation state, and must not be swallowed by the `except ValueError` in the sweeps.

Measured, `wacc` row, `as_of = 2026-08-19`, market close 2026-08-14:

| Symbol | Driver_Ratio | Mean_Last_Three | Last | base | market | Upside at base |
|---|---|---|---|---|---|---|
| apple | 126.28 (28.81%) | 133.44 (31.10%) | 136.16 (31.97%) | Mean_Last_Three | 305.93 | -56.4% |
| microsoft | 274.12 (41.59%) | 288.02 (44.01%) | 297.28 (45.62%) | Mean_Last_Three | 495.40 | -41.9% |
| procter_gamble | 139.85 (22.09%) | 143.86 (22.81%) | 151.96 (24.26%) | Mean_Last_Three | 144.55 | -0.5% |
| tesla | 14.67 (6.32%) | 20.35 (9.53%) | 11.60 (4.59%) | Last | 342.27 | -96.6% |
| boeing | 89.63 (6.98%) | -6.51 (1.86%) | 48.42 (4.79%) | Last | 231.67 | -79.1% |

Percentages are `EBIT_Margin_Target`, the terminal margin the fade arrives at.

**The margin axis is the widest of the three, and it confirms step 8 rather than closing the gap.**
Apple moves 126.28 to 136.16 across the whole axis — 7.8% — while the market sits 129% above. The
axis that was supposed to reach the terminal block does move it (`Implied_Multiple` 9.41 to 9.49 on
Apple, 3.30 to 4.53 on Tesla), but by single-digit percentages against a sector 24-25x. Combined with
step 10's grid: none of the three axes reaches the gap, and P&G still matches the market at base.

**Boeing's `Mean_Last_Three` cell is negative, and it is the most informative cell in the table.**
-6.51 per share at a 1.86% terminal margin — the three clean years feeding that mean end in 2023,
so the statistic describes the 737 MAX aftermath, not the current business. It is the same
non-stationarity that step 4c decided the `Last` base on, now visible as a sign flip rather than as
an argument. The cell is not a scenario; it is the evidence for the base choice.

#### Step 12 — the NWC intensity axis, Boeing-specific — DONE

The last carried-forward item from step 4d/4e. `NWC_INTENSITY` came out of `driver_ratio(data,
"NWC")[nwc_str]` and could only take two values, the median or the three-year mean, which for Boeing
sit 1.2 points apart (22.11% against 20.92%) inside an observed range of 2.82% to 43.68%. The
statistic choice was not an axis. `project_fcf` now takes `nwc_intensity: float | None = None`,
appended at the end of the signature like step 10's parameters, threaded through `dcf_value`, and
swept by `nwc_scenario` over `NWC_INTENSITIES = (0.0282, 0.1686, 0.2092, 0.2211, 0.4368)`.

Measured on Boeing, `wacc` row, `as_of = 2026-08-19`, market 231.67:

| Intensity | Source | Value_Per_Share | TV_Share | Implied_Multiple |
|---|---|---|---|---|
| 2.82% | minimum (2018) | 64.34 | 0.6215 | 7.81 |
| 16.86% | last actual year (2025) | 52.75 | 0.6987 | 7.81 |
| 20.92% | `Mean_Last_Three` | 49.40 | 0.7247 | 7.81 |
| 22.11% | median, the base | 48.42 | 0.7327 | 7.81 |
| 43.68% | maximum (2016) | 30.61 | 0.9159 | 7.81 |

- **The levels are a fixed tuple, not min/median/max derived from the data.** Derived levels change
  with every cache refresh, which makes two runs incomparable and the cells impossible to pin as
  golden values. Same reason `WACC_OFFSETS` is a constant. Each of the five has a name, so the axis
  stays interpretable: the two observed extremes, the current balance sheet, and the two statistics
  the model can actually produce.
- **`Implied_Multiple` and `EBIT_Margin_Target` are constant along this axis by construction.**
  `dNWC` is `None` in the terminal row — the terminal block depends only on `EBIT_MARGIN`,
  `terminal_roic` and `g`. This axis moves `PV_Explicit` alone. The readout is `TV_Share`, which runs
  0.6215 to 0.9159; anyone reusing step 11's `Implied_Multiple` readout here would read an unmoved
  number as stability.
- **It stays Boeing-specific, and the reason is now quantified.** Apple's entire observed NWC range
  (-13.07% to -8.03%) moves its value from 133.39 to 132.85, 0.4%. Boeing's range moves 64.34 to
  30.61, 70% of the base. A shared axis would fill four companies with noise so that one shows
  signal. Other symbols need their own tuple passed in; the default is Boeing's.
- **`Is_Base` reads the statistic from `ASSUMPTIONS[symbol]["metrics"]`, not always `Driver_Ratio`.**
  Boeing is on the median for NWC, but Apple and P&G are on `Mean_Last_Three`. Comparing against the
  median unconditionally would have marked a cell as the base that was never computed. The fallback
  cascade is duplicated from `project_fcf`, because `project_fcf` only exposes the choice as a
  display string in `Metrics`, and a comparison must not depend on a display format.
- **The override renames the provenance.** `nwc_str` becomes `"Override"`, so the row's `Metrics`
  reads `Driver_Ratio+Mean_Last_Three+Override` instead of claiming a statistic that was never
  consulted. `nwc_intensity` defaults to `None`, not `0.0`, because 0 is a legitimate intensity —
  Tesla sits at -0.52%.
- **`nwc_intensity` is not an `ASSUMPTIONS` key and does not pass through `resolve_assumptions`.**
  It is a sweep axis like `terminal_growth` and `wacc_offset`, not a company assumption.
  `ASSUMPTIONS` stays the single source for what the base case is.

#### Golden values reset — the risk-free cache, not the model

All 35 golden values from step 9 moved by +0.4% to +0.9% and had to be reset. The cause is neither
step 11 nor step 12: `as_of` freezes the ledger data but not the completeness of the rate cache.
`risk_free_rate(as_of)` resolves to the newest cached DGS10 row `<= as_of`. When the goldens were
pinned the cache ended 2026-08-14 (4.68%); a run of `valuation.py`'s `__main__` without `as_of` fell
through to `datetime.now()`, found nothing for today, and `fetch_rates` backfilled DGS10 to
2026-08-21. The same `as_of = 2026-08-19` now resolves to 4.65% from 2026-08-19 itself. Apple:
WACC 0.09025 to 0.08996, exactly the 3bp.

- **`RF_Date` is now part of `dcf_value`'s row dict and part of the golden suite** (`test_rf_date`,
  40 tests). The incident presented as five opaque numeric deviations; with the date pinned, the
  same event fails at one assertion that names its own cause. `RF_Fetched_At` is deliberately *not*
  pinned — it changes on every fetch and would be unstable by construction.
- **Standing rule from this: every call in a `__main__` block carries `as_of`.** Without it a debug
  run silently mutates the cache the goldens are pinned against.
- **Whether "newest row <= as_of" survives is a Phase 6 question**, together with the gitignored
  database. Options are an exact-date match with an explicit staleness error, or a rate frozen into
  the test fixture. Not decided here, because both change what `as_of` means for every consumer.

#### Step 13 — the Monte Carlo layer — DONE

The last Phase 3 item, listed there as optional. `monte_carlo` in `valuation.py` draws three inputs
per iteration and returns one aggregate dict, not a table of cells like the three sweeps before it.
`MC_DRAWS = 2000`, `MC_SEED = 12345`, `MC_Z = 1.96`, `MC_PERCENTILES = (0.05, 0.25, 0.5, 0.75, 0.95)`
and `MC_BORDERS = (min(TERMINAL_GROWTHS), TERMINAL_GROWTH, max(TERMINAL_GROWTHS))` as module
constants. No new parameter on `dcf_value` was needed — `terminal_growth`, `wacc_offset` and
`ebit_margin` already existed from steps 10 to 12; this step only samples them.

**Two distributions, chosen for what the input actually is, not for convenience.**

- **WACC: normal.** `calc_wacc` produces a Low/High band from a regression confidence interval, which
  is symmetric around the estimate by construction. `sigma = (wacc_high - wacc_low) / (2 * MC_Z)`
  inverts the 1.96 that built the band. Anything else would discard the only real uncertainty
  measurement the model has.
- **Terminal growth and EBIT margin: triangular.** Both have hard bounds and a preferred value and no
  tail worth modelling — `g` outside 1.5-3.5% stops being a long-run growth rate, and the margin
  outside the three `MARGIN_BASES` targets is not a statistic the model can produce.
  `random.triangular` takes `(low, high, mode)`, while `MC_BORDERS` is stored as `(low, mode, high)`
  to stay readable next to `TERMINAL_GROWTHS`; the call is
  `rng.triangular(MC_BORDERS[0], MC_BORDERS[2], MC_BORDERS[1])`. Passing the tuple straight through
  samples a different distribution without raising.

**The margin vertices come from a pre-pass, not from the draw loop.** Three `dcf_value` calls over
`MARGIN_BASES` fill a `mb -> EBIT_Margin_Target` dict; `m_low`/`m_high` are its min/max and `m_mode`
is the entry for `ASSUMPTIONS[symbol]["margin_base"]`. The vertices do not depend on the draw, so
computing them inside the loop would triple a 14-second run for nothing. The mode must be read from
that dict — the assumption key is a string like `"Mean_Last_Three"`, not a number.

**`random.Random(seed)` is instantiated exactly once, after the pre-pass.** Re-seeding inside a loop
replays an identical sequence, which looks like a working simulation and is a constant. The draw
order WACC, then `g`, then margin is part of the specification: reordering it changes every pinned
number while the model stays identical.

**Successes and failures are stored apart.** Values go into a list, failures into a
`message -> count` dict, and the `try` wraps the `dcf_value` call itself, not the dict literal built
from its result. `Draws_OK + Draws_Failed == draws` is then a checkable invariant, and a failure is
never confusable with a value — which a draw-indexed dict of rows would not give. Percentiles use
an explicit linear interpolation (`k = (len(values) - 1) * p`) rather than `statistics.quantiles`, so
the convention is pinned in the repo instead of in a library default. `P_Above_Market` counts draws
above the market price, not the base value against it. The percentile loop sits behind an
`if values:` guard: with an empty list `int((0 - 1) * 0.05)` is `0` and `values[0]` raises
`IndexError`, which no caller filters for, and it would fire exactly in the case where `Failures`
holds the explanation.

Measured, `as_of = 2026-08-19`, 2000 draws, seed 12345, market close 2026-08-14:

| Symbol | base | P05 | P25 | P50 | P75 | P95 | Mean | market | P_Above_Market |
|---|---|---|---|---|---|---|---|---|---|
| apple | 133.44 | 119.68 | 126.68 | 132.05 | 138.45 | 148.35 | 132.87 | 305.93 | 0.0% |
| microsoft | 288.02 | 253.31 | 272.19 | 286.73 | 304.43 | 332.08 | 289.24 | 495.40 | 0.0% |
| procter_gamble | 143.86 | 123.82 | 135.41 | 145.31 | 157.70 | 178.85 | 147.74 | 144.55 | 51.7% |
| tesla | 11.60 | 11.38 | 12.77 | 14.36 | 16.37 | 19.81 | 14.79 | 342.27 | 0.0% |
| boeing | 48.42 | 10.53 | 28.67 | 43.38 | 59.97 | 83.68 | 45.08 | 231.67 | 0.0% |

`WACC_Sigma` and the margin vertices behind those columns:

| Symbol | WACC_Sigma | m_low | m_mode | m_high | Draws_Failed |
|---|---|---|---|---|---|
| apple | 0.4158pp | 28.81% | 31.10% | 31.97% | 0 |
| microsoft | 0.4902pp | 41.59% | 44.01% | 45.62% | 0 |
| procter_gamble | 0.3760pp | 22.09% | 22.81% | 24.26% | 0 |
| tesla | 1.2612pp | 4.59% | 4.59% | 9.53% | 0 |
| boeing | 0.5015pp | 1.86% | 4.79% | 6.98% | 0 |

**P&G is the only company whose distribution straddles the market, and it does so almost exactly.**
51.7% of draws land above 144.55, with the median at 145.31 against a base of 143.86. That is the
same result steps 10 and 11 produced from a single cell, now with a probability attached rather than
a point. For the other four the market lies outside the 95th percentile entirely — Apple's P95 is
148.35 against 305.93 — so `P_Above_Market` is structurally 0 and carries no information there. The
metric is only readable where the base sits near the price.

**Tesla's triangular is degenerate, and that is a modelling defect, not a Tesla fact.** Its
`margin_base` is `Last`, which is also the minimum of the three targets, so
`m_low == m_mode == 4.59%` and the distribution is one-sided upward. The consequence: mean 14.79 and
median 14.36 against a base of 11.60, +27% and +24%. The simulation reports a centre the base case
never computes. This fires whenever a company's assumed margin base is an extreme of `MARGIN_BASES`
rather than the middle one — it is a property of using the three statistics as vertices, and any
company can land there after a cache refresh. Not fixed here; the honest reading for now is that
Tesla's MC centre is not its base case. Options for later: widen the vertices by a fixed spread
around the mode, or fall back to a symmetric distribution when the mode equals a bound.

**Boeing's left tail samples a scenario step 11 already rejected.** `m_low` is 1.86%, the
`Mean_Last_Three` margin whose three clean years end in 2023 and describe the 737 MAX aftermath —
the cell step 11 measured at -6.51 per share. The MC draws the whole way down to it, which is why P05
is 10.53 against a base of 48.42 and the spread is by far the widest of the five. That left tail is
not a risk estimate; it is the non-stationarity the `Last` base choice exists to avoid, re-entering
through the margin vertices.

**Where the median tracks the base, the machinery is behaving.** Apple 132.05 against 133.44 and
Microsoft 286.73 against 288.02 — a central mode plus a symmetric WACC draw returns the base case,
with the small downward shift coming from the `g` mode at 2.5% sitting slightly below the midpoint of
its own range. No draw failed for any company: with WACC between 6.7% and 11.3% and `g` capped at
3.5%, `wacc > g` never comes under pressure, so the `Failures` path is untested against real data.

**Two limitations to carry forward.** First, the three inputs are drawn independently, while in
reality a high margin, a high growth rate and a low WACC co-occur. The simulation therefore
understates both tails; the percentiles are narrower than the true uncertainty, not wider. Modelling
that correlation needs a joint distribution and is out of scope here. Second, the function returns
only the aggregate. A histogram in Phase 4 needs the individual values, so the return carries them as
`Draws` — a `list(values)` copy, not the list the aggregation itself computes on, which a caller
could mutate. The binning stays in the presentation layer: derived bin edges would change with every
cache refresh, the same reason `NWC_INTENSITIES` in step 12 is a fixed tuple rather than a range
pulled from the data.

**The MC values are pinned, and the suite goes from 40 to 70 tests.** `MC_GOLDEN` in
`tests/test_golden_values.py` holds the five percentiles, `Mean`, `P_Above_Market`, `WACC_Sigma` and
`Margin_Range` per symbol, driven by a second module-scoped fixture `mc_result` alongside the
existing `result`. `Base_Value_Per_Share`, `Market_Price` and `WACC` are deliberately not pinned here
— they already sit in `GOLDEN`, and the same number in two places has to be reset twice after every
shift.

- **`DRAWS = 2000` and `SEED = 12345` are local test constants, passed explicitly to `monte_carlo`,
  not imported from `MC_DRAWS`/`MC_SEED`.** A golden value checked against a constant that moves with
  the code checks nothing: change `MC_DRAWS` and the suite silently re-pins itself green.
- **`P_Above_Market` is compared with `==`, not `pytest.approx`.** It is a count over a denominator
  of 2000, exactly representable, and an exact assertion catches an off-by-one in the counting that
  a relative tolerance of 1e-9 would still let through.
- **`Margin_Range` is asserted element by element**, so a failure names which vertex moved. As a
  tuple comparison it would only say that the triangle changed.
- **`test_draw_accounting` is the one test here that is not a golden value.** It asserts
  `Draws_OK + Draws_Failed == draws`, `Draws_OK == len(Draws)` and
  `sum(Failures.values()) == Draws_Failed`. Those hold after any cache refresh, so they keep working
  as a structural check once the pinned numbers have to be reset again.
- **The six MC tests carry `@pytest.mark.slow`, registered in `pytest.ini`.** Measured: the full
  suite runs 57-60 seconds against 0.61 for `-m "not slow"` (40 passed, 30 deselected). Without the
  marker every parser-only change costs a minute, and the predictable outcome is that the suite gets
  run less often, which is the opposite of what pinning is for.

### Phase 3 — Sensitivity & scenarios — DONE
- Sensitivity table (WACC vs. terminal growth rate) — DONE (step 10). The football field as a
  *chart* is Phase 4; the numbers behind it are complete.
- The current market price belongs in the output as a reference bar, not just the value range
  (see the phase order note above).
- Carried in from step 8: the terminal block is where the conservatism sits (implied 8-10x against
  a sector 24-25x on Apple and Microsoft). Terminal growth and the EBIT margin fade are the two
  axes that move it; `Implied_Multiple` is the readout that makes the sensitivity legible against
  an external number rather than only against itself.
- Carried in from step 4d/4e: Boeing's NWC intensity is not stationary, so NWC intensity is a
  Boeing-specific axis, not a shared one.
- Monte Carlo simulation over uncertain inputs for a valuation range — DONE (step 13)

**Learning goals:** master sensitivity analysis as a valuation tool; for Monte Carlo,
understand random distributions and sampling, not just call a library function.

#### Step 14 — the cost-of-debt basis — DONE

Item 1 of the four carried out of Phase 2. `cost_of_debt` measured interest expense over average
debt, i.e. the coupon on the existing stack. A DCF discounts ten years forward, so the fremdkapital
leg has to be the rate new debt would cost, not the rate old debt does. The definitional error was
the reason to act; the measured size was not.

**Decision: the synthetic rate is the basis, with an explicit and visible fallback.**
`synthetic_cost_of_debt` now lives in `wacc_calculation.py`, together with the `SPREADS` table and
`synthetic_rating` that moved over from `damodaran.py`. `calc_wacc` tries the synthetic first and
only falls back to the realised chain (2023+, then 2018+) when the synthetic is not usable.

**Two rejection cases, kept distinct.** `Unavailable` means no year survived the flag filter — the
same filter `cost_of_debt` uses, yoy outliers removed. `Below_Investment_Grade` means the coverage
was computed and lands under `INVESTMENT_GRADE = 2.5`, the lower bound of the Baa2/BBB row. The
second is the substantive one: below investment grade the spread prices default, while the model's
own terminal value assumes the same company grows at 2.5% forever. Discounting a going concern at a
default-grade rate is internally inconsistent, so the model refuses that input rather than using it.
The consequence, and it belongs in the README: **this model cannot value a distressed company.**

**The rejected number is still reported.** `COD_Basis`, `COD_Alternative` and `COD_Evidence`
(rating, coverage, year, n) are carried out of `calc_wacc` and through `dcf_value`. Boeing's WACC
therefore states in the output that it stands on a fallback and what the synthetic would have said.
Without those keys Boeing's 4.73% is indistinguishable from Microsoft's measured rate — the same
failure the `unchecked` flag exists to prevent.

**The spread table had to move, not be copied.** Step 8 recorded that nothing in `logic/` reads
`damodaran.py`, so the cross-check can never quietly become a model input. That guarantee now holds
only for `DAMODARAN`, the sector rows. `SPREADS` is a market data table and became a model input, so
it moved into `logic/` and `damodaran.py` imports it from there. Two copies would drift at the next
Damodaran vintage and the check would then verify the model against its own stale duplicate.

Measured, `as_of = 2026-08-19`, `start_year = 2016`, settings from `ASSUMPTIONS`:

| Symbol | COD before | COD after | Basis | coverage (year) | W_Debt | WACC before | WACC after | VPS before | VPS after |
|---|---|---|---|---|---|---|---|---|---|
| apple | 2.71% | 5.05% | Synthetic, Aaa/AAA | 29.06x (2023) | 2.12% | 8.9957% | 9.0329% | 133.44 | 132.80 |
| microsoft | 5.03% | 5.05% | Synthetic, Aaa/AAA | 53.89x (2025) | 1.23% | 9.1527% | 9.1529% | 288.02 | 288.01 |
| procter_gamble | 2.71% | 5.05% | Synthetic, Aaa/AAA | 22.55x (2025) | 9.25% | 6.6973% | 6.8597% | 143.86 | 138.73 |
| tesla | 4.66% | 5.05% | Synthetic, Aaa/AAA | 12.88x (2025) | 0.69% | 11.2545% | 11.2566% | 11.60 | 11.60 |
| boeing | 4.73% | 4.73% | Realised_Fallback | -0.31x (2023) | 26.85% | 7.8280% | 7.8280% | 48.42 | 48.42 |

**The synthetic does not discriminate at the top of the table.** Four of five land on the same
5.05%, `rf` 4.65% plus the 40bp Aaa/AAA spread, because the spread table saturates above 8.5x
coverage and all four sit between 12.88x and 53.89x. The company-specific information sits in the
realised rate (Apple 2.71% against Microsoft 5.03%) and is exactly the backward-looking part the
switch removes. That is a real cost of the decision, not a footnote: the model now prices the debt
of four very different balance sheets identically. It is accepted because the debt weights are
0.69% to 9.25% there, so the effect on WACC is 0 to 16bp.

**Boeing is the reason the fallback exists, not an exception to the rule.** A blanket switch would
have taken its WACC 7.83% → 11.64% and its value per share 48.42 → 7.41, a loss of 84.7%, against a
market price of 231.67 and external DCF ranges of 160-390. The synthetic is not wrong about Boeing
in 2023; it is a default-grade rate applied to a going-concern model, and step 14 rejects the
combination rather than the number.

**Golden values reset for four of five, Boeing untouched.** `GOLDEN` moves on apple, microsoft,
procter_gamble and tesla; `MC_GOLDEN` on the same four. Boeing passing all seven tests unchanged was
the control that the edit touched only the debt leg. Two MC readings changed enough to record:
P&G's `P_Above_Market` falls from 51.65% to 39.90% and its median from 145.31 to 140.11 — the one
company whose distribution straddled the market now sits below it more often than above. Apple's
median moves 132.05 → 131.42, Microsoft's and Tesla's move in the last decimals only.

**Item 2 is now labelled, not solved.** Boeing keeps 4.73% off a 2023 window with `n = 5`; what it
gained is a `COD_Basis` saying so. The written justification for accepting a flagged fallback at a
26.85% debt weight is the next item.

#### Step 15 — Boeing's cost of debt — DONE

Item 2 of the four carried out of Phase 2, and the direct continuation of step 14. Boeing was the
only company on the fallback path, so its cost of debt was still what step 14 had just rejected for
everyone else: the coupon on debt issued between 2016 and 2021, applied to a ten-year projection,
on the company with the highest debt weight of the five (26.85%).

**Two separate defects, found by measurement rather than by reading the code.**

*The year selection read past the newest data point.* `synthetic_cost_of_debt` takes `max()` over the
flag-clean years, and Boeing's 2024 and 2025 `OperatingIncome` both carry `outlier` — the
`margin_change_pp 0.07` rule fires on the recovery itself. The function therefore reported coverage
-0.31x from 2023 while the newest reading was +1.54x from 2025. The guard that should have caught
this existed since step 14 but tested `OUTLIER_RULES["OperatingIncome"][0] == "yoy"`, and the rule
is `margin_change_pp`, so it never fired. A dead guard, invisible in every test, because
`COD_Evidence` is not pinned in `test_golden_values.py`.

The fix drops the `margin_change_pp` outlier from the `OperatingIncome` flags the same way
`cost_of_debt` already drops `yoy` — the argument is identical: that rule marks a *change*, not an
implausible level, and a company recovering from a loss is exactly the case where the change is the
signal. `recon`, `unchecked` and everything else still disqualify a year. Measured effect on the
other four: none. All keep their rating and their year; only `n` rises (Apple 5 → 8, the rest to 10).

*The fallback had no floor.* Below investment grade the model refuses the synthetic spread because
it prices default while the terminal value assumes 2.5% growth forever — step 14's argument. But
without a floor it then falls back to whatever the old bonds happen to cost, which asserts that a
sub-investment-grade issuer borrows at its own investment-grade-era coupon. **The floor is
`rf + spread` of the Baa2/BBB row, taken from `synthetic_rating(INVESTMENT_GRADE)`, and the used
rate is the larger of that and the realised rate.** No new constant: a second constant holding the
spread would drift out of step with `INVESTMENT_GRADE` at the next Damodaran vintage, and the model
would then discount at a boundary that no longer exists in `SPREADS`. The `max` matters in the other
direction — an issuer already paying more than BBB has measured evidence of it, and a fixed floor
would throw that away in precisely the case it is needed.

**Why this is the right size of correction, measured.** The full plausible range of the cost of debt
moves Boeing's value per share from 50.55 to 37.89 against a market price of 231.67:

| basis | cost of debt | WACC | value per share |
|---|---|---|---|
| realised 2016+ | 4.18% | 7.7166% | 50.55 |
| realised 2018+ | 4.30% | 7.7411% | 50.07 |
| realised 2023+ (before) | 4.73% | 7.8280% | 48.42 |
| **Baa2/BBB floor (after)** | **5.76%** | **8.0358%** | **44.68** |
| synthetic on 2025, 1.54x, B2/B | 7.86% | 8.4587% | 37.89 |
| synthetic on 2023, -0.31x, D2/D | 23.65% | 11.6385% | 7.41 |

Item 2 called this "the least defensible single input in the set" and that was accurate; calling it
Boeing's problem would not have been. The model is off by a factor of five on Boeing, and the cost
of debt cannot account for more than 13 of those points. The causes stay where step 3d put them:
beta 1.108 out of a regression with R² = 0.29, and a 27% debt weight built on book value.

**The model's own projection says Boeing is sub-investment-grade for five more years.** At interest
expense of 2.771bn the projected EBIT implies forward coverage of 1.72x in 2026, crossing 2.5x only
in 2031. Discounting that path at an investment-grade floor is already generous; discounting it at
the 2016-2021 coupon was indefensible. Rated per projected year: B2/B, B1/B+, Ba2/BB, Ba2/BB,
Ba1/BB+, then Baa2/BBB.

**The floor is an assumption and the roadmap should say so plainly.** It asserts that Boeing borrows
at no worse than BBB, which is probably too generous — new issues price closer to 5.5-6.5% by market
knowledge that is not in the model and not obtainable from EDGAR. It is more conservative than the
status quo and less conservative than an honest market read, and `COD_Basis` reads
`IG_Floor+Below_Investment_Grade` so the choice is visible in every report rather than buried.

**`COD_Evidence` gained a `Realised` key.** On the floor path the measured 4.73% is otherwise gone
from the output entirely: `Cost_of_Debt` holds the floor, `COD_Alternative` the rejected synthetic
7.86%, and the only number actually measured from filings would have vanished. Same principle as
`unchecked` — the rejected reading stays visible. On the synthetic path the key duplicates
`COD_Alternative`; that redundancy is the price of `COD_Evidence` being readable on its own.

`calc_wacc` also stopped reassigning `cost_debt` and now carries `cod_used`, `cod_realised` and
`cod_border` separately. Overwriting `cost_debt` with the floor would have left `cost_debt["n"]` and
`cost_debt["Source"]` attached to a number they no longer describe — the flag convention applied to
a local variable.

Measured, `as_of = 2026-08-19`, `start_year = 2016`, settings from `ASSUMPTIONS`. Boeing only; the
other four are byte-identical and served as the control:

| field | before | after |
|---|---|---|
| `Cost_of_Debt` | 4.728185% | 5.76% |
| `COD_Basis` | Realised_Fallback+Below_Investment_Grade | IG_Floor+Below_Investment_Grade |
| `COD_Alternative` | 23.65% | 7.86% |
| `COD_Evidence` | D2/D, -0.31x, 2023, n=5 | B2/B, 1.54x, 2025, n=10, Realised 4.73% |
| `WACC` | 7.827978% | 8.035768% |
| `Value_Per_Share` | 48.417191 | 44.677033 |
| `Implied_Multiple` | 7.81x | 7.52x |
| `TV_Share` | 73.27% | 72.37% |
| MC median | 43.38 | 39.86 |
| MC mean | 45.08 | 41.38 |

`P_Above_Market` stays 0.0, `WACC_Sigma` and `Margin_Range` are untouched — the equity leg was not
part of this step. Seven Boeing assertions failed, sixty-three passed, and that split was the
verification: any movement in the other four would have meant the flag change was broader than
intended.

#### Step 16 — the price staleness bound — DONE

Item 3 of the four carried out of Phase 2, and the last hole in the vintage chain. The rate path has
refused data older than `RF_MAX_AGE_DAYS = 10` since step 3a-1; the price path had no equivalent, so
a valuation could mix a ten-day-old rate with an arbitrarily old market cap and report neither fact.

**The measured finding is not the stale price, it is that there are two of them.** At
`as_of = 2026-08-19` the newest close is identical for all six symbols: 2026-07-31 on `1mo` (19 days)
and 2026-08-14 on `1wk` (5 days). `debt_to_equity` builds the market cap from the monthly close,
`dcf_value` prices `Upside` off the weekly one, and the two disagree by more than the staleness
question ever could:

| Symbol | `1mo` close (2026-07-31) | `1wk` close (2026-08-14) | gap |
|---|---|---|---|
| apple | 308.64 | 305.93 | -0.9% |
| microsoft | 464.72 | 495.40 | +6.6% |
| procter_gamble | 144.49 | 144.55 | +0.0% |
| tesla | 311.21 | 342.27 | +10.0% |
| boeing | 216.14 | 231.67 | +7.2% |

The same report therefore states an upside against one price and weights the WACC against another.
Arithmetic on the printed weights: moving Boeing's market cap to the weekly close takes `W_Debt`
26.85% → 25.51% and the WACC 8.0358% → roughly 8.10%, about +7bp — it is the only one of the five
where the debt weight is large enough for the gap to reach the WACC at all. The Phase 2 note sized
this item at "max 30bp, closing the vintage chain, not accuracy", and that framing was right about
the size and wrong about the defect.

**`PRICE_MAX_AGE_DAYS` is a dict over `freq`, not a scalar** — `{"1mo": 45, "1wk": 14}` in
`prices.py`. A single number cannot serve both: 45 days is no bound at all on a weekly series, and 14
is a permanent failure on a monthly one. The monthly value follows from the sampling interval, one
month plus the two weeks a resample can lag the last trading day.

**`price_reference(symbol, freq, as_of)` in `prices.py` reads the newest row and raises past the
bound. It does not refetch, unlike `risk_free_rate`.** `debt_to_equity` runs once per year of the
beta window inside `adjusted_beta`, so a yfinance download in the failure path would be a network
call inside a loop. The ingest stays an explicit run of the `prices.py` `__main__` block; the
function only refuses. That is a deliberate divergence from the rate path and the reason for it is
the call site, not the data source.

**The bound applies to the current read only, never to the series.** `debt_to_equity` routes only
its `year is None` branch through `price_reference`; the `year` branch and `raw_beta` keep reading
old closes directly, because a December 2019 close is not stale data, it is the regression input. A
bound placed inside `get_prices` would have killed the beta.

Verified at `as_of = 2026-08-19`: 70 passed, no golden value moved. That was the control — the bound
must not touch a number at an `as_of` where it does not fire. The boundaries fire as intended:
`1mo` at `as_of = 2026-09-15` against the 2026-07-31 close (age 46), `1wk` fourteen days past its
newest close.

**The reporting side, and why it needed its own keys.** `dcf_value` and `calc_wacc` both read
through `price_reference` now, so both prices are gated and both dates are in the output:
`Price_Date` / `Price_Age_Days` for the `1wk` reference price, `MCap_Price_Date` /
`MCap_Price_Age_Days` for the `1mo` close behind the weights. `calc_wacc` calls `price_reference`
itself rather than taking the date out of `debt_to_equity` — that function returns a float, and
widening its signature would have dragged `adjusted_beta` along for a value it never uses. Measured
at `as_of = 2026-08-19`, identical for all five: reference 2026-08-14 at 5 days, market cap
2026-07-31 at 19 days. Nineteen days is inside the bound and outside the rate's ten — the mix the
Phase 2 note described is still there, it is now stated in every row instead of nowhere.

**Absence and staleness are separate raises.** `price_reference` wraps the `get_prices` call and
re-raises with its own message when no row exists at or before `as_of`; the age check produces the
other one. `get_prices` raises before it returns, so the case cannot be read off a return value —
the `try` is not decoration. Same distinction as `unchecked` against `recon_unchecked`, and it
decides whether the answer is an ingest or a corrected `as_of`.

**The bound is pinned, and the pin is derived rather than written down.** `test_price_bound` in
`tests/test_golden_values.py`, parametrised over `1mo` and `1wk`, reads the newest row through
`get_prices` with a far-future `as_of`, then builds two dates from it: newest plus the bound, where
`Age` must equal the bound and nothing may raise, and one day later, where `ValueError` is required.
`test_price_reference_absence` covers the empty side at `as_of = 2000-01-01`. Cache-only, no `slow`
mark, 70 tests to 73.

Three things about that test are deliberate. It hangs on no fixture — `result` runs a full
valuation per symbol and can say nothing about the guard, because a broken bound leaves `dcf_value`
working perfectly. It asserts the non-raising side too, since a `>=` slip moves the boundary by one
day and is invisible from the raising side alone. And the dates are computed from the cache instead
of written into the file: the `1wk` series moved from 2026-08-14 to 2026-08-21 during this step, so
a hard-coded date would have gone green without testing anything — the mechanism that kept the
step 15 coverage guard dead. Checked by mutation: raising `PRICE_MAX_AGE_DAYS["1mo"]` to 450 makes
the test fail, which is the only evidence that it tests anything at all.

**Found while verifying, not caused by this step: the price series is retroactively rewritten.**
`fetch_prices` downloads with `auto_adjust = True` and `insert_prices` overwrites, so every dividend
re-adjusts the whole history. Microsoft's 2026-08-14 weekly close was 495.40 before an ingest during
this step and 494.47 after — a difference of 0.93, one MSFT quarterly dividend, on a date that was
already in the past. No test saw it because Microsoft's `P_Above_Market` sits at 0.0; the same
event on P&G, whose distribution straddles the price, would have moved a pinned number with no code
change behind it. This is the filing-vintage problem on the price path, and it is now the only
unpinned vintage left after `RF_Date`, `Data_Filed` and the two price dates. Not fixed here: it is
the same scope as full point-in-time filings, which step 6b scoped and deferred.

**Decided: two prices, both reported.** The market cap keeps the `1mo` series and the reference
price keeps `MARKET_PRICE_FREQ = "1wk"`. The argument is internal consistency of the WACC leg, not
freshness: `DE_Window` in `adjusted_beta` averages `debt_to_equity` over the December closes of the
monthly series, so moving `de_current` to the weekly close would measure the window and the current
point on two different frequencies inside one beta. The reference price is not a model input — it is
the external comparison behind `Upside` and `P_Above_Market` — and there the newest close is the
right one. The gap in the table above therefore stays; what changes is that both dates are now in
the output, `Price_Date` for the reference and `MCap_Price_Date` for the weights.

Measured cost of getting this backwards, and the reason it is worth a line here: routing `dcf_value`
through the beta `freq` instead of `MARKET_PRICE_FREQ` moves P&G's market price 144.55 → 144.49, six
cents, and its `P_Above_Market` 39.9% → 40.1%. One assertion in the pinned Monte Carlo suite caught
it; the other four companies are unaffected because only P&G's distribution straddles the price at
all. Without step 13's pinning this would have been a silent change to a headline number.

#### Step 17 — the fade start, reported instead of filtered — DONE

Item 4 of the four carried out of Phase 2, and the last one. `m_t` runs from `LAST_EBIT_MARGIN` to
`EBIT_MARGIN` over the horizon; step 4c decided the target per company and left the start as it was
found — `data[last_year]["OperatingIncome"]["Value"]` divided by revenue, with no flag check, no
absence check and no reporting key. Phase 4 will print the fade, so one half of the printed line
would have stood on an unexamined number.

**Filtering the start was measured and rejected.** Boeing is the only one of the five whose last
actual `OperatingIncome` carries a flag — `outlier` under the `margin_change_pp` rule, and not only
in 2025 but in 2019, 2020, 2021 and 2024 as well. Its last clean year is 2023 at an EBIT margin of
-0.9936%. Boeing's `margin_base` is `Last`, which resolves to `LAST_EBIT_MARGIN` rather than to a key
in `driver_ratio`, so a flag-checked start pulls the target down with it: start and target both go to
-0.99%, and value per share goes **44.68 → -84.60** with `TV_Share` collapsing to `None`
(`PV_Explicit <= 0`). That is not a conservative correction, it is an unnamed extreme assumption
wearing the label "no change". Measured at `as_of = 2026-08-19`, base WACC, by substituting the last
clean margin into the 2025 row.

**Decided: report the start, do not filter it.** The start means "where the company is", and that is
the one statement in the model that must not be quietly replaced by a statistic. What was missing was
not a filter but visibility — the same rule as everywhere else in this project: absence and doubt are
reported, never substituted. `project_fcf` now derives `MARGIN_START_SOURCE` from the flag list of the
last actual year, `Last_Actual` against `Last_Actual_Flagged`, keeps the value either way, and writes
`Margin_Start`, `Margin_Start_Year` and `Margin_Start_Source` into both the projected rows and the TV
row. `dcf_value` lifts them into every valuation row as `EBIT_Margin_Start`, `Margin_Start_Year` and
`Margin_Start_Source`, next to the existing `EBIT_Margin_Target`.

Measured at `as_of = 2026-08-19`, `start_year = 2016`, `years = 10`:

| | `EBIT_Margin_Start` | `Margin_Start_Source` | `EBIT_Margin_Target` | `Margin_Base` |
|---|---|---|---|---|
| apple | 31.97% | `Last_Actual` | 31.10% | `Mean_Last_Three` |
| microsoft | 45.62% | `Last_Actual` | 44.01% | `Mean_Last_Three` |
| procter_gamble | 24.26% | `Last_Actual` | 22.81% | `Mean_Last_Three` |
| tesla | 4.59% | `Last_Actual` | 4.59% | `Last` |
| boeing | 4.79% | **`Last_Actual_Flagged`** | 4.79% | `Last` |

No value moves: the step is reporting plus a guard, and all pinned numbers from step 16 reproduce
exactly.

**The step 4c sentence was too kind to itself.** "The fade start is unfiltered, the fade target is
not" holds only for the three companies on `Mean_Last_Three`. For Boeing and Tesla, `margin_base` is
`Last`, and `Last` resolves to `LAST_EBIT_MARGIN` — `driver_ratio` is never called, so **both ends of
the fade are unfiltered** and the fade is a constant. That is the intended behaviour from step 4c, but
it was not written down as such, and nothing in the output revealed it. The two new keys make it
readable: where start equals target, there is no fade, and where the source reads
`Last_Actual_Flagged`, the whole thing stands on a year the validation layer objected to.

**The absence guard, and why it is split in two.** `LAST_EBIT_MARGIN` divided without checking, so a
missing `OperatingIncome` died with `TypeError` and a zero revenue with `ZeroDivisionError` — both
before the `None` check for EBIT, D&A, CapEx and NWC further down, which was built for exactly this
class of problem. `project_fcf` now raises two separate `ValueError`s naming the metric and the year:
`OperatingIncome` against `None` only, `Revenue` against `None` and `0`. The asymmetry is deliberate
and is the same convention as `dNWC`: an operating income of exactly zero is a measured margin of
zero, not missing data, and collapsing both metrics into one `in (0, None)` check would turn a
legitimate reading into a data error. Verified: with the 2025 `OperatingIncome` set to `0.0` the
projection runs and reports `Margin_Start` `0.0` under `Last_Actual`.

**Pinned by four tests, three of them new.** `test_margin_start` asserts `EBIT_Margin_Start`,
`Margin_Start_Source` and `Margin_Start_Year` for all five companies across all three WACC legs — the
start does not depend on the WACC, which is the point of asserting it three times. The two guard tests
call `project_fcf` directly on a `deepcopy` of the cached data with the last year's value knocked out,
and use `pytest.raises(..., match = ...)` on the metric name rather than a bare `ValueError`:
`project_fcf` has six `ValueError` paths, and a bare catch would stay green if the new guard vanished
and an older check caught the same input further down. The third new test is the positive case for a
zero operating income. Mutation check as in step 16: with both guard lines removed from a scratch copy
of `model.py`, the two inputs raise `TypeError` and `ZeroDivisionError` instead — the tests bite. Suite
78 → 81, all green.

**Checked and deliberately not done.** `project_revenue` reads the same unguarded base level,
`data[sorted(data)[-1]]["Revenue"]["Value"]`, and would die the same way. Its only caller is
`project_fcf`, one line below the new guard, and both read the identical value — a second guard there
is unreachable code today. It becomes relevant the moment a Phase 4 module calls `project_revenue`
on its own for a revenue view; noted here so the next review does not rediscover it as a hole.

#### Before Phase 4 — what is actually left

Written 2026-08-28 after step 17 emptied the Phase 2 carry-forward list, closed 2026-08-29. Nothing
here was structural in the sense of step 6b — no signature and no dict key changed. Item 1 was the
only blocker: a dashboard freezes the output format and makes an unpinned key expensive to discover.
Item 2 is a decision, recorded so it is not re-litigated. Item 3 was cosmetic, inherited from step 16.
All three are closed; the suite went 81 → 87. **Phase 4 is unblocked.**

**1. CLOSED 2026-08-29 — `COD_Basis` and `COD_Evidence` are pinned.** Step 15 fixed a guard that had
been dead since step 14: it tested `OUTLIER_RULES["OperatingIncome"][0] == "yoy"` while the rule is
`margin_change_pp`, and nothing noticed for two steps. The same shape survives in code —
`synthetic_cost_of_debt` and `cost_of_debt` gate their outlier-stripping on the literal rule name, so
renaming a rule in `validation.py`, or retuning `margin_change_pp` past the threshold that fires on
Boeing's recovery, silently changes which year the coverage ratio is read from. Boeing's cost of debt
hangs on that selection: 2023 gave -0.31x and D2/D, 2025 gives +1.54x and B2/B, 3.74 per share apart.
`WACC` alone never catches it, because the IG floor keeps binding while the evidence underneath moves.

`GOLDEN` now carries `COD_Basis`, `COD_Rating`, `COD_Year` and `COD_N` per company, asserted by
`test_cod_evidence` across all three WACC legs — the cost of debt does not depend on the WACC offset,
which is what asserting it three times states:

| | `COD_Basis` | `COD_Rating` | `COD_Year` | `COD_N` |
|---|---|---|---|---|
| apple | `Synthetic` | `Aaa/AAA` | **2023** | 8 |
| microsoft | `Synthetic` | `Aaa/AAA` | 2025 | 10 |
| procter_gamble | `Synthetic` | `Aaa/AAA` | 2025 | 10 |
| tesla | `Synthetic` | `Aaa/AAA` | 2025 | 10 |
| boeing | `IG_Floor+Below_Investment_Grade` | `B2/B` | 2025 | 10 |

**Apple is the finding this pin surfaced.** Its coverage stands on 2023, not 2025, because
`InterestExpense` is `missing` in both 2024 and 2025 — the parser finds no tag. Apple's rating
evidence is therefore two years stale, `n = 8` against 10 for the others, and nothing in the output
said so: `COD_Basis` reads `Synthetic`, the WACC is unremarkable, and the year sat only inside the
`COD_Evidence` dict. It is now a pinned number, so it cannot drift further without a red test.

`Coverage` and `Realised` are deliberately not pinned. The failure mode is the year selection, which
shows up discretely in `Year` and in the `Rating` derived from it; the two floats would need
`pytest.approx` and would additionally go red on any re-ingest with restated figures — a test that
fails without a logic change is a test nobody believes the next time it fails.

The `Unavailable` branch from item 2 is pinned separately by `test_cod_unavailable`, which nulls
`InterestExpense` in every year of a `deepcopy` and asserts `Source == "Unavailable"` with
`Cost_of_Debt`, `Coverage` and `Year` all `None` and `n == 0`. It calls `synthetic_cost_of_debt`
directly with a literal `RF_STUB` rather than `risk_free_rate`, because the branch returns before the
rate is read and a real call would make the test depend on the FRED cache and `RF_MAX_AGE_DAYS` for a
value it never uses.

**2. Decided 2026-08-28 — `Unavailable` keeps the investment-grade floor, and the reason is written
here so it is not re-litigated.** In `calc_wacc`, when the synthetic rate is not usable the code
falls back to the realised rate against `rf + spread(Baa2/BBB)` — at `as_of = 2026-08-19` that is
4.65% + 1.11% = 5.76% — and it does so identically whether `synthetic_cost_of_debt` returned
`Below_Investment_Grade` (coverage measured, below `INVESTMENT_GRADE = 2.5`) or `Unavailable`
(no flag-clean year with a usable interest expense, coverage `None`). Step 14 kept the two states
distinct and the shared treatment was never argued.

It is argued now, and the floor stays for both. The floor's justification never depended on the
coverage measurement: it exists because a realised rate computed from legacy coupons is a statement
about debt issued years ago, not about what the company would pay today, and that stays true when
coverage cannot be computed at all. The floor is also directionally safe — it can only raise the
cost of debt and lower the value, never the reverse — so applying it under ignorance is conservative,
not optimistic. The competing reading, that `rf + BBB` is a *rating assumption* and therefore a
plausible default substituted for missing data, is the one the project convention forbids; it fails
because the floor is not a claim that the company is investment grade. It is a lower bound on what
any corporate borrower pays, applied to a realised rate that is known to be backward-looking. The
label carries the difference: `IG_Floor+Below_Investment_Grade` means the company was measured as
junk and the floor still bound; `IG_Floor+Unavailable` means nothing could be measured and the bound
was used in place of a rating.

Two consequences to keep on record. The `Unavailable` path is unreached by all five companies today
— Boeing is the only floor case and it is `Below_Investment_Grade` — so the decision is untestable
end to end and must be pinned at the level of `synthetic_cost_of_debt` on constructed data instead.
And `COD_Alternative` is `None` on the `Unavailable` path where it holds the rejected synthetic rate
everywhere else; a reader of the output has to know that `None` there means "no synthetic rate
existed", not "the synthetic rate was zero".

**3. CLOSED 2026-08-29 — `price_reference` now names both failure modes.** Step 16 split absence from
staleness into two `raise` statements, but the absence branch re-raised inside `except ValueError`
without `from None`, so every traceback carried a "During handling of the above exception, another
exception occurred" chain — a sentence that means a bug in the handler, where in fact an expected
state was being translated deliberately. The message said "Failed to retrieve price data", which
reads as a technical failure rather than the actual state: no row at or before `as_of`. The staleness
message named neither the date found, nor the age, nor the bound it was measured against.

Both are rewritten. The absence branch drops the unused `as e`, raises `from None` — the underlying
`Too few prices` message carries nothing the new one does not — and says `No price data for {symbol}
on or before {as_of}`, where "on or before" makes the `date <= as_of` semantics of `get_prices`
readable: a reader knows immediately that re-fetching will not help for a date before the cache
begins. The staleness branch now reports the date, the bound and the age, per the convention that a
ratio is only quoted together with its window.

`test_price_bound` and `test_price_reference_absence` gained `match = "is older than"` and
`match = "No price data"`. The fragments carry no date and no number on purpose: a pattern containing
the age or the newest close would go red at the next price refresh with no code change behind it,
which is the same trap avoided by leaving `Realised` out of the COD pin above.

**Deferred by decision, not to be reopened as findings.** Point-in-time filings (`parser.py`
resolves newest-filing-wins at write time, step 6b). The retroactive price rewrite from
`auto_adjust = True` (step 16) — same scope, same deferral. The unguarded base level in
`project_revenue` (step 17), unreachable while `project_fcf` is its only caller.

#### Step 18 — das Geschäftsjahresfenster, auf das laufende Jahr geöffnet — DONE

Erster Punkt der Phase-5-Prüfung (externer Review, 2026-08-29, Finding 9). Zwei unabhängige
Jahresfenster schlossen das laufende Kalenderjahr per Konstruktion aus: `parser.py` →
`get_last_n_years` mit `range(cur_year - n, cur_year)` auf der Schreibseite und `database.py` →
`get_data` mit `range(start_year, datetime.now().year)` auf der Leseseite. Microsofts FY2026
(Ende 2026-06-30, eingereicht 2026-07-29, Umsatz 331,839 Mrd) und P&Gs FY2026 (eingereicht
2026-08-04, 87,032 Mrd) lagen fertig in `storage/*.json` und waren unerreichbar. Beide Grenzen
sind jetzt inklusiv.

**Was das kostete, solange es drin war.** Das erste projizierte Jahr war bei beiden ein Ist-Jahr,
und der Stub betrug 1,1362 Jahre statt 0,1369 — also rund ein volles Jahr Aufzinsung auf einen
Umsatzsockel, der bereits berichtet war. Die Brücke (Debt, Cash, Aktienzahl) stand auf einer 14
Monate alten Bilanz. `Data_Filed` meldete für Microsoft 2026-07-29, also das FY2026-10-K, obwohl
nur dessen Vorjahresvergleichszahlen verwendet wurden — der Vintage-Key war aktiv irreführend.

**Der Filter für nicht berichtete Jahre, und warum er dort steht, wo er steht.** Ein inklusives
Fenster materialisiert 2026 auch für Apple, Tesla und Boeing, deren Geschäftsjahr am 2026-08-19
noch nicht zu Ende ist. Ohne Filter schreibt `insert_data` dort 13 Zeilen mit `value = NULL`,
`dcf_value` nimmt `max(data)` als Basisjahr und bricht mit `ValueError: Missing Debt or
SharesOutstanding value` — gemessen, alle drei. Der Filter sitzt deshalb im Ingest-Block von
`database.py`, direkt nach `clean_values`, und entfernt Jahre, in denen kein einziger Slot einen
Wert trägt. Nicht in `get_values`: der läuft zweimal, mit `metrics` und mit `RECON_TAGS`, die
beiden Aufrufe verlieren unterschiedliche Jahresmengen, und `validation.py` →
`reconcile_working_capital` indiziert `recon_values[year]` für jedes Jahr aus `values` —
gemessen `KeyError: 2006`. `rec_values` muss eine Obermenge bleiben.

Das ist kein Verstoß gegen die Konvention, dass Absenz sichtbar bleibt. Ein nicht berichtetes
Geschäftsjahr ist kein fehlender Wert in einem vorhandenen Jahr; ein `None` dort würde behaupten,
das Jahr existiere und die Zahl fehle.

**Operativ.** `insert_data` schreibt per `ON CONFLICT DO UPDATE` und löscht nie. Eine
Fensteränderung erfordert deshalb einen Re-Ingest, und ein Fehlversuch hinterlässt Leerzeilen, die
ein später nachgerüsteter Filter nicht mehr entfernt — dann `DELETE FROM data WHERE year = 2026`,
die `flags` hängen per `ON DELETE CASCADE` daran. Der Ingest ist offline und deterministisch:
ein Kontrolllauf ohne Codeänderung reproduzierte alle fünf Werte bitgleich.

**Werte, `as_of = 2026-08-19`, `start_year = 2016`, `years = 10`, `freq = "1mo"`, Basis-WACC.**
Apple 132,7992, Tesla 11,6022 und Boeing 44,6770 bleiben unverändert — das ist die Kontrolle
dafür, dass der Filter nicht zu breit greift.

| | vorher | nachher | |
|---|---|---|---|
| microsoft VPS | 288,0109 | 291,6980 | +1,28% |
| procter_gamble VPS | 138,7314 | 133,7774 | -3,57% |
| `Stub_Years` beide | 1,1362 | 0,1369 | |
| Umsatzsockel MSFT / P&G | 281,72 / 84,28 Mrd | 331,839 / 87,032 Mrd | |
| `Margin_Start_Year`, `COD_Year` | 2025 | 2026 | |
| `COD_N` | 10 | 11 | |

**Die Vorzeichen sind gegenläufig, und das ist erwartbar.** P&G fällt trotz höherer Umsatzbasis,
weil der Wegfall eines Aufzinsungsjahres zu 6,86% schwerer wiegt als der um 3,3% höhere Sockel.
Bei Microsoft überkompensieren ein um 17,8% höherer Sockel und die höhere Marge denselben Verlust
zu 9,16%. Der WACC bewegt sich bei beiden um weniger als 0,3 Basispunkte — das Beta-Fenster hängt
an den Preisen, nicht an den Geschäftsjahren, und das ist die Gegenprobe dafür.

**Microsofts FY2026 ist bei `CapEx`, `D&A` und `NWC` als `outlier` geflaggt.** `driver_ratio`
entfernt den `outlier`-Flag bei `yoy`-Regeln bewusst (Schritt 2a), `CapEx` ist eine `yoy`-Regel,
das Jahr zählt also mit: `Mean_Last_Three` der CapEx-Intensität springt von 18,11% auf 25,33%.
Das ist der AI-Capex-Ramp, der ins Modell einwandert, und es ist die richtige Behandlung — ein
Niveausprung, kein Einmaleffekt. Es ist aber der zweitgrößte Einzeleffekt dieses Schritts und
erklärt, warum Microsofts `TV_Share` von 0,6128 auf 0,6890 steigt.

**Offen, bewusst vertagt.** `get_data` liest weiter gegen `datetime.now().year`, nicht gegen
`as_of`. Heute folgenlos, weil beide 2026 sind. Ab 2027-01-01 zieht das Fenster Teslas und Boeings
FY2026 in einen auf 2026-08-19 gepinnten Lauf — Look-ahead, und die Golden Values gehen ohne
Codeänderung rot. Dieselbe Fehlerklasse wie der an die Wanduhr gebundene Horizont aus Schritt 2b.
Der Fix ist ein `as_of`-Parameter auf `get_data` und damit eine Signaturänderung mit sechs
Aufrufstellen; er gehört gebündelt mit den übrigen Phase-5-Findings.

Zweitens: `MC_GOLDEN` in `tests/test_golden_values.py` steht für Microsoft und P&G noch auf den
Werten von vor diesem Schritt und ist rot. Entscheidung vom 2026-08-29: die Monte-Carlo-Werte
werden einmal am Ende aller Phase-5-Fixes neu gepinnt, nicht nach jedem einzelnen. Bis dahin
läuft die Suite als `pytest -m "not slow"` — 57 passed, 30 deselected. Genau dafür existiert der
`slow`-Marker.

#### Step 19 — die Reinvestitionsnaht geschlossen — DONE

Finding 1 des externen Reviews. Die zehn expliziten Jahre bauten den FCF von unten auf
(`nopat + da - capex - dnwc`, aus gemessenen Quoten), die Terminalzeile von oben ab
(`nopat * terminal_growth / terminal_roic`). Marge und Steuersatz treffen sich an der Naht bereits
exakt — bei `i == years` ist `m_t` gleich `EBIT_MARGIN` und `t_t` gleich `MARGINAL_TAX_RATE` —,
die Reinvestition nicht. Gemessener FCF-Sprung: Apple -13,8%, Microsoft +93,6%, P&G -7,3%,
Tesla -300,1% (Vorzeichenwechsel), Boeing +8,4%. Der implizierte ROIC in Jahr 10 lag bei Apple bei
1030%, weil die Kapitalbasis über die Projektion auf 36% schrumpfte, während der Umsatz um 51%
wuchs.

**Gelöst in `model.py` → `project_fcf`:** die Nettoreinvestition ist jetzt eine Mischung aus dem
Quotenwert `capex + dnwc - da` und dem Steady-State-Wert `nopat * terminal_growth / terminal_roic`,
gewichtet mit `i / len(projected_years)` — demselben Fadeprofil, das `m_t` und `t_t` benutzen. Bei
`i == years` ist das Gewicht 1, Jahr 10 rechnet damit schon nach der Terminalregel, und die Naht
schließt konstruktionsbedingt: gemessener Sprung 1e-16 bei allen fünf. Der `if i == years`-Block
wurde nicht angefasst, `PV_TV` und `Implied_Multiple` sind unverändert.

**Zwei Alternativen gemessen und verworfen.** Die Terminalzeile der expliziten Phase folgen zu
lassen (Apple 143,13, Tesla 4,72) schreibt eine gemessene Quote in die Ewigkeit fort: bei Apple
-1,5%, also dauerhafter Kapitalabbau bei 2,5% ewigem Wachstum, bei Tesla 139,6%, was einen ROIC von
1,8% gegen einen WACC von 11,26% impliziert. Die explizite Phase ganz an `terminal_roic` zu hängen
(Apple 117,32, Tesla 18,95) ist konsistent, wirft aber Schritt 4b weg: zehn Jahre Cashflow hingen
dann allein an einer handgesetzten Zahl in `ASSUMPTIONS`. Die gewählte Variante hält beide früheren
Entscheidungen — gemessene Quoten dort, wo sie Evidenz sind, Steady-State-Identität dort, wo sie
gelten muss.

| | vorher | nachher |
|---|---|---|
| apple | 132,7992 | 128,1716 |
| microsoft | 291,6980 | 328,3643 |
| procter_gamble | 133,7774 | 131,7907 |
| tesla | 11,6022 | 15,7087 |
| boeing | 44,6770 | 50,4251 |
| `PV_Explicit` (Mrd) | 900,63 / 643,16 / 120,65 / -8,96 / 17,62 | 837,33 / 912,18 / 116,08 / 5,44 / 21,92 |
| `Reinvestment_Rate` Jahr 1 | nicht gefüllt | -0,9% / 43,5% / 6,1% / 120,8% / 65,1% |
| `Reinvestment_Rate` Jahr 10 | nicht gefüllt | `terminal_growth / terminal_roic` |

**Zwei Tests haben die Änderung korrekt gefangen.** `test_margin_start_zero_operating_income`
(Schritt 17) lief in eine `ZeroDivisionError`, weil `Reinvestment_Rate` durch `nopat` teilt und der
Testfall ein Operating Income von 0 fährt; die Quote ist dort jetzt `None`, nicht `0` — `0` wäre
eine gemessene Quote und behauptet mehr als bekannt ist. Der `Reinvestment`-Betrag bleibt definiert.
Und `test_tv_share` pinnte Teslas `TV_Share_Source` auf `"PV_Explicit <= 0"`; Teslas `PV_Explicit`
dreht mit dieser Änderung von -8,96 auf +5,44 Mrd, `TV_Share` ist 0,7473, die Sonderbehandlung im
Test ist entfallen. Der Guard aus Schritt 5 hört bei Tesla auf zu feuern, weil die Ursache weg ist,
nicht weil der Guard geändert wurde.

**Was das nicht löst.** `terminal_roic` steht weiter handgesetzt in `ASSUMPTIONS` und trägt jetzt
zehn Jahre statt eines. Gemessen kostet das wenig — die Spannweite über `terminal_roic ± 5pp` geht
bei Apple von 3,7% auf 5,5%, bei Boeing von 20,7% auf 24,4% —, weil der Terminalblock ohnehin
dominierte. Der Konsistenztest zwischen `terminal_roic` und der eigenen Terminalmarge (Finding 7)
wird durch diesen Schritt überhaupt erst aussagekräftig. Zweitens steuert `TERMINAL_GROWTH` über
`terminal_growth / terminal_roic` jetzt auch die explizite Phase — die Materialität von Finding 3
ist damit gestiegen. `MC_GOLDEN` bleibt weiter ungepinnt bis zum Ende der Phase-5-Fixes; Suite läuft
als `pytest -m "not slow"`, 57 passed.

#### Step 20 — `TERMINAL_GROWTH` begründet und nach oben begrenzt — DONE

Finding 3 des externen Reviews: 15 Treffer für `TERMINAL_GROWTH` in dieser Datei, alle mechanisch,
keiner leitet die 2,5% her. Bei 51–75% TV-Anteil trägt die Konstante mehr Wert als jede andere
Einzelzahl, und seit Schritt 19 steuert sie über `terminal_growth / terminal_roic` zusätzlich die
explizite Phase. Gemessene Spanne über 1,5%–3,5%: Boeing 35,6%, P&G 33,9%, Microsoft 17,5%,
Apple 15,6%, Tesla 1,3%. Zum Vergleich: der Cost of Debt, für den zwei volle Schritte aufgewendet
wurden, bewegt 1,6–20,1 Basispunkte WACC.

**Die Begründung, die gefehlt hat.** Ewiges Wachstum ist eine Aussage über die Volkswirtschaft,
nicht über die Firma: auf unendlicher Sicht wächst kein Unternehmen schneller als die Wirtschaft,
in der es sitzt, sonst wird es irgendwann größer als sie. 2,5% = Inflationsziel 2% plus ein halber
Punkt real. Die Obergrenze ist der risikofreie Zins, weil der 10-Jahres-Nominalzins die beste im
Modell verfügbare Näherung für langfristiges nominales Wachstum ist — und er ist bereits datiert,
gecacht und an `as_of` gebunden.

**Firmenspezifisches `g` wurde geprüft und verworfen.** Die Differenzierung zwischen den Firmen
steht längst in der expliziten Phase — `base`, Margen-Fade, `terminal_roic`. Ein zweites Mal in der
Perpetuität zu differenzieren ist der Hebel, über den sich Optimismus unauffällig einschleusen
lässt; P&Gs 33,9% Spanne zeigt, wie viel daran hängt. Nicht erneut aufmachen.

**Umgesetzt in `valuation.py` → `dcf_value`.** Der Deckel steht direkt nach `calc_wacc`, weil
`wacc_calc["Risk_Free_Rate"]` erst dort bekannt ist. `resolve_assumptions` musste dafür unter
`calc_wacc` wandern: dessen `terminal_roic <= terminal_growth`-Prüfung muss gegen den effektiven
Wert laufen, nicht gegen den übergebenen. Das war gefahrlos, weil `settings` erst in der
WACC-Schleife gebraucht wird. `Terminal_Growth` meldet jetzt den effektiven Wert, `Terminal_Growth_Source`
unterscheidet `Assumption from TERMINAL_GROWTH` von `Terminal growth ceiling` — ohne diesen zweiten
Schlüssel liest sich ein gedeckelter Wert im Output wie eine gewählte Annahme, und genau diese
Unterscheidung ist der Zweck des Schritts.

**Kein Wert bewegt sich.** 2,5% liegt weit unter den 4,65% des Stichtags; alle fünf `Value_Per_Share`
sind bitgleich. Der Deckel ist heute unerreichter Code — dieselbe Lage wie der `Unavailable`-Pfad aus
Schritt 14 und aus demselben Grund akzeptabel: `test_terminal_growth` pinnt ihn an der Funktion
selbst, mit `terminal_growth = 0.05` gegen den rf von 4,65% am `as_of`, und prüft beide Zustände des
Source-Schlüssels. Ein Test nur auf den gedeckelten Wert wäre auch grün geblieben, wenn der
Source-Schlüssel wieder verschwindet. Suite 57 → 58.

#### Step 21 — der Terminal-ROIC-Konsistenztest als Diagnose — DONE

Finding 7 des externen Reviews, durch Schritt 19 überhaupt erst aussagekräftig: erst seit die
Nettoreinvestition pro Jahr definiert ist, lässt sich die Kapitalbasis im Terminaljahr aus dem
Modell selbst ableiten. `IC` im Terminaljahr = `roic(data)["IC_Last"]` plus die über die zehn
expliziten Jahre kumulierte Nettoreinvestition; der implizierte ROIC ist der Terminal-NOPAT gegen
diese Basis. Damit stehen zwei unabhängige Aussagen über dieselbe Größe nebeneinander — die
handgesetzte in `ASSUMPTIONS` und die aus Marge, Umsatz und Reinvestition folgende.

| | `terminal_roic` gesetzt | impliziert | Umschlag nötig | Umschlag 2025 | WACC |
|---|---|---|---|---|---|
| apple | 20,0% | 121,5% | 5,21x | 10,41x | 9,03% |
| microsoft | 20,0% | 26,9% | 0,78x | 0,90x | 9,16% |
| procter_gamble | 20,0% | 20,8% | 1,21x | 1,11x | 6,86% |
| tesla | 12,0% | **6,4%** | 1,87x | 2,02x | 11,26% |
| boeing | 15,0% | 11,9% | 3,32x | 2,40x | 8,04% |

**Tesla ist der Befund.** Der implizierte ROIC von 6,4% liegt unter dem WACC von 11,26%: das Modell
lässt die Firma im Terminaljahr Kapital zu einer Rendite unter ihren Kapitalkosten einsetzen und
rechnet ewiges Wachstum trotzdem als wertneutral bis positiv ein. Das ist kein konservativer Ansatz,
sondern ein innerer Widerspruch. Boeing zeigt dieselbe Richtung milder — gesetzte 15% gegen
implizierte 11,9%, bei einem nötigen Kapitalumschlag von 3,32x gegen tatsächliche 2,40x. Microsoft
und P&G bestehen den Test; ihre Annahme ist konservativ und der nötige Umschlag liegt beim
historischen. Apples 121,5% ist ein Artefakt der negativen gemessenen Reinvestition, kein Befund —
gepinnt wird es trotzdem, weil es sich bewegt, sobald jemand die Driver-Fenster anfasst.

**Diagnose statt Kopplung, bewusst entschieden.** `terminal_roic` automatisch aus der eigenen
Projektion abzuleiten würde die Zahl zirkulär machen — das Modell bestätigte sich selbst. Die beiden
Größen stehen deshalb als `Implicit_ROIC` und `Capital_Turnover` auf der TV-Zeile in
`model.py` → `project_fcf` und werden von `valuation.py` → `dcf_value` in die Ausgabe gehoben. Der
Umschlag ist die Hälfte, die man gegen eine externe Zahl halten kann; der ROIC allein ist schwer
einzuordnen.

**Das Flag sitzt in `dcf_value`, nicht in `project_fcf`,** weil der WACC dort nicht bekannt und pro
Zeile verschieden ist. `ROIC_Consistency` kennt drei Zustände — `Consistent`,
`Implicit_ROIC < WACC` und `Unavailable`, letzteres wenn `IC_Last` fehlt und die Diagnoseschlüssel
`None` bleiben. Kein `raise`: Tesla ist ein Ergebnis, das man sehen will, kein Abbruchgrund —
dieselbe Logik wie bei `TV_Share_Source`.

**Ein Off-by-one beim Bauen gefunden und behoben.** `implicit_roic` und `cap_turnover` standen
zuerst vor der Neuzuweisung von `cur_rev`, `ebit` und `nopat` auf die Terminalwerte, maßen also den
Gewinn von Jahr 10 gegen die Kapitalbasis des Terminaljahrs — Apple 118,5% statt 121,5%. Die
gepinnten Werte haben das gefangen. Die Kapitalbasis selbst summiert bewusst nur die zehn expliziten
Jahre: die Reinvestition der TV-Zeile passiert *im* Terminaljahr und kann dessen Gewinn nicht
erwirtschaftet haben.

Keine Wertänderung, der Schritt rechnet nur mit. Suite 58 → 68.

#### Step 22 — das Lesefenster an `as_of` gebunden, Monte Carlo neu gepinnt — DONE

Der Nachtrag aus Schritt 18, geschlossen 2026-08-30. `database.py` → `get_data` las gegen
`datetime.now().year`; ab dem ersten Ingest im Januar 2027 hätte ein auf 2026-08-19 gepinnter Lauf
Teslas und Boeings FY2026 mitgezogen. `get_data` nimmt jetzt `as_of` als ISO-String und verwirft
jedes Geschäftsjahr, dessen frühestes `Filed` später als der Stichtag liegt.

**Die Jahreszahl reicht nicht, und das war die eigentliche Korrektur am ursprünglichen Plan.** Ein
Schnitt `year <= as_of.year` behebt genau den benannten Fall nicht: Teslas FY2026 endet am
2026-12-31 und wird um den 2027-01-29 eingereicht — die Jahreszahl 2026 passiert einen 2026er-Schnitt
anstandslos. Das Prädikat muss das Einreichungsdatum sein, nicht die Periode.

**Jahresebene, nicht Zeilenebene, und der Grund ist unangenehm.** `filed` ist das Datum des *letzten
Schreibvorgangs*, nicht der Erstveröffentlichung: newest-filing-wins überschreibt die Vorjahreszahlen
mit dem jeweils neuesten 10-K. Gemessen tragen 12 von 13 Zeilen von Microsofts FY2025 das Datum
2026-07-29, also das der FY2026-Einreichung. Ein zeilenweiser Schnitt vor dem letzten Ingest würde
damit fast die gesamte Historie ausräumen. Der Schnitt liegt deshalb auf dem Minimum der
Filing-Daten eines Jahres.

**`Filed IS NULL` darf nichts entscheiden.** Das ist exakt der Marker für den fehlenden Metrikwert —
683 Zeilen, keine einzige davon mit `value`. Ohne expliziten Ausschluss aus dem `min()` verschwindet
Apples `InterestExpense` 2024/2025 als Schlüssel statt als Wert, und `COD_Year` kippt von 2023 auf
2025. Das ist die Absenz-Falle aus der `CLAUDE.md`: `cost_of_debt` ist gegen `Value is None`
geschrieben, nicht gegen einen fehlenden Key.

**Eine unbeabsichtigte Abhängigkeit, die dabei sichtbar wurde.** Über alle 52 Firmenjahre ab 2016 ist
das früheste `Filed` eines Jahres *ausnahmslos* das von `SharesOutstanding` — der einzige Tag, den
kein späteres Filing überschreibt, weil er auf der Titelseite steht und nur im eigenen Bericht
vorkommt. Die Jahresvintage hängt damit faktisch an einer einzigen Metrik. Heute folgenlos (0 Jahre
ohne `SharesOutstanding`), aber es ist kein Design, sondern ein Nebeneffekt, und es gehört bei jedem
Eingriff in `WORKING_CAPITAL_TAGS` oder die Metrikliste mitgedacht.

**Was der Schritt nicht löst.** Der Schnitt entscheidet, *ob* ein Geschäftsjahr am Stichtag existierte,
nicht *welche Zahlen* damals veröffentlicht waren. Ein rückdatierter Lauf liest weiterhin die heute
restated Werte. Point-in-time bleibt vertagt (Schritt 6b), die Lücke ist nur kleiner geworden.

**Kein Wert bewegt sich am Stichtag** — das neueste `Filed` im Cache ist 2026-08-04, alle fünf
`Value_Per_Share` sind bitgleich. Der Schnitt ist damit unerreichter Code am Stichtag und musste an
`get_data` selbst gepinnt werden, dieselbe Lage wie beim Terminal-Growth-Deckel aus Schritt 20:

| Aufruf | `max(data)` | Jahre | 2025 `Revenue` |
|---|---|---|---|
| `get_data("microsoft", 2016, "2026-06-30")` | 2025 | 10 | belegt |
| `get_data("microsoft", 2016, "2026-08-19")` | 2026 | 11 | belegt |

`test_data_vintage` pinnt beide Zustände plus die Gegenprobe auf `Revenue` — die ist der wichtigste
Teil, weil sie als einzige einen späteren Umbau auf einen zeilenweisen Schnitt rot macht.
`test_vintage_keeps_missing` pinnt, dass Apples `InterestExpense` 2025 als Schlüssel mit `Value =
None` überlebt. `CUT_PG` für P&Gs engen Fall (Schnitt 2026-08-01, eingereicht 2026-08-04) wurde
verworfen statt tot stehenzulassen.

**`MC_GOLDEN` neu gepinnt, und die Erwartung aus Schritt 18 war zu eng.** Dort stand, nur Microsoft
und P&G seien rot. Tatsächlich haben die Schritte 19 bis 21 alle fünf bewegt — die
Reinvestitionsnaht wirkt auf jede Projektion:

| `Mean` | vorher | nachher | |
|---|---|---|---|
| apple | 132,2248 | 127,6177 | -3,5% |
| boeing | 41,3822 | 47,2773 | +14,2% |
| microsoft | 289,2342 | 325,6492 | +12,6% |
| procter_gamble | 142,2740 | 132,4579 | -6,9% |
| tesla | 14,7857 | 18,7348 | +26,7% |

P&Gs `P_Above_Market` fällt von 0,399 auf 0,1905. Suite 68 → 70 → **100 passed** ohne Marker-Filter.

**Offen, beim Neupinnen aufgefallen.** Der Monte Carlo ist nicht um den Basisfall zentriert, wo die
gewählte `margin_base` am Rand der Margenspanne sitzt. Teslas `Margin_Range` ist
(0,0459 / 0,0459 / 0,0953) — Modus gleich Minimum, Maximum das 2,1-fache —, der MC-Median liegt
damit 16,5% über dem Basiswert von 15,7087. Boeing kippt in die Gegenrichtung, -9,0%. Bei den
übrigen drei liegen Median und Basiswert unter 2% auseinander. Die Dreiecksverteilung ist damit bei
zwei von fünf Firmen keine Streuung um das Ergebnis, sondern eine einseitige Verschiebung davon.
Das ist eine Aussage über die Wahl der Margenbänder, nicht über das Unternehmen, und gehört vor
Phase 4 entschieden — ein Dashboard, das Median und Basisfall nebeneinander zeigt, macht die
Differenz sonst zu einer Erkenntnis.

#### Step 23 — die Bewertungslücke pro Hebel zurückgerechnet — DONE

Phase 5 fragt, ob die Abweichung zum Marktpreis mit plausiblen Inputs erreichbar ist oder nur mit
unplausiblen. Bis hierhin wurde das von Hand pro Firma beantwortet und war nicht reproduzierbar.
`valuation.py` → `implied_assumptions` dreht die Rechnung um: pro Stellschraube den Wert lösen, der
`Value_Per_Share` auf den Marktpreis hebt, und ihn gegen eine aus den eigenen Daten gezogene
Schranke stellen. Dazu `_lever_value` als Kapselung eines einzelnen `dcf_value`-Aufrufs.

Vier Hebel, weil `dcf_value` genau vier numerische Overrides hat, die ohne Eingriff in `model.py`
von außen gesetzt werden können: `ebit_margin`, `wacc_offset`, `terminal_growth`, `nwc_intensity`.
Jeder wird einzeln gelöst, die anderen drei bleiben auf Basis — sobald zwei gleichzeitig laufen, ist
es kein Zerlegen mehr, sondern ein Fit auf den Marktpreis.

**Die Schranken kommen aus der Historie, nicht aus einer Meinung.** `ebit_margin` gegen die höchste
je erreichte `OperatingIncome/Revenue` über die sauberen Jahre aus `driver_ratio(...)["Years"]`,
`nwc_intensity` gegen die niedrigste `NWC/Revenue` derselben Auswahl, `wacc_offset` gegen die halbe
Breite des eigenen WACC-Konfidenzintervalls, `terminal_growth` gegen den Deckel aus Schritt 20.
Richtung jeweils die, in die der Hebel den Wert hebt: Maximum bei der Marge, Minimum bei der
NWC-Intensität. `Ratio` ist der geforderte Wert geteilt durch die Schranke, `Verdict` ist
`Plausible` bei `Ratio <= 1`.

**Drei Fallen, die den Solver sonst still falsch machen.** Erstens muss die untere WACC-Grenze
`WACC_Low` freihalten, nicht `WACC`: `dcf_value` rechnet alle drei Beine, und `terminal_value` wirft
am tiefsten zuerst — mit `-(wacc - g)` liefert jede einzelne Firma `no_bracket`, und der stärkste
Hebel im Modell meldet nichts. Zweitens wird `terminal_growth` in `dcf_value` still auf den
RF-Deckel zurückgeschnitten; ohne die Deckel-Probe (ein `dcf_value`-Aufruf mit
`terminal_growth = 1.0`, der den wirksamen Wert zurückgibt) bisektiert der Solver in eine flache
Zone oberhalb des Deckels und meldet einen Punkt darin als Lösung. Drittens ist die Richtung nicht
einheitlich — Marge und Terminal Growth heben den Wert, WACC-Offset und NWC-Intensität senken ihn;
eine fest verdrahtete Vergleichsrichtung dreht zwei von vier Hebeln um.

**`unreachable` ist ein eigener Status, kein zurückgegebener Randwert**, und `Ratio` bleibt dort
`None`. Sonst geht "Apple braucht 4,65% Terminal Growth" als Ergebnis durch, obwohl der Deckel dort
nur bis 158,92 trägt statt bis 305,93.

Gemessen bei `as_of = 2026-08-19`, `start_year = 2016`, `years = 10`, Deckel 0,0465 für alle fünf:

| Symbol | Gap | `ebit_margin` | `wacc_offset` | `terminal_growth` | `nwc_intensity` | `Closable` |
|---|---|---|---|---|---|---|
| apple | -58,1% | 0,8990 / 2,81x | -0,0403 / 4,95x | unreachable | unreachable | - |
| microsoft | -33,6% | 0,7288 / 1,56x | -0,0216 / 2,25x | unreachable | unreachable | - |
| procter_gamble | -8,8% | 0,2550 / 1,05x | -0,0037 / **0,51x** | **0,0303** / 0,65x | unreachable | wacc_offset, terminal_growth |
| tesla | -95,4% | unreachable | unreachable | unreachable | unreachable | - |
| boeing | -78,2% | 0,1520 / 1,28x | -0,0359 / 3,66x | unreachable | unreachable | - |

**Einzeln schließt kein Hebel die Lücke, außer bei P&G.** Der jeweils stärkste Kandidat ist überall
der WACC, und der müsste bei Apple auf 5,00% und bei Boeing auf 4,44% — beides unter dem
risikofreien Satz von 4,65%. Als Einzelaussage pro Hebel heißt das: die Abweichung ist nicht mit
einer einzelnen vertretbaren Annahme erklärbar.

**Gemeinsam sieht es anders aus, und das korrigiert die naheliegende Schlussfolgerung.** Setzt man
alle vier Hebel gleichzeitig auf ihre Schranke, kommt heraus: apple 195,20 (-36,2% zum Markt),
microsoft 544,43 (+10,1%), procter_gamble 348,81 (+141,3%), tesla 57,82 (-83,1%), boeing 389,36
(+68,1%). Für Microsoft, P&G und Boeing liegt der Marktpreis also sehr wohl im erreichbaren Bereich
des Modells; nur Apple und Tesla bleiben auch gemeinsam unerreichbar. Die Einzelhebel-Tabelle darf
deshalb nicht als "das Modell hält die Marktpreise für nicht darstellbar" gelesen werden — sie sagt
nur, dass keine *einzelne* Annahme reicht.

**Mit der ausdrücklichen Einschränkung, dass der Terminal-Growth-Hebel die gemeinsame Rechnung
dominiert.** Bei P&G bringt er allein +67,4%, bei Boeing +60,5%. Ein ewiges Wachstum in Höhe des
risikofreien Satzes ist die äußerste Kante des Modells, kein plausibler Zentralwert; die
Gemeinschaftszahl ist damit eine Obergrenze des Erreichbaren, kein Szenario. Wer sie als Szenario
liest, hat den Deckel aus Schritt 20 als Prognose missverstanden.

**Was pro Firma übrig bleibt.** Boeing hängt fast vollständig an einem einzigen Eingang: die
Startmarge von 4,79% stammt aus einem gedrückten Jahr, und allein die historische Höchstmarge von
11,85% hebt den Wert um +244% auf 173,45. Tesla ist der einzige Fall, in dem gar nichts trägt —
implizite ROIC 6,4% unter WACC 11,26%, mehr Explizitjahre senken den Wert (20 Jahre: 13,38), und
selbst die gemeinsame Obergrenze liegt um den Faktor 5,9 unter dem Markt. Das ist entweder eine
Aussage über den Markt oder eine über den Modellumfang (kein Energie-/FSD-Geschäft separat
modelliert), und es ist mit den vorhandenen Hebeln nicht entscheidbar. Apple liegt dazwischen und
zeigt auf die beiden Eingänge, die das Instrument nicht abdeckt.

**Was das Instrument nicht abdeckt, und das ist der nächste offene Punkt.** `years` ist der stärkste
Hebel überhaupt für Microsoft (10 Jahre -33,6%, 20 Jahre -7,8%, 15 Jahre -21,1%), aber ganzzahlig
und damit nicht bisektierbar. Umsatzwachstum hat gar keinen numerischen Override; die drei
String-Basen spannen bei Apple nur 109,21 bis 136,43 gegen nötige 305,93, ein numerischer Parameter
würde `project_revenue`, `project_fcf` und `dcf_value` anfassen. Und der Vergleich läuft weiterhin
gegen den Marktpreis, nicht gegen Konsens-Kursziele — Phase 5 verlangt letzteres ausdrücklich, und
dafür existiert im Projekt keine Datenquelle.

#### Step 24 — der Prognosehorizont als Hebel — DONE

Der erste der drei in Schritt 23 offenen Punkte. `years` war dort als stärkster Einzelhebel für
Microsoft gemessen (10 Jahre -33,6%, 15 Jahre -21,1%, 20 Jahre -7,8%), steckte aber nicht im
Instrument — die Aussage "keine einzelne Annahme schließt die Lücke" war damit über einen
unvollständigen Hebelsatz getroffen. `valuation.py` → `implied_horizon` schließt das.

**Scannen statt bisektieren.** Ein `dcf_value`-Aufruf kostet bei warmem Cache rund 8 ms, die 30
Horizonte also gut 0,2 s pro Firma. Bisektion würde nichts Messbares sparen, aber Monotonie
voraussetzen, die niemand geprüft hat; der lineare Scan liefert die vollständige Kurve, die Richtung
und den besten erreichbaren Punkt ohne Zusatzkosten mit. Die Kurve bleibt als `Curve` im Ergebnis.

**Die Richtung wird aus der Kurve gelesen, nicht gesetzt.** Dieselbe Falle wie bei den vier Hebeln
aus Schritt 23: Apple, Microsoft, P&G und Boeing steigen mit dem Horizont, Tesla fällt — von 18,67
bei einem Jahr auf 11,73 bei dreißig. Das ist der numerische Beleg für die bisher nur behauptete
Aussage implizite ROIC 6,4% unter WACC 11,26%: jedes zusätzliche Explizitjahr vernichtet dort Wert.
Eine verdrahtete Richtung würde bei Tesla im `unreachable`-Zweig das falsche Randjahr als besten
Punkt melden.

**Bewusst keine fünfte Zeile in `specs` und nicht Teil von `plausible_ceiling`.** Technisch, weil
`_lever_value` `years` bereits positional an `dcf_value` reicht — ein `**{"years": ...}` löst dort
`TypeError` aus, den die vorhandene `except ValueError`-Absicherung nicht fängt. Inhaltlich, weil
die gemeinsame Obergrenze aus Schritt 23 "alle Hebel gleichzeitig an ihrer historisch belegten
Kante" bedeutet, und der Horizont keine solche Kante hat.

**Und das ist die eigentliche Schwäche dieses Hebels: seine Schranke ist eine Konvention, keine
Messung.** Marge, NWC-Intensität, WACC und Terminal Growth ziehen ihre Grenze aus den eigenen Daten
der Firma; für `years` gibt es keine solche Quelle. Gesetzt sind deshalb
`IMPLIED_YEARS_COMPARATOR = 15` und `IMPLIED_YEARS_BOUNDS = (1, 30)`, beide als offen deklarierte
Annahme — `Comparator_Source` steht als Konventionsname im Ergebnis, und `Bounds` und `Comparator`
reisen mit, weil "unreachable" sonst nicht interpretierbar ist.

Gemessen bei `as_of = 2026-08-19`, `start_year = 2016`, Basis `years = 10`, `bounds = (1, 30)`,
`comparator = 15`:

| Symbol | 10 Jahre | 15 Jahre | 30 Jahre | Richtung | `Required_Years` | `Ratio` | `Verdict` |
|---|---|---|---|---|---|---|---|
| apple | 128,17 | 139,71 | 168,07 | steigend | - | - | unreachable |
| microsoft | 328,36 | 389,91 | 603,24 | steigend | 23 | 1,53 | Implausible |
| procter_gamble | 131,79 | 133,43 | 137,28 | steigend | - | - | unreachable |
| tesla | 15,71 | 14,44 | 11,73 | fallend | - | - | unreachable |
| boeing | 50,43 | 63,48 | 107,14 | steigend | - | - | unreachable |

**Der Hebel dreht kein Urteil, und genau das ist sein Beitrag.** Microsoft scheitert jetzt
quantifiziert statt gar nicht bewertet zu werden: 23 nötige Jahre gegen 15 vertretbare, Faktor 1,53.
Die anderen vier bleiben im Bereich unerreichbar.

**Der Deckel trägt das Urteil, nicht die Rechnung — nachgemessen.** Ohne obere Grenze erreicht
Boeing den Marktpreis bei 63 Jahren und P&G bei 94; beide kippen dann formal auf `solved`. Als
Prognose ist das sinnlos, als Befund über das Instrument ist es zentral: der Unterschied zwischen
"unerreichbar" und "erreichbar" liegt hier allein in einer gesetzten Zahl. `test_horizon_bounds_decide`
in `tests/test_golden_values.py` nagelt beide Zustände nebeneinander fest, damit das im Testcode
steht und nicht nur hier. Nur Apple und Tesla sind auch ohne Deckel unerreichbar — Apple konvergiert
bei 100 Jahren gegen 235,99 statt der nötigen 305,93, Tesla fällt auf 7,16.

**Ein toter Pfad, bewusst stehen gelassen.** Die `try`/`except`-Klammer im Scan und das `Failures`-
Dict können derzeit nicht auslösen: kein `raise ValueError` in `dcf_value`, `project_fcf` oder
`terminal_value` hängt an `years`, und der Basisaufruf läuft mit derselben Konfiguration bereits
vorher durch. Entweder ist die Kurve vollständig belegt oder die Funktion kommt nie bis zum Loop.
Die Struktur bleibt trotzdem, falls je ein jahresabhängiger Abbruch dazukommt; `assert
val["Failures"] == {}` ist damit heute eine Tautologie und keine Absicherung.

**Offen bleiben die zwei anderen Punkte aus Schritt 23.** Umsatzwachstum hat weiterhin keinen
numerischen Override — die drei String-Basen spannen bei Apple nur 109,21 bis 136,43 gegen nötige
305,93, und ein numerischer Parameter würde `project_revenue`, `project_fcf` und `dcf_value`
anfassen. Und der Vergleich läuft weiter gegen den Marktpreis statt gegen Konsens-Kursziele, wofür
im Projekt keine Datenquelle existiert.

#### Step 25 — Umsatzwachstum als numerischer Hebel — DONE

Der zweite der drei in Schritt 23 offenen Punkte. Umsatzwachstum war dort nur über drei String-Basen
verstellbar, die bei Apple 109,21 bis 136,43 gegen nötige 305,93 spannen — als Hebel also gar nicht
messbar. `model.py` → `project_revenue` und `project_fcf`, `valuation.py` → `dcf_value` und die
`specs`-Tabelle in `implied_assumptions` schließen das mit einem numerischen `revenue_growth`.

**Der Override setzt den Startwert des Fades, nicht eine konstante Rate.** `project_revenue`
interpoliert weiterhin linear von `growth` auf `terminal_growth` über den Horizont; der Parameter
ersetzt nur den Startpunkt und schaltet `Source` auf `"Override"`. Eine konstante Rate über alle
Explizitjahre wäre der andere denkbare Schnitt, hätte aber die Fade-Logik des Modells umgangen und
den Hebel mit dem Terminal-Growth-Hebel verkoppelt.

**Die Richtung ist gemessen, nicht gesetzt.** Ein Scan über -0,50 bis +2,00 ist bei allen fünf Firmen
streng monoton steigend — auch bei Tesla, das beim Horizont-Hebel aus Schritt 24 fällt. Der
Unterschied ist sauber erklärbar: mehr Explizitjahre verlängern dort einen wertvernichtenden Pfad
(impliziter ROIC 6,4% unter WACC 11,26%), mehr Umsatz skaliert dagegen auch die Terminalbasis.

**Die Bracket-Obergrenze ist 2,0, und das ist eine Lehre aus Schritt 24.** Tesla löst bei 1,2878. Mit
der naheliegenden 1,0 stünde dort `unreachable`, und das Urteil käme wieder aus einer gesetzten Zahl
statt aus dem Comparator — genau der Vorwurf gegen den `years`-Deckel. Bei `IMPLIED_GROWTH_BOUNDS =
(-0.5, 2.0)` löst jede Firma, die Schranke trägt nirgends ein Urteil. Die Reserve bei Tesla ist mit
Faktor 1,55 allerdings dünn genug, dass eine spätere Datenänderung sie kippen kann.

**Comparator ist `max(Rates)`, das höchste historische Jahreswachstum.** `growth_rate` gibt die
Einzelraten dafür neu als `Rates` heraus, auch im `Insufficient`-Zweig. Formal ist das konsistent mit
`Max_Hist_OI_Margin` und `Min_Hist_NWC_Intensity`: der beste je erreichte eigene Wert der Firma.
Ökonomisch ist es die weichste Schranke im ganzen Satz — eine Spitzenmarge ist ein Niveau, eine
Spitzenwachstumsrate ist eine Ableitung, und sie als Startwert eines Zehnjahres-Fades zu setzen
behauptet bei Tesla 82,5% Wachstum im ersten Projektionsjahr. Das ist bewusst so gewählt und bewusst
als Schwäche notiert.

Gemessen bei `as_of = 2026-08-19`, `start_year = 2016`, `years = 10`:

| Symbol | `Base` | `Required` | `Comparator` | `Ratio` | `Verdict` |
|---|---|---|---|---|---|
| apple | 0,0630 | 0,3144 | 0,3326 | 0,95 | Plausible |
| microsoft | 0,1461 | 0,2621 | 0,1796 | 1,46 | Implausible |
| procter_gamble | 0,0260 | 0,0479 | 0,0728 | 0,66 | Plausible |
| tesla | 0,0560 | 1,2878 | 0,8251 | 1,56 | Implausible |
| boeing | 0,1226 | 0,4657 | 0,3450 | 1,35 | Implausible |

**Das korrigiert zwei Aussagen aus Schritt 23.** Erstens: "Einzeln schließt kein Hebel die Lücke,
außer bei P&G" gilt nicht mehr. Apple schließt sie mit `revenue_growth` bei Ratio 0,95, `Closable`
steht dort jetzt auf `["revenue_growth"]`. Die Aussage war über einen unvollständigen Hebelsatz
getroffen, genau wie beim Horizont. Zweitens: "Apple und Tesla bleiben auch gemeinsam unerreichbar"
ist tot — die gemeinsame Obergrenze erreicht jetzt bei allen fünf Firmen den Marktpreis.

| Symbol | Deckel alt | Deckel neu | `Ceiling_Gap` neu | Beitrag `revenue_growth` | `Dominant` |
|---|---|---|---|---|---|
| apple | 195,20 | 518,29 | +69,4% | 323,09 | revenue_growth |
| microsoft | 544,43 | 617,14 | +24,8% | 72,71 | terminal_growth |
| procter_gamble | 348,81 | 425,44 | +194,3% | 76,64 | terminal_growth |
| tesla | 57,82 | 708,88 | +107,1% | 651,06 | revenue_growth |
| boeing | 389,36 | 947,98 | +309,2% | 558,62 | ebit_margin |

**Und damit hat der Hebel den gemeinsamen Deckel als Indikator entwertet.** `Reachable` ist jetzt bei
allen fünf Firmen `True`. Vorher trennte die Kennzahl drei erreichbare von zwei unerreichbaren
Firmen; jetzt trennt sie nichts mehr. Das ist kein Messergebnis über die Firmen, sondern eine Folge
davon, wie weit `max(Rates)` die Kante schiebt — ein Indikator, der bei jedem Input dasselbe sagt,
trägt keine Information. Wer den Deckel weiter als Aussage lesen will, braucht einen härteren
Comparator; naheliegend wäre das Maximum derselben Statistik, die auch die Basis liefert, also über
rollierende Dreijahresmittel statt über Einzeljahre. Bei Tesla fiele die Schranke damit deutlich
unter 0,8251 und die `Ratio` würde überall härter. Bewusst nicht jetzt geändert, weil das denselben
Eingriff bei `max_OI` und `min_NWC` nach sich ziehen müsste, um konsistent zu bleiben.

**Apples 0,95 ist ein Grenzfall, kein Urteil.** `project_revenue` rundet `g_t` auf vier
Nachkommastellen, der Wert ist im `revenue_growth` also eine Treppenfunktion mit Stufenbreite rund
1,1e-4 im ersten Projektionsjahr. Die Bisektion konvergiert gegen eine Stufenkante, nicht gegen einen
Punkt: alles hinter der vierten Stelle von `Required` ist reproduzierbares Rauschen. Ob Apple bei
0,95 oder über 1,00 landet, hängt an der dritten Stelle des Comparators. "Plausible" heißt dort
"nicht unterscheidbar von der historischen Kante", nicht "plausibel".

`LEVER_GOLDEN` in `tests/test_golden_values.py` ist auf den Fünf-Hebel-Deckel repinnt, 152 Tests
grün. Die vier bestehenden `Required`-Werte pro Firma stehen bitweise unverändert — das ist der
Beleg, dass `implied_assumptions` jeden Hebel unabhängig löst und die fünfte `specs`-Zeile die
anderen nicht bewegt. `Subset_Ceiling` und `Subset_Reachable` sind ebenfalls unverändert, weil
`LEVER_SUBSET` den neuen Hebel nicht enthält.

**Beide Nacharbeiten sind erledigt.** Der `Source`-String aus `dcf_value` meldete die aufgelöste
`ASSUMPTIONS`-Basis auch dann, wenn `revenue_growth` gesetzt war — Apple lieferte mit Override 306,05
bei `Source = 1mo+Growth_Rate_Median+gordon`, obwohl der Median von 6,3% nicht benutzt wurde. Der
String liest jetzt `fcf[min(fcf)]["Growth_Rate_Source"]` statt `base` und meldet damit `Override`. Das
ist derselbe Wert, der schon als `Revenue_Growth_Source` in der Zeile steht; er wird einmal gebunden
und zweimal benutzt. Die Bindung steht innerhalb der WACC-Schleife, weil `fcf` pro Szenario neu
projiziert wird — außerhalb hätte sie den letzten Durchlauf für alle drei gemeldet.

**Der `max(Rates)`-Punkt war überzeichnet, der Guard bleibt trotzdem.** Eine leere Liste ist an dieser
Stelle strukturell unerreichbar: `implied_assumptions` ruft `dcf_value` schon in Zeile 347 auf, und
`project_revenue` wirft bei `Source == "Insufficient"` vorher `ValueError("Growth_Rate_Median is not
defined")` — nachgemessen an Boeing mit `start_year = 2023`, n = 2. `implied_assumptions` prüft jetzt
selbst auf `growth["Source"] == "Insufficient"` und wirft mit Symbol und `n`, statt die Invariante aus
`model.py` zu erben. Der Guard prüft die Quelle, nicht `len(rates) == 0`: bei n = 1 oder 2 käme sonst
ein Comparator aus einem einzigen Jahr zurück, und der sieht aus wie eine Zahl. Dieselbe Kante bei
`max_OI` und `min_NWC` bleibt ungeschützt.

**Dabei aufgefallen, offen:** mit dünnem `start_year` stirbt der Pfad noch vor der Wachstumsbasis.
`implied_assumptions("boeing", 2023, ...)` bricht mit `KeyError: 2021` in `wacc_calculation.py` →
`debt_to_equity` ab, weil das Beta-Fenster über Jahre iteriert, die im `data`-Dict nicht existieren.
Das ist die echte ungeschützte Kante bei kurzen Fenstern, und sie liegt in Phase 3c, nicht hier.

Der Bracket-Test ist mit `test_tesla` erledigt: bei `GROWTH_NARROW_BOUNDS = (-0.5, 1.0)`, per
`monkeypatch.setattr` auf das Modulattribut gesetzt, kippt Tesla auf `unreachable` mit `Required =
1.0` und `Ratio is None`. Das ist das Gegenstück zu `test_horizon_bounds_decide` und hält fest, dass
die Schranke bei 2,0 kein Urteil trägt, bei 1,0 aber sehr wohl eins tragen würde.

#### Der externe Anker für Phase 5 — entschieden

**Der dritte offene Punkt aus Schritt 23 war falsch formuliert.** Er lautete, es existiere im Projekt
keine Datenquelle für Konsens-Kursziele. Die Alternative liegt seit 2026-08-27 vor: die externen
DCF-Fair-Value-Ranges, die Gregor pro Firma geliefert hat (Gemini-Recherche, Stand August 2026, nicht
unabhängig verifiziert). Eine bessere Quelle gibt es hier nicht — Analystenkonsens ist über yfinance
und FRED, die beiden Marktdatenpfade des Projekts, nicht erreichbar, und eine bezahlte Quelle
anzubinden wäre ein Datenprojekt statt eines Bewertungsprojekts. Damit ist Phase 5 anker-seitig
bedient, mit dem ausdrücklichen Vorbehalt, dass die Range weicher ist als ein echter Konsens.

**Die Range ist ein zweiter Anker, kein Ziel.** Das Modell wird nicht darauf getuned; sie dient dazu,
Abweichungen zu dimensionieren. Gemessen bei `as_of = 2026-08-19`, `start_year = 2016`, `years = 10`,
Preis aus dem `1mo`-Fenster per 2026-07-31:

| Symbol | Basis-VPS | externe Range | Markt | Deckel (5 Hebel) |
|---|---|---|---|---|
| apple | 128,17 | 175–285 | 308,64 | 518,29 |
| microsoft | 328,36 | 380–530 | 464,72 | 617,14 |
| procter_gamble | 131,79 | 135–175 | 144,49 | 425,44 |
| tesla | 15,71 | 130–450+ | 311,21 | 708,88 |
| boeing | 50,43 | 160–390 | 216,14 | 947,98 |

**Zwei Ablesungen, und beide sind unbequem.** Erstens liegt der Basisfall jetzt bei allen fünf Firmen
unter der Untergrenze der externen Range, auch bei P&G — in der Notiz vom 2026-08-27 lag P&G mit 144
noch innerhalb, seither haben die Schritte 17 bis 22 den Wert auf 131,79 gedrückt. Der einzige Fall,
der das Modell je extern bestätigt hat, ist damit weg. Zweitens überschießt der gemeinsame Deckel bei
allen fünf Firmen die Obergrenze der Range, bei Boeing um Faktor 2,4 und bei P&G um Faktor 2,4. Der
Deckel soll die Kante des Plausiblen markieren; wenn er systematisch über dem oberen Ende einer
unabhängig erstellten Spanne liegt, sind die Comparatoren zu weich. Das ist derselbe Befund wie in
Schritt 25 über `max(Rates)`, nur diesmal von außen bestätigt statt aus der eigenen Konstruktion
abgeleitet.

**Was daraus folgt und was nicht.** Es folgt nicht, dass die Range recht hat — sie ist unverifiziert
und selbst modellbasiert. Es folgt, dass zwei unabhängige Instrumente in dieselbe Richtung zeigen:
der Basisfall ist zu konservativ, die Plausibilitätskante zu großzügig, und der Abstand zwischen
beiden trägt deshalb weniger Information als die Zahlen suggerieren. Die inhaltliche Konsequenz — ein
härterer Comparator über rollierende Dreijahresmittel statt über Einzeljahre, konsistent gezogen bei
`max_OI` und `min_NWC` — bleibt der nächste offene Punkt. Für Tesla bleibt der Fall unentscheidbar:
15,71 gegen eine Range, deren untere Hälfte auf das Autogeschäft allein zielt und die das Modell
trotzdem um Faktor 8 verfehlt, deutet auf den Modellumfang, nicht auf einen Rechenfehler.

#### Step 26 — der Comparator auf rollierende Dreijahresmittel — DONE

Der Deckel aus Schritt 25 hat aufgehört, etwas zu unterscheiden: `Reachable` stand bei allen fünf
Firmen auf `True`, und der gemeinsame Deckel überschoss jede Obergrenze der externen Range. Die
Ursache lag nicht im Solver, sondern im Comparator — ein einzelnes Spitzenjahr als Kante des
Plausiblen. `model.py` → `rolling_means` und `growth_rate`, `valuation.py` → `implied_assumptions`
setzen die Kante jetzt auf das beste zusammenhängende Dreijahresmittel.

**Die Fenster laufen über Jahre, nicht über Listenindizes.** `rolling_means(pairs, k)` nimmt
`(Jahr, Wert)`-Paare und verwirft jedes Fenster, dessen Jahre nicht lückenlos sind. Ohne diese
Prüfung mittelt der Flag-Filter stillschweigend über eine Lücke hinweg: fällt ein Jahr wegen eines
`recon_gap` heraus, stünden 2018, 2019 und 2021 nebeneinander und hießen weiter "Dreijahresmittel".
`growth_rate` gibt dafür die Startjahre der Ratenpaare als `Years` heraus — `sorted(data)` wäre die
falsche Liste, weil sie auch die verworfenen Jahre enthält und dann länger ist als `Rates`.

**Ein Fenster von drei Jahren, als Konstante.** `COMPARATOR_WINDOW = 3` in `model.py`, und die
`Comparator_Source`-Labels hängen per f-String daran, damit Fensterbreite und Beschriftung nicht
auseinanderlaufen. Drei ist dieselbe Breite wie bei `Mean_Last_Three`; ein längeres Fenster würde bei
n = 9 bis 10 die Zahl der Fenster so weit drücken, dass der Comparator wieder an einzelnen Jahren
hängt, nur verdeckt.

**Der Guard prüft die leere Fensterliste, nicht die Jahresanzahl.** `rolling_means` kann auch bei
n ≥ 3 leer zurückkommen, wenn kein Tripel zusammenhängt; `max()` würde dort wieder kontextlos werfen.
`implied_assumptions` bindet die drei Listen und wirft mit Symbol, Fensterbreite und Metrik. Für die
fünf Firmen ist das nicht auslösbar — Apple, Tesla und Boeing haben 7 Fenster, Microsoft und P&G 8.

Gemessen bei `as_of = 2026-08-19`, `start_year = 2016`, `years = 10`:

| Symbol | `max_OI` | `min_NWC` | `max_growth` |
|---|---|---|---|
| apple | 0,3197 → 0,3110 | −0,1307 → −0,1283 | 0,3326 → 0,1552 |
| microsoft | 0,4678 → 0,4568 | −0,1518 → −0,0994 | 0,1796 → 0,1638 |
| procter_gamble | 0,2426 → 0,2301 | −0,0396 → −0,0361 | 0,0728 → 0,0582 |
| tesla | 0,1676 → 0,1174 | −0,0706 → −0,0446 | 0,8251 → 0,5500 |
| boeing | 0,1185 → 0,0995 | 0,0282 → 0,0794 | 0,3450 → 0,1226 |

Die Marge bewegt sich kaum, das Wachstum halbiert sich fast. Das ist der erwartete Unterschied
zwischen einem Niveau und einer Ableitung: eine Spitzenmarge hält drei Jahre, eine Spitzenwachstums-
rate nicht. Boeings NWC-Intensität dreht als einzige in die unbequeme Richtung — 0,0794 statt 0,0282
ist eine härtere Schranke, weil das beste Einzeljahr dort ein Ausreißer in einer nicht-stationären
Reihe war (Schritt 4d).

**Und damit trennt `Reachable` wieder.**

| Symbol | Deckel | `Reachable` | `Closable` | `Subset_Ceiling` | `Subset_Reachable` |
|---|---|---|---|---|---|
| apple | 518,29 → 269,56 | True → False | `["revenue_growth"]` → `[]` | 147,27 → 144,20 | False |
| boeing | 947,98 → 320,15 | True | `[]` | 234,33 → 190,41 | True → False |
| microsoft | 617,14 → 568,06 | True | `[]` | 395,95 → 386,75 | False |
| procter_gamble | 425,44 → 380,14 | True | unverändert (3) | 167,41 → 159,47 | True |
| tesla | 708,88 → 217,01 | True → False | `[]` | 49,36 → 36,92 | False |

Herausgefallen sind genau Apple und Tesla — dieselben zwei, die Schritt 23 als die harten Fälle
benannt hatte, bevor der Umsatzhebel sie scheinbar erreichbar machte. Apples `Ratio` beim
Umsatzwachstum geht von 0,95 auf 2,03, der Grenzfall aus Schritt 25 ist keiner mehr. P&G bleibt die
einzige Firma mit plausiblen Einzelhebeln (0,824 beim Wachstum, 0,652 beim Terminal Growth, 0,508
beim WACC-Offset). Boeings Teilmenge kippt mit: 190,41 gegen 231,67 Marktpreis.

**Gegenprobe an der externen Range.** Der Deckel liegt jetzt bei Apple (270 gegen 285), Tesla (217
gegen 450) und Boeing (320 gegen 390) unter der Obergrenze der extern erhobenen Spanne, bei Microsoft
knapp darüber (568 gegen 530). Nur P&G bleibt mit 380 gegen 175 grob daneben — dort tragen Terminal
Growth und WACC-Offset zusammen 325 von 380, also die zwei Hebel, deren Comparator nicht aus der
Firmenhistorie stammt. Das ist der nächste Ansatzpunkt, falls der Deckel weiter geschärft werden
soll.

**Was sich ausdrücklich nicht bewegt hat.** Alle 25 `Required`-Werte in `LEVER_GOLDEN` stehen
bitweise unverändert, vor dem Neupinnen automatisch geprüft. Der Comparator geht nur in `Ratio`,
`Verdict` und `Override` ein, nicht in die Bisektion — hätte sich ein `Required` bewegt, wäre er in
den Solver geraten. Neu gepinnt sind `Ceiling_Value_Per_Share`, `Reachable`, `Dominant`,
`Contribution`, `Closable` und beide `Subset`-Werte; 158 Tests grün.

**Nebenbefund, offen und außerhalb dieser Phase.** Mit dünnem `start_year` bricht
`implied_assumptions` weiterhin vor allem anderen ab: `wacc_calculation.py` → `adjusted_beta` baut
sein D/E-Fenster aus der Preishistorie und indiziert damit in `data`, das erst bei `start_year`
beginnt. Boeing ab 2023 wirft `KeyError: 2021`. Der Fix wäre der Schnitt beider Fenster in
`adjusted_beta`, nicht in `debt_to_equity` — die Funktion wird auch mit `year = None` gerufen und darf
keine Fensterpolitik entscheiden.

#### Step 27 — das Beta-Fenster gegen die Datenreihe geschnitten — DONE

Der Nebenbefund aus Schritt 26, jetzt geschlossen. `wacc_calculation.py` → `adjusted_beta` baute sein
D/E-Fenster aus der Preishistorie (`N_MONTHS`, Dezember-Beobachtungen) und indizierte damit in `data`,
das erst bei `start_year` beginnt. Zwei unabhängige Fenster, und bei kurzem `start_year` enthielt das
erste Jahre, die das zweite nicht hat: Boeing ab 2023 warf `KeyError: 2021`.

**Der Schnitt liegt in `adjusted_beta`, nicht in `debt_to_equity`.** Die Jahresliste wird gegen `data`
gefiltert, bevor sie in die Mittelwertbildung geht, und eine leere Schnittmenge wirft. `debt_to_equity`
wird auch mit `year = None` für den aktuellen Stichtag gerufen und darf deshalb keine Fensterpolitik
entscheiden — ein Guard dort hätte den Gegenwartsfall mitbestraft.

**Das geschrumpfte Fenster bleibt sichtbar.** `adjusted_beta` gibt die tatsächlich benutzten Jahre als
`DE_Years` heraus. Ohne das ruhte `Beta_Unlevered` unbemerkt auf zwei Jahren statt fünf, und die
Verschuldungsanpassung ist der Schritt, der bei Boeing am meisten Hebel hat (Schritt 3b).

| Boeing, `as_of = 2026-08-19` | `DE_Years` | Beta |
|---|---|---|
| `start_year = 2016` | 2021–2025 | 1,1098 |
| `start_year = 2023` | 2023–2025 | 1,1361 |

Für alle fünf Firmen bei `start_year = 2016` ist die Schnittmenge vollständig, die Betas stehen
unverändert und 158 Tests sind grün. Zusammen mit den auf `COMPARATOR_WINDOW` umgestellten
`Comparator_Source`-Labels ist damit alles geschlossen, was Phase 5 an Code offen hatte. Offen bleibt
allein die Textentscheidung zu Tesla: 15,71 gegen eine externe Range, deren untere Hälfte nur das
Autogeschäft meint, ist eine Aussage über den Modellumfang und gehört als Scope-Grenze in die
Limitations-Sektion von Phase 7, nicht in eine weitere Annahme.

#### Phase 5 — Ergebnis und die Scope-Grenze bei Tesla — DONE

Phase 5 sollte die Modellwerte gegen einen externen Maßstab stellen und Abweichungen über 40% auf eine
Ursache zurückführen. Beides ist passiert, allerdings mit einem anderen Instrument als geplant: statt
eines Konsens-Kursziels trägt die extern erhobene Fair-Value-Range den Vergleich, und statt einer
Fehlersuche im Diskontierungspfad hat der Hebelsolver aus den Schritten 23 bis 26 die Abweichung pro
Eingang zerlegt.

**Das Ergebnis in einem Satz: der Basisfall ist bei allen fünf Firmen zu niedrig, und bei drei von
fünf lässt sich das mit plausiblen Eingängen nicht schließen.** `Reachable` steht nach Schritt 26 bei
Microsoft, P&G und Boeing auf `True`, bei Apple und Tesla auf `False`. Das ist die Aussage, die Phase 5
liefern sollte, und sie ist erst dadurch belastbar, dass der Comparator die Kante nicht mehr aus einem
einzelnen Spitzenjahr zieht.

**Tesla ist eine Scope-Grenze, keine Annahmefrage.** 15,71 gegen eine externe Spanne, deren untere
Hälfte (130–180) ausdrücklich nur das Autogeschäft bewertet, ist Faktor 8 — und der gemeinsame Deckel
aller fünf Hebel kommt mit 217,01 nicht an den Marktpreis von 342,27 heran. Kein Satz plausibler
Annahmen schließt das, weil das Modell Energie- und FSD-Geschäft nicht separat abbildet und ein
Segmentmodell ein anderes Projekt wäre. Die Konsequenz ist, das in Phase 7 als Grenze zu benennen,
statt weiter nach Annahmen zu suchen, die die Lücke rechnerisch schließen — jede solche Annahme wäre
Anpassung an den Preis, und genau das soll das Instrument aufdecken.

**Was Phase 5 nicht geleistet hat.** Der externe Anker ist unverifiziert und selbst modellbasiert,
also kein Konsens im engeren Sinn. Und P&G bleibt der Fall, in dem der Deckel mit 380 gegen eine
Obergrenze von 175 weit danebenliegt; dort tragen Terminal Growth und WACC-Offset zusammen 325 von 380,
also die beiden Hebel, deren Comparator nicht aus der Firmenhistorie stammt. Wer den Deckel weiter
schärfen will, muss dort ansetzen.

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

#### Phase 6 — die vier Entscheidungen vorab

Phase 6 stand mit vier offenen Punkten aus den Schritten 9, 12 und 26 in der Warteschlange. Alle vier
sind hier entschieden, bevor die erste Zeile Testcode entsteht, weil drei davon die Bedeutung von
`as_of` oder die Aussagekraft der gesamten Suite betreffen und nachträglich nicht mehr billig zu
drehen sind.

**1. Die Fixture-Datenbank wird eingecheckt, nicht `skipif`.** Alle 158 Tests hängen an
`storage/values.db`, die gitignored ist. Ein `skipif` auf die Existenz der Datei liefert in Actions
ein grünes Badge, unter dem 158 Tests geskippt sind — CI, die nichts prüft, ist schlechter als keine
CI, weil sie Vertrauen erzeugt, das sie nicht deckt. Gemessen: die echte Datenbank ist 17,6 MB, davon
entfällt fast alles auf `raw_downloads` (86 Zeilen mit vollständigen CSV-Bodies, die nur geschrieben
und nie gelesen werden). Ohne diese Tabelle und mit `rates` ab 2015-01-01 bleiben **708 KB** — eine
Größe, die in Git gehört. Verifiziert: 158 Tests grün gegen die getrimmte Kopie, 98 s.

Umgeleitet wird über `monkeypatch.setattr(database, "database", ...)` in einer autouse-Session-Fixture
in `tests/conftest.py`. `get_data`, `get_rate` und `get_prices` lesen das Modulglobal `database` erst
zur Aufrufzeit, deshalb greift das Repointing ohne eine einzige Änderung in `logic/`. Eine
Umgebungsvariable in `database.py` wäre die Alternative gewesen und wurde verworfen: sie verlegt
Testkonfiguration in den Produktionspfad, für einen Effekt, den die Fixture bereits hat.

**Der Preis, ausdrücklich benannt: `test_data_filed` verliert seine Rolle als Kanarienvogel.** Der
Test war in Schritt 9 genau dafür gebaut, einen Re-Ingest sichtbar zu machen (Boeing 80,54 auf 79,82).
Gegen eine eingefrorene Fixture kann er das nicht mehr — er wird tautologisch. Das Signal wandert
damit aus der Suite in das Regenerierungsskript: Fixture neu erzeugen, Goldens laufen lassen, und was
sich bewegt, ist die Datenbasis. Das ist ein echter Verlust an Automatik und kein Nebeneffekt, den man
wegdefinieren sollte.

**2. Der risikofreie Zins wird eingefroren, `as_of` bleibt unangetastet.** Die in Schritt 12 offene
Frage war, ob "newest row <= as_of" überlebt oder durch einen exakten Datums-Match mit Staleness-Fehler
ersetzt wird. Sie erledigt sich mit Entscheidung 1: die Fixture enthält `rates` bis 2026-09-01, bei
`AS_OF = 2026-08-19` liegt die neueste Zeile innerhalb von `RF_MAX_AGE_DAYS = 10`, `risk_free_rate`
greift nicht auf FRED zu, und der Lauf ist netzfrei und deterministisch. Der exakte Datums-Match wird
verworfen: er ändert für jeden Consumer, was `as_of` bedeutet, um ein Problem zu lösen, das die
Fixture bereits entfernt. Keine Änderung in `prices.py`.

**3. CI läuft die volle Suite, nichts wird per Marker abgewählt.** ubuntu-latest, Python 3.14 (die
lokale venv ist 3.14.6), `pip install -r requirements.txt`, `pytest`. Die sieben `@pytest.mark.slow`
markierten Monte-Carlo-Tests bleiben drin: der gesamte Lauf dauert rund 100 s, und gerade der Monte
Carlo mit `MC_SEED = 12345` ist der Teil, dessen Determinismus man in einer fremden Umgebung sehen
will. Ein `-m "not slow"` in CI würde die einzige Stelle abwählen, an der eine abweichende
NumPy-Version auffiele.

**4. `requirements.txt` wird als UTF-8 neu geschrieben.** Die Datei ist UTF-16 LE mit BOM, entstanden
aus `pip freeze >` in PowerShell, und ein Kandidat für `Invalid requirement` beim ersten Lauf in
Actions. 34 gepinnte Pakete, davon nur `colorama` mit Windows-Beigeschmack — das installiert unter
Linux sauber, die Liste bleibt inhaltlich unverändert.

**Korrektur zu Schritt 26.** Dort steht, die Kante bei `max_OI` und `min_NWC` bleibe bei n = 1 oder 2
ungeschützt. Das ist seit Schritt 27 nicht mehr richtig: `valuation.py` → `implied_assumptions` prüft
in der Schleife über `(("OperatingIncome", oi_windows), ("NWC", nwc_windows), ("Revenue_Growth",
growth_windows))` auf `len(windows) == 0` und wirft mit Symbol und Metrik. Ein zu kurzes Fenster kann
dort keinen Comparator aus einem einzelnen Jahr mehr liefern. Der Punkt ist erledigt und geht nicht als
Phase-6-Aufgabe weiter.

#### Phase 6 — was an Tests fehlt, nach Kosten eines stillen Fehlers geordnet

Die 158 bestehenden Tests sind ganz überwiegend end-to-end über `dcf_value`-Fixtures. Sie halten das
Ergebnis fest, nicht die Formel: sie sagen, dass sich 132,93 nicht unbemerkt bewegt hat, aber nicht,
dass 132,93 aus der richtigen Rechnung stammt. Das ist die Lücke, die Phase 6 schließt.

- **`wacc_calculation.py` → `calc_wacc`, `cost_of_equity`, `adjusted_beta`, `cost_of_debt`,
  `synthetic_rating`.** Keine dieser Funktionen hat einen handgerechneten Fall. Der Diskontsatz geht
  in jede Zahl des Modells ein und in den Terminalblock quadratisch; ein Vorzeichen- oder
  Klammerfehler hier bewegt alle fünf Firmen gleichgerichtet und sieht deshalb nach einer
  Modellaussage aus statt nach einem Bug. Höchste Priorität.
- **`valuation.py` → `terminal_value`.** Bisher nur indirekt über `TV_Share` gedeckt. Der Kantenfall
  ist `g >= wacc`: die Gordon-Formel liefert dann einen negativen oder explodierenden Wert, und der
  läuft ohne Guard bis ins `Value_Per_Share` durch. Genau diese Grenze pinnt Schritt 24 als
  `Terminal_Growth_Ceiling` — die Funktion selbst muss sie ebenfalls kennen.
- **`model.py` → `project_revenue`, `project_fcf`, `effective_tax_rate`, `driver_ratio`,
  `growth_rate`, `rolling_means`, `roic`.** Reine Funktionen auf Dicts, billig isoliert zu testen.
  `project_fcf` ist die Fehlerklasse aus Schritt 4d (eine Zeile eine Ebene zu tief, Boeing 48,01 auf
  -29,90). `rolling_means` ist aus Schritt 27 neu und trägt seit Schritt 26 alle Comparator-Fenster.
- **`validation.py` → `validate_values`, `reconcile_working_capital`, `check_recon_tolerance`.**
  Vollständig ungetestet, und das ist die Schicht, die entscheidet, welche Zahlen überhaupt ins Modell
  kommen. Ein zu lascher Flag lässt einen Ausreißer durch, ein zu scharfer wirft ein gültiges Jahr weg
  — beides ohne Spur im Ergebnis.
- **`parser.py` → `clean_values`, `get_last_n_years`, die Selektoren.** Nur die netzfreien Teile.
  `get_response` und `get_values` gehen gegen SEC EDGAR und gehören nicht in CI.

Kantenfälle, die die Phase laut Lernziel abdecken soll, konkret: `terminal_value` bei `g >= wacc`,
`project_fcf` mit einer Lücke mitten in der Jahresreihe, `growth_rate` unter `MIN_YEARS = 3` mit
`Source = "Insufficient"`, `roic` bei negativem Eigenkapital (Boeing ist der reale Fall),
`cost_of_debt` bei Schuldenstand null, `synthetic_rating` genau auf den Spread-Grenzen.

#### Schritt 28 — die Fixture-Datenbank steht — DONE

Punkt 1 der vier Phase-6-Entscheidungen, umgesetzt wie beschlossen. `tests/make_fixture.py` kopiert
`storage/values.db`, leert `raw_downloads`, schneidet `rates` bei `RATES_FROM = "2015-01-01"` ab,
ruft `VACUUM` nach dem Commit und druckt einen Report aus Dateigröße, `count(*)` je Tabelle und
`min(date)`/`max(date)` aus `rates`. Ergebnis: **724.992 Bytes**, data 1876, flags 1031, prices 2700,
rates 2918, raw_downloads 0, Zinsreihe von 2015-01-02 bis 2026-09-01.

`tests/conftest.py` leitet über eine autouse-Session-Fixture mit `pytest.MonkeyPatch.context()` das
Modulglobal `database.database` auf `tests/fixtures/values.db` um. `.gitignore` bekommt
`!tests/fixtures/values.db` als Negation zu `*.db`; `git status` führt die Datei als untracked, die
Negation greift also. `logic/` blieb unangetastet.

**`scope="session"` ist Korrektheit, nicht Optimierung.** `test_golden_values.py` baut seine
`result`-Fixture module-scoped. pytest richtet Fixtures von der weitesten Scope nach innen ein, eine
session-scoped Fixture ist damit garantiert vor jeder module-scoped fertig. Mit `scope="function"`
liefe die Umleitung nach dem ersten `dcf_value`-Aufruf — die Suite wäre grün, aber gegen
`storage/values.db` gerechnet.

**Der Guard existiert, weil `sqlite3.connect` bei fehlender Datei nicht scheitert, sondern eine leere
Datenbank anlegt.** Ohne ihn stirbt die Suite mit `no such table: data`, was nach kaputtem Schema
aussieht statt nach fehlender Fixture, und hinterlässt eine leere `values.db`, die den nächsten Lauf
durchwinkt.

**Grün beweist die Umleitung nicht, und das ist der wichtige Punkt.** Beide Datenbanken tragen
denselben Inhalt, die 158 Tests wären auch dann grün, wenn `mp.setattr` ins Leere liefe. Nachgewiesen
wurde es separat über einen `pytest_runtest_call`-Hook, der `database.database` zur Testlaufzeit
ausliest: er zeigt `testsixturesalues.db`. Zweite Absicherung: kein Modul macht
`from database import database` — alle vier Consumer importieren nur Funktionen, die das Modulglobal
erst zur Aufrufzeit lesen, deshalb erreicht der Patch jeden von ihnen.

**Was damit verloren geht, wie angekündigt:** `test_data_filed` ist kein Re-Ingest-Kanarienvogel mehr,
sondern ein Fixture-Drift-Detektor. Das Signal hängt ab jetzt daran, dass jemand `make_fixture.py`
laufen lässt.

#### Schritt 29 — CI auf GitHub Actions — DONE

Punkte 3 und 4 der Phase-6-Entscheidungen. `.github/workflows/tests.yml` läuft auf `push` und
`pull_request` gegen `main` plus `workflow_dispatch`, auf `ubuntu-latest`, mit
`actions/setup-python@v5` auf `python-version: "3.14"` und `cache: "pip"`, dann
`python -m pip install -r requirements.txt` und `pytest` ohne Argumente. **Erster Lauf grün, 158
Tests, 1m53s** — schneller als die lokal gemessenen 98 s plus Installation erwarten ließ.

Der Workflow weiß nichts über die Projektstruktur: `pytest.ini` im Root setzt die rootdir,
`tests/conftest.py` erledigt `sys.path` und die Umleitung. Wissen, das doppelt im YAML und in
`pytest.ini` stünde, wäre die erste Stelle, die auseinanderdriftet.

**Kein Netzzugriff, nachgemessen statt angenommen.** `get_rate("DGS10", "2026-08-19")` liefert aus der
Fixture die Zeile vom 2026-08-19 selbst, `age = 0` gegen `RF_MAX_AGE_DAYS = 10`. `risk_free_rate`
erreicht seinen `fetch_rates`-Zweig damit nie, und `fetch_prices` wird nur aus einem `__main__`-Block
gerufen. Beide Netzpfade des Projekts sind im Testlauf zu.

**`-m "not slow"` wurde bewusst nicht gesetzt.** Die sieben Monte-Carlo-Tests sind die einzigen, an
denen ein NumPy-Versionswechsel überhaupt sichtbar würde — `MC_SEED = 12345` ist nur so lange
deterministisch, wie der RNG-Stream derselbe ist. Der Lauf bestätigt, dass die gepinnte
`numpy==2.5.2` auf einem Linux-Runner dieselben Ziehungen liefert wie lokal auf Windows.

**Korrektur zu Entscheidung 4.** Die Begründung war falsch: pip liest die UTF-16-Datei anstandslos,
nachgemessen mit `pip install --dry-run`, weil pip das Encoding über sein vendored
`charset_normalizer` erkennt. Der echte Grund für die Umstellung ist git — eine Datei mit NUL-Bytes
in den ersten 8000 Bytes gilt als binär, und jeder Dependency-Bump erschiene als
`Binary files differ` statt als lesbare Zeile. Gemessen an zwei Kopien mit einer geänderten
Versionsnummer: UTF-16 `Bin 1238 -> 1238 bytes`, UTF-8 `1 insertion(+), 1 deletion(-)`. Die Datei ist
jetzt UTF-8 mit BOM; das BOM ist unschädlich, weil es keine NUL-Bytes enthält.

**Offen bleibt der Rest von Phase 6:** die Formeln in Isolation und die Kantenfälle, in der oben
notierten Reihenfolge — WACC-Kette, `terminal_value`, die reinen Funktionen in `model.py`,
`validation.py`, die netzfreien Teile von `parser.py`.

#### Schritt 30 — die WACC-Kette in Isolation — DONE

Erster der fünf Testblöcke aus der Phase-6-Liste. `tests/test_wacc.py`, 43 Tests, Suite jetzt bei
**201 grün in 95 s**. Getestet werden `synthetic_rating`, `cost_of_debt`, `synthetic_cost_of_debt`,
`debt_to_equity`, `adjusted_beta`, `cost_of_equity` und `calc_wacc` einzeln, gegen die Fixture bei
`AS_OF = "2026-08-19"` und `Risk_Free_Rate = 0.0465`.

**Handgebaute Dicts statt neuer Fixture-Zeilen.** Ein Helper `make_year` erzeugt Jahres-Dicts der
Form `{"Value": x, "Flag": []}`. Damit sind die Zweige erreichbar, die im echten Datensatz nicht
vorkommen: `synthetic_cost_of_debt` mit `Source = "Unavailable"`, `cost_of_debt` bei Schuldenstand
null, der Flag-Filter, und die beiden `calc_wacc`-Zweige. Neue Fixture-Zeilen wären die Alternative
gewesen und sind verworfen: sie würden alle bestehenden Golden Values verschieben, für Fälle, die
mit fünf Zeilen Testcode zu haben sind. Für die beiden `calc_wacc`-Zweige wird stattdessen eine
`deepcopy` der echten Apple-Daten punktuell verbogen, damit Preise und Beta real bleiben.

**Fund: die Spread-Tabelle hat vierzehn Lücken.** Jedes Band in `SPREADS` endet auf `...999`, das
nächste beginnt eine Dezimalstelle höher, dazwischen liegt ein Intervall ohne Eintrag. Gemessen:
`synthetic_rating(2.499995)` wirft `ValueError: Coverage ratio ... outside the spread table`. Die
breiteste Lücke liegt zwischen `2.49999` und `2.5`, also unmittelbar unter `INVESTMENT_GRADE` — genau
der Schwelle, über die `calc_wacc` seinen Floor legt. Ein Coverage-Ratio, das dort landet, sieht im
Traceback nach kaputten Daten aus, obwohl die Tabelle das Problem ist. `test_synthetic_rating_gaps`
pinnt den Zustand als Fund, nicht als Spezifikation; die Entscheidung, ob die Bänder auf
`high = next_low` umgestellt werden, ist offen.

**Der `outlier`-Carve-out ist derzeit wirkungslos.** `cost_of_debt` entfernt den Flag `outlier`, wenn
`OUTLIER_RULES` für die Position auf `"yoy"` steht — und für `InterestExpense` wie für `Debt` steht
sie das. Die Bedingung ist damit immer wahr. Der Test parametrisiert deshalb über zwei Flags
(`outlier` → `Calculated`, `missing` → `Insufficient`); ein Test nur auf `outlier` hätte die
Filterung überhaupt nicht geprüft.

**Zwei Invarianten statt Golden Values, wo es geht.** `adjusted_beta` entlevert über `DE_Window` und
relevert über `DE_Current`; mit einem monkeypatch auf das Modulglobal `wacc_calculation.debt_to_equity`,
der beide gleich macht, muss `Beta_Relevered == Beta_Raw` gelten. Das fängt ein vertauschtes
Zähler-Nenner-Paar, das eine Golden-Zahl nur als Bewegung melden würde. Ebenso in `calc_wacc`:
Gewichte summieren sich auf 1, und `WACC_Low <= WACC <= WACC_High`. `cost_of_equity` läuft ganz ohne
Datenbank, weil beide Argumente Dicts sind.

**Was die Zweigabdeckung über die Daten sagt.** Boeing ist die einzige Firma unter
`INVESTMENT_GRADE` und damit die einzige, die den `IG_Floor`-Zweig real erreicht: realisierter Satz
`0.04728184827492066`, Floor `0.0465 + 0.0111 = 0.0576`, Floor gewinnt. Apple ist der einzige Fall,
in dem `COD_Alternative` über den Rückfall auf `COD_FALLBACK_START_YEAR` entsteht, weil
`InterestExpense` in 2024 und 2025 den Flag `missing` trägt und ab 2023 nur ein Jahr übrig bleibt.
Derselbe Flag drückt Apples Coverage-Jahr auf 2023, obwohl Daten bis 2025 vorliegen —
`synthetic_cost_of_debt` nimmt `max(candidates)`, nicht `max(data)`, und das ist jetzt über den
`Year`-Key gepinnt.

**Nebenbefund, nicht behoben:** ein schuldenfreies Unternehmen ist im Modell nicht darstellbar.
`cost_of_debt` überspringt Jahre mit `Debt in (None, 0)` und landet bei `Insufficient`, und
`debt_to_equity` wirft bei denselben Werten hart. Das ist eine Scope-Grenze wie der Bankenausschluss,
keine Lücke im Code; der Test pinnt den `ValueError` als beabsichtigt.

**Offen bleibt der Rest von Phase 6:** `terminal_value` mit der Kante `g >= wacc`, die reinen
Funktionen in `model.py`, `validation.py` vollständig, und die netzfreien Teile von `parser.py`.

#### Schritt 31 — `terminal_value` in Isolation — DONE

Zweiter der fünf Testblöcke. `tests/test_valuation.py`, 10 Tests, Suite jetzt bei **211 grün in
92 s**. `terminal_value` trägt bei Apple 51,4 Prozent des Unternehmenswerts und war bisher nur
indirekt über `TV_Share` gedeckt.

**Korrektur zur Phase-6-Liste.** Dort steht, die Gordon-Formel liefere bei `g >= wacc` einen
negativen oder explodierenden Wert, der ohne Guard bis ins `Value_Per_Share` durchläuft. Das ist
falsch: `valuation.py:84` wirft `ValueError("WACC must be greater than Terminal Growth.")`, und zwar
auf `<=`, also auch bei Gleichheit. Nachgemessen, beide Fälle werfen. Der Kantenfall war kein Loch,
sondern ein ungetesteter Guard; die Aufgabe war Festnageln, nicht Einbauen. Stünde dort `<`, wäre
`wacc == terminal_growth` eine Division durch null mitten in der Bewertung.

**Die Funktion ist rein und wird auch so getestet.** Neun der zehn Tests laufen gegen handgebaute
Zeilen-Dicts aus einem Helper `val_dct(fcf, ebit, da)` — keine Datenbank, keine Symbole, kein
`as_of`. Der Testdatensatz `FCF_ROWS` hat drei Zeilen statt der minimal nötigen zwei, und die
älteste trägt absichtlich absurde EBIT- und D&A-Werte: `last_explicit` ist `sorted(fcf)[-2]`, und
mit nur zwei Zeilen wäre das dasselbe wie `[0]` — die Zeilenauswahl wäre ungeprüft. Das Dict-Literal
ist zusätzlich in verkehrter Jahresreihenfolge notiert, weil die Funktion selbst sortiert.

**`Implied_Multiple` bleibt Gordon-basiert, auch bei `method = "multiple"`.** Gemessen: bei
`exit_multiple = 8.0` gibt die Funktion `Terminal_Value = 1000.0` zurück, das `Implied_Multiple`
bleibt aber `11.0` statt `8.0`. Das ist Absicht — die Kennzahl beantwortet, welches Multiple die
Gordon-Annahme implizit unterstellt, und ist damit der Vergleichsmaßstab für das gesetzte. Ohne Test
liest das später jemand als vergessene Verzweigung und macht sie tautologisch.

**Zwei ungeschützte Stellen, gepinnt statt behoben.** `Implied_Multiple` teilt durch
`EBIT + D&A` der vorletzten Zeile, ohne den Nenner zu prüfen. Bei EBITDA gleich null fliegt ein
`ZeroDivisionError` — und zwar auch bei `method = "multiple"`, weil die Division im `return` steht,
also nach der Methodenverzweigung: die Funktion stirbt an einer Kennzahl, die sie für diese Methode
nicht braucht. Bei negativem EBITDA kommt ein negatives Multiple heraus, kommentarlos, und wandert
über `dcf_value` in die Ergebnis-Dicts; Boeing ist der reale Kandidat mit mehreren Jahren negativen
Operating Income. Beide Tests tragen `unguarded` im Namen, damit sie nicht als Spezifikation gelesen
werden. **Offene Entscheidung:** Guard oder `Source`-Marker. Die Projektkonvention spräche für einen
Marker — Abwesenheit soll sichtbar bleiben, und `None` sagt mehr als eine negative Zahl.

**Ein Test gegen echte Daten, als Strukturnachweis.** Eine module-scoped Fixture baut die Kette aus
`dcf_value` nach — `get_data`, `calc_wacc`, `resolve_assumptions`, `project_fcf` — und der Test prüft
`sorted(fcf) == list(range(2026, 2037))`, also elf Zeilen bei zehn Projektionsjahren. Genau diese
Struktur nehmen die neun synthetischen Tests als gegeben an, ohne sie je zu prüfen. Gemessen:
`Terminal_Value = 2011707660197.802`, `Implied_Multiple = 9.41545108964314` — letzteres identisch mit
`GOLDEN["apple"]["Implied_Multiple"]`, was die Verdrahtung bestätigt. **Fallstrick dabei:** das
dritte Argument von `project_fcf` ist der Terminal ROIC aus `ASSUMPTIONS` (Apple: 0,2), nicht der
WACC — `dcf_value` fällt nur dann auf den WACC zurück, wenn der Eintrag `None` ist. Mit der falschen
Verdrahtung kommt ein plausibler, aber anderer Terminal Value heraus.

**Was der Test nicht kann:** er baut die Verdrahtung nach, statt sie zu benutzen. Ändert `dcf_value`
seinen `project_fcf`-Aufruf, läuft er unverändert weiter. Er sichert die Zeilenstruktur ab, nicht die
Verdrahtung.

**Offen bleibt der Rest von Phase 6:** die reinen Funktionen in `model.py`, `validation.py`
vollständig, und die netzfreien Teile von `parser.py`.

#### Schritt 32 — die Messfunktionen in `model.py` — DONE

Dritter der fünf Testblöcke, und davon der erste von drei Teilen. `tests/test_model.py`, 46 Tests,
Suite jetzt bei **257 grün in 89 s**. Abgedeckt sind `effective_tax_rate`, `driver_ratio`,
`rolling_means` und `growth_rate` — die vier Funktionen, aus denen `project_fcf` jede Zahl seiner
Projektion zieht. Offen bleiben aus dem Block `project_revenue` und `roic` (Teil 2) sowie
`project_fcf` selbst (Teil 3).

**Der Schnitt ist nach Abhängigkeit gelegt, nicht nach Umfang.** Die vier hier getesteten Funktionen
nehmen ein Dict und geben ein Dict zurück, ohne Symbol, ohne `as_of`, ohne Preise; `rolling_means`
braucht nicht einmal die Datenbank. Alles darüber ruft sie auf. Damit liegt ein Fehler in Teil 3
danach nachweislich in Teil 3 und nicht in einem der Eingänge — die Reihenfolge ist der eigentliche
Nutzen des Blocks.

**`==` statt `pytest.approx`, anders als in den beiden vorigen Dateien.** `effective_tax_rate`,
`driver_ratio` und `growth_rate` geben `round(..., 4)` zurück; das Literal `0.0356` parst auf
denselben Double. Eine Toleranz vorzugeben, die die Funktion nicht hat, würde eine geänderte
Rundungsstelle durchwinken. `rolling_means` gibt ungerundet zurück und wird deshalb als einzige mit
`approx(rel = 1e-9)` geprüft.

**`Years` steht in jedem `driver_ratio`-Assert.** Ohne diesen Key ist ein Test grün, der die richtige
Zahl aus den falschen Jahren zieht. Boeing ist der Beleg: `OperatingIncome` läuft über
`[2016, 2017, 2018, 2022, 2023]` — fünf Einträge über einen Achtjahreszeitraum, weil 2019 bis 2021
und 2024 bis 2025 den Flag `outlier` tragen. Die Golden-Tabelle führt deshalb alle vier Metriken für
Apple als Formprobe und `OperatingIncome` für alle fünf Firmen, weil nur dort der Flag-Filter real
Jahre entfernt.

**Fund: `Mean_Last_Three` mittelt die letzten drei sauberen Einträge, nicht die letzten drei Jahre.**
Gemessen bei Boeing `OperatingIncome`: `0.0186` aus 2018, 2022 und 2023 — ein Fünfjahresfenster unter
dem Namen "Last_Three". `rolling_means` prüft Kontiguität ausdrücklich über
`w[-1][0] - w[0][0] != k - 1`, `driver_ratio` mit demselben `[-3:]`-Slice nicht. Das kollidiert mit
der Projektkonvention, dass eine Kennzahl nur zusammen mit ihrem Fenster definiert ist. Gepinnt, nicht
behoben — `Mean_Last_Three` ist der `margin_base` von Apple, eine Änderung verschiebt die Golden
Values.

**Fund: `effective_tax_rate` prüft nur den Flag auf `Tax`, nicht den auf `PretaxIncome`**
(`model.py:18`). `test_effective_tax_rate_pretax_flag_ignored_unguarded` belegt es an drei Jahren mit
`outlier` auf `PretaxIncome`: die Funktion liefert `Source = "Median"` über alle drei. In den echten
Daten ist das heute folgenlos — Boeing 2025 ist der einzige Fall, und Boeing scheitert ohnehin an
`MIN_YEARS` und landet bei `Fallback` mit `n = 2`. Genau dieser `Fallback`-Zweig existiert im
Datensatz nur bei Boeing; fiele es aus der Parametrisierung, wäre er ungetestet.

**Der `outlier`-Carve-out greift hier, anders als in Schritt 30.** `driver_ratio` entfernt den Flag
nur, wenn `OUTLIER_RULES[metric][0] == "yoy"` ist. Bei `cost_of_debt` war dieselbe Bedingung immer
wahr und damit wirkungslos; hier läuft die Funktion über Metriken mit verschiedenen Regeln, also
behält `D&A` (`yoy`) das geflaggte Jahr und `OperatingIncome` (`margin_change_pp`) verliert es. Der
Test parametrisiert über beide Metriken mal `outlier`/`missing`, sonst wäre nur die eine Hälfte
geprüft.

**Zwei rohe Exceptions, gepinnt statt behoben.** `effective_tax_rate` wirft bei
`PretaxIncome = 0.0` einen `ZeroDivisionError` — der Guard in Zeile 18 prüft nur auf `None`.
`rolling_means` wirft bei `k = 0` einen `IndexError`, weil `pairs[i:i]` leer ist und `w[-1]` daneben
greift. Dazu eine dritte, stille Kante: `rolling_means` sortiert nicht, die Kontiguitätsprüfung ist
gerichtet, und unsortierte Paare liefern kommentarlos ein anderes Ergebnis. Alle drei tragen
`unguarded` im Namen.

**Der Helper heißt `row(flags = None, **values)` und ist bewusst nicht `make_year` aus
`tests/test_wacc.py`.** `model.py` fasst zehn verschiedene Positionen an (`Tax`, `PretaxIncome`,
`Revenue`, `D&A`, `CapEx`, `NWC`, `OperatingIncome`, `Debt`, `Cash`, `Equity`); eine feste Signatur
wie dort wäre eine Zehn-Parameter-Zeile, von der jeder Test zwei benutzt. `test_wacc.py` blieb
unangetastet — eine grüne Datei für einen gemeinsamen Helper anzufassen, kauft nichts.

**Eine Fixture lädt, die andere parametrisiert.** `all_data` ist module-scoped und lädt die fünf
Firmen einmal; `data_result` ist darüber parametrisiert und reicht `(symbol, data)` durch. Zwei
unabhängige Fixtures mit je eigenem `get_data` hätten dieselben fünf Datensätze zweimal geholt, ohne
dass ein Test davon profitiert.

**Offen bleibt der Rest von Phase 6:** `project_revenue` und `roic`, dann `project_fcf`, danach
`validation.py` vollständig und die netzfreien Teile von `parser.py`.

#### Schritt 33 — `project_revenue` und `roic` in Isolation — DONE

Zweiter Teil des dritten Testblocks. `tests/test_model.py` wächst auf 75 Tests, Suite jetzt bei
**286 grün in 93 s**. Damit sind alle Eingänge von `project_fcf` gepinnt; offen bleibt aus dem Block
nur `project_fcf` selbst.

**Korrektur zur Phase-6-Liste.** Dort steht `roic` bei negativem Eigenkapital, "Boeing ist der reale
Fall". Das trifft nicht zu: `roic` rechnet mit `IC = Debt + Equity - Cash`, und Boeings Schulden
überdecken das negative Eigenkapital der Jahre 2019 bis 2024 in jedem einzelnen Jahr — `IC` läuft von
523 Mio (2016) auf 37,3 Mrd (2025), durchgehend positiv. **Apple ist der Fall:** `IC` ist von 2016
bis 2021 negativ, Tiefpunkt -22,3 Mrd, weil die Nettoliquidität Schulden plus Eigenkapital
übersteigt. Apple ist die einzige der fünf Firmen mit `Source = "Insufficient"`, und der Zweig wäre
ungetestet geblieben, wenn man ihn bei Boeing gesucht hätte.

**Fund: `Source = "Insufficient"` ist klebrig und rückwirkend.** Ein einziges Jahr mit `IC <= 0`
setzt die Variable, und der Guard am Ende (`len(roics) >= MIN_YEARS and source != "Insufficient"`)
verwirft danach alle bereits berechneten Werte. Apple berechnet drei gültige ROICs aus 2023, 2024
und 2025 — genau `MIN_YEARS` — und bekommt trotzdem `None`, allein wegen der Jahre 2016 bis 2021.
Gepinnt, nicht behoben; ob eine Kennzahl über eine alte Bilanzlage die aktuelle löschen soll, ist
eine offene Entscheidung.

**Fund: `IC_Last` überlebt `Insufficient` und kommt aus `max(data)`, nicht aus `max(dct)`.** Apple
liefert `ROIC_Median = None` und gleichzeitig `IC_Last = 39,97 Mrd`, und genau dieser Wert geht in
`project_fcf` als `cap_basis` in die Terminalzeile — die Kennzahl ist also aus, die Kapitalbasis
läuft weiter. Umgekehrt reicht ein `None` in einer der vier Positionen des letzten Datenjahres, damit
`IC_Last` `None` wird, während `ROIC_Median` weiterrechnet; dann fallen `Implicit_ROIC` und
`Capital_Turnover` in der TV-Zeile still auf `None`. Beide Hälften stehen als synthetische Fälle im
Test.

**`roic` prüft überhaupt keine Flags, nur auf `None`.** Ein als `outlier` markiertes `Equity` geht
voll ein. Das ist der Gegensatz zu `driver_ratio` und `effective_tax_rate` und steht als eigener
Fall (`flag_ignored`) im Test, damit es nicht als Versehen gelesen wird.

**Apple steht bewusst nicht in `ROIC_GOLDEN`.** `pytest.approx(None)` wirft, und die Tabelle wird
über `list(ROIC_GOLDEN)` parametrisiert — Apple darin hätte `test_roic_golden` mitgerissen. Dieselbe
Konstruktion wie bei Teslas `TV_Share` in `test_golden_values.py`. Apple bekommt einen eigenen Test
mit Literalen.

**Die erste `Growth_Rate` ist nie die Basisrate.** `g_t` fadet schon bei `i = 1`, Apples Median
`0.063` erscheint im ersten Projektionsjahr als `0.0592`. Die Golden-Tabelle führt deshalb die
gefadete Zahl, nicht die Basis. Gegenstück dazu die Invariante über alle fünf: die `Growth_Rate` des
letzten Projektionsjahres ist exakt `TERMINAL_GROWTH` — das ist der Test, der festhält, dass der Fade
ankommt.

**Die acht mittleren Projektionsjahre bleiben ungepinnt.** Vierzig weitere Golden-Zahlen für einen
linearen Fade, dessen Endpunkte, Länge und Terminalrate schon stehen. Ein Vorzeichen- oder
Rundungsfehler in der Mitte verschiebt `rev_last`. Nicht gedeckt ist eine Vertauschung zweier
mittlerer Jahre bei gleichem Produkt — konstruierbar, aber keine reale Fehlerklasse.

**Microsoft und P&G projizieren ab 2027, die anderen drei ab 2026.** Beide haben ein Geschäftsjahr
2026 in der Fixture. Das erste Projektionsjahr steht deshalb in `REV_GOLDEN` und nicht als Literal im
Test.

**Zwei stille Kanten, gepinnt.** `years = 0` gibt kommentarlos `{}` zurück, ohne `raise` — der Test
trägt `unguarded` im Namen. Und `revenue_growth = True` wirft, weil die Prüfung
`type(growth) not in (int, float)` lautet und nicht `isinstance`; mit `isinstance` liefe `True` als
100 Prozent Wachstum durch, da `bool` von `int` erbt. Hier ist die schärfere Variante die richtige,
der Test hält sie fest.

**Offen bleibt der Rest von Phase 6:** `project_fcf`, dann `validation.py` vollständig und die
netzfreien Teile von `parser.py`.

#### Schritt 34 — `project_fcf` in Isolation — DONE

Dritter Teil und Abschluss des dritten Testblocks. `tests/test_model.py` steht bei 119 Tests, Suite
bei **330 grün in 88 s**. Damit ist `model.py` vollständig abgedeckt; offen bleiben von Phase 6
`validation.py` und die netzfreien Teile von `parser.py`.

**Der Grund für den Block war Schritt 4d** — eine Zeile eine Ebene zu tief, Boeing von 48,01 auf
-29,90, ein Vorzeichenwechsel, der nur durch manuelles Nachrechnen aufgefallen ist. Die Funktion
läuft jetzt gegen fünf Firmen mit `terminal_roic = 0.2`, `years = 10` und sonst Defaults.

**Der zentrale Fund: die letzte explizite Zeile ist blind für alle drei Treiber.** `net_reinvest`
mischt `capex + dnwc - da` und `reinvestment_rate * nopat` über `w = i / len(projected_years)`. Bei
`i == years` ist `w = 1`, der erste Term fällt vollständig heraus, und die letzte explizite Zeile
hängt nur noch an NOPAT und der Terminal-Reinvestitionsrate. Gemessen: `nwc_intensity = 0.1` und
`metrics` komplett auf `Mean_Last_Three` verändern den FCF dieser Zeile um exakt null, den des ersten
Projektionsjahres dagegen um 4,4 respektive 1,5 Mrd. Ein Golden nur auf der letzten Zeile — die
naheliegende Wahl, weil sie an den Terminalblock grenzt — hätte den gesamten Treiberpfad ungetestet
gelassen. `FCF_GOLDEN` führt deshalb erste Zeile, letzte explizite Zeile und TV-Zeile.

**Die Gegenprobe dazu als Invariante:** `Reinvestment_Rate` der letzten expliziten Zeile ist exakt
`TERMINAL_GROWTH / TERMINAL_ROIC`, also 0,125, und identisch mit der der TV-Zeile. Das hält fest,
dass der Übergang am Ende ankommt, ohne eine weitere Golden-Zahl zu kosten.

**Die erste Projektionszeile ist als eigener Test über elf Keys parametrisiert** — `Revenue`, `EBIT`,
`NOPAT`, `D&A`, `CapEx`, `dNWC`, `FCF`, `EBIT_Margin`, `Tax_Rate`, `Reinvestment`,
`Reinvestment_Rate`. Ein Assert pro Key statt eines Tupels, damit bei einem Fehler der Name der
kaputten Position im Report steht und nicht ein elfstelliges Tupel.

**Boeing ist der einzige `Last_Actual_Flagged`-Fall.** Sein `OperatingIncome` trägt 2025 den Flag
`outlier`, die anderen vier starten den Margin-Fade auf `Last_Actual`. Der Zweig setzt nur ein Label
und beeinflusst keine Zahl — genau deshalb würde er sonst nie auffallen.

**Fund: die Fehlermeldung für eine ungültige Metrik nennt nichts.** `metrics = {"D&A": "Bogus"}`
wirft `ValueError: Unkown metric: []` — die Prüfung im `any(...)` deckt Keys und Values ab, die
Liste in der Meldung filtert aber nur über die Keys. Ein falscher Wert erzeugt damit eine leere
Liste. Dazu der Tippfehler "Unkown". Beides so gepinnt, wie es ist; ein Fix an der Meldung wäre
Kosmetik in `logic/` und gehört in die gesammelte Liste am Ende der Phase.

**`years = 0` gibt eine einzelne Nullzeile zurück**, keine TV-Zeile und kein `raise`, weil `value`
über `range(last_year + 1, last_year + 2 + years)` vorbelegt wird und die Schleife nie läuft. Wie bei
`project_revenue` mit `unguarded` im Namen gepinnt.

**Die neun `raise`-Pfade laufen über eine Tabelle mit optionaler Mutation.** Sieben kommen über
Argumente, zwei brauchen verbogene Daten (`OperatingIncome` auf `None`, `Revenue` auf `0.0` im
letzten Ist-Jahr) und arbeiten deshalb auf einer `deepcopy` der echten Apple-Daten — dasselbe Muster
wie bei den beiden `calc_wacc`-Zweigen aus Schritt 30. Die beiden Metrik-Meldungen brauchen im
`match` escapte eckige Klammern, weil `pytest.raises` einen Regex erwartet.

**Offen bleibt der Rest von Phase 6:** `validation.py` vollständig und die netzfreien Teile von
`parser.py`.

#### Schritt 35 — `validation.py` in Isolation — DONE

Vierter der fünf Testblöcke. `tests/test_validation.py`, 31 Tests, Suite bei **361 grün**. Die
Schicht war vollständig ungetestet und entscheidet, welche Zahlen überhaupt ins Modell kommen.

**Die Datei rührt die Fixture-Datenbank nicht an, und das ist der Kern.** `validate_values` liest die
Parser-Form, in der Abwesenheit das Fehlen des Keys `Value` ist — `get_data` setzt stattdessen
`Value: None`. Ein Test gegen die Fixture hätte also nicht nur andere Zahlen geprüft, sondern eine
Form, die die Funktion nie sieht: `values[year][metric]["Value"] < 0` würde bei `None` mit einem
`TypeError` sterben. Alle 31 Fälle sind deshalb handgebaut, über eine Modulkonstante `BASE` mit allen
dreizehn Positionen aus `OUTLIER_RULES` und einen Helper `pyear(missing = (), **over)`.

**Der Basisfall ist so gewählt, dass alle vier Regeln schweigen** — Umsatz in beiden Jahren gleich,
EBIT-Marge 0,20, Vorsteuermarge 0,18, Steuerquote 0,25, Working Capital bei 2 Prozent des Umsatzes.
Erst dadurch stammt in jedem der folgenden Fälle jeder Flag von genau der einen geänderten Zahl. Vier
Fälle sind bewusst Ein-Jahres-Dicts: ohne Vorjahr fällt der gesamte `year-1`-Block weg, und
`pct_of_revenue` beziehungsweise `effective_rate` stehen isoliert da. Mit zwei Jahren reißt eine
negative Vorsteuerzahl den `margin_change_pp`-Test auf `PretaxIncome` mit, und der Fall prüft dann
zwei Regeln gleichzeitig.

**Beide Vergleiche sind strikt, und beide Grenzen sind gepinnt.** Eine Margenänderung von exakt
0,07 Prozentpunkten und ein Working Capital von exakt 10 Prozent des Umsatzes erzeugen **keinen**
Flag. Dasselbe bei `check_recon_tolerance`: `Residuum_pct` exakt auf `RECON_TOLERANCE` bleibt ohne
`recon_gap`.

**Die Flag-Blöcke hängen an, sie konkurrieren nicht.** `CapEx = -60.0` nur im zweiten Jahr liefert
`['negative', 'outlier']` — der Vorzeichentest und der Yoy-Test laufen beide. Stehen beide Jahre auf
`-60.0`, bleibt je Jahr nur `['negative']`, weil die Yoy-Änderung null ist. Ein Test, der nur den
zweiten Fall prüft, hätte die Reihenfolge der Blöcke nicht abgesichert.

**`Tax = -10.0` bekommt `outlier`, aber kein `negative`.** `Tax` steht auf der `exceptions`-Liste,
zusammen mit `OperatingIncome`, `WorkingCapital`, `PretaxIncome`, `Equity` und `NWC` — bei diesen
sechs ist ein negativer Wert legitim. Der Fall `OperatingIncome` von 10,0 auf -10,0 zeigt die
Gegenprobe: Vorzeichenwechsel, Margenänderung 0,02 Prozentpunkte, kein einziger Flag.

**Zwei ungeschützte Stellen in `reconcile_working_capital`, gepinnt.** `residuum_pct` teilt durch den
Umsatz ohne Prüfung — `Revenue = 0.0` gibt `ZeroDivisionError`. Und die Funktion iteriert über
`values`, indiziert aber `recon_values[year]`: ein Jahr, das nur in `values` steht, gibt `KeyError`.
Der zweite Fall ist der realistischere, weil beide Dicts aus getrennten `get_values`-Aufrufen mit
unterschiedlichen Tag-Mengen stammen.

**`check_recon_tolerance` mutiert `flags` in place und gibt dasselbe Objekt zurück.** Ein eigener Test
hält das fest (`out is flags`). Wer die Funktion später als rein annimmt und den Rückgabewert
verwirft, verliert die Flags nicht — er bekommt sie doppelt, wenn er sie zweimal aufruft.

**Offen bleibt von Phase 6:** die netzfreien Teile von `parser.py`.

#### Schritt 36 — die netzfreien Teile von `parser.py` — DONE

Fünfter und letzter Testblock. `tests/test_parser.py`, 24 Tests, Suite bei **385 grün in 91 s**.
Abgedeckt sind `get_last_n_years`, die sieben Slot-Selektoren und `clean_values`. `get_response` und
`get_values` bleiben draußen: der eine geht gegen SEC EDGAR, der andere liest eine JSON-Datei aus
`storage/`, die nicht eingecheckt ist.

**`get_last_n_years(n)` liefert `n + 1` Jahre.** `range(cur_year - n, cur_year + 1)` schließt beide
Enden ein. Der Test pinnt Länge, letztes Jahr und Lückenlosigkeit; die Länge ist der Punkt, weil der
Aufrufer `get_values(3, ...)` schreibt und vier Jahre bekommt. Er hängt an `datetime.now()` und wird
deshalb gegen `datetime.now().year` geprüft statt gegen eine feste Zahl — ein hartes Jahr wäre am
1. Januar rot.

**Die Selektoren zerfallen in zwei Bauarten, und beide sind getestet.** `select_wc`, `select_cash`
und `select_nwc_level` sammeln alles, was gefüllt ist. `select_pretax`, `select_deferred_taxes` und
`select_shares` sind Prioritätsketten mit Alles-oder-nichts-Rückfall: `select_pretax` nimmt den
direkten Tag, sonst Domestic **und** Foreign, sonst nichts — mit nur einer der beiden Hälften kommt
`[]` zurück und das Jahr fällt aus. Genau dieser Halb-Fall ist je ein eigener Test, weil er der
einzige ist, in dem echte Daten still verschwinden.

**`select_debt` ist der einzige Selektor mit einer Sonderregel, und sie hängt am Tag-Namen.**
`CommercialPaper` bleibt nur, wenn `DebtCurrent` seinen Wert aus dem Tag `LongTermDebtCurrent` zieht
— steht dort `DebtCurrent`, ist das Commercial Paper darin schon enthalten und wird entfernt. Ist der
Slot leer, greift `.get("Tag")` auf `None` und die Regel entfernt ebenfalls. Alle drei Zustände sind
gepinnt.

**`clean_values` schreibt den Aggregatwert in dasselbe Dict, in dem die Slots stehen.** Nach dem Lauf
trägt `WorkingCapital` sowohl `Receivables`, `Inventory`, `Payables`, `DeferredRevenue` als auch
`Value`, `Tag`, `End`, `Form`, `Filed`. Der Test prüft beides, weil ein späterer Umbau auf ein
flaches Ergebnis-Dict die Provenienz der Einzelposten stillschweigend verlöre.

**Die Provenienz-Keys folgen drei verschiedenen Regeln:** `Tag` ist die Verkettung mit `+`, `End` und
`Filed` sind jeweils das Maximum, `Form` ist `forms[0]` — der Wert des ersten gewählten Slots. Im
Test steht der zweite Slot bewusst auf `10-Q`, und das Ergebnis meldet trotzdem `10-K`. Real
unerreichbar, weil `get_values` alles außer `10-K` verwirft; wird dieser Filter je gelockert,
behauptet die Aggregatzeile eine Form, die nur einer ihrer Bestandteile hat.

**Der `if not chosen: continue`-Pfad ist die Brücke zu `validation.py`.** Ist kein Slot gefüllt,
bleibt das Metrik-Dict unverändert und ohne Key `Value` — und genau daraus macht `validate_values`
den Flag `missing`. Derselbe Mechanismus bei den einschlitzigen Metriken: `{"Revenue": {}}` kollabiert
zu `{}`, nicht zu `{"Value": None}`.

#### Phase 6 — abgeschlossen, und was sie an Entscheidungen hinterlässt

Alle fünf Blöcke stehen: WACC-Kette, `terminal_value`, `model.py` in drei Teilen, `validation.py`,
`parser.py`. Von 158 Tests zu Beginn der Phase auf **385**, Laufzeit 91 s, CI grün. Die Lücke, die
die Phase schließen sollte — die bestehenden Tests hielten das Ergebnis fest, nicht die Formel — ist
zu.

Kein Test hat eine Zeile in `logic/` geändert. Was sie gefunden haben, steht als Liste offener
Entscheidungen, gesammelt statt einzeln behoben, weil jeder Fix die Golden Values verschiebt und
mehrfaches Nachziehen teurer ist als ein Durchgang:

1. **`SPREADS` hat vierzehn Lücken** (Schritt 30). Jedes Band endet auf `...999`, das nächste beginnt
   eine Dezimalstelle höher. Breiteste Lücke direkt unter `INVESTMENT_GRADE`. Option: `high = next_low`.
2. **`Implied_Multiple` teilt ungeschützt durch EBITDA** (Schritt 31). Null gibt `ZeroDivisionError`
   auch bei `method = "multiple"`, negativ gibt ein stilles negatives Multiple. Boeing ist der reale
   Kandidat. Option: Guard oder `Source`-Marker; die Konvention spricht für den Marker.
3. **`Mean_Last_Three` in `driver_ratio` ist nicht kontingent** (Schritt 32). Boeing mittelt 2018,
   2022 und 2023 unter dem Namen "letzte drei". Der teuerste Fix, weil `Mean_Last_Three` bei Apple
   der `margin_base` ist.
4. **`effective_tax_rate` prüft den Flag auf `PretaxIncome` nicht** (Schritt 32) und wirft bei
   `PretaxIncome = 0` einen `ZeroDivisionError`.
5. **`rolling_means` wirft bei `k = 0` einen `IndexError` und sortiert nicht** (Schritt 32).
6. **`roic`: `Insufficient` ist klebrig** (Schritt 33) — ein Jahr mit `IC <= 0` löscht alle übrigen.
   `IC_Last` kommt aus `max(data)` statt `max(dct)` und überlebt `Insufficient`. Flags werden nicht
   geprüft.
7. **`project_revenue` und `project_fcf` bei `years = 0`** (Schritte 33, 34) geben still ein leeres
   Dict beziehungsweise eine Nullzeile zurück.
8. **`Unkown metric: []`** (Schritt 34) — Tippfehler, und bei einem ungültigen Metrik-*Wert* nennt die
   Meldung nichts.
9. **`reconcile_working_capital`** (Schritt 35) wirft `ZeroDivisionError` bei Umsatz null und
   `KeyError`, wenn ein Jahr nur in `values` steht.
10. **`clean_values` setzt `Form = forms[0]`** (Schritt 36), heute unerreichbar hinter dem
    `10-K`-Filter in `get_values`.

Reihenfolge für den Durchgang: 2, 6 und 3 zuerst, weil sie Zahlen im Ergebnis bewegen; 1, 4, 5, 7, 8,
9, 10 danach, weil sie nur Fehlerbilder und Meldungen betreffen. Als Nächstes steht laut
Phasenreihenfolge Phase 4 an, das Output-Interface.

#### Fix-Durchgang, Punkt 2 — `Implied_Multiple` gegen EBITDA <= 0 — DONE

Erster der zehn gesammelten Punkte aus Phase 6. Suite bleibt bei **385 grün in 86 s**, alle fünf
Golden `Implied_Multiple` unverändert — genau das war die Bedingung, unter der der Fix richtig ist.

**Die Roadmap hatte den Anlass falsch beschrieben.** Punkt 2 nannte Boeing den realen Kandidaten für
EBITDA <= 0. Nachgemessen ist das falsch: im letzten expliziten Jahr steht Boeing bei 1,279e10, der
schlechteste erreichbare Fall über `margin_base = "Mean_Last_Three"` bei 7,709e9, und selbst am
unteren Rand von `IMPLIED_MARGIN_BOUNDS` (`ebit_margin = 0.0`) bleiben 4,479e9, weil D&A die Zahl
abstützt. Keiner der fünf Titel kommt unter irgendeinem dokumentierten Hebel in die Nähe der Null.
Der Fix ist damit Prophylaxe plus Trennung von Diagnose und Ergebnis, nicht die Reparatur eines
aktiven Bugs.

**Der Guard sitzt auf der Diagnosezahl, nicht auf dem Terminal Value.** `Implied_Multiple` wird in
`terminal_value` vor dem `method`-Block entschieden: bei `ebitda > 0` der Quotient und
`Implied_Multiple_Source = "Calculated"`, sonst `None` und `"EBITDA <= 0"`. Ein `raise` an der Stelle
hätte `method = "multiple"` einen legitimen Terminal Value gekostet — `exit_multiple` mal null ist
null, mal negativ ist negativ, beides korrekte Ergebnisse der gewählten Methode, die mit dem
Gordon-Quotienten nichts zu tun haben. Der Test pinnt deshalb `Terminal_Value` 1375,0 für gordon und
0,0 für multiple 8,0 im Zero-Fall.

**Die Grenze ist `<= 0`, nicht `== 0`.** Der Negativ-Fall gab vorher -7,857 zurück. Eine negative
Zahl sieht in einer Tabelle plausibel aus und liest sich als "billig" — genau der Fall, den die
Konvention "kein plausibler Default für fehlende Daten" ausschließt. Die beiden Tests, die den
Zustand vorher als `unguarded` festhielten, sind entsprechend umgeschrieben.

**Benennung nach dem Muster `TV_Share` / `TV_Share_Source`** aus `dcf_value`: Zahl darf `None` sein,
der Grund steht im Nachbarkey. Ein Marker im `Source`-Dict von `terminal_value` wäre nicht
angekommen, weil `dcf_value` unter demselben Namen etwas völlig anderes führt, den zusammengesetzten
String `wacc_source+growth_source+method`. Der neue Key läuft durch `dcf_value` und durch beide
Zweige von `sensitivity_grid`, `sensitivity_table` und `nwc_scenario` — ohne das letzte Stück zeigte
eine Zelle `Implied_Multiple: None` bei `Status: "calculated"` und wäre von der `except`-Zeile
daneben nicht zu unterscheiden.

**Nebenfund, und der wiegt schwerer als der Fix selbst: `sensitivity_table` und `nwc_scenario` werden
von keinem Test aufgerufen.** Ein Tippfehler beim Durchreichen (`dcf[wacc]` statt `wacc`, ein Dict als
Dict-Key) hat beide Funktionen vollständig getötet, `TypeError` beim ersten Aufruf, und die Suite
blieb grün. Aufgefallen ist es nur durch einen manuellen Aufruf gegen die Fixture. Die Phase-6-Bilanz
"385 grün" deckt das Output-nahe Ende von `valuation.py` also nicht ab. Gehört vor Phase 4
nachgezogen, weil das Output-Interface genau auf diesen beiden Funktionen aufsetzt.

**Nächster Punkt im Durchgang ist 3** (`Mean_Last_Three` ist nicht kontingent), danach 6 (`roic`).
Die Reihenfolge 2, 3, 6 statt der ursprünglich notierten 2, 6, 3, weil `roic` über
`effective_tax_rate` an denselben Daten hängt und die Golden Values sonst zweimal nachgezogen werden.

#### Fix-Durchgang, Punkte 1 und 3 bis 10 — DONE

Der Rest der Liste in einem Durchgang, wie geplant: erst 3, dann 6, dann die sieben, die nur
Fehlerbilder betreffen. Suite von 385 auf **391 grün in 94 s**. Bewegt haben sich Zahlen bei genau
einer Firma im Basisfall (Procter & Gamble) und bei drei Firmen in Monte Carlo.

**Punkt 3 — `Mean_Last_Three` prüft jetzt Kontiguität.** `driver_ratio` und `growth_rate` mitteln nur
noch, wenn die letzten `COMPARATOR_WINDOW` sauberen Jahre lückenlos sind; sonst `None`. Beide
Funktionen führen dazu `Mean_Last_Three_Source` und `Mean_Last_Three_Years`. Betroffen sind
ausschließlich `OperatingIncome` bei Boeing (2018, 2022, 2023) und Tesla (2022, 2024, 2025) — Apple,
Microsoft und P&G haben lückenlose Endfenster, entgegen der ursprünglichen Notiz, die Apple als
teuersten Fall nannte. `Mean_Last_Three_Years` ist absichtlich getrennt von `Years`: `Years` ist das
Fenster des Medians, und zwei verschieden gefensterte Kennzahlen unter einem Fensterschlüssel sind
genau der Zustand, den die Konvention verbietet.

**Verworfen wurde die Alternative, auf das letzte kontingente Fenster auszuweichen.** `rolling_means`
könnte das liefern, gibt bei Boeing aber 0,0995 aus 2016-2018 — Boeing vor 737 MAX, acht Jahre alt,
als Margin-Treiber einer Bewertung per 2026. Eine Zahl, die so heißt wie das Fenster, das sie nicht
hat, ist der plausible Default, den die Konvention ausschließt.

**Folgeänderung in `monte_carlo`:** die Schleife über `MARGIN_BASES` fing nichts ab und wäre bei
Boeing und Tesla ab dem Fix jedes Mal gestorben. Sie überspringt eine Basis jetzt, die konfigurierte
Basis-Margin dagegen wirft — fehlt die, ist die Verteilung nicht mehr um den Basisfall zentriert. Das
Ergebnis führt `Margin_Bases_Used`, sonst stünde dort ein Zweier-Intervall ohne Hinweis, dass es aus
drei Kandidaten entstanden ist.

**Das kostet Boeing und Tesla ihr breitestes Margenband, und die Wirkung ist groß.** Boeings
MC-Median steigt von 45,87 auf 62,47, weil die gestrichene Zahl (0,0186) der untere Rand war; Teslas
fällt von 18,30 auf 16,65, weil dort 0,0953 der obere war. Beide Bänder sind danach schmaler. Das ist
eine echte Nebenwirkung, keine Verbesserung: die Verteilung wird selbstsicherer, ohne dass neue
Evidenz dazugekommen wäre. Das Gegenargument, auf dem die Entscheidung steht: eine Zahl aus einem
kaputten Fenster ist keine Evidenz für einen Rand, sie sah nur wie eine aus.

**Punkt 6 — `roic` filtert jetzt pro Komponente statt pro Jahr.** Die Kopplung war der eigentliche
Fund: `IC` hängt an Debt, Equity und Cash, `NoPat` an OperatingIncome, und ein Jahresfilter über alle
vier hätte Boeings `IC_Last` auf 2023 zurückgeworfen, obwohl nur das OperatingIncome 2025 geflaggt
ist. Getrennt gefiltert bleiben alle fünf `IC_Last`-Werte unverändert. Die Flag-Regel folgt
`driver_ratio`: bei `yoy`-Metriken wird `outlier` toleriert, bei `margin_change_pp` nicht — dafür
steht die Prüfung jetzt einmal in `flags_clean` statt dreimal inline. Dazu: `Insufficient` ist nicht
mehr klebrig, `IC_Last` kommt aus dem letzten Jahr mit brauchbarem IC statt aus `max(data)`, und
`IC_Last_Year` macht sichtbar, welches Jahr das war.

**Neuer Fund, und er gehört auf die nächste Liste: `roic` liefert jetzt absurde Zahlen, wo es vorher
schwieg.** Apple kommt auf `ROIC_Median` 16,17, Boeing auf 2,84 — beides echte Quotienten, weil das
Invested Capital dieser Jahre knapp über null liegt (Apple 2022: 1,6 Mrd bei rund 100 Mrd NOPAT). Der
alte klebrige `Insufficient`-Zweig hat das zufällig maskiert. Ein Schwellwert wäre eine
Finanzannahme, keine Aufräumarbeit, und gehört deshalb entschieden statt nebenbei eingebaut.
`ROIC_Median` und `ROIC_Last` gehen heute in keine Bewertung ein, nur `IC_Last` — der Schaden ist
vorerst auf die Diagnose begrenzt.

**Punkt 4 — `effective_tax_rate` prüft beide Positionen.** Der Flag auf `PretaxIncome` wurde ignoriert
und ein Nenner von null lief in einen `ZeroDivisionError`. Das trifft P&G: 2019 trägt `outlier` auf
`PretaxIncome`, fällt jetzt heraus, und die Steuerquote geht von 0,2034 (n=7) auf 0,2026 (n=6). Das
ist die einzige Bewegung im Basisfall überhaupt — Value_Per_Share 131,79 auf 131,82, EV 330,53 auf
330,60 Mrd, dazu Lever-, Horizon- und MC-Goldens. Boeing verliert ein Jahr (n=2 auf n=1), bleibt aber
beim Fallback 0,25.

**Punkt 1 — `SPREADS` ist lückenlos.** Jedes `high` ist das `low` des nächsten Bandes, der Vergleich
ist `low <= coverage < high`. Damit landet 2,4999 in Ba1/BB+ statt im Nichts, und die drei Tests, die
die Lücken als `raise` festhielten, prüfen jetzt das Gegenteil plus die Kontiguität der Tabelle. Eine
Coverage von exakt 100000,0 wirft ab sofort, weil das oberste Band rechts offen verglichen wird —
absurd genug, dass die ehrliche Fehlermeldung die richtige Antwort ist.

**Punkte 5, 7, 8 — Guards und Meldungen.** `rolling_means` wirft bei `k < 1` und sortiert selbst,
statt Sortierung stillschweigend vorauszusetzen. `project_revenue` und `project_fcf` werfen bei
`years < 1`, statt `{}` beziehungsweise eine Nullzeile zurückzugeben. Die Metrikprüfung in
`project_fcf` ist in zwei Checks getrennt: ein falscher Key nennt den Key, ein falscher Wert nennt
den Wert — vorher meldete letzterer `Unkown metric: []`, Tippfehler inklusive.

**Punkt 9 — `reconcile_working_capital`.** Jahre, die nur in `values` stehen, und Jahre mit Umsatz
null werden übersprungen statt in `KeyError` beziehungsweise `ZeroDivisionError` zu laufen. Beide
landen als leeres Jahres-Dict im Ergebnis, und `check_recon_tolerance` macht daraus von selbst
`recon_unchecked` — Absenz bleibt sichtbar, ohne dass eine zweite Meldung nötig wäre.

**Punkt 10 — `clean_values`.** `Form` ist jetzt die Verkettung der eindeutigen Formen statt
`forms[0]`. Hinter dem `10-K`-Filter in `get_values` ändert das nichts; wird der Filter je gelockert,
behauptet die Aggregatzeile nicht länger eine Form, die nur einer ihrer Bestandteile hat.

**Offen bleibt aus dem letzten Schritt: `sensitivity_table` und `nwc_scenario` haben keinen einzigen
Test.** Ein Tippfehler beim Durchreichen hat beide getötet, und die Suite blieb grün. Das ist die
Lücke, die vor Phase 4 zu schließen ist, weil das Output-Interface genau auf diesen beiden Funktionen
aufsetzt. Zusammen mit dem `roic`-Schwellwert sind das die zwei offenen Punkte, mit denen Phase 4
startet.

#### Die drei Tabellenfunktionen gepinnt — DONE

`tests/test_tables.py`, 16 Tests, Suite bei **407 grün in 91 s**. Damit ist die Lücke zu, die der
`dcf[wacc]`-Tippfehler aufgedeckt hat: `sensitivity_grid`, `sensitivity_table` und `nwc_scenario`
hatten zusammen null Tests, und ein Fehler, der zwei von ihnen komplett tötet, ließ die Suite grün.

**Der Kern ist die Verdrahtung, nicht die Zahl.** Je Funktion prüft ein Test, dass die Basiszeile
exakt dem nackten `dcf_value`-Lauf entspricht — `grid[(0.0, TERMINAL_GROWTH)]`, die Zeile mit
`Is_Base` in `sensitivity_table`, die mit `Is_Base` in `nwc_scenario`. Das ist die Assertion, die
jeden falsch durchgereichten Key trifft, ohne eine einzige weitere Golden-Zahl zu kosten.

**Der zweite Kern ist die Schlüsselmenge in beiden Zweigen.** Für `sensitivity_grid` und
`sensitivity_table` ist der `except`-Zweig eigens erzwungen: P&G mit `offset = -0.03` und
`g = 0.035` fällt unter `wacc > g`, Boeing mit `margin_bases = ("Mean_Last_Three",)` läuft in
"Missing data for EBIT, D&A, CapEx, or Working Capital" — der Pfad, den der Kontiguitäts-Fix erst
erreichbar gemacht hat. Beide Zeilen tragen dieselbe Schlüsselmenge wie eine gerechnete und
unterscheiden sich nur in `Status`. `nwc_scenario` bleibt dort ungetestet: über seine eigenen
Parameter ist kein `ValueError` erreichbar, ein nicht-numerischer Wert stirbt vorher im
`Is_Base`-Vergleich an einem `TypeError`.

**Fund: `NWC_INTENSITIES` markiert nur bei Boeing eine Basiszeile.** Die Konstante ist
(0,0282 / 0,1686 / 0,2092 / 0,2211 / 0,4368), Boeings NWC-Driver-Ratio ist 0,2211 und trifft. Die
anderen vier liegen daneben — Apple -0,0882, Microsoft -0,084, P&G -0,0227, Tesla -0,0052, drei davon
negativ und damit außerhalb jeder Zahl der Tupels. Für vier von fünf Firmen ist `Is_Base` in keiner
Zeile wahr, die Szenariotabelle hat also keinen Anker. Gepinnt als
`test_nwc_intensities_anchor_only_boeing`, damit der Zustand nicht stillschweigend bleibt; der Fix
gehört in Phase 4, weil erst das Output entscheidet, ob die Achse pro Firma um den eigenen Basiswert
gelegt wird oder fest bleibt.

**Der Monte-Carlo-Versatz aus Schritt 22 ist durch den Kontiguitäts-Fix schlechter geworden, nicht
besser.** Boeings MC-Median liegt jetzt 23,9% über dem Basisfall (62,47 gegen 50,43), vorher -9,0%.
Tesla ist von +16,5% auf +6,0% gefallen, die übrigen drei bleiben unter 2%. Ursache ist dieselbe wie
vorher: `m_mode` sitzt bei Boeing und Tesla auf dem Minimum der Spanne, und das Streichen der
`Mean_Last_Three`-Basis hat bei Boeing genau den unteren Rand entfernt. Vor Phase 4 zu entscheiden,
wie zuvor notiert — ein Dashboard, das Median und Basiswert nebeneinander zeigt, macht die Differenz
sonst zu einer Erkenntnis über das Unternehmen statt über die Wahl der Margenbänder.

#### Die drei offenen Punkte vor Phase 4 — entschieden

Suite bei **412 grün in 90 s**. Keine Bewertungszahl bewegt sich: alle fünf `GOLDEN`-Blöcke,
`FCF_GOLDEN`, `LEVER_GOLDEN` und `HORIZON_GOLDEN` bleiben unverändert. Betroffen sind nur die drei
Ausgaben, um die es ging.

**1. Der Monte-Carlo-Versatz wird benannt, nicht wegdefiniert.** Die Dreiecksverteilung über die drei
Margin-Basen bleibt exakt wie sie ist. `monte_carlo` führt zwei neue Keys: `Median_Offset`
(Median gegen Basiswert) und `Mode_Position` ("Min" / "Interior" / "Max" / "Degenerate"). Gemessen:
Boeing +23,9% bei Modus auf dem Minimum, Tesla +6,0% ebenso, P&G -1,2% bei Modus auf dem Maximum,
Apple -1,1% und Microsoft -1,7% mit Modus im Inneren.

Die Alternative wäre gewesen, das Band symmetrisch um den Basiswert zu legen. Verworfen: das
erfindet eine Spanne, für die es keine Evidenz gibt. Die drei Margin-Basen **sind** die Evidenz, und
wenn die konfigurierte Basis unter ihnen die niedrigste ist, dann ist die Rechtsschiefe der
Verteilung eine korrekte Aussage — nur eben eine über die Wahl der Basis, nicht über das
Unternehmen. `Mode_Position` sagt genau das, in einem Wort, direkt neben der Zahl. Damit ist die
Voraussetzung erfüllt, unter der ein Panel Median und Basiswert nebeneinander zeigen darf.

**2. Die NWC-Achse liegt jetzt um den eigenen Basiswert.** `NWC_INTENSITIES` (absolute Tupel-Werte,
erkennbar aus Boeing abgeleitet) ist ersetzt durch `NWC_OFFSETS = (-0.05, -0.025, 0.0, 0.025, 0.05)`,
Prozentpunkte vom Umsatz. `nwc_scenario` addiert den Offset auf die eigene NWC-Ratio der Firma,
keyt die Tabelle nach dem Offset und führt `NWC_Intensity` und `NWC_Offset` in jeder Zeile.
`Is_Base` ist damit für **jede** Firma in genau einer Zeile wahr, bei Offset null.

Der Grund für Prozentpunkte statt relativer Schritte ist derselbe, der in Schritt 20 schon für die
WACC-Achse notiert wurde: relative Schritte bleiben nicht vergleichbar. Hier kommt dazu, dass drei
der fünf Basiswerte negativ sind (Apple -0,0882, Microsoft -0,084, P&G -0,0227) — eine absolute
Achse kann eine Kennzahl mit Vorzeichenwechsel nicht firmenübergreifend abdecken, und genau daran ist
die alte Konstante gescheitert. Zusätzlich wirft `nwc_scenario` jetzt, wenn die NWC-Ratio selbst
`None` ist; ohne den Guard wäre die Achse still um `None` gelegt worden.

**3. `roic` bekommt eine Schwelle auf den Nenner, relativ zum Umsatz.**
`MIN_IC_REVENUE_SHARE = 0.05` in `model.py`: liegt das Invested Capital des Vorjahres unter 5% des
damaligen Umsatzes, wird das Paar verworfen und in `Excluded_Small_IC` gezählt. Absolute Schwellen
wären größenabhängig und damit für fünf Firmen unterschiedlicher Größe wertlos.

Wirkung: Apple verliert alle drei Paare (IC-Anteile 0,41% / 2,91% / 1,77%) und steht bei n=0,
Boeing verliert zwei von vier (0,56% / 1,68%) und steht bei n=2 — beide `Insufficient`, aber mit
`Excluded_Small_IC` als sichtbarem Grund statt des zufälligen Nebeneffekts, den der alte klebrige
Zweig hatte. Microsoft, P&G und Tesla ändern sich nicht, ihre Nenner liegen zwischen 14% und 123%.
`IC_Last` bleibt bei allen fünf unverändert und ist bewusst nicht gefiltert: es ist ein Bestand, der
in `project_fcf` mit dem akkumulierten Reinvestment summiert wird, keine Ratio.

Damit ist auch die inhaltliche Aussage sauber: Apple hat auf `Debt + Equity - Cash` praktisch kein
Invested Capital, und eine Rendite darauf ist nicht definiert — nicht 1617%.

**Ein Nebenfund, der in die Serialisierungsschicht gehört:** `dcf_value` meldet `NWC_Intensity: None`
im Basisfall, weil der Key den Override führt und nicht die effektiv verwendete Intensität. Für den
Annahmen-Block in Phase 4 ist das zu wenig — dort muss stehen, welche Intensität gerechnet wurde,
nicht ob sie überschrieben war. Gleiches Muster wie `Revenue_Growth`, das ebenfalls nur den Override
trägt.

#### Phase 4, Schritt 1 und 2 — Effektivwerte im Modell, Serialisierungsschicht

Suite bei **412 grün in 88 s**, keine Bewertungszahl bewegt sich. Der Schritt hat zwei Teile, die
nur zusammen Sinn ergeben.

**Der Anlass.** `dcf_value` meldete `NWC_Intensity: None` im Basisfall — der Key trug den Override,
nicht die gerechnete Intensität. Dasselbe bei `Revenue_Growth`. D&A- und CapEx-Marge tauchten im
Ergebnis überhaupt nicht auf: `project_fcf` berechnete sie aus `driver_ratio` und warf sie weg. Ein
Annahmen-Panel ist damit nicht schreibbar.

**Erster Teil, `model.py` und `valuation.py`.** `project_revenue` führt jetzt `Growth_Rate_Base` in
jeder Zeile, `project_fcf` zusätzlich `DA_Margin`, `CapEx_Margin`, `NWC_Intensity` und
`Revenue_Growth` — die Terminalzeile bekommt sie nicht, dort steht `EBIT_Margin` bereits als
Zielmarge. In `dcf_value` heißen die alten Override-Keys jetzt `NWC_Intensity_Override` und
`Revenue_Growth_Override`; die freigewordenen Namen tragen den Effektivwert aus `fcf[min(fcf)]`,
dazu `DA_Margin` und `CapEx_Margin`. Neu ist auch `Projection`: die vollständige FCF-Tabelle des
jeweiligen WACC-Zweigs.

Die Alternative wäre gewesen, die Effektivwerte in der Serialisierung nachzurechnen. Verworfen: die
Auflösung von `metrics` samt Default `Driver_Ratio` stünde dann an zwei Stellen und würde driften —
das Dashboard zeigte irgendwann eine Annahme an, die das Modell nicht gerechnet hat. Aus demselben
Grund gibt `dcf_value` die Projektion heraus, statt die Serialisierung `project_fcf` ein zweites Mal
aufrufen zu lassen; sie müsste dafür `terminal_roic` selbst auflösen.

Gemessen, `as_of = "2026-08-19"`, Fenster 2016 bis 2025 bzw. 2026:

| Firma | NWC_Intensity | DA_Margin | CapEx_Margin | Revenue_Growth |
|---|---|---|---|---|
| apple | -0,0882 | 0,0291 | 0,0278 | 0,0630 |
| boeing | 0,2211 | 0,0258 | 0,0287 | 0,1226 |
| microsoft | -0,0840 | 0,0635 | 0,2533 | 0,1461 |
| procter_gamble | -0,0227 | 0,0348 | 0,0450 | 0,0260 |
| tesla | -0,0052 | 0,0508 | 0,0990 | 0,0560 |

**Zweiter Teil, `logic/serialize.py` mit `serialize_company`.** Eine Funktion, ein Dict pro Firma,
fünfzehn Top-Level-Keys: `Symbol`, `As_Of`, `Status`, `Blocks_Failed` und elf Blöcke — `Headline`,
`Assumptions`, `Provenance`, `Quality`, `Projection`, `Grid`, `Margin_Table`, `NWC_Table`,
`Implied`, `Ceiling`, `Horizon`. Die Key-Menge ist im Erfolgs- und im Fehlerfall identisch, damit
das Template nicht zwei Formen kennen muss.

Vier Entscheidungen, die nicht offensichtlich sind:

- Die Quelle wird nie in der Serialisierung hergeleitet. `project_fcf` setzt `margin_base` und
  `nwc_str` schon auf `"Override"`, wenn überschrieben wurde. Eine zweite Ableitung aus den
  `_Override`-Keys erzeugte zwei Wahrheiten über dieselbe Zeile.
- `Assumptions` ist eine Liste von zehn Dicts mit `Label`, `Value`, `Unit`, `Source`, kein Dict. Die
  Reihenfolge im Panel ist eine inhaltliche Entscheidung und darf nicht von der Sortierung im
  Template abhängen.
- Die sechs teuren Blöcke haben je ein eigenes `except ValueError` und tragen ihren Namen in
  `Blocks_Failed` ein. Ein gemeinsames `try` machte aus einer fehlenden NWC-Ratio eine Seite ohne
  Sensitivitätsgitter.
- Keine Formatierung, nur Zahlen und Quellen. Prozentzeichen, Tausendertrenner und Vorzeichenfarbe
  entstehen im Template — sonst testet man Strings statt Werte.

Zwei Fallen, die beim Bauen aufgetreten sind und im Code stehen bleiben: `Source` in `dcf_value` hat
eine **variable** Segmentzahl, Boeing liefert `"1mo+2023+Mean_Last_Three+gordon"`, weil die
COD-Quelle ein Jahr mitführt — die WACC-Zeile nimmt deshalb alles bis auf die letzten zwei Segmente,
nicht das erste. Und die Terminalzeile der Projektion führt an `D&A`, `CapEx` und `dNWC` `None`; das
bleibt `None`, `0` behauptete, sie seien modelliert worden.

**Der Monte Carlo bleibt draußen.** Gemessen für Apple bei warmem Cache: `monte_carlo` kostet 14,0 s
von 17,9 s Gesamtlaufzeit, weil er `dcf_value` 2000-mal aufruft. `serialize_company` liegt damit bei
1,7 bis 5,0 s je Firma. Er bekommt in Phase 4 eine eigene Funktion und einen eigenen Endpunkt, den
die Seite nachlädt — sonst kostet jeder Request 18 statt 4 Sekunden.


#### Phase 4, Schritt 3 — die Serialisierungsschicht gepinnt — DONE

`tests/test_serialize.py`, 63 Tests, Suite von 407 auf **475 grün in 101 s**. Damit hat die letzte
Schicht ohne Test eine, und zwar die, die fast nur aus Durchreichen besteht — genau die Fehlerklasse,
die beim `dcf[wacc]`-Tippfehler zwei Funktionen getötet und die Suite grün gelassen hat.

**Die Form ist die Aussage, nicht die Zahl.** Bewertungszahlen stehen schon in `test_golden_values.py`
und `test_tables.py`; hier wird dreimal gegen den nackten `dcf_value`-Lauf verglichen (Headline,
Projektion, Gittermitte) und ansonsten die Struktur geprüft. `TOP_KEYS` ist eine einzige Konstante,
gegen die beide Rückgabezweige laufen — zwei getrennte Listen würden auseinanderlaufen, sobald ein
Block dazukommt, und die Identität der Key-Menge ist die Zusage, auf der das Template steht.

**Der Fehlerzweig ist über zwei echte Auslöser erreichbar,** nicht über einen Monkeypatch:
`years = 0` trifft den Guard in `project_fcf` ("Years must be at least 1, got 0."), `start_year =
2024` die Datenlage ("Insufficient Data"). Beide geben dieselben fünfzehn Keys zurück, elf davon
`None`.

**Der Blockfehler dagegen muss erzwungen werden.** Alle fünf Firmen liefern `Blocks_Failed == []`;
über echte Daten ist keiner der sechs `except`-Zweige erreichbar. `test_block_failure_is_isolated`
patcht `serialize.plausible_ceiling` auf eine werfende Funktion und prüft, dass genau `Ceiling` auf
`None` fällt, `Status` bei `"calculated"` bleibt und die anderen fünf Blöcke stehen. Ohne den Test
wäre nicht belegt, dass eine fehlende NWC-Ratio eine Seite ohne Gitter erzeugt statt einer kaputten
Seite.

**Zwei Fallen, gegen die eigens gepinnt wurde:**

- **Die WACC-Zeile schneidet die letzten zwei Segmente, nicht das erste.** `Source` hat variable
  Segmentzahl, boeing liefert `"1mo+2023+Mean_Last_Three+gordon"`, weil die COD-Quelle ein Jahr
  mitführt. `WACC_SOURCE_GOLDEN` pinnt boeing auf `"1mo+2023"` und die anderen vier auf `"1mo"`.
- **Die Gitterorientierung wird über jede Zelle geprüft, nicht über die Mitte.** Bei zwei Achsen mit
  je fünf Elementen und dem Basisfall mittig ist die Mitte gegen eine Transposition invariant. Die
  Mitte selbst wird über `offsets.index(0.0)` und `growths.index(TERMINAL_GROWTH)` gefunden, nicht
  als `[2][2]`, damit der Test eine Änderung der Achsenkonstanten überlebt.

**Der teuerste Fund beim Schreiben: die Quellenstrings allein reichen nicht.** `serialize.py`
zerlegt `Metrics` positional in `[0]`, `[1]`, `[2]` für D&A, CapEx, NWC. Ein Test, der dieselbe
Zerlegung benutzt, prüft nichts, also wird die erwartete Quelle unabhängig aus
`ASSUMPTIONS[symbol]["metrics"]` mit Default `"Driver_Ratio"` aufgelöst. Das reicht aber immer noch
nicht: bei apple und procter_gamble sind alle drei Quellen identisch, bei boeing und microsoft sind
Position 0 und 2 identisch (`Driver_Ratio+Mean_Last_Three+Driver_Ratio`). Ein D&A-NWC-Tausch wäre
über die Quellen bei **keiner** der fünf Firmen sichtbar. Gefangen wird er erst über den Wert:
`driver_ratio(data, metric)[source]`, weil 0,0258 und 0,2211 sich unterscheiden. Beide Assertions
stehen deshalb nebeneinander.

**Laufzeit:** zwei sessionweite Fixtures, `panels` und `bases`, je fünf Aufrufe, dazu der eine
gepatchte Lauf. 19,5 s für das Modul allein. Ein Aufruf pro Test statt pro Session hätte es auf
mehrere Minuten gebracht.

**Offen, gehört ins Template, nicht in die Serialisierung:** im Fehlerzweig listet `Blocks_Failed`
nur die sechs teuren Blöcke, `Headline`, `Assumptions`, `Provenance`, `Quality` und `Projection`
sind ebenfalls `None` und stehen nicht drin. Und `As_Of` trägt dort den Eingabewert, im Erfolgsfall
den aufgelösten aus `wacc["As_Of"]` — bei `as_of = None` gibt der Fehlerzweig `None` zurück, der
Erfolgsfall ein Datum. Das Template darf `Blocks_Failed` deshalb nicht als Ja-Nein-Prüfung dafür
benutzen, ob eine Headline existiert; die Prüfung ist `Status == "calculated"`.

**Nächster Punkt in Phase 4 ist der Monte Carlo als eigene Funktion in `serialize.py`** mit eigenem
Endpunkt, wie in Schritt 1 und 2 notiert. Danach das Template.


#### Phase 4, Schritt 4 — der Monte Carlo als eigener Endpunkt — DONE

`serialize_monte_carlo` in `logic/serialize.py`, dazu `tests/test_serialize_mc.py` mit 57 Tests.
Suite von 475 auf **532 grün in 129 s**. Keine Bewertungszahl bewegt sich, `MC_GOLDEN` bleibt
unverändert.

**Warum eine zweite Funktion und nicht ein zwölfter Block.** Gemessen bei warmem Cache und 2000
Ziehungen: `monte_carlo` kostet 12,2 bis 13,1 s je Firma, `serialize_company` liegt komplett bei 1,7
bis 5,0 s. In einem Panel zusammengelegt kostete jeder Request 18 statt 4 Sekunden. Die Seite lädt
den Monte Carlo nach.

**Acht Top-Level-Keys: `Symbol`, `As_Of`, `Status`, `Distribution`, `Offset`, `Inputs`,
`Reliability`, `Draws`.** Kein `Blocks_Failed` — anders als bei `serialize_company` gibt es hier
keine unabhängig scheiternden Teile, der Lauf gelingt ganz oder gar nicht. Die beiden Funktionen
haben damit bewusst verschiedene Formen; ein gemeinsamer Schlüssel, der bei der einen immer leer
ist, verleitet das Template dazu, ihn als Erfolgsprüfung zu benutzen. Die Prüfung ist bei beiden
`Status == "calculated"`.

Drei Entscheidungen, die nicht offensichtlich sind:

- **`Distribution` ist eine Liste aus `Percentile`/`Value`, kein Dict.** `monte_carlo` gibt
  `Percentiles` mit Float-Keys heraus, und Float-Keys überleben keine JSON-Serialisierung — aus
  `0.05` wird `"0.05"`, das Template müsste zurückparsen. Dazu derselbe Grund wie bei `Assumptions`:
  die Reihenfolge ist eine inhaltliche Entscheidung und darf nicht von der Sortierung im Template
  abhängen.
- **`Margin_Range` wird in `Margin_Low`, `Margin_Mode`, `Margin_High` aufgelöst.** Ein Dreiertupel
  trägt seine Bedeutung positional, und ein Leser liest die Mitte als Mitte. Bei Boeing und Tesla
  sitzt der Modus aber auf dem Minimum, bei Procter & Gamble auf dem Maximum. Genau diesen Irrtum
  soll `Mode_Position` verhindern, und ein unaufgelöstes Tupel daneben stellt ihn wieder her.
- **`Draws` geht roh und ungebinnt heraus.** 2000 Floats sind rund 36 KB, für einen nachgeladenen
  Request nichts. Eine Binanzahl wäre eine Darstellungsentscheidung und gehört nach der Konvention
  aus Schritt 2 ins Template.

**`Draws_Requested` kommt aus dem Parameter, nicht aus dem Ergebnis.** `monte_carlo` führt nur
`Draws_OK` und `Draws_Failed`. Ohne den dritten Wert ist im Panel nicht unterscheidbar, ob 2000
angefordert und 2000 gelungen sind oder 5000 angefordert und 2000 gelungen — Absenz bliebe
unsichtbar.

**Die Tests laufen mit `draws = 200`, nicht 2000.** Die 2000er-Zahlen sind in `MC_GOLDEN` gepinnt;
ein zweites Pinnen derselben Werte kostete 126 s und brächte nichts. Verglichen wird gegen einen
frischen `monte_carlo`-Lauf mit identischem `seed`, nicht gegen Konstanten — geprüft wird das
Durchreichen, nicht die Arithmetik. Das Modul kostet so 14 s.

Gemessen bei `draws = 200`, `seed = 12345`, `as_of = "2026-08-19"`:

| Firma | Median | Median_Offset | Mode_Position | Margin_Low / Mode / High |
|---|---|---|---|---|
| apple | 126,355172 | -0,0142 | Interior | 0,2881 / 0,3110 / 0,319708 |
| boeing | 60,471560 | +0,1992 | Min | 0,047852 / 0,047852 / 0,0698 |
| microsoft | 320,817230 | -0,0230 | Interior | 0,4168 / 0,4568 / 0,467808 |
| procter_gamble | 130,337682 | -0,0112 | Max | 0,2211 / 0,2301 / 0,2301 |
| tesla | 16,469635 | +0,0484 | Min | 0,045926 / 0,045926 / 0,0632 |

`Draws_OK` ist bei allen fünf 200, `Draws_Failed` null. Der Fehlerzähler ist damit über echte Daten
nicht erreichbar, bei 200 wie bei 2000 Ziehungen; `test_empty_distribution` patcht `monte_carlo`
deshalb auf ein Ergebnis mit `Draws_OK = 0` und prüft nicht den Monte Carlo, sondern die
Absenzbehandlung in der Serialisierung — ohne Guard liefe `Percentiles[MC_MEDIAN]` dort in einen
`TypeError`.

**Die `As_Of`-Asymmetrie ist geschlossen.** `monte_carlo` in `valuation.py` führt jetzt
`As_Of` aus `dcf["wacc"]["As_Of"]` — den `dcf_value`-Lauf macht es in seiner ersten Zeile ohnehin,
der Key kostet nichts. `serialize_monte_carlo` nimmt den Stichtag von dort statt aus dem Parameter,
womit beide Panels denselben aufgelösten Wert liefern. Vorher gab das MC-Panel bei `as_of = None`
`None` zurück, während das Company-Panel ein Datum lieferte; eine Seite, die beide Endpunkte
nacheinander ruft, hätte zwei Stichtage nebeneinander anzeigen können, ohne dass es auffällt.

**Was der Test davon belegt und was nicht.** `test_as_of_comes_from_the_result` prüft, dass
`monte_carlo` den Key überhaupt führt und die Serialisierung ihn von dort nimmt — fällt der Key weg,
bricht der Test mit `KeyError`. Den eigentlichen Unterschied kann er nicht zeigen: gegen die
Fixture-Datenbank ist `as_of = None` nicht erreichbar, die gecachten Preise sind dort 21 Tage alt und
beide Funktionen laufen in die Staleness-Schranke aus Schritt 16. Der Fall ist also durch Konstruktion
gefixt, nicht durch Messung.

#### Phase 4 — die zwei Entscheidungen für die Ausgabeschicht

**Flask.** Zwei GET-Routen und ein Template; FastAPI wäre für diesen Umfang Overhead, und der
Monte-Carlo-Endpunkt braucht kein async, weil die 12 s Rechenzeit CPU-gebunden sind und nicht auf IO
warten. Gehört vor dem ersten Template-Schritt in `requirements.txt`.

**`mock_design.html` im Root ist der Zielentwurf, kein verworfener Zwischenstand.** Der Stil der
Seite richtet sich danach. Hier festgehalten, weil die Datei bis hierher in keinem Roadmap-Eintrag
vorkam und ihr Status damit nur im Kopf existierte.

**Damit ist die Datenseite von Phase 4 fertig.** Zwei Funktionen, zwei Endpunkte, 120 Tests über
beide. Als Nächstes das Template — Formatierung, Prozentzeichen, Tausendertrenner und
Vorzeichenfarbe entstehen dort, die Serialisierung liefert bewusst nur Zahlen und Quellen.


#### Phase 4, Schritt 5 — die Flask-Schicht, Grundgerüst

`app.py`, `templates/` und `static/` im Projektwurzelverzeichnis. Zwei Routen, drei Jinja-Filter, ein
Context Processor, drei Templates, zwei Stylesheets, zehn Schriftdateien. Drei der elf Blöcke sind
gerendert: `Headline`, `Assumptions`, `Provenance`. Die Testsuite ist unberührt, es gibt bisher keine
Tests auf die Ausgabeschicht.

**Was `mock_design.html` tatsächlich ist.** Kein statisches HTML, sondern ein gebundeltes Artifact:
392 Zeilen Loader, dahinter ein 1,4-MB-Manifest mit React, ReactDOM, Babel-standalone und 20
woff2-Dateien. Der `<body>` ist leer bis auf `<div id="root">`. Inhaltlich ist es ein
Broker-Dashboard ("Ledger", Holdings-Tabelle, New-Order-Modal), null Überschneidung mit den Blöcken
aus `serialize_company`. Es ist die **Stilvorlage**, nicht die Layoutvorlage — das Markup lässt sich
nicht übernehmen, weil dort alles in React-Inline-Style-Objekten steckt und keine einzige CSS-Klasse
existiert.

Übernommen wurde das Designsystem vollständig: Farbrampen (Indigo, Slate, Green, Red, Amber), die
Rollentokens in hell und dunkel, Typo-, Space-, Radius-, Schatten- und Motion-Tokens. Die sechs
verstreuten `:root`-Blöcke des Mocks sind in `static/tokens.css` zu einem zusammengezogen, die zwei
Dark-Blöcke ebenfalls — sonst überschreiben sich Schatten und Farben aus verschiedenen Stellen.

**Die Schriften liegen lokal, nicht auf einem CDN.** DM Sans und IBM Plex Mono, aus dem Manifest
extrahiert: 10 Dateien, 184 KB, 16 `@font-face`-Regeln. Nur `latin` und `latin-ext`; Cyrillic, Greek
und Vietnamese sind weggelassen, für englische Labels und deutsche Umlaute totes Gewicht im Repo.
DM Sans normal ist eine Variable-Font-Datei und deckt 400 bis 700 aus einer Datei ab, daher 16 Regeln
auf 10 Dateien. Der Grund gegen Google Fonts ist derselbe wie überall sonst im Projekt: Cache-DB,
Fixture-DB und Staleness-Schranken machen es offline-fähig, eine CDN-Abhängigkeit widerspricht dem.

**`DEFAULT_AS_OF` ist ein Datum, nicht `None`, und das ist keine Bequemlichkeit.** Ohne Stichtag nimmt
das Modell heute und prüft den neuesten Kurs im Cache dagegen — der ist vom 21.08.2026, also 21 Tage
alt bei einer Grenze von 14, und die Staleness-Schranke aus Schritt 16 greift. Mit `as_of = None`
zeigen **alle fünf** Firmen die Fehlerkarte. Der Stichtag kommt aus `?as_of=`, mit
`request.args.get("as_of") or DEFAULT_AS_OF`: `or` statt `is None`, weil `?as_of=` den leeren String
liefert und nicht `None`.

**Der Geldfilter wählt die Skala über den Betrag.** Der `Headline`-Block führt zwei Größenordnungen —
`Value_Per_Share` 128,17 in Dollar je Aktie, `EV` 1.860.146.063.224,25 in absoluten Dollar. Ein fester
Suffix kann beides nicht; `MONEY_SCALES = ((1e12, "T"), (1e9, "B"), (1e6, "M"))` mit `abs()` beim
Vergleich, sonst fällt jeder negative Wert durch alle Stufen.

**Die Grenze davon gehört notiert, weil sie später beißt:** Auto-Skalierung macht zwei Zahlen in
derselben Spalte unvergleichbar, eine Zeile zeigt "B", die nächste "M", und das Auge liest die
Ziffern. Für die vier StatCards ist das folgenlos, jede steht für sich. Sobald die Projektionstabelle
eine Geldspalte bekommt, braucht diese Spalte **eine** feste Skala für alle Zeilen — dann ein zweiter
Filter mit explizitem Faktor.

Gemessen, `as_of = "2026-08-19"`, gegen die Live-DB:

| Firma | Value per share | Market price | Enterprise value | WACC | Upside |
|---|---|---|---|---|---|
| apple | $128.17 | $305.93 | $1.86 T | 9,03 % | -58,10 % |
| boeing | $50.43 | $231.67 | $71.46 B | 8,04 % | -78,23 % |
| microsoft | $328.36 | $494.47 | $2.37 T | 9,16 % | -33,59 % |
| procter_gamble | $131.82 | $144.55 | $330.60 B | 6,86 % | -8,81 % |
| tesla | $15.71 | $342.27 | $23.04 B | 11,26 % | -95,41 % |

Antwortzeit 2 bis 4,5 s je Seite, blockierend gerendert. Das ist für ein lokales Werkzeug in Ordnung;
der Grund für den getrennten Monte-Carlo-Endpunkt war der Faktor 4 darauf, nicht die Blockierung an
sich. Es wird nichts zwischengespeichert, jeder Aufruf rechnet neu.

**Zwei Template-Regeln, die aus der Serialisierung kommen und dort schon begründet sind:** die
Erfolgsprüfung ist `Status == "calculated"` und nicht `Blocks_Failed` — im Fehlerzweig sind
`Headline`, `Assumptions` und `Provenance` ebenfalls `None` und stehen dort nicht drin. Und
`Assumptions` wird ohne `|sort` iteriert, weil die Reihenfolge Teil der Daten ist; `Provenance` ist
dagegen ein Dict und wird zeilenweise ausgeschrieben, eine Schleife über `.items()` würde die
Reihenfolge dem Zufall überlassen.

`COD_Evidence` bleibt vorerst draußen. Es ist selbst ein Dict (`Rating`, `Coverage`, `Year`, `n`,
`Realised`) und stünde sonst roh als `{'Rating': 'Aaa/AAA', ...}` in einer Zelle.

**Offen für die nächsten Schritte:** der Monte-Carlo-Endpunkt samt Nachladen im Browser, und die
restlichen sieben Blöcke — `Projection`, `Grid`, `Margin_Table`, `NWC_Table`, `Implied`, `Ceiling`,
`Horizon`. Das Sensitivitätsgitter und die Projektionstabelle sind die beiden, die eine eigene
Darstellungsentscheidung brauchen; die anderen fünf sind Tabellen wie `Assumptions`.


#### Phase 4, Schritt 6 — der Monte-Carlo-Endpunkt, nachgeladen

Zweite GET-Route `/company/<symbol>/monte-carlo`, das Fragment `templates/_monte_carlo.html`,
`static/mc.js` und die Lade- und Fehlerstile in `static/app.css`. `templates/company.html` trägt
dafür ein leeres `<section id="mc-panel" data-url="...">` mit Platzhalter. Damit sind vier der elf
Blöcke gerendert; die Testsuite ist weiterhin unberührt.

**Der Endpunkt liefert HTML, nicht JSON.** Das ist die Entscheidung, die alle sieben restlichen
Blöcke erben. Die Formatierung steckt in `pct`, `money` und `signed` in `app.py` — ein JSON-Endpunkt
zwänge dieselben drei Regeln ein zweites Mal in JavaScript, inklusive Tausendertrenner,
Skalenwahl und `None` → "N/A". Zwei Implementierungen derselben Darstellung driften auseinander,
und die zweite hätte keine Tests. Der Preis ist, dass der Browser Markup statt Daten bekommt: für
das Histogramm reicht das nicht, deshalb reiten die rohen Ziehungen als
`<script type="application/json" id="mc-draws">` mit.

**Das Fragment hat kein `{% extends %}`.** Es wird per `innerHTML` in eine bestehende Seite
gehängt; mit `extends` käme ein vollständiges Dokument samt `<!doctype>`, `<head>` und Sidebar
zurück und würde in die Seite hineinverschachtelt. Der Browser meckert dabei nicht, er baut es
einfach falsch zusammen.

**`as_of` geht über `url_for` in die `data-url`.** `url_for('monte_carlo', symbol = ...,
as_of = request.args.get('as_of'))` — ohne das fällt der Nachlade-Request auf `DEFAULT_AS_OF`
zurück, während die Seite darüber den Stichtag aus der Query zeigt. Zwei Stichtage nebeneinander,
ohne dass es auffällt; derselbe Fehler, der in Schritt 4 auf der Serialisierungsebene geschlossen
wurde, nur eine Schicht höher.

**`<script src="mc.js">` relativ ist eine Falle, die schweigt.** Auf `/company/apple` löst der
Browser das zu `/company/mc.js` auf, bekommt 404 und lädt nichts — der Spinner bleibt für immer
stehen, die Konsole ist leer, weil ein fehlendes Skript kein JS-Fehler ist. `url_for('static',
filename='mc.js')` in `base.html`, nicht optional.

**Der Timeout ist ein `AbortController`, kein Serverlimit.** `MC_TIMEOUT_MS = 60000` bei
gemessenen 13 bis 14 s: großzügig genug, dass ein kalter Lauf nicht darin läuft, knapp genug, dass
ein hängender Request nicht als Dauerspinner endet. `AbortError` trägt eine unbrauchbare
`.message` ("signal is aborted without reason") und wird über `error.name` auf einen eigenen Text
abgebildet; `clearTimeout` steht in `finally`, sonst hält der Timer die Seite unnötig wach.

**Der Fehlertext geht über `textContent`, nicht `innerHTML`.** Er kann eine Servermeldung
enthalten; über `innerHTML` liefe der Parser darüber. `.error-card` hängt in `app.css` an
derselben Regel wie `.card` statt eine zweite Kopie zu sein — ein roter Rahmen, eine Wahrheit.

**Der Leer-Zweig ist über echte Daten nicht erreichbar.** `Draws_Failed` ist bei allen fünf Firmen
null, wie schon bei 200 Ziehungen in Schritt 4. Sichtbar wird der Zweig nur über
`MC_PANEL_DRAWS = 0` in `app.py` — zwei Sekunden statt vierzehn, und genau dafür ist die Konstante
von `MC_DRAWS` getrennt. Der Zweig zeigt dann ein normales `.panel` mit `Draws OK` **und**
`Draws requested`, keine Fehlerkarte: `Status` ist dort `"calculated"`, und "0" allein ist die
halbe Aussage, "0 von 2000" die ganze.

Gemessen gegen die Live-DB, `as_of = "2026-08-19"`, `draws = 2000`, `seed = 12345`:

| Firma | Median | Median_Offset | P_Above_Market | Mode_Position | Antwortzeit | Fragment |
|---|---|---|---|---|---|---|
| apple | $126.79 | -1,08 % | 0,00 % | Interior | 14,2 s | 42,4 KB |
| boeing | $62.47 | +23,89 % | 0,00 % | Min | 13,6 s | 41,1 KB |
| microsoft | $322.74 | -1,71 % | 0,00 % | Interior | 13,8 s | 41,6 KB |
| procter_gamble | $130.26 | -1,18 % | 19,10 % | Max | 13,4 s | 42,5 KB |
| tesla | $16.65 | +5,99 % | 0,00 % | Min | 13,8 s | 42,3 KB |

`Draws_OK` ist überall 2000, `Draws_Failed` null. Vom Fragment sind rund 39 KB der `mc-draws`-Block,
das Markup selbst sind knapp 3 KB.

**`P_Above_Market` ist bei vier von fünf Firmen exakt null**, und das ist kein Rechenfehler: die
Streuung über WACC, Marge und Terminal Growth ist um Größenordnungen kleiner als die Lücke zum
Marktpreis aus Schritt 5 (-58 % bis -95 %). Keine einzige von 2000 Ziehungen erreicht den Kurs. Nur
Procter & Gamble mit -8,81 % Abstand liegt nah genug, dass 19,10 % der Ziehungen darüber landen. Die
Aussage des Panels ist damit nicht "wie wahrscheinlich ist der Kurs", sondern "wie eng ist das
Modell um seinen eigenen Punktwert" — die 12,7 bis 13,9 s kaufen eine Streuungsbreite, keine
Marktwahrscheinlichkeit.

**Offen:** `#mc-draws` liegt im DOM, aber nichts liest es — das ist der Histogramm-Schritt. Und die
Ausgabeschicht hat nach wie vor null Tests; nach diesem Schritt ist sie die einzige Schicht ohne.
Ein Test auf `/company/<symbol>/monte-carlo` gegen die Fixture-DB müsste mit kleinem `draws` laufen,
sonst kostet das Modul allein 70 s.


#### Phase 4, Schritt 7 — das Histogramm

`HIST_BINS = 24` und die Funktion `histogram` in `app.py`, ein Block in `_monte_carlo.html`,
103 Zeilen in `static/app.css`. `<script type="application/json" id="mc-draws">` ist gelöscht.

**Gebinnt wird auf dem Server, nicht im Browser.** Schritt 4 hatte das vorentschieden — eine
Binanzahl ist eine Darstellungsentscheidung und gehört in die Template-Schicht. Binning in `mc.js`
hieße Skalenwahl, Tausendertrenner und `None` → "N/A" ein zweites Mal in JavaScript, also genau die
Doppelung, die Schritt 6 vermieden hat. `histogram` sitzt deshalb in `app.py` neben den Filtern, nicht
in `serialize.py`: die Serialisierung liefert Zahlen und Quellen, sonst nichts.

**Damit ist `mc-draws` weggefallen.** Der Block war für ein JS-seitiges Histogramm gedacht und trug
39 KB, rund 93 % des Fragments. Verloren geht die Möglichkeit, die Binanzahl im Browser ohne
13-s-Neulauf zu ändern; nichts auf dem Plan braucht sie. Das Fragment ist von 42 KB auf 8 KB
gefallen. Kommt in einer Zeile zurück, sobald etwas die rohen Ziehungen tatsächlich liest.

**24 Bins, gemessen statt geschätzt.** Bei 16 ist kein Bin leer und der rechte Schwanz verschwindet
in der Balkenbreite; bei 32 sind bis zu 2 Bins leer und 7 haben unter vier Ziehungen; bei 40 bis zu
3 leere. 24 ist der Punkt, an dem höchstens ein Bin leer ist und die Rechtsschiefe trotzdem als Form
lesbar bleibt. Microsoft hat bei 24 genau einen echt leeren Bin — der Fall ist also real und nicht
konstruiert.

Vier Entscheidungen, die nicht offensichtlich sind:

- **Der Maximalwert muss auf den letzten Bin geklemmt werden.** `(hi - lo) / width` ergibt für ihn
  exakt `bins`, also einen Index, den es nicht gibt. Ohne die Klemme summieren sich die Zählungen auf
  1999 statt 2000, und zwar lautlos.
- **`Share` rechnet gegen `max_count`, nicht gegen die Gesamtzahl.** Bei 24 Bins hält der höchste
  Balken rund 12 % der Ziehungen; gegen 2000 gerechnet füllte die Grafik ein Achtel der Fläche und
  sagte nichts.
- **Nicht-leere Balken haben einen Mindestboden von 2 px, leere nicht.** Der letzte Bin hält 1 bis 5
  Ziehungen, also 0,3 bis 2 % der Höhe — unter einem Pixel. Ohne Boden ist "eine Ziehung" von "keine
  Ziehung" nicht unterscheidbar, mit Boden auf allen Bins ist es umgekehrt falsch. Das ist dieselbe
  Konvention wie überall im Projekt: Absenz muss sichtbar bleiben, und sie muss von Anwesenheit
  unterscheidbar bleiben.
- **Eine Markerposition außerhalb 0..1 ist `None`, nicht geklemmt.** Geklemmt stünde die Marktlinie
  bei vier von fünf Firmen am rechten Rand und sähe aus wie die höchste Ziehung. Stattdessen fällt
  der Marker weg und eine Zeile unter der Achse nennt den Preis und die Richtung.

**Diese Zeile ist bei vier von fünf Firmen die einzige Aussage zum Marktpreis**, und sie ist der
Kern des Panels. Die Streuung über WACC, Marge und Terminal Growth ist um Größenordnungen kleiner als
die Lücke zum Kurs aus Schritt 5: keine einzige von 2000 Ziehungen erreicht ihn. Nur Procter & Gamble
mit -8,81 % Abstand liegt nah genug, dass die Linie ins Bild fällt. Was das Histogramm zeigt, ist die
Enge des Modells um seinen eigenen Punktwert, nicht eine Marktwahrscheinlichkeit — dieselbe
Einschränkung wie bei `P_Above_Market`, nur jetzt sichtbar statt als Prozentzahl getarnt.

Gemessen gegen die Live-DB, `as_of = "2026-08-19"`, `draws = 2000`, `seed = 12345`, `HIST_BINS = 24`:

| Firma | Spanne | Binbreite | höchster Balken | Punktwert bei | Marktpreis |
|---|---|---|---|---|---|
| apple | 103,70 – 159,42 | 2,3218 | 241 @ 122,27–124,59 | 43,9 % | außerhalb, darüber |
| boeing | 28,51 – 122,68 | 3,9241 | 252 @ 59,90–63,82 | 23,3 % | außerhalb, darüber |
| microsoft | 245,39 – 434,29 | 7,8706 | 242 @ 308,36–316,23 | 43,9 % | außerhalb, darüber |
| procter_gamble | 96,13 – 198,56 | 4,2678 | 272 @ 126,00–130,27 | 34,8 % | **47,3 %** |
| tesla | 13,17 – 25,61 | 0,5184 | 288 @ 16,28–16,80 | 20,4 % | außerhalb, darüber |

Die Summe der Zählungen ist bei allen fünf exakt 2000, der höchste Balken exakt `100.0%`.
Antwortzeit 13,0 bis 14,0 s, unverändert gegenüber Schritt 6 — das Binnen kostet im Rauschen.

**Tests auf die Ausgabeschicht: bewusst verworfen.** Gregors Entscheidung, mit der Begründung, dass
ein kaputtes Template im Browser sofort sichtbar ist. Das stimmt für Layout und Formatierung. Es
stimmt nicht für die Fälle, die über echte Daten nicht auftreten: der Leer-Zweig ist nur über
`MC_PANEL_DRAWS = 0` erreichbar, der Entartungs-Zweig `hi == lo` in `histogram` über gar nichts, und
die Klemme im Zählschritt fällt bei 1999 statt 2000 Ziehungen optisch nicht auf. Diese drei sind
damit ungeprüft und bleiben es. Die Serialisierungsschicht darunter ist mit 120 Tests gepinnt, der
Schaden bleibt also auf die Darstellung begrenzt.


#### Phase 4, Schritt 8 — die Projektionstabelle

`PROJECTION_UNIT`, `PROJECTION_ROWS` und der Filter `unit` in `app.py`, die Tabelle in
`templates/company.html`, 46 Zeilen in `static/app.css`. Fünf der elf Blöcke sind gerendert:
`Headline`, `Assumptions`, `Provenance`, der Monte-Carlo-Endpunkt und jetzt `Projection`.

**Die in Schritt 5 notierte Grenze der Autoskalierung wird hier fällig, und zwar messbar.** Der
`money`-Filter wählt die Skala je Wert: Tesla hätte dNWC bei 26 M und Revenue bei 99.843 M in
derselben Tabelle, also "M" neben "B", und das Auge liest die Ziffern. Procter & Gamble mit dNWC bei
51 M gegen Revenue bei 89.286 M genauso. Deshalb ein zweiter Filter `unit` mit festem Faktor aus
`PROJECTION_UNIT = (1e6, "$ in millions")` — Faktor und Beschriftung als **ein** Paar, weil zwei
getrennte Konstanten still auseinanderlaufen: Kopfzeile sagt millions, Filter teilt durch 1e9, jede
Zahl ist um Faktor 1000 daneben und nichts wirft einen Fehler.

**Die Tabelle ist transponiert: Positionen als Zeilen, Jahre als Spalten.** Das ist die
Bankenkonvention und es ist hier auch das, was funktioniert — elf Positionen als Spalten hätten elf
verschiedene Einheiten nebeneinander, elf Jahre als Spalten teilen sich eine. Die Zeilenordnung und
die Beschriftungen stehen als `PROJECTION_ROWS` in `app.py`, ein Tupel aus Dreiertupeln
(Beschriftung, Schlüssel, Art). Der Nebeneffekt ist der eigentliche Gewinn: der Zugriff läuft über
`p[key]`, und damit ist `D&A` kein Sonderfall mehr — `p.D&A` wäre ein Jinja-Parse-Fehler, weil `&`
kein Operator in Ausdrücken ist.

**Die Terminalzeile hat drei leere Zellen, bei allen fünf Firmen.** `D&A`, `CapEx` und `dNWC` sind
dort `None`, weil die Reinvestition im Terminaljahr aus g/ROIC kommt und nicht aus den drei
Komponenten. Sie bleiben als "N/A" stehen. Auf `0` setzen wäre die direkte Verletzung der Konvention:
`0` ist anderswo ein gültiger dNWC-Wert, und die drei Zellen würden dann etwas behaupten. Praktische
Folge für jede spätere Änderung an dieser Tabelle: Arithmetik oder `|round` **vor** dem Filter wirft
dort `TypeError`, und der Negativtest muss `is not none` links vom `< 0` haben, sonst stirbt die Seite
bei allen fünf.

**`Is_Terminal` ist als Spaltentönung markiert, nicht als Badge.** Ohne Markierung liest die letzte
Spalte als elftes explizites Jahr; sie ist es nicht, ihr FCF speist die Terminal Value. Wer die elf
FCF-Zellen addiert und gegen `PV_Explicit` hält, sucht sonst einen Fehler, den es nicht gibt. Ein
Badge im Kopf schied aus, weil es eine von zwölf Spalten aufbläht statt sie zu markieren.

**`Projection` hat als einziger der restlichen Blöcke keinen Fehlerzweig.** Es wird in
`serialize.py` außerhalb der try-Schleife gebaut und steht nie in `Blocks_Failed`; innerhalb von
`{% if ok %}` ist es garantiert eine Liste. Ein `{% if panel.Projection %}` wäre toter Code. Bei
`Grid`, `Margin_Table`, `NWC_Table`, `Implied`, `Ceiling` und `Horizon` ist es genau umgekehrt — die
sechs brauchen den Guard, und das ist der Unterschied, der beim nächsten Block zählt.

**Zwölf Spalten passen nicht auf jeden Bildschirm.** Ein Wrapper mit `overflow-x: auto` und eine
klebende erste Spalte; die Trennlinie der klebenden Spalte ist ein `box-shadow` und kein `border`,
weil Ränder klebender Zellen bei `border-collapse: collapse` beim Scrollen verschwinden. Der Wrapper
muss der Scroll-Container sein, sonst übernimmt `.panel` mit seinem `overflow: hidden` und die Spalte
scrollt mit. Dazu eine Hover-Regel eigens für die klebende Zelle: sie trägt einen eigenen
Hintergrund und bliebe bei `tbody tr:hover` sonst als einzige Zelle hell stehen.

Gemessen gegen die Live-DB, `as_of = "2026-08-19"`, alle fünf Seiten Status 200:

| Firma | Jahre | Revenue erste | Revenue Terminal | FCF erste | FCF Terminal | dNWC erste | negative Zellen | Zeit |
|---|---|---|---|---|---|---|---|---|
| apple | 2026-2036 | $440,798 | $643,933 | $118,077 | $131,423 | $-2,173 | 12 | 4,7 s |
| boeing | 2026-2036 | $99,554 | $177,961 | $1,245 | $5,322 | $2,231 | 0 | 4,4 s |
| microsoft | 2027-2037 | $376,305 | $727,142 | $81,531 | $217,979 | $-3,735 | 10 | 4,0 s |
| procter_gamble | 2027-2037 | $89,286 | $114,696 | $15,107 | $17,319 | $-51 | 10 | 5,2 s |
| tesla | 2026-2036 | $99,843 | $142,378 | $-756 | $3,882 | $-26 | 12 | 1,7 s |

Überall 12 `<tr>`, 13 `<th>`, 132 `<td>`, 3-mal "N/A", 12-mal die Terminalklasse. Die Jahre laufen
nicht bei allen gleich — microsoft und procter_gamble beginnen ein Jahr später, deshalb kommt die
Kopfzeile aus `p.Year` und nicht aus einer festen Liste in `app.py`. Antwortzeit unverändert
gegenüber Schritt 5, das Rendern der 132 Zellen kostet im Rauschen.

**Das Vorzeichen steht vor dem Dollarzeichen, in beiden Geldfiltern.** Erst kam `$ -2,173` heraus,
weil das Minus aus der Zahl selbst stammt und die Formatierung es mitten im Ausdruck stehen lässt.
Korrigiert über ein abgespaltenes Vorzeichen und `abs()` im Formatstring — `money` hatte denselben
Fehler und ist mitgezogen, das ändert Headline, Histogrammachse und Monte-Carlo-Panel mit. Die
Restgrenze: `unit` rundet auf ganze Millionen, ein Betrag zwischen 0 und -500.000 zeigte `-$0`. In
der Projektion tritt das nicht auf, der kleinste Absolutwert über alle fünf Firmen ist 10 M
(Tesla dNWC).


#### Phase 4, Schritt 9 — das Sensitivitätsgitter

Ein Block in `templates/company.html`, 48 Zeilen in `static/app.css`, nichts in `app.py`. Sechs der
elf Blöcke sind gerendert. Anders als bei `Projection` liefert die Serialisierung hier alles, was die
Darstellung braucht: `Offsets`, `Growths`, `Rows`, und jede Zelle trägt ihre eigenen Koordinaten
(`Offset`, `Terminal_Growth`, `WACC`, `TV_Share`, `Status`). Kein neuer Filter, keine neue Konstante.

**Die Darstellungsentscheidung: Zweizustandsfärbung gegen den Marktpreis, keine Heatmap.** Eine
Farbskala über Minimum und Maximum des Gitters normiert innerhalb jeder Firma. Teslas Spanne von
14,05 bis 18,91 — Verhältnis 1,35 — bekäme damit exakt denselben Verlauf wie Boeings 21,95 bis
145,62, Verhältnis 6,63. Das ist die Histogramm-Falle ein zweites Mal, und hier schlimmer, weil fünf
Firmen nebeneinander gelesen werden. Die Schwelle beantwortet stattdessen die Frage, für die ein
Sensitivitätsgitter überhaupt existiert: welche Annahmenpaare rechtfertigen den aktuellen Kurs.

Die Antwort ist bei drei von fünf Firmen "keines", und das ist die Aussage, nicht ein Mangel an
Farbe. Gemessen, `as_of = "2026-08-19"`, `WACC_OFFSETS = (-0.02, -0.01, 0.0, 0.01, 0.02)`,
`TERMINAL_GROWTHS = (0.015, 0.02, 0.025, 0.03, 0.035)`:

| Firma | Gitterspanne | Verhältnis | Marktpreis | Zellen über Markt | TV-Anteil |
|---|---|---|---|---|---|
| apple | $97.88 – $207.87 | x2,12 | $305.93 | 0 von 25 | 39,4 – 68,5 % |
| boeing | $21.95 – $145.62 | x6,63 | $231.67 | 0 von 25 | 55,2 – 83,5 % |
| microsoft | $237.45 – $565.68 | x2,38 | $494.47 | 2 von 25 | 49,3 – 75,8 % |
| procter_gamble | $81.86 – $396.69 | x4,85 | $144.55 | 10 von 25 | 49,2 – 86,6 % |
| tesla | $14.05 – $18.91 | x1,35 | $342.27 | 0 von 25 | 66,1 – 83,6 % |

**Die Mittelzelle ist der Prüfstein, nicht Dekoration.** Offset `0.0` und Growth `0.025` sind exakt
die Basisannahmen; die Zelle ist bei allen fünf bis auf zehn Nachkommastellen identisch mit
`Headline.Value_Per_Share` — apple 128,17, boeing 50,43, microsoft 328,36, procter_gamble 131,82,
tesla 15,71. Stimmt sie nicht, ist die Zeilen- oder Spaltenreihenfolge verrutscht, und die Färbung
sitzt dann auf den falschen Zellen, ohne dass man es sieht.

`is-above` und `is-center` mussten zwei unabhängige `{% if %}` werden. Als `{% elif %}` geschrieben
schließen sie sich aus; das ist mit den heutigen Daten folgenlos, weil keine Mittelzelle über ihrem
Kurs liegt, verschluckt aber genau den Fall, für den das Gitter da ist — eine Firma, die unter ihrem
eigenen Basiswert handelt. Im CSS ist `is-center` deshalb ein Innenrahmen und keine Füllung, sonst
überschreibt eine der beiden Klassen die andere bei microsoft und procter_gamble.

**Die Monotonie gilt nicht durchgehend, und das ist kein Fehler.** Bei Tesla fällt die unterste Zeile
(Offset +0,02, WACC 13,26 %) mit steigendem Terminal Growth: 14,15 auf 14,05. Die vorletzte Zeile ist
praktisch flach. Ursache ist die Reinvestitionsmechanik — Tesla liegt bei einer Reinvestitionsquote
über 100 %, mehr Wachstum kostet dort mehr Kapital, als es an NOPAT einbringt. Jede spätere
Vereinfachung, die annimmt, die Werte stiegen nach rechts (etwa um das Maximum an einer Ecke
abzugreifen), hat in dieser Zeile ihren Gegenbeweis.

**Der Terminal-Value-Anteil ist gemessen, aber nicht dargestellt.** Er läuft über das Gitter von
39,4 % bis 86,6 %. Die Ecke oben rechts, die bei Procter & Gamble mit $396.69 den Kurs mühelos
schlägt, bezieht 86,6 % ihres Werts aus der Terminal Value und sagt damit fast nichts über die zehn
explizit modellierten Jahre aus. `TV_Share` liegt in jeder Zelle bereit; ein `title`-Attribut wie
beim Histogramm wäre der Ort dafür. Solange es fehlt, zeigt eine Zelle nur den Preis und verschweigt,
worauf er beruht.

**`Grid` ist der erste Block mit einem echten Fehlerzweig.** `Projection` entsteht außerhalb der
try-Schleife in `serialize.py` und ist innerhalb von `{% if ok %}` garantiert eine Liste; `Grid`,
`Margin_Table`, `NWC_Table`, `Implied`, `Ceiling` und `Horizon` laufen alle durch die Schleife und
werden bei `ValueError` zu `None`. Der `{% if panel.Grid %}` mit seinem `{% else %}` ist die Vorlage
für die nächsten fünf.

**Zwei Zweige bleiben ungeprüft.** Keine der 125 Zellen über alle fünf Firmen hat
`Status != "calculated"`, und `Grid` steht bei keiner in `Blocks_Failed`. Zellfehlerzweig und
Blockfehlerzweig sind über echte Daten beide unerreichbar, wie der Leer-Zweig des Histogramms. Sie
wären nur über eine künstlich enge `WACC_OFFSETS`-Reihe oder ein Symbol ohne Kursdaten zu sehen.

Gerendert: 6 Zeilen zu je 6 Zellen, 25 `<td>`, kein "N/A", genau eine `is-center` je Firma, grüne
Zellen 0/0/2/10/0. Antwortzeit unverändert, das Gitter war schon vorher Teil von `serialize_company`.

**Offen:** die Notizzeile unter der Tabelle für den Fall, dass keine Kombination den Marktpreis
erreicht. Betrifft apple, boeing und tesla. Ohne sie ist ein farbloses Gitter nicht davon zu
unterscheiden, dass es die Schwellenfärbung gar nicht gibt — dieselbe Lücke, die beim Histogramm die
Zeile unter der Achse schließt.


### Phase 7 — Documentation
- README with an explicit limitations section: which assumptions are judgment calls,
  where the model can be wrong, what it doesn't cover (no M&A adjustments, no one-off
  item cleanup, no bank support)
- Name Tesla as a scope limit, decided in Phase 5: the model covers the auto business only,
  misses the external low end by a factor of 8, and the joint lever ceiling (217.01) stays
  below the market price (342.27). Not an assumption to tune.

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
