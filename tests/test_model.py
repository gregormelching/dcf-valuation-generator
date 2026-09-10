import copy
import pytest
from database import get_data
from model import (
    MARGINAL_TAX_RATE, MIN_YEARS, TAX_WINDOW_START, TERMINAL_GROWTH,
    effective_tax_rate, driver_ratio, rolling_means, growth_rate, project_revenue, roic, project_fcf
)

TERMINAL_ROIC = 0.2
YEARS = 10
AS_OF = "2026-08-19"
START_YEAR = 2016
REL = 1e-9
SYMBOLS = ("apple", "boeing", "microsoft", "procter_gamble", "tesla")
TAX_GOLDEN = {
    "apple":          (0.1578, 8, "Median"),
    "boeing":         (0.25,   1, "Fallback"),
    "microsoft":      (0.1707, 8, "Median"),
    "procter_gamble": (0.2026, 6, "Median"),
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
    ("boeing", "OperatingIncome"):          (0.0698,  None,    5, [2016, 2017, 2018, 2022, 2023]),
    ("microsoft", "OperatingIncome"):       (0.4168,  0.4568, 10, list(range(2017, 2027))),
    ("procter_gamble", "OperatingIncome"):  (0.2211,  0.2301,  9, [2016, 2017, 2018, 2021, 2022, 2023, 2024, 2025, 2026]),
    ("tesla", "OperatingIncome"):           (0.0632,  None,    7, [2017, 2019, 2020, 2021, 2022, 2024, 2025]),
}
ROIC_GOLDEN = {
    "microsoft":      (0.9579696691104921,   0.46532944444444446, 10, 369490000000.0, 2026),
    "procter_gamble": (0.2035821136094938,   0.20388232430472836,  8, 78507000000.0,  2026),
    "tesla":          (0.12204813846153846,  0.07712261862369803,  7, 46901000000.0,  2025),
}
ROIC_SMALL_IC = {
    "apple":  (0, 3, 39970000000.0, 2025),
    "boeing": (2, 2, 37318000000.0, 2025),
}
REV_GOLDEN = {
    "apple":          (2026, 0.0592, 440797731199.99994, 628227735421.482),
    "boeing":         (2026, 0.065,  95278095000.0,      138803185384.6235),
    "microsoft":      (2027, 0.134,  376305425999.99994, 709406861343.6075),
    "procter_gamble": (2027, 0.0259, 89286128800.0,      111898351266.13243),
    "tesla":          (2026, 0.2573, 119225987099.99998, 347661701178.7101),
}
FCF_GOLDEN = {
    "apple":          (2026, 118984867042.3343,  118776269439.79715, 121745676175.79207),
    "boeing":         (2026, 2786036759.8959374, 6358053410.524411,  6517004745.78752),
    "microsoft":      (2027, 125285852074.45753, 194040511749.01025, 198891524542.73547),
    "procter_gamble": (2027, 15183014711.017233, 16236101086.368109, 16642003613.52731),
    "tesla":          (2026, -619219475.9234953, 14419269056.387003, 14779750782.796675),
}
ROIC_BASE = {"Tax": 25.0, "PretaxIncome": 100.0, "Debt": 400.0, "Cash": 100.0,
             "Equity": 700.0, "OperatingIncome": 100.0, "Revenue": 5000.0}
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

def test_effective_tax_rate_pretax_flag_skipped():
    data = {year: row(Tax = 20.0, PretaxIncome = 100.0, flags = {"PretaxIncome": ["outlier"]})
            for year in (2020, 2021, 2022)}
    out = effective_tax_rate(data)

    assert (out["Effective_Tax_Rate"], out["n"], out["Source"]) == (MARGINAL_TAX_RATE, 0, "Fallback")

def test_effective_tax_rate_zero_pretax_skipped():
    data = {year: row(Tax = 20.0, PretaxIncome = 0.0) for year in (2020, 2021, 2022)}
    out = effective_tax_rate(data)

    assert (out["Effective_Tax_Rate"], out["n"], out["Source"]) == (MARGINAL_TAX_RATE, 0, "Fallback")

