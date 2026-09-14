# DCF Valuation Generator

A discounted cash flow model for five US large caps, built from filings instead of from a
spreadsheet someone handed over. It pulls XBRL facts from SEC EDGAR, derives the drivers, projects
ten years of free cash flow, discounts at a CAPM/synthetic-spread WACC and serves one page per
company — every assumption next to its source and its sensitivity.

The point is not the fair value. It is that every number can be traced to a filing, to a constant,
or to a decision written down here.

**This file is the only document in the project.** The code carries no explanatory comments by
design, so what the code cannot say — why an assumption is what it is, what was measured and
rejected, and where the model is known to be wrong — is below. Numbers quoted here were measured at
`as_of = 2026-08-19`, `start_year = 2016`, `years = 10`, `freq = "1mo"`.

## Run it

```
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
python logic/database.py    # EDGAR -> storage/values.db (put your own contact in the User-Agent in parser.py)
python logic/prices.py      # yfinance + FRED -> same db
python app.py               # http://127.0.0.1:5000/company/apple
```

Two URL parameters: `?as_of=2026-08-19` moves the valuation date, `?start_year=2016` the driver
window. Both fall back to the defaults in `app.py` when missing or unparsable.

Two things the scripts do not do for you: the `__main__` in `prices.py` fetches the weekly series
only, so a fresh database also needs `fetch_prices(symbol, "1mo")` per symbol for the market cap side,
and the FRED rates arrive on the first valuation that asks for them.

`damodaran.py` is a standalone cross-check of the WACC machinery against a pinned set of Damodaran
sector values (vintage January 2026, pulled 2026-08-20). Four of five land within 70 bp of their
sector cost of capital — Apple -68, Boeing +44, Microsoft -18, P&G -17 — and Tesla is +188 bp. It is
not part of the app.

## What comes out

| Company | Value/share | Market | Upside | WACC | TV share | Lever ceiling | Reachable |
|---|---|---|---|---|---|---|---|
| Apple | $128.17 | $305.93 | -58.1 % | 9.03 % | 51.4 % | $269.56 | no |
| Boeing | $50.43 | $231.67 | -78.2 % | 8.04 % | 67.8 % | $320.15 | yes |
| Microsoft | $328.36 | $494.47 | -33.6 % | 9.16 % | 61.0 % | $568.06 | yes |
| Procter & Gamble | $131.82 | $144.55 | -8.8 % | 6.86 % | 64.6 % | $380.17 | yes |
| Tesla | $15.71 | $342.27 | -95.4 % | 11.26 % | 74.7 % | $217.01 | no |

"Lever ceiling" is the value with all five levers — EBIT margin, WACC offset, terminal growth, NWC
intensity, revenue growth — simultaneously at their historical extreme. "Reachable" says whether
that ceiling clears the market price.

All five come out below market. Read the table as a ranking and as a list of what you would have to
believe, not as five price targets. Two companies cannot be argued to their price at all without
leaving the historical range, and that is the output the model exists to produce.

## Pipeline

| File | Does |
|---|---|
| `logic/parser.py` | 20 years of 10-K XBRL facts per company from EDGAR, tag by tag, multi-slot metrics summed or selected |
| `logic/validation.py` | one flag list per value: `missing`, `negative`, `outlier`, plus the working capital reconciliation |
| `logic/database.py` | SQLite cache: values, flags, prices, rates, raw downloads. Nothing is refetched per request |
| `logic/model.py` | effective tax rate, growth rates, driver ratios, revenue and FCF projection |
| `logic/prices.py` | yfinance prices (daily pull, resampled), FRED `DGS10` risk-free rate |
| `logic/wacc_calculation.py` | beta chain, CAPM, synthetic cost of debt, WACC with a confidence band |
| `logic/valuation.py` | DCF, sensitivity grid and tables, implied levers, plausible ceiling, implied horizon, Monte Carlo |
| `logic/serialize.py` | one dict per company for the view layer; no math |
| `app.py`, `templates/`, `static/` | Flask, three routes: index, company page, lazily loaded Monte Carlo fragment |

