import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "logic"))

from logic.database import get_data
from logic.model import effective_tax_rate, roic, MARGINAL_TAX_RATE
from logic.prices import risk_free_rate
from logic.wacc_calculation import calc_wacc, adjusted_beta, cost_of_debt, EQUITY_RISK_PREMIUM, COD_FALLBACK_START_YEAR, synthetic_cost_of_debt
from logic.valuation import dcf_value, ASSUMPTIONS
from logic.validation import OUTLIER_RULES

REFERENCE_VINTAGE = "January 2026"
REFERENCE_PULLED = "2026-08-20"
REFERENCE_SOURCES = {
    "wacc": "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/wacc.htm",
    "betas": "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/Betas.html",
    "vebitda": "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/vebitda.html",
    "eva": "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/EVA.html",
    "ratings": "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/ratings.htm",
    "erp": "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/ctryprem.html",
}

IMPLIED_ERP = {"ERP": 0.0446, "As_Of": "2026-01-05", "Source": "ctryprem"}

DAMODARAN = {
    "apple": {
        "Industry": "Computers/Peripherals", "Firms": 36,
        "Beta": 1.35, "Beta_Unlevered": 1.32, "DE_Current": 0.0462,
        "Effective_Tax_Rate": 0.0591, "Cost_of_Equity": 0.0997, "Cost_of_Debt": 0.0529,
        "Weight_Equity": 0.9558, "WACC": 0.0971, "Implied_Multiple": 25.42, "ROIC": 0.4476,
    },
    "microsoft": {
        "Industry": "Software (System & Application)", "Firms": 309,
        "Beta": 1.28, "Beta_Unlevered": 1.25, "DE_Current": 0.0558,
        "Effective_Tax_Rate": 0.0551, "Cost_of_Equity": 0.0964, "Cost_of_Debt": 0.0529,
        "Weight_Equity": 0.9472, "WACC": 0.0934, "Implied_Multiple": 24.48, "ROIC": 0.2932,
    },
    "procter_gamble": {
        "Industry": "Household Products", "Firms": 110,
        "Beta": 0.82, "Beta_Unlevered": 0.74, "DE_Current": 0.1815,
        "Effective_Tax_Rate": 0.0650, "Cost_of_Equity": 0.0759, "Cost_of_Debt": 0.0529,
        "Weight_Equity": 0.8464, "WACC": 0.0703, "Implied_Multiple": 13.17, "ROIC": 0.3442,
    },
    "boeing": {
        "Industry": "Aerospace/Defense", "Firms": 79,
        "Beta": 0.95, "Beta_Unlevered": 0.87, "DE_Current": 0.1556,
        "Effective_Tax_Rate": 0.1158, "Cost_of_Equity": 0.0817, "Cost_of_Debt": 0.0529,
        "Weight_Equity": 0.8653, "WACC": 0.0760, "Implied_Multiple": 21.58, "ROIC": 0.1601,
    },
    "tesla": {
        "Industry": "Auto & Truck", "Firms": 33,
        "Beta": 1.46, "Beta_Unlevered": 1.31, "DE_Current": 0.1970,
        "Effective_Tax_Rate": 0.0374, "Cost_of_Equity": 0.1045, "Cost_of_Debt": 0.0529,
        "Weight_Equity": 0.8355, "WACC": 0.0938, "Implied_Multiple": 47.76, "ROIC": 0.0225,
    },
}

METRICS = [
    ("Beta", "Levered beta", "num", 0.30),
    ("Beta_Unlevered", "Unlevered beta", "num", 0.30),
    ("DE_Current", "D/E (market)", "pct", 0.10),
    ("Weight_Equity", "E/(D+E)", "pct", 0.10),
    ("Cost_of_Equity", "Cost of equity", "pct", 0.0200),
    ("Cost_of_Debt", "Cost of debt (pre-tax)", "pct", 0.0200),
    ("Effective_Tax_Rate", "Effective tax rate", "pct", 0.1000),
    ("WACC", "WACC / cost of capital", "pct", 0.0200),
    ("ROIC", "ROIC", "pct", 0.1500),
    ("Implied_Multiple", "EV/EBITDA", "mult", 0.50),
]