@pytest.mark.parametrize("symbol, metric", list(DRIVER_GOLDEN),
                         ids = [f"{symbol}-{metric}" for symbol, metric in DRIVER_GOLDEN])
def test_driver_ratio_golden(all_data, symbol, metric):
    ratio, mean_last_three, n, years = DRIVER_GOLDEN[(symbol, metric)]
    out = driver_ratio(all_data[symbol], metric)
    
    assert (out["Driver_Ratio"], out["Mean_Last_Three"]) == (ratio, mean_last_three)
    assert (out["n"], out["Years"], out["Source"]) == (n, years, "Median")
    if mean_last_three is None:
        assert (out["Mean_Last_Three_Source"], out["Mean_Last_Three_Years"]) == ("Not_Contiguous", [])
    else:
        assert (out["Mean_Last_Three_Source"], out["Mean_Last_Three_Years"]) == ("Calculated", years[-MIN_YEARS:])

def test_driver_ratio_insufficient():
    data = {year: row(Revenue = 1000.0, CapEx = 100.0) for year in (2020, 2021)}
    out = driver_ratio(data, "CapEx")
    
    assert out["n"] < MIN_YEARS
    assert (out["Driver_Ratio"], out["Mean_Last_Three"]) == (None, None)
    assert (out["Mean_Last_Three_Source"], out["Mean_Last_Three_Years"]) == ("Insufficient", [])
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

@pytest.mark.parametrize("k", [0, -1])
def test_rolling_means_invalid_k(k):
    with pytest.raises(ValueError, match = "Window must be at least 1"):
        rolling_means(PAIRS, k)

def test_rolling_means_sorts():
    assert rolling_means(PAIRS[-1:] + PAIRS[:-1], 2) == pytest.approx([1.5, 2.5, 3.5], rel = REL)

def test_growth_rate_golden(data_result):
    symbol, data = data_result
    median, mean, mean_last_three, n, source, last_year = GROWTH_GOLDEN[symbol]
    out = growth_rate(data)
    
    assert (out["Growth_Rate_Median"], out["Growth_Rate_Mean"], out["Mean_Last_Three"]) == (median, mean, mean_last_three)
    assert (out["n"], out["Source"], out["Years"][-1]) == (n, source, last_year)
    assert out["Mean_Last_Three_Source"] == "Calculated"
    assert out["Mean_Last_Three_Years"] == out["Years"][-MIN_YEARS:]

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
    assert (out["Mean_Last_Three_Source"], out["Mean_Last_Three_Years"]) == ("Insufficient", [])
    assert (out["n"], out["Years"], out["Source"]) == (2, [2020, 2021], "Insufficient")

def test_growth_rate_gap():
    data = {year: row(Revenue = rev) for year, rev in
            ((2020, 100.0), (2021, 110.0), (2022, 121.0), (2024, 200.0), (2025, 220.0), (2026, 242.0))}
    out = growth_rate(data)
    
    assert (out["Growth_Rate_Median"], out["Growth_Rate_Mean"], out["Mean_Last_Three"]) == (0.1, 0.1, None)
    assert (out["Mean_Last_Three_Source"], out["Mean_Last_Three_Years"]) == ("Not_Contiguous", [])
    assert (out["n"], out["Years"], out["Source"]) == (4, [2020, 2021, 2024, 2025], "Calculated")

@pytest.mark.parametrize("symbol", list(ROIC_GOLDEN), ids = list(ROIC_GOLDEN))
def test_roic_golden(all_data, symbol):
    median, last, n, ic_last, ic_last_year = ROIC_GOLDEN[symbol]
    out = roic(all_data[symbol])

    assert out["ROIC_Median"] == pytest.approx(median, rel = REL)
    assert out["ROIC_Last"] == pytest.approx(last, rel = REL)
    assert out["IC_Last"] == pytest.approx(ic_last, rel = REL)
    assert (out["n"], out["Source"], out["IC_Last_Year"]) == (n, "Median", ic_last_year)
    assert len(out["Years"]) == out["n"]
    assert out["Excluded_Small_IC"] == 0

