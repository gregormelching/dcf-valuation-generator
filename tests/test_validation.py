import pytest
from validation import (
    RECON_TOLERANCE, validate_values, reconcile_working_capital, check_recon_tolerance,
)

BASE = {"Revenue": 1000.0, "OperatingIncome": 200.0, "D&A": 50.0, "CapEx": 60.0,
        "SharesOutstanding": 10.0, "WorkingCapital": 20.0, "Cash": 100.0, "Debt": 400.0,
        "PretaxIncome": 180.0, "InterestExpense": 5.0, "Tax": 45.0, "Equity": 700.0, "NWC": 30.0}
RECON_BASE = {"NetIncome": 150.0, "OCF": 220.0, "SBC": 30.0, "DeferredTaxes": 10.0}

def pyear(missing = (), **over):
    return {name: ({} if name in missing else {"Value": value}) for name, value in {**BASE, **over}.items()}

def ryear(missing = (), **over):
    return {name: ({} if name in missing else {"Value": value}) for name, value in {**RECON_BASE, **over}.items()}

def flagged(values):
    flags = validate_values(values)
    return {year: {name: f for name, f in flags[year].items() if f}
            for year in flags if any(flags[year].values())}

def test_validate_clean():
    flags = validate_values({2020: pyear(), 2021: pyear()})

    assert sorted(flags) == [2020, 2021]
    assert sorted(flags[2020]) == sorted(BASE)
    assert all(f == [] for year in flags for f in flags[year].values())

@pytest.mark.parametrize("values, expected", [
    ({2020: pyear(), 2021: pyear()},
     {}),
    ({2020: pyear(), 2021: pyear(missing = ("CapEx",))},
     {2021: {"CapEx": ["missing"]}}),
    ({2020: pyear(CapEx = -60.0), 2021: pyear(CapEx = -60.0)},
     {2020: {"CapEx": ["negative"]}, 2021: {"CapEx": ["negative"]}}),
    ({2020: pyear(), 2021: pyear(CapEx = -60.0)},
     {2021: {"CapEx": ["negative", "outlier"]}}),
    ({2020: pyear(OperatingIncome = 10.0), 2021: pyear(OperatingIncome = -10.0)},
     {}),
    ({2020: pyear(), 2021: pyear(CapEx = 100.0)},
     {2021: {"CapEx": ["outlier"]}}),
    ({2020: pyear(CapEx = 0.0), 2021: pyear()},
     {2021: {"CapEx": ["unchecked"]}}),
    ({2020: pyear(), 2021: pyear(OperatingIncome = 280.0)},
     {2021: {"OperatingIncome": ["outlier"]}}),
    ({2020: pyear(), 2021: pyear(OperatingIncome = 270.0)},
     {}),
    ({2020: pyear(missing = ("Revenue",)), 2021: pyear()},
     {2020: {"Revenue": ["missing"], "WorkingCapital": ["unchecked"]},
      2021: {"OperatingIncome": ["unchecked"], "PretaxIncome": ["unchecked"]}}),
    ({2020: pyear(WorkingCapital = 200.0)},
     {2020: {"WorkingCapital": ["outlier"]}}),
    ({2020: pyear(WorkingCapital = 100.0)},
     {}),
    ({2020: pyear(Revenue = 0.0)},
     {2020: {"WorkingCapital": ["unchecked"]}}),
    ({2020: pyear(Tax = 100.0)},
     {2020: {"Tax": ["outlier"]}}),
    ({2020: pyear(Tax = -10.0)},
     {2020: {"Tax": ["outlier"]}}),
    ({2020: pyear(PretaxIncome = -180.0)},
     {2020: {"Tax": ["unchecked"]}}),
    ({2020: pyear(PretaxIncome = 0.0)},
     {2020: {"Tax": ["unchecked"]}}),
    ({2020: pyear(CapEx = 1000.0)},
     {}),
], ids = ["clean", "missing", "negative_both_years", "negative_and_outlier", "exception_negative",
          "yoy_outlier", "yoy_unchecked", "margin_pp_outlier", "margin_pp_boundary",
          "revenue_missing_prior", "pct_of_revenue_outlier", "pct_of_revenue_boundary",
          "pct_of_revenue_unchecked", "effective_rate_high", "effective_rate_negative",
          "effective_rate_pretax_negative", "effective_rate_pretax_zero", "first_year_no_yoy"])
def test_validate_flags(values, expected):
    assert flagged(values) == expected

@pytest.mark.parametrize("recon, expected", [
    (ryear(),                       {"Residuum": 0.0,   "Residuum_pct": 0.0,   "Own": 20.0, "Implicit": 20.0}),
    (ryear(OCF = 260.0),            {"Residuum": -40.0, "Residuum_pct": -0.04, "Own": 20.0, "Implicit": -20.0}),
    (ryear(missing = ("SBC",)),     {}),
], ids = ["in_tolerance", "gap", "missing_input"])
def test_reconcile(recon, expected):
    out = reconcile_working_capital({2020: pyear()}, {2020: recon})

    assert out == {2020: expected}

def test_reconcile_missing_own_value():
    out = reconcile_working_capital({2020: pyear(missing = ("D&A",))}, {2020: ryear()})

    assert out == {2020: {}}

def test_reconcile_zero_revenue_unguarded():
    with pytest.raises(ZeroDivisionError):
        reconcile_working_capital({2020: pyear(Revenue = 0.0)}, {2020: ryear()})

def test_reconcile_missing_year_unguarded():
    with pytest.raises(KeyError):
        reconcile_working_capital({2020: pyear(), 2021: pyear()}, {2020: ryear()})

@pytest.mark.parametrize("rec_wc, expected", [
    ({2020: {}},                                                     ["recon_unchecked"]),
    ({2020: {"Residuum_pct": RECON_TOLERANCE + 0.01}},               ["recon_gap"]),
    ({2020: {"Residuum_pct": -(RECON_TOLERANCE + 0.01)}},            ["recon_gap"]),
    ({2020: {"Residuum_pct": RECON_TOLERANCE}},                      []),
    ({2020: {"Residuum_pct": 0.0}},                                  []),
], ids = ["unchecked", "gap_positive", "gap_negative", "boundary", "clean"])
def test_check_recon_tolerance(rec_wc, expected):
    flags = validate_values({2020: pyear()})
    out = check_recon_tolerance(flags, rec_wc)

    assert out[2020]["WorkingCapital"] == expected

def test_check_recon_tolerance_mutates_in_place():
    flags = validate_values({2020: pyear()})
    out = check_recon_tolerance(flags, {2020: {}})

    assert out is flags