NOTES = [
    "The reference is an industry aggregate over all US firms in the sector, not a peer set picked for size or business mix. A mega-cap deviating from its sector average is information, not an error.",
    "The reference effective tax rate is computed over the sector including loss-making firms, which drags it far below any profitable large cap. The gap on that row is structural; MARGINAL_TAX_RATE is the comparable number.",
    "The reference cost of debt is one US-wide figure, not per industry. Ours is a realised interest/debt ratio over the 2023+ or 2018+ window, i.e. the coupon on legacy debt rather than today's marginal rate. The synthetic row is the like-for-like comparison.",
    "The reference EV/EBITDA is a current market multiple on trailing EBITDA. Implied_Multiple is the Gordon terminal value over year-10 EBITDA, so it prices a faded, mature business ten years out and belongs below the reference. A gap only indicts the model if the fade or the terminal growth is the cause.",
    "The reference ROC is a single trailing year over book capital; ROIC_Median is the median over the available history on the same book basis.",
]

TOLERANCE_ERP = 0.0050
TOLERANCE_SYNTHETIC_COD = 0.0200

def own_numbers(symbol: str, start_year: int, years: int, freq: str, n: int, as_of: str) -> dict:
    data = get_data(symbol, start_year)
    wacc = calc_wacc(data, symbol, freq, n, as_of=as_of)
    beta = adjusted_beta(data, symbol, freq, n, as_of)
    tax = effective_tax_rate(data)
    returns = roic(data)
    valuation = dcf_value(symbol, start_year, years, freq, n, as_of=as_of)["wacc"]
    rf = risk_free_rate(as_of)
    cod_long = cost_of_debt(data, COD_FALLBACK_START_YEAR)

    return {
        "Beta": beta["Beta"], "Beta_Raw": beta["Beta_Raw"], "Beta_Unlevered": beta["Beta_Unlevered"],
        "DE_Current": beta["DE_Current"], "Weight_Equity": wacc["Weight_Equity"],
        "Cost_of_Equity": wacc["Cost_of_Equity"], "Cost_of_Debt": wacc["Cost_of_Debt"],
        "Cost_of_Debt_Long": cod_long["Cost_of_Debt"], "COD_Source": wacc["COD_Source"],
        "Effective_Tax_Rate": tax["Effective_Tax_Rate"], "Tax_Source": tax["Source"], "Tax_n": tax["n"],
        "WACC": wacc["WACC"], "ROIC": returns["ROIC_Median"], "ROIC_Source": returns["Source"],
        "Implied_Multiple": valuation["Implied_Multiple"], "Value_Per_Share": valuation["Value_Per_Share"],
        "Data_Filed": valuation["Data_Filed"], "Risk_Free_Rate": rf["Risk_Free_Rate"], "RF_Date": rf["Date"],
        "Synthetic": synthetic_cost_of_debt(data, rf),
    }


def fmt(value, unit: str) -> str:
    if value is None:
        return "n/a"
    if unit == "pct":
        return f"{value * 100:.2f}%"
    if unit == "mult":
        return f"{value:.2f}x"
    return f"{value:.3f}"


def fmt_delta(delta, unit: str) -> str:
    if delta is None:
        return "n/a"
    if unit == "pct":
        return f"{delta * 10000:+.0f}bp"
    if unit == "mult":
        return f"{delta:+.2f}x"
    return f"{delta:+.3f}"


def verdict(delta, tolerance: float, unit: str, reference) -> str:
    if delta is None:
        return "n/a"
    if unit == "mult":
        return "OK" if abs(delta) <= tolerance * reference else "GAP"
    return "OK" if abs(delta) <= tolerance else "GAP"


