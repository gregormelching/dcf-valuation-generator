import pytest
from datetime import datetime
from parser import (
    WORKING_CAPITAL_TAGS, SLOT_SELECTORS, clean_values, get_last_n_years,
    select_wc, select_cash, select_debt, select_pretax, select_deferred_taxes,
    select_shares, select_nwc_level,
)

def slot(value, tag = "T", end = "2025-12-31", form = "10-K", filed = "2026-01-01"):
    return {"Value": value, "Tag": tag, "End": end, "Form": form, "Filed": filed}

@pytest.mark.parametrize("n", [1, 3, 10])
def test_get_last_n_years(n):
    years = get_last_n_years(n)

    assert len(years) == n + 1
    assert years[-1] == datetime.now().year
    assert years == list(range(years[0], years[-1] + 1))

@pytest.mark.parametrize("selector, slots, expected", [
    (select_wc, {"Receivables": slot(10.0), "Inventory": {}, "Payables": slot(4.0), "DeferredRevenue": {}},
     ["Receivables", "Payables"]),
    (select_wc, {name: {} for name in WORKING_CAPITAL_TAGS},
     []),
    (select_cash, {"Cash": slot(1.0), "ShortTermInv": {}, "LongTermInv": slot(2.0)},
     ["Cash", "LongTermInv"]),
    (select_nwc_level, {"Receivables": slot(1.0), "Inventory": {}, "Payables": slot(2.0), "DeferredRev": {}},
     ["Receivables", "Payables"]),
    (select_pretax, {"PretaxIncome": slot(1.0), "Domestic": {}, "Foreign": {}},
     ["PretaxIncome"]),
    (select_pretax, {"PretaxIncome": {}, "Domestic": slot(1.0), "Foreign": slot(2.0)},
     ["Domestic", "Foreign"]),
    (select_pretax, {"PretaxIncome": {}, "Domestic": slot(1.0), "Foreign": {}},
     []),
    (select_deferred_taxes, {"DeferredTaxes": slot(1.0), "Fed": {}, "For": {}, "St": {}},
     ["DeferredTaxes"]),
    (select_deferred_taxes, {"DeferredTaxes": {}, "Fed": slot(1.0), "For": slot(2.0), "St": slot(3.0)},
     ["Fed", "For", "St"]),
    (select_deferred_taxes, {"DeferredTaxes": {}, "Fed": slot(1.0), "For": slot(2.0), "St": {}},
     []),
    (select_shares, {"SharesOutstanding": slot(1.0), "SharesDated": slot(2.0)},
     ["SharesDated"]),
    (select_shares, {"SharesOutstanding": slot(1.0), "SharesDated": {}},
     ["SharesOutstanding"]),
    (select_shares, {"SharesOutstanding": {}, "SharesDated": {}},
     []),
], ids = ["wc_partial", "wc_empty", "cash_partial", "nwc_partial", "pretax_direct", "pretax_split",
          "pretax_half", "deferred_direct", "deferred_split", "deferred_half",
          "shares_dated_wins", "shares_fallback", "shares_none"])
def test_selectors(selector, slots, expected):
    assert selector(slots) == expected

@pytest.mark.parametrize("current_tag, expected", [
    ("LongTermDebtCurrent", ["DebtNoncurrent", "DebtCurrent", "CommercialPaper"]),
    ("DebtCurrent",         ["DebtNoncurrent", "DebtCurrent"]),
], ids = ["commercial_paper_kept", "commercial_paper_dropped"])
def test_select_debt(current_tag, expected):
    slots = {"DebtNoncurrent": slot(100.0), "DebtCurrent": slot(20.0, tag = current_tag),
             "CommercialPaper": slot(5.0)}

    assert select_debt(slots) == expected

def test_select_debt_without_current():
    slots = {"DebtNoncurrent": slot(100.0), "DebtCurrent": {}, "CommercialPaper": slot(5.0)}

    assert select_debt(slots) == ["DebtNoncurrent"]

def test_clean_values_signs_and_provenance():
    values = {2025: {"WorkingCapital": {
        "Receivables": slot(10.0, tag = "A", end = "2025-09-30", form = "10-K", filed = "2026-01-01"),
        "Inventory": {},
        "Payables": slot(4.0, tag = "B", end = "2025-12-31", form = "10-Q", filed = "2026-02-01"),
        "DeferredRevenue": {}}}}
    out = clean_values(values)[2025]["WorkingCapital"]

    assert out["Value"] == pytest.approx(6.0)
    assert (out["Tag"], out["End"], out["Filed"]) == ("A+B", "2025-12-31", "2026-02-01")
    assert out["Form"] == "10-K"
    assert out["Receivables"] == slot(10.0, tag = "A", end = "2025-09-30", form = "10-K", filed = "2026-01-01")
    assert out["Inventory"] == {}

def test_clean_values_no_slot_chosen():
    values = {2025: {"WorkingCapital": {name: {} for name in WORKING_CAPITAL_TAGS}}}
    out = clean_values(values)[2025]["WorkingCapital"]

    assert "Value" not in out
    assert out == {name: {} for name in WORKING_CAPITAL_TAGS}

def test_clean_values_single_slot_collapses():
    values = {2025: {"Revenue": {"Revenue": slot(500.0)}}}

    assert clean_values(values) == {2025: {"Revenue": slot(500.0)}}

def test_clean_values_single_slot_empty():
    values = {2025: {"Revenue": {"Revenue": {}}}}

    assert clean_values(values) == {2025: {"Revenue": {}}}

def test_slot_selectors_cover_every_multi_slot_metric():
    assert sorted(SLOT_SELECTORS) == ["Cash", "Debt", "DeferredTaxes", "NWC",
                                      "PretaxIncome", "SharesOutstanding", "WorkingCapital"]
