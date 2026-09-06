import copy
import pytest
import wacc_calculation
from database import get_data
from model import MARGINAL_TAX_RATE
from prices import risk_free_rate
from wacc_calculation import (
    COD_START_YEAR, COD_FALLBACK_START_YEAR, INVESTMENT_GRADE, N_MONTHS,
    synthetic_rating, cost_of_debt, synthetic_cost_of_debt, debt_to_equity,
    adjusted_beta, cost_of_equity, calc_wacc,
)

AS_OF = "2026-08-19"
START_YEAR = 2016
FREQ = "1mo"
REL = 1e-9
SYMBOLS = ("apple", "boeing", "microsoft", "procter_gamble", "tesla")
RF = 0.0465
SYNTH_GOLDEN = {
    "apple":          (29.062039155860667, 2023,  8, "Aaa/AAA", 0.0040, "Calculated"),
    "boeing":         (1.544929628293035,  2025, 10, "B2/B",    0.0321, "Below_Investment_Grade"),
    "microsoft":      (50.880694854146185, 2026, 11, "Aaa/AAA", 0.0040, "Calculated"),
    "procter_gamble": (22.517673888255416, 2026, 11, "Aaa/AAA", 0.0040, "Calculated"),
    "tesla":          (12.884615384615385, 2025, 10, "Aaa/AAA", 0.0040, "Calculated"),
}
WACC_GOLDEN = {
    "apple":          (0.09032896943021052, 0.0505, "Synthetic", None, 0.027107463302849168),
    "boeing":         (0.08035768255431033, 0.0576, "IG_Floor+Below_Investment_Grade", 2023, 0.0786),
    "microsoft":      (0.09155341740072441, 0.0505, "Synthetic", None, 0.0548496174233592),
    "procter_gamble": (0.06860383894985718, 0.0505, "Synthetic", None, 0.0263194718755936),
    "tesla":          (0.1125655849108643,  0.0505, "Synthetic", None, 0.046553267681289166),
}

@pytest.fixture(scope = "module", params = SYMBOLS, ids = SYMBOLS)
def data_result(request):
    return request.param, get_data(request.param, START_YEAR, AS_OF)

@pytest.fixture(scope = "module")
def rfr_result():
    return risk_free_rate(AS_OF)

@pytest.fixture(scope = "module")
def apple_data():
    return get_data("apple", START_YEAR, AS_OF)

def make_year(oi = None, ie = None, debt = None, shares = None, flags = None):
    flags = flags or {}
    values = {"OperatingIncome": oi, "InterestExpense": ie, "Debt": debt, "SharesOutstanding": shares}
    return {k: {"Value": v, "Flag": flags.get(k, [])} for k, v in values.items()}

@pytest.mark.parametrize("coverage, rating, spread", [
    (3.0, "A3/A-", 0.0089),
    (2.5, "Baa2/BBB", 0.0111),
    (2.25, "Ba1/BB+", 0.0138),
    (2.2499999, "Ba2/BB", 0.0184),
    (INVESTMENT_GRADE, "Baa2/BBB", 0.0111)
])
def test_synthetic_rating_bands(coverage, rating, spread):
    out = synthetic_rating(coverage)
    assert (out["Rating"], out["Spread"]) == (rating, spread)
    
@pytest.mark.parametrize("coverage", [0.1999995, 2.499995, 8.4999995])
def test_synthetic_rating_gaps(coverage):
    with pytest.raises(ValueError, match = "outside the spread table"):
        synthetic_rating(coverage)

@pytest.mark.parametrize("coverage", [-200000.0, 200000.0])
def test_synthetic_rating_outside_table(coverage):
    with pytest.raises(ValueError, match = "outside the spread table"):
        synthetic_rating(coverage)
        
def test_debt_median():
    data = {y: make_year(ie = ie, debt = 1000.0) for y, ie in ((2023, 20.0), (2024, 50.0), (2025, 30.0))}
    out = cost_of_debt(data, 2023)
    
    assert out["Cost_of_Debt"] == pytest.approx(0.03, rel = REL)
    assert (out["n"], out["Source"]) == (3, "Calculated")

def test_debt_average():
    years = {y: make_year(ie = ie, debt = 1500.0) for y, ie in ((2023, 100.0), (2024, 30.0), (2025, 300.0))}
    with_prior = {2022: make_year(debt = 500.0), **years}

    assert cost_of_debt(with_prior, 2023)["Cost_of_Debt"] == pytest.approx(0.1, rel = REL)
    assert cost_of_debt(years, 2023)["Cost_of_Debt"] == pytest.approx(100 / 1500, rel = REL)
    
def test_debt_null():
    data = {y: make_year(ie = 100.0, debt = 0.0) for y in (2023, 2024, 2025)}

    assert cost_of_debt(data, 2023)["Source"] == "Insufficient"
    assert cost_of_debt(data, 2023)["Cost_of_Debt"] is None

def test_debt_apple(apple_data):
    short = cost_of_debt(apple_data, COD_START_YEAR)
    long = cost_of_debt(apple_data, COD_FALLBACK_START_YEAR)
    
    assert (short["Cost_of_Debt"], short["n"], short["Source"]) == (None, 1, "Insufficient")
    assert long["Cost_of_Debt"] == pytest.approx(0.027107463302849168, rel = REL)
    assert (long["n"], long["Source"]) == (6, "Calculated")
    
@pytest.mark.parametrize("flag, expected", [("outlier", "Calculated"), ("missing", "Insufficient")])
def test_debt_flag(flag, expected):
    data = {y: make_year(ie = 30.0, debt = 1000.0, flags = {"InterestExpense": [flag]}) for y in (2023, 2024, 2025)}
    assert cost_of_debt(data, 2023)["Source"] == expected