@pytest.mark.parametrize("symbol", list(ROIC_SMALL_IC), ids = list(ROIC_SMALL_IC))
def test_roic_small_ic_excluded(all_data, symbol):
    n, excluded, ic_last, ic_last_year = ROIC_SMALL_IC[symbol]
    out = roic(all_data[symbol])

    assert (out["ROIC_Median"], out["ROIC_Last"]) == (None, None)
    assert (out["n"], out["Excluded_Small_IC"], out["Source"]) == (n, excluded, "Insufficient")
    assert out["IC_Last"] == pytest.approx(ic_last, rel = REL)
    assert out["IC_Last_Year"] == ic_last_year

@pytest.mark.parametrize("overrides, flags, expected", [
    ({},                          None,                            (0.075, 0.075, 1000.0, 2024, 4, "Median")),
    ({2021: {"Equity": -400.0}},  None,                            (0.075, 0.075, 1000.0, 2024, 3, "Median")),
    ({2024: {"Debt": None}},      None,                            (0.075, 0.075, 1000.0, 2023, 4, "Median")),
    ({},                          {"Equity": ["outlier"]},         (0.075, 0.075, 1000.0, 2024, 4, "Median")),
    ({},                          {"OperatingIncome": ["outlier"]},(None,  None,  1000.0, 2024, 0, "Insufficient")),
], ids = ["clean", "negative_ic", "last_year_missing", "yoy_flag_ignored", "oi_flagged"])
def test_roic_synth(overrides, flags, expected):
    data = {year: row(flags = flags, **{**ROIC_BASE, **overrides.get(year, {})}) for year in range(2020, 2025)}
    out = roic(data)

    assert (out["ROIC_Median"], out["ROIC_Last"], out["IC_Last"], out["IC_Last_Year"], out["n"], out["Source"]) == expected

@pytest.mark.parametrize("symbol", list(REV_GOLDEN), ids = list(REV_GOLDEN))
def test_proj_rev_golden(all_data, symbol):
    first_year, growth, rev_first, rev_last = REV_GOLDEN[symbol]
    out = project_revenue(all_data[symbol], YEARS)
    years = sorted(out)

    assert (years[0], out[years[0]]["Growth_Rate"]) == (first_year, growth)
    assert out[years[0]]["Revenue"] == pytest.approx(rev_first, rel = REL)
    assert out[years[-1]]["Revenue"] == pytest.approx(rev_last, rel = REL)

def test_proj_rev_invariants(data_result):
    symbol, data = data_result
    out = project_revenue(data, YEARS)
    years = sorted(out)
    last_actual = data[sorted(data)[-1]]["Revenue"]["Value"]

    assert len(out) == YEARS
    assert out[years[-1]]["Growth_Rate"] == TERMINAL_GROWTH
    assert out[years[0]]["Revenue"] == pytest.approx(last_actual * (1 + out[years[0]]["Growth_Rate"]), rel = REL)

@pytest.mark.parametrize("base, revenue_growth, growth, rev_last, source", [
    ("Growth_Rate_Median", None, 0.0592, 628227735421.482,   "Growth_Rate_Median"),
    ("Growth_Rate_Mean",   None, 0.0749, 676652225007.0891,  "Growth_Rate_Mean"),
    ("Mean_Last_Three",    None, 0.0194, 518389250195.35,    "Mean_Last_Three"),
    ("Growth_Rate_Median", 0.05, 0.0475, 594022013599.4677,  "Override"),
    ("Growth_Rate_Median", 0.0,  0.0025, 476937088221.56537, "Override"),
])
def test_proj_rev_bases(all_data, base, revenue_growth, growth, rev_last, source):
    out = project_revenue(all_data["apple"], YEARS, base, revenue_growth = revenue_growth)
    years = sorted(out)

    assert (out[years[0]]["Growth_Rate"], out[years[0]]["Source"]) == (growth, source)
    assert out[years[-1]]["Revenue"] == pytest.approx(rev_last, rel = REL)

