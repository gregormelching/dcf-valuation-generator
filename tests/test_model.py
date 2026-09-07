import pytest
from database import get_data
from model import (
    MARGINAL_TAX_RATE, MIN_YEARS, TAX_WINDOW_START,
    effective_tax_rate, driver_ratio, rolling_means, growth_rate,
)

AS_OF = "2026-08-19"
START_YEAR = 2016
REL = 1e-9
SYMBOLS = ("apple", "boeing", "microsoft", "procter_gamble", "tesla")
TAX_GOLDEN = {
    "apple":          (0.1578, 8, "Median"),
    "boeing":         (0.25,   2, "Fallback"),
    "microsoft":      (0.1707, 8, "Median"),
    "procter_gamble": (0.2034, 7, "Median"),
    "tesla":          (0.2043, 5, "Median"),
}
GROWTH_GOLDEN = {
    "apple":          (0.063,  0.0804, 0.0188,  9, "Calculated", 2024),
    "boeing":         (0.0694, 0.0118, 0.1226,  9, "Calculated", 2024),
    "microsoft":      (0.1461, 0.1387, 0.1613, 10, "Calculated", 2025),
    "procter_gamble": (0.026,  0.0294, 0.0201, 10, "Calculated", 2025),
    "tesla":          (0.2831, 0.3691, 0.056,   9, "Calculated", 2024),
}
DRIVER_GOLDEN = {
    ("apple", "D&A"):                       (0.0356,  0.0291, 10, list(range(2016, 2026))),
    ("apple", "CapEx"):                     (0.0304,  0.0278, 10, list(range(2016, 2026))),
    ("apple", "NWC"):                       (-0.0968, -0.0882, 10, list(range(2016, 2026))),
    ("apple", "OperatingIncome"):           (0.2881,  0.311,  10, list(range(2016, 2026))),
    ("boeing", "OperatingIncome"):          (0.0698,  0.0186,  5, [2016, 2017, 2018, 2022, 2023]),
    ("microsoft", "OperatingIncome"):       (0.4168,  0.4568, 10, list(range(2017, 2027))),
    ("procter_gamble", "OperatingIncome"):  (0.2211,  0.2301,  9, [2016, 2017, 2018, 2021, 2022, 2023, 2024, 2025, 2026]),
    ("tesla", "OperatingIncome"):           (0.0632,  0.0953,  7, [2017, 2019, 2020, 2021, 2022, 2024, 2025]),
}
PAIRS = [(2020, 1.0), (2021, 2.0), (2022, 3.0), (2023, 4.0)]
GAPPED = [(2020, 1.0), (2021, 2.0), (2023, 3.0), (2024, 4.0)]

@pytest.fixture(scope = "module")
def all_data():
    return {symbol: get_data(symbol, START_YEAR, AS_OF) for symbol in SYMBOLS}

@pytest.fixture(scope = "module", params = SYMBOLS, ids = SYMBOLS)
def data_result(request, all_data):
    return request.param, all_data[request.param]

def row(flags = None, **values):
    flags = flags or {}
    return {k: {"Value": v, "Flag": flags.get(k, [])} for k, v in values.items()}

def test_effective_tax_rate_golden(data_result):
    symbol, data = data_result
    out = effective_tax_rate(data)
    assert (out["Effective_Tax_Rate"], out["n"], out["Source"]) == TAX_GOLDEN[symbol]

def test_effective_tax_rate_window():
    data = {year: row(Tax = 20.0, PretaxIncome = 100.0)
            for year in (TAX_WINDOW_START - 2, TAX_WINDOW_START - 1)}
    out = effective_tax_rate(data)
    assert (out["Effective_Tax_Rate"], out["n"], out["Source"]) == (MARGINAL_TAX_RATE, 0, "Fallback")

def test_effective_tax_rate_median():
    data = {year: row(Tax = tax, PretaxIncome = 100.0)
            for year, tax in ((2020, 25.0), (2021, 40.0), (2022, 10.0), (2023, 30.0))}
    out = effective_tax_rate(data)
    assert (out["Effective_Tax_Rate"], out["n"], out["Source"]) == (0.275, 4, "Median")

def test_effective_tax_rate_flagged():
    data = {year: row(Tax = 20.0, PretaxIncome = 100.0, flags = {"Tax": ["outlier"]})
            for year in (2020, 2021, 2022)}
    out = effective_tax_rate(data)
    assert (out["Effective_Tax_Rate"], out["n"], out["Source"]) == (MARGINAL_TAX_RATE, 0, "Fallback")

def test_effective_tax_rate_pretax_flag_ignored_unguarded():
    data = {year: row(Tax = 20.0, PretaxIncome = 100.0, flags = {"PretaxIncome": ["outlier"]})
            for year in (2020, 2021, 2022)}
    out = effective_tax_rate(data)
    assert (out["Effective_Tax_Rate"], out["n"], out["Source"]) == (0.2, 3, "Median")