def test_synth_debt(data_result, rfr_result):
    symbol, data = data_result
    coverage, year, n, rating, spread, source = SYNTH_GOLDEN[symbol]
    out = synthetic_cost_of_debt(data, rfr_result)
    assert out["Coverage"] == pytest.approx(coverage, rel = REL)
    assert (out["Year"], out["n"], out["Rating"], out["Source"]) == (year, n, rating, source)
    assert out["Cost_of_Debt"] == pytest.approx(RF + spread, rel = REL)

def test_synth_debt_unavailable(rfr_result):
    data = {y: make_year(oi = 100.0, ie = None) for y in (2023, 2024, 2025)}
    out = synthetic_cost_of_debt(data, rfr_result)
    assert out["Source"] == "Unavailable"
    assert (out["Cost_of_Debt"], out["Rating"], out["Spread"]) == (None, None, None)
    
def test_adj_beta_relever(monkeypatch, apple_data):
    monkeypatch.setattr(wacc_calculation, "debt_to_equity", lambda *args, **kwargs: 0.25)
    out = adjusted_beta(apple_data, "apple", FREQ, N_MONTHS, AS_OF)
    assert out["Beta_Relevered"] == pytest.approx(out["Beta_Raw"], rel = REL)
    assert out["Beta"] == pytest.approx(0.67 * out["Beta_Relevered"] + 0.33, rel = REL)

def test_adj_beta_apple(apple_data):
    out = adjusted_beta(apple_data, "apple", FREQ, N_MONTHS, AS_OF)
    assert out["Beta_Raw"] == pytest.approx(1.089, rel = REL)
    assert out["Beta"] == pytest.approx(1.0505530456077643, rel = REL)
    assert out["DE_Current"] == pytest.approx(0.021632317518153286, rel = REL)
    assert out["DE_Window"] == pytest.approx(0.03870109752095135, rel = REL)
    assert out["DE_Years"] == [2021, 2022, 2023, 2024, 2025]

def test_equity_capm_and_band():
    beta = {"Beta": 1.0505530456077643, "DE_Current": 0.021632317518153286,
            "DE_Window": 0.03870109752095135, "Std_Error": 0.15, "Source": FREQ}
    out = cost_of_equity(beta, {"Risk_Free_Rate": RF})
    assert out["Cost_of_Equity"] == pytest.approx(0.09146367035201232, rel = REL)
    assert out["Std_Error_adj"] == pytest.approx(0.09924973079996754, rel = REL)
    assert out["CI_Low"] == pytest.approx(0.08313780893466463, rel = REL)
    assert out["CI_High"] == pytest.approx(0.09978953176935998, rel = REL)
    
def test_calc_wacc(data_result):
    symbol, data = data_result
    wacc, cod, basis, cod_source, alternative = WACC_GOLDEN[symbol]
    out = calc_wacc(data, symbol, FREQ, N_MONTHS, as_of = AS_OF)
    assert out["WACC"] == pytest.approx(wacc, rel = REL)
    assert out["Cost_of_Debt"] == pytest.approx(cod, rel = REL)
    assert out["Cost_of_Debt_After_Tax"] == pytest.approx(cod * (1 - MARGINAL_TAX_RATE), rel = REL)
    assert (out["COD_Basis"], out["COD_Source"]) == (basis, cod_source)
    assert out["COD_Alternative"] == pytest.approx(alternative, rel = REL)

def test_calc_wacc_weights_and_band(data_result):
    symbol, data = data_result
    out = calc_wacc(data, symbol, FREQ, N_MONTHS, as_of = AS_OF)
    assert out["Weight_Equity"] + out["Weight_Debt"] == pytest.approx(1.0, rel = REL)
    assert out["WACC_Low"] <= out["WACC"] <= out["WACC_High"]

def test_debt_to_equity_current(apple_data):
    assert debt_to_equity(apple_data, "apple", None, AS_OF) == pytest.approx(0.021632317518153286, rel = REL)

def test_debt_to_equity_year(apple_data):
    assert debt_to_equity(apple_data, "apple", 2025, AS_OF) == pytest.approx(0.024626113292023695, rel = REL)

@pytest.mark.parametrize("debt, shares", [(0.0, 100.0), (None, 100.0), (1000.0, 0.0), (1000.0, None)])
def test_debt_to_equity_missing_inputs(debt, shares):
    data = {2025: make_year(debt = debt, shares = shares)}
    with pytest.raises(ValueError, match = "Missing Debt or SharesOutstanding"):
        debt_to_equity(data, "apple", None, AS_OF)

def test_calc_wacc_realised_fallback(apple_data):
    data = copy.deepcopy(apple_data)
    for year in (2023, 2024, 2025):
        data[year]["InterestExpense"] = {"Value": 1.0e10, "Flag": []}
    data[2025]["OperatingIncome"] = {"Value": 2.0e10, "Flag": []}

    realised = cost_of_debt(data, COD_START_YEAR)
    out = calc_wacc(data, "apple", FREQ, N_MONTHS, as_of = AS_OF)

    assert out["COD_Basis"] == "Realised_Fallback+Below_Investment_Grade"
    assert out["COD_Source"] == COD_START_YEAR
    assert out["Cost_of_Debt"] == pytest.approx(realised["Cost_of_Debt"], rel = REL)
    assert out["Cost_of_Debt"] > RF + synthetic_rating(INVESTMENT_GRADE)["Spread"]

def test_calc_wacc_insufficient_data(apple_data):
    data = copy.deepcopy(apple_data)
    for year in data:
        data[year]["InterestExpense"] = {"Value": None, "Flag": ["missing"]}

    with pytest.raises(ValueError, match = "Insufficient Data"):
        calc_wacc(data, "apple", FREQ, N_MONTHS, as_of = AS_OF)