@pytest.mark.parametrize("short, base, revenue_growth, message", [
    (False, "Bogus",              None,   "Unknown base: Bogus"),
    (False, "Growth_Rate_Median", "0.05", "Growth is not an integer or float."),
    (False, "Growth_Rate_Median", True,   "Growth is not an integer or float."),
    (True,  "Growth_Rate_Median", None,   "Growth_Rate_Median is not defined"),
], ids = ["unknown_base", "string_override", "bool_override", "insufficient_growth"])
def test_proj_rev_raises(all_data, short, base, revenue_growth, message):
    short_data = {year: row(Revenue = rev) for year, rev in ((2020, 100.0), (2021, 110.0), (2022, 121.0))}
    data = short_data if short else all_data["apple"]

    with pytest.raises(ValueError, match = message):
        project_revenue(data, YEARS, base, revenue_growth = revenue_growth)

@pytest.mark.parametrize("years", [0, -1])
def test_proj_rev_invalid_years(all_data, years):
    with pytest.raises(ValueError, match = "Years must be at least 1"):
        project_revenue(all_data["apple"], years)

def test_fcf_golden(data_result):
    symbol, data = data_result
    first_year, fcf_first, fcf_last_explicit, fcf_tv = FCF_GOLDEN[symbol]
    out = project_fcf(data, YEARS, TERMINAL_ROIC)
    years = sorted(out)

    assert (len(out), years[0]) == (YEARS + 1, first_year)
    assert out[years[0]]["FCF"] == pytest.approx(fcf_first, rel = REL)
    assert out[years[-2]]["FCF"] == pytest.approx(fcf_last_explicit, rel = REL)
    assert out[years[-1]]["FCF"] == pytest.approx(fcf_tv, rel = REL)

@pytest.mark.parametrize("key, expected", [
    ("Revenue",           440797731199.99994),
    ("EBIT",              139533286635.872),
    ("NOPAT",             116228437101.94867),
    ("D&A",               15692399230.719997),
    ("CapEx",             13400251028.479998),
    ("dNWC",              -2384835580.159994),
    ("FCF",               118984867042.3343),
    ("EBIT_Margin",       0.31654719786332697),
    ("Tax_Rate",          0.16702),
    ("Reinvestment",      -2756429940.3856363),
    ("Reinvestment_Rate", -0.02371562424063106),
])
def test_fcf_first_row(all_data, key, expected):
    out = project_fcf(all_data["apple"], YEARS, TERMINAL_ROIC)

    assert out[2026][key] == pytest.approx(expected, rel = REL)

def test_fcf_terminal_row(all_data):
    out = project_fcf(all_data["apple"], YEARS, TERMINAL_ROIC)
    tv = out[sorted(out)[-1]]

    assert tv["Flag"] == "TV"
    assert (tv["D&A"], tv["CapEx"], tv["dNWC"]) == (None, None, None)
    assert (tv["Tax_Rate"], tv["Terminal_ROIC"]) == (MARGINAL_TAX_RATE, TERMINAL_ROIC)
    assert tv["Implicit_ROIC"] == pytest.approx(1.2774720191730067, rel = REL)
    assert tv["Capital_Turnover"] == pytest.approx(5.912169474363099, rel = REL)

def test_fcf_reinvestment_weight(data_result):
    symbol, data = data_result
    out = project_fcf(data, YEARS, TERMINAL_ROIC)
    years = sorted(out)

    assert out[years[-2]]["Reinvestment_Rate"] == pytest.approx(TERMINAL_GROWTH / TERMINAL_ROIC, rel = REL)
    assert out[years[-1]]["Reinvestment_Rate"] == pytest.approx(TERMINAL_GROWTH / TERMINAL_ROIC, rel = REL)

def test_fcf_margin_start_source(data_result):
    symbol, data = data_result
    expected = "Last_Actual_Flagged" if symbol == "boeing" else "Last_Actual"
    out = project_fcf(data, YEARS, TERMINAL_ROIC)

    assert out[sorted(out)[0]]["Margin_Start_Source"] == expected

