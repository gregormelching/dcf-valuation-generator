# DCF Valuation Generator

A ten-year discounted cash flow model for five US large caps, built from filings instead of from a
spreadsheet. It pulls XBRL facts from SEC EDGAR, derives the drivers, projects free cash flow,
discounts at a CAPM WACC and serves one page per company with every assumption next to its source.
The output is not meant as a price target; the point is that every number traces back to a filing,
a constant, or a decision written down here.

## Run it

```
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
python logic/database.py    # EDGAR -> storage/values.db (put your own contact in the User-Agent)
python logic/prices.py      # yfinance + FRED -> same db
python app.py               # http://127.0.0.1:5000/company/apple
```

`?as_of=` moves the valuation date, `?start_year=` the driver window. Note that `prices.py` fetches
the weekly series only, so a fresh database also needs `fetch_prices(symbol, "1mo")` per symbol.

## Results

Measured at `as_of = 2026-08-19`, `start_year = 2016`, `years = 10`.

| Company | Value/share | Market | Upside | WACC | TV share |
|---|---|---|---|---|---|
| Apple | $128.17 | $305.93 | -58.1 % | 9.03 % | 51.4 % |
| Boeing | $50.43 | $231.67 | -78.2 % | 8.04 % | 67.8 % |
| Microsoft | $328.36 | $494.47 | -33.6 % | 9.16 % | 61.0 % |
| Procter & Gamble | $131.82 | $144.55 | -8.8 % | 6.86 % | 64.6 % |
| Tesla | $15.71 | $342.27 | -95.4 % | 11.26 % | 74.7 % |

All five come out below market, so read the table as a ranking and as a list of what you would have
to believe. Apple and Tesla cannot be argued up to their price even with all five levers at their
historical extreme at once, and that is the output the model exists to produce.

## Assumptions worth knowing

Revenue growth is the median of the yearly rates in the window, not a CAGR, because a CAGR reads
only the first and last year. For Boeing and Tesla the base is the mean of the last three years
instead, since their windows contain a structural break. Growth then fades linearly to 2.5 %
terminal growth, and the EBIT margin fades from the last actual margin to a per-company target.

The effective tax rate is measured from 2018 on, because the TCJA cut the federal rate from 35 % to
21 % and anything earlier averages two regimes. It fades to a 25 % marginal rate.

Working capital sums four slots including deferred revenue, and it is reconciled against the cash
flow statement at a 3 % tolerance. Four of five companies carry negative working capital, so growth
releases cash rather than consuming it.

Beta comes from 61 monthly closes against `^GSPC`, unlevered and relevered via Hamada, then
Blume-adjusted, with the standard error propagated into a WACC band. The equity risk premium is a
constant 4.28 %; there is no honest way to derive an implied ERP from this stack. The cost of debt
is synthetic, from interest coverage into Damodaran's spread table.

Terminal value is Gordon growth only, with reinvestment pinned by `g / ROIC`. A multiple would price
the company off the market price the model is supposed to test. Beyond the base case each page shows
a WACC/growth sensitivity grid, the value each lever alone would need to reach the market price, a
Monte Carlo over 2000 draws, and the number of projection years that would justify the price.

## Where it is wrong

- Boeing's WACC of 8.04 % is too low and nothing in the model can see it. Its beta window contains
  the 737 MAX grounding and the pandemic, and it gets an investment-grade floor on the debt side
  instead of the B2/B its coverage implies. Consensus runs 9 to 10 %.
- P&G's 6.86 % rests on a beta of 0.59 that the weekly cross-check does not confirm. The monthly
  window won on sample stability, not on evidence.
- The Monte Carlo is not centred on the base case. Boeing's median sits 23.9 % above its own base
  value because the triangular margin distribution is skewed by the spread between the margin bases.
- Terminal ROIC is hand-set per company with no derivation. It is the mildest of the five levers,
  so it is a credibility problem rather than a numerical one.
- Tesla is a scope limit, not an assumption question. The model values the auto business and would
  need a segment model for energy and FSD. Banks and insurers are out entirely, since operating
  income, CapEx and the working capital tags are missing for them under US-GAAP.

Figures are used as filed: no cleanup of one-off items, no M&A or segment adjustments, no lease or
stock compensation normalization. Anything suspicious is flagged rather than corrected, because a
number that is wrong but visible beats one that is clean but silent.

## Tests

537 tests under `pytest`, run in GitHub Actions on push and pull request. The fixture database is
checked in so the suite runs offline. Valuation results are pinned as golden values: reset them only
in a commit that says why, and update the numbers above in the same commit.