## The assumptions that move the number

Measured first, so the order is not a guess. Each column is one input moved away from the base case,
everything else held:

| Company | WACC -1 pp | EBIT margin +2 pp | Revenue growth +2 pp | Terminal growth +0.5 pp | Terminal ROIC x1.5 |
|---|---|---|---|---|---|
| Apple | +15.6 % | +4.7 % | +7.4 % | +4.1 % | +3.5 % |
| Boeing | +42.5 % | +69.0 % | +11.6 % | +9.5 % | +10.8 % |
| Microsoft | +18.5 % | +3.7 % | +7.4 % | +4.6 % | +4.0 % |
| Procter & Gamble | +30.7 % | +7.8 % | +8.8 % | +9.1 % | +4.2 % |
| Tesla | +7.2 % | +21.2 % | +3.6 % | +0.3 % | +4.1 % |

The discount rate dominates everywhere except Boeing and Tesla, where the EBIT margin does — both
operate near zero margin, so two points is a large relative move. Terminal ROIC is the weakest of the
five even at a 50 % relative change, which is worth knowing before anyone spends a week deriving it.

### Cash flows

- **Revenue growth is the median of the yearly rates in the window, not a CAGR.** A CAGR reads only
  the first and last year and inherits whatever happened in those two. Per company the base is a
  decision: median for Apple, Microsoft and P&G, mean of the last three clean years for Tesla and
  Boeing, whose medians sit on a window with a structural break in it. Set in
  `valuation.ASSUMPTIONS`.
- **Growth fades linearly** from the base rate to terminal growth, reaching it exactly in the last
  explicit year: `g_t = g0 + (g_terminal - g0) * i/N`.
- **The EBIT margin fades too**, from the last actual margin to a target chosen per company —
  `Mean_Last_Three` for Apple, Microsoft, P&G; `Last` for Boeing and Tesla. A flat margin from year
  one was the previous behaviour and was wrong for Boeing, which earned 4.79 % in 2025 against a
  ten-year mean far above it.
- **The fade start is reported, not filtered.** If the last actual margin sits on a flagged year
  (Boeing does), the number is still used and the flag is carried into the output. The start means
  "where the company is"; silently substituting a cleaner year would hide exactly the situation the
  reader needs to see.
- **"Mean of the last three" means three contiguous years.** Averaging the last three *clean* entries
  quietly mixed 2018, 2022 and 2023 for Boeing under a label that claims recency.
- **The tax rate is measured from 2018 on** (`TAX_WINDOW_START`), because the TCJA cut the federal
  rate from 35 % to 21 % and anything earlier averages two tax regimes. It fades to
  `MARGINAL_TAX_RATE = 25 %`, which the terminal year uses outright: a company cannot hold a 15.8 %
  effective rate forever.
- **Working capital has four slots**, including deferred revenue (`ContractWithCustomerLiability`),
  and they are summed, not selected. Four of five companies carry *negative* working capital —
  payables and deferred revenue exceed receivables and inventory — so growth releases cash instead
  of consuming it. Apple -8.82 %, Microsoft -8.40 %, P&G -2.27 %, Tesla -0.52 %, Boeing +22.11 % of
  revenue.
- **Working capital is reconciled against the cash flow statement** with a 3 % tolerance
  (`RECON_TOLERANCE`). Beyond that the year is flagged rather than corrected.
- **Terminal reinvestment is pinned by `g / ROIC`**, not inherited from the explicit period. The
  terminal ROIC is a hand-set per-company assumption — Apple, Microsoft and P&G 20 %, Boeing 15 %,
  Tesla 12 % — and it is the single least defensible input in the model. It is checked against the
  implicit terminal ROIC, not derived from it, because deriving it would make the check circular.

### Discount rate

- **Beta comes from 61 monthly closes against `^GSPC`**, unlevered and relevered via Hamada at the
  marginal 25 %, then Blume-adjusted (`0.67 * beta + 0.33`). The standard error is computed by hand
  and propagated into `WACC_Low` / `WACC_High`.