def compare(own: dict, reference: dict) -> list:
    rows = []
    for key, label, unit, tolerance in METRICS:
        ours = own.get(key)
        theirs = reference.get(key)
        delta = None if ours is None or theirs is None else ours - theirs
        rows.append({
            "Metric": label, "Ours": fmt(ours, unit), "Damodaran": fmt(theirs, unit),
            "Delta": fmt_delta(delta, unit), "Verdict": verdict(delta, tolerance, unit, theirs),
        })
    return rows


def print_rows(rows: list) -> None:
    columns = ["Metric", "Ours", "Damodaran", "Delta", "Verdict"]
    widths = {c: max(len(c), max(len(str(r[c])) for r in rows)) for c in columns}
    print("  ".join(c.ljust(widths[c]) for c in columns))
    print("  ".join("-" * widths[c] for c in columns))
    for row in rows:
        print("  ".join(str(row[c]).ljust(widths[c]) for c in columns))


def run(start_year: int = 2016, years: int = 10, freq: str = "1mo", n: int = 61, as_of: str = "2026-08-19") -> dict:
    print(f"Damodaran cross-check  |  as_of {as_of}  |  reference vintage {REFERENCE_VINTAGE}  |  pulled {REFERENCE_PULLED}")
    print()

    erp_delta = EQUITY_RISK_PREMIUM - IMPLIED_ERP["ERP"]
    print(f"ERP  ours {EQUITY_RISK_PREMIUM * 100:.2f}%  Damodaran {IMPLIED_ERP['ERP'] * 100:.2f}% ({IMPLIED_ERP['As_Of']})  "
          f"delta {erp_delta * 10000:+.0f}bp  {'OK' if abs(erp_delta) <= TOLERANCE_ERP else 'GAP'}")
    print(f"Marginal tax rate  ours {MARGINAL_TAX_RATE * 100:.2f}%")
    print()

    results = {}
    for symbol in sorted(DAMODARAN):
        reference = DAMODARAN[symbol]
        own = own_numbers(symbol, start_year, years, freq, n, as_of)
        rows = compare(own, reference)
        results[symbol] = {"Own": own, "Rows": rows}

        print(f"{symbol.upper()}  |  {reference['Industry']} ({reference['Firms']} firms)  |  "
              f"value per share {own['Value_Per_Share']:.2f}  |  data filed {own['Data_Filed']}")
        print_rows(rows)

        synthetic = own["Synthetic"]
        if synthetic["Source"] == "Calculated":
            delta = None if own["Cost_of_Debt"] is None else synthetic["Cost_of_Debt"] - own["Cost_of_Debt"]
            print(f"  synthetic cost of debt: coverage {synthetic['Coverage']:.2f}x ({synthetic['Year']}) -> {synthetic['Rating']} "
                  f"-> rf {own['Risk_Free_Rate'] * 100:.2f}% + {synthetic['Spread'] * 100:.2f}% = {synthetic['Cost_of_Debt'] * 100:.2f}%  "
                  f"vs ours {fmt(own['Cost_of_Debt'], 'pct')} (window {own['COD_Source']}+)  delta {fmt_delta(delta, 'pct')}  "
                  f"{verdict(delta, TOLERANCE_SYNTHETIC_COD, 'pct', None)}")
        else:
            print(f"  synthetic cost of debt: {synthetic['Source']} - no year with clean EBIT and InterestExpense")

        print(f"  terminal ROIC assumed {ASSUMPTIONS[symbol]['terminal_roic'] * 100:.2f}%  |  "
              f"ROIC median source {own['ROIC_Source']}  |  reference sector ROC {reference['ROIC'] * 100:.2f}%")
        print(f"  tax rate source {own['Tax_Source']} (n={own['Tax_n']})  |  cost of debt 2018+ {fmt(own['Cost_of_Debt_Long'], 'pct')}  |  "
              f"rf {own['Risk_Free_Rate'] * 100:.2f}% ({own['RF_Date']})")
        print()

    print("Comparability notes")
    for i, note in enumerate(NOTES, start=1):
        print(f"  {i}. {note}")
    print()
    print("Sources")
    for name, url in REFERENCE_SOURCES.items():
        print(f"  {name}: {url}")

    return results


if __name__ == "__main__":
    run()