def test_effective_tax_rate_zero_pretax_unguarded():
    data = {year: row(Tax = 20.0, PretaxIncome = 0.0) for year in (2020, 2021, 2022)}
    with pytest.raises(ZeroDivisionError):
        effective_tax_rate(data)

@pytest.mark.parametrize("symbol, metric", list(DRIVER_GOLDEN),
                         ids = [f"{symbol}-{metric}" for symbol, metric in DRIVER_GOLDEN])
def test_driver_ratio_golden(all_data, symbol, metric):
    ratio, mean_last_three, n, years = DRIVER_GOLDEN[(symbol, metric)]
    out = driver_ratio(all_data[symbol], metric)
    assert (out["Driver_Ratio"], out["Mean_Last_Three"]) == (ratio, mean_last_three)
    assert (out["n"], out["Years"], out["Source"]) == (n, years, "Median")

def test_driver_ratio_insufficient():
    data = {year: row(Revenue = 1000.0, CapEx = 100.0) for year in (2020, 2021)}
    out = driver_ratio(data, "CapEx")
    assert out["n"] < MIN_YEARS
    assert (out["Driver_Ratio"], out["Mean_Last_Three"]) == (None, None)
    assert (out["n"], out["Years"], out["Source"]) == (2, [2020, 2021], "Insufficient")

def test_driver_ratio_zero_revenue():
    data = {year: row(Revenue = 0.0 if year == 2022 else 1000.0, CapEx = 100.0)
            for year in (2020, 2021, 2022, 2023)}
    out = driver_ratio(data, "CapEx")
    assert out["Driver_Ratio"] == 0.1
    assert (out["n"], out["Years"], out["Source"]) == (3, [2020, 2021, 2023], "Median")

@pytest.mark.parametrize("metric, flag, n, source", [
    ("D&A",             "outlier", 3, "Median"),
    ("D&A",             "missing", 0, "Insufficient"),
    ("OperatingIncome", "outlier", 0, "Insufficient"),
    ("OperatingIncome", "missing", 0, "Insufficient"),
])
def test_driver_ratio_flag_filter(metric, flag, n, source):
    data = {year: row(Revenue = 1000.0, flags = {metric: [flag]}, **{metric: 100.0})
            for year in (2020, 2021, 2022)}
    out = driver_ratio(data, metric)
    assert (out["n"], out["Source"]) == (n, source)

@pytest.mark.parametrize("pairs, k, expected", [
    (PAIRS,  1, [1.0, 2.0, 3.0, 4.0]),
    (PAIRS,  2, [1.5, 2.5, 3.5]),
    (PAIRS,  3, [2.0, 3.0]),
    (PAIRS,  4, [2.5]),
    (PAIRS,  5, []),
    (GAPPED, 2, [1.5, 3.5]),
    (GAPPED, 3, []),
    ([],     3, []),
])
def test_rolling_means(pairs, k, expected):
    assert rolling_means(pairs, k) == pytest.approx(expected, rel = REL)

def test_rolling_means_zero_k_unguarded():
    with pytest.raises(IndexError):
        rolling_means(PAIRS, 0)

def test_rolling_means_unsorted_unguarded():
    assert rolling_means(PAIRS[-1:] + PAIRS[:-1], 2) == pytest.approx([1.5, 2.5], rel = REL)

def test_growth_rate_golden(data_result):
    symbol, data = data_result
    median, mean, mean_last_three, n, source, last_year = GROWTH_GOLDEN[symbol]
    out = growth_rate(data)
    assert (out["Growth_Rate_Median"], out["Growth_Rate_Mean"], out["Mean_Last_Three"]) == (median, mean, mean_last_three)
    assert (out["n"], out["Source"], out["Years"][-1]) == (n, source, last_year)

def test_growth_rate_lengths(data_result):
    symbol, data = data_result
    out = growth_rate(data)
    assert len(out["Rates"]) == out["n"]
    assert len(out["Years"]) == out["n"]

def test_growth_rate_insufficient():
    data = {year: row(Revenue = rev) for year, rev in ((2020, 100.0), (2021, 110.0), (2022, 121.0))}
    out = growth_rate(data)
    assert out["n"] < MIN_YEARS
    assert (out["Growth_Rate_Median"], out["Growth_Rate_Mean"], out["Mean_Last_Three"]) == (None, None, None)
    assert (out["n"], out["Years"], out["Source"]) == (2, [2020, 2021], "Insufficient")

def test_growth_rate_gap():
    data = {year: row(Revenue = rev) for year, rev in
            ((2020, 100.0), (2021, 110.0), (2022, 121.0), (2024, 200.0), (2025, 220.0), (2026, 242.0))}
    out = growth_rate(data)
    assert (out["Growth_Rate_Median"], out["Growth_Rate_Mean"], out["Mean_Last_Three"]) == (0.1, 0.1, 0.1)
    assert (out["n"], out["Years"], out["Source"]) == (4, [2020, 2021, 2024, 2025], "Calculated")