- **The window choice is unresolved and it matters.** A five-year monthly window measures a
  different company than a two-year weekly one; the weekly cross-check contradicts the monthly
  estimate for two of the five. Monthly won on sample stability, not on evidence.
- **The equity risk premium is a constant, 4.28 %.** There is no honest source for an implied ERP in
  this stack, and a hand-waved regression would be worse than a stated constant.
- **The cost of debt is synthetic**: interest coverage into Damodaran's spread table, on top of the
  risk-free rate. It lands at Aaa/AAA for four of five companies (5.05 %), so it carries no
  company-specific information for them.
- **Boeing gets an investment-grade floor**, not its synthetic rate. Its coverage of 1.54x implies
  B2/B and a 7.86 % cost of debt; the model asserts it can borrow at the investment-grade boundary
  instead (5.76 %). This is an assumption about a turnaround, and the rejected alternative — plus the
  realised rate, 4.73 % — stays visible on the page.
- **Weights use gross debt and market cap, never net debt.** Cash is added back in the equity bridge;
  netting it in both places would count it twice.
- **Two prices, both reported.** The market price for the upside comes from the weekly series, the
  market cap from the monthly one, with separate staleness bounds (14 and 45 days). A single series
  would either be stale for the bridge or too jumpy for the headline.

### Terminal value

- **Gordon growth only.** `method="multiple"` exists in `terminal_value` but is not used: EDGAR
  carries filings, not peer multiples, and a multiple taken from today's market prices the company
  off the price the model is supposed to test. The implied multiple is reported as a diagnostic
  instead — the inverse direction, and the honest one.
- **Terminal growth is 2.5 %, capped at the 10-year Treasury.** Perpetual growth is a statement about
  the economy, not about a company, so it is not differentiated per company; that was checked and
  rejected. The cap binds only when rates fall below 2.5 %; at the pinned date it does not.
- **The terminal value is discounted at exponent N, not N+1**, and all cash flows use the mid-year
  convention.
- **Between 51 % and 75 % of enterprise value sits in the terminal value.** Most of the answer is an
  assumption about year 11 and later, and no amount of detail in the explicit period changes that.

## What the page shows beyond the base case

- **Sensitivity grid**: WACC offset -2 to +2 pp against terminal growth 1.5 % to 3.5 %.
- **Margin table** over the three margin bases, **NWC table** over ±5 pp around the company's own
  intensity.
- **Implied levers**: for each of the five levers, the value it would have to take alone to reach the
  market price, plus whether that value is inside the company's own history.
- **Plausible ceiling**: all five levers at their historical extreme at once. The per-lever
  contributions do not add up to the total — interactions are counted twice, by up to 114 % — and the
  page says so.
- **Implied horizon**: how many years of the current projection would be needed to reach the price,
  scanned over 1 to 30 years. Tesla's curve *falls* — above a 100 % reinvestment rate another year of
  growth costs more capital than it earns.
- **Monte Carlo**, 2000 draws, seed 12345: WACC normal around the base with the beta standard error,
  EBIT margin triangular over the three margin bases, terminal growth uniform over 1.5/2.5/3.5 %.
  The three inputs are drawn independently, which they are not in reality.

## Conventions in this codebase

- **Every ratio is defined only together with its window.** Quote the window whenever you quote the
  ratio.
- **Absence stays visible.** Functions return a `Source` and an `n` next to the number. Flags separate
  "checked and clean" from "not checkable" (`unchecked`, `recon_unchecked`). A plausible default is
  never substituted for missing data — `0` is a legitimate dNWC value.
- **The parser path and the cache path signal absence differently.** Parser dicts omit `Value`;
  `get_data` sets it to `None`. A guard written for one is dead code against the other.
- **A number that is wrong but visible beats a number that is clean but silent.** Most of the
  decisions above follow from that.