@pytest.mark.parametrize("kwargs, fcf, metrics, margin_base", [
    ({},                                    118984867042.3343,  "Driver_Ratio+Driver_Ratio+Driver_Ratio",          "Driver_Ratio"),
    ({"margin_base": "Last"},               120130928778.59999, "Driver_Ratio+Driver_Ratio+Driver_Ratio",          "Last"),
    ({"margin_base": "Mean_Last_Three"},    119815188977.65878, "Driver_Ratio+Driver_Ratio+Driver_Ratio",          "Mean_Last_Three"),
    ({"metrics": {"D&A": "Mean_Last_Three", "CapEx": "Mean_Last_Three", "NWC": "Mean_Last_Three"}},
                                            117246978706.3343,  "Mean_Last_Three+Mean_Last_Three+Mean_Last_Three", "Driver_Ratio"),
    ({"ebit_margin": 0.35},                 121229274369.69609, "Driver_Ratio+Driver_Ratio+Driver_Ratio",          "Override"),
    ({"nwc_intensity": 0.1},                114621209212.19032, "Driver_Ratio+Driver_Ratio+Override",              "Driver_Ratio"),
    ({"revenue_growth": 0.05},              117270065761.80252, "Driver_Ratio+Driver_Ratio+Driver_Ratio",          "Driver_Ratio"),
], ids = ["default", "margin_last", "margin_mean_last_three", "metrics_mean_last_three",
          "ebit_margin_override", "nwc_override", "revenue_growth_override"])
def test_fcf_variants(all_data, kwargs, fcf, metrics, margin_base):
    out = project_fcf(all_data["apple"], YEARS, TERMINAL_ROIC, **kwargs)

    assert out[2026]["FCF"] == pytest.approx(fcf, rel = REL)
    assert (out[2026]["Metrics"], out[2026]["Margin_Base"]) == (metrics, margin_base)

@pytest.mark.parametrize("mutation, terminal_roic, kwargs, message", [
    (None, TERMINAL_ROIC, {"margin_base": "Bogus"},                  "Unknown margin_base: Bogus"),
    (None, TERMINAL_ROIC, {"metrics": {"Bogus": "Driver_Ratio"}},    r"Unknown metric: \['Bogus'\]"),
    (None, TERMINAL_ROIC, {"metrics": {"D&A": "Bogus"}},             r"Unknown metric base: \['Bogus'\]"),
    (None, 0.025,         {},                                        "Terminal ROIC must be greater than terminal growth"),
    (None, 0.02,          {},                                        "Terminal ROIC must be greater than terminal growth"),
    (None, TERMINAL_ROIC, {"ebit_margin": "x"},                      "Ebit Margin must be a number or float"),
    (None, TERMINAL_ROIC, {"nwc_intensity": "x"},                    "Invalid type for NWC intensity"),
    (("OperatingIncome", None), TERMINAL_ROIC, {},                   "Operating Income from 2025 is None."),
    (("Revenue", 0.0),          TERMINAL_ROIC, {},                   "Revenue from 2025 is None or 0."),
], ids = ["margin_base", "metric_key", "metric_value", "roic_equal", "roic_below",
          "ebit_margin_type", "nwc_type", "operating_income_none", "revenue_zero"])
def test_fcf_raises(all_data, mutation, terminal_roic, kwargs, message):
    data = all_data["apple"]
    if mutation is not None:
        metric, value = mutation
        data = copy.deepcopy(data)
        data[2025][metric] = {"Value": value, "Flag": []}

    with pytest.raises(ValueError, match = message):
        project_fcf(data, YEARS, terminal_roic, **kwargs)

@pytest.mark.parametrize("years", [0, -1])
def test_fcf_invalid_years(all_data, years):
    with pytest.raises(ValueError, match = "Years must be at least 1"):
        project_fcf(all_data["apple"], years, TERMINAL_ROIC)