- **Badge labels are a width budget, not free prose.** `.panel` clips instead of scrolling, so a
  long status label pushed the quality table's source column off screen below 960 px before the
  table was wrapped in `.horizontal-scroll`. Keep new labels short and check the narrow viewport.
- No explanatory comments in the code. New assumptions go into this file.

## Known defects and open gaps

Ranked by what they cost.

1. **Boeing's WACC of 8.04 % is probably too low, and neither the model nor the cross-check can see
   it.** Company-level consensus runs 9 to 10 %. Its beta is measured over a window containing the
   737 MAX grounding and the pandemic, and the investment-grade floor pushes the debt side down
   further. The Damodaran check passes it at +44 bp because it compares against an average of 79
   aerospace firms, most of which are not in a turnaround.
2. **P&G's 6.86 % is the weakest number in the model**, resting on a beta of 0.59 that the weekly
   cross-check does not confirm.
3. **The Monte Carlo is not centred on the base case.** Boeing's median sits 23.9 % above its own base
   value, Tesla's 6.0 %. The triangular margin distribution is skewed by the spread between the three
   margin bases, so the distribution describes the input set, not the uncertainty around the answer.
4. **`terminal_roic` is hand-set per company and has no derivation.** Measured, it is the mildest of
   the five levers — a 50 % relative move buys 3.5 % to 10.8 % — so it is a credibility problem in an
   interview, not a numerical one.
5. **`^GSPC` is a price index without dividends** while the stock series are total-return adjusted.
   The beta is measured across that mismatch.
6. **Tesla is a scope limit, not an assumption question.** The model values the auto business; it
   misses the low end of the external range by a factor of 8, and even the lever ceiling of $217.01
   stays below the market price of $342.27. A segment model for energy and FSD would be a different
   project.
7. **`Data_Start_Year` only checks that a value exists, not that it is usable.** A year with one set
   field and flags on everything else counts as the data start. For these five it coincides; for a
   sixth it need not.
8. **Boeing's NWC intensity is not stationary** — it falls from 43.7 % to 16.9 % across the window —
   and the median hides that.
9. **Microsoft's CapEx has no fade path.** Its 25.3 % of revenue is a data-centre build-out held flat
   for ten years.
10. **Apple FY2025 carries a 19.4 bn working capital residuum** that is flagged but unexplained.
11. **A `start_year` before the first filed year widens the window to the earliest year on file** —
    2006 for Apple and Boeing, 2007 for Microsoft and P&G, 2008 for Tesla. The Provenance panel names
    the effective year and flags it, but nothing refuses the request.
12. **Prices are read from the cache, never fetched on demand.** A valuation date outside the cached
    window fails at the price bound instead of pulling data.

Out of scope by decision, not by omission:

- **Banks and insurers.** Operating income, CapEx and every working capital tag are missing for them
  under US-GAAP; a classic opex/working-capital DCF is not buildable from these filings.
- **No cleanup of one-off items, no M&A or segment adjustments, no normalization of leases or stock
  compensation.** Figures are used as filed, with flags.
- **No historical ROIC for Apple** (invested capital is negative in six of ten years, and the years
  below 5 % of revenue are excluded so a tiny denominator cannot manufacture a 300 % return) **and
  none for Boeing** (too few years with clean flags). For those two the consistency check rests on
  the implicit terminal ROIC alone.

## Tests

537 tests, `pytest`, GitHub Actions on push and pull request to `main`.

- The fixture database is **checked in**. Every test runs against it, offline, including the
  risk-free rate — a suite that silently skips itself when a file is missing is worse than no suite.
- Valuation results are pinned as golden values. **Reset them only in a commit whose message says
  why**, and update the numbers in this file in the same commit. A golden value that moves without a
  written reason is indistinguishable from a regression.
- `app.py` and the templates are deliberately untested; the tested surface ends at `serialize.py`. A
  wrong label shows up on the first page load, a wrong formula would not.
- Template branches that no company triggers — the `Unavailable` cost-of-debt path, the block-failure
  cards — are unverified. A smoke test would not have caught them either, since it would call the
  same five companies.
