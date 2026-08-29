import pytest 
import copy
from datetime import datetime, timedelta
from valuation import dcf_value, monte_carlo
from prices import price_reference, PRICE_MAX_AGE_DAYS
from database import get_prices, get_data
from wacc_calculation import N_MONTHS, synthetic_cost_of_debt
from model import project_fcf

RF_STUB = {"Risk_Free_Rate": 0.0465}
AS_OF = "2026-08-19"
START_YEAR = 2016
YEARS = 10
FREQ = "1mo"
REL = 1e-9
DRAWS = 2000
SEED = 12345
BOUND_SYMBOL = "apple"
FUTURE = "2999-12-31"
GUARD_SYMBOL = "apple"
GUARD_ROIC = 0.3

MC_GOLDEN = {
    "apple": {
        "Percentiles": {0.05: 119.17818493922017, 0.25: 126.10118133952095, 0.5: 131.42130107562522, 0.75: 137.73294224832281, 0.95: 147.51588142114724},
        "Mean": 132.2248100788426,
        "P_Above_Market": 0.0,
        "WACC_Sigma": 0.004157942544885411,
        "Margin_Range": (0.2881, 0.311, 0.31970799762591884),
    },
    "boeing": {
        "Percentiles": {0.05: 8.472696614060744, 0.25: 25.79423287171261, 0.5: 39.86044008885555, 0.75: 55.59335629423009, 0.95: 77.84158284755351},
        "Mean": 41.38221408798717,
        "P_Above_Market": 0.0,
        "WACC_Sigma": 0.005015380997594274,
        "Margin_Range": (0.0186, 0.0478521847020556, 0.0698),
    },
    "microsoft": {
        "Percentiles": {0.05: 253.30394728707313, 0.25: 272.1878773938189, 0.5: 286.7211461157707, 0.75: 304.4174599040743, 0.95: 332.0734301945462},
        "Mean": 289.23419052256327,
        "P_Above_Market": 0.0,
        "WACC_Sigma": 0.004901827056874809,
        "Margin_Range": (0.4159, 0.4401, 0.4562195624085985),
    },
    "procter_gamble": {
        "Percentiles": {0.05: 120.07676387527653, 0.25: 130.9127135014122, 0.5: 140.1133896905416, 0.75: 151.541230354551, 0.95: 170.77216215576624},
        "Mean": 142.27404937548926,
        "P_Above_Market": 0.399,
        "WACC_Sigma": 0.003759716864892804,
        "Margin_Range": (0.2209, 0.2281, 0.24264391818138675),
    },
    "tesla": {
        "Percentiles": {0.05: 11.381936766343426, 0.25: 12.767000345513559, 0.5: 14.356745881522277, 0.75: 16.36387497721796, 0.95: 19.807474748154995},
        "Mean": 14.785736280971102,
        "P_Above_Market": 0.0,
        "WACC_Sigma": 0.012612017977356959,
        "Margin_Range": (0.04592573845001951, 0.04592573845001951, 0.0953),
    },
}

GOLDEN = {
    "apple": {
        "Value_Per_Share": 132.79924995433032,
        "WACC": 0.09032896943021052,
        "EV": 1928525595460.4187,
        "Low": 148.7645694842523,
        "High": 120.3281783225311,
        "Implied_Multiple": 9.41545108964314,
        "TV_Share": 0.49552357194015606,
        "Data_Filed": "2025-10-31",
        "RF_Date": "2026-08-19",
        "EBIT_Margin_Start": 0.31970799762591884,
        "Margin_Start_Source": "Last_Actual",
        "Margin_Start_Year": 2025,
        "COD_Basis": "Synthetic",
        "COD_Rating": "Aaa/AAA",
        "COD_Year": 2023,
        "COD_N": 8
    },
    "microsoft": {
        "Value_Per_Share": 288.0109140958672,
        "WACC": 0.09152909150854131,
        "EV": 2074014043442.4573,
        "Low": 335.66100012669517,
        "High": 252.62177285299597,
        "Implied_Multiple": 8.837582530587735,
        "TV_Share": 0.6127923483953206,
        "Data_Filed": "2026-07-29",
        "RF_Date": "2026-08-19",
        "EBIT_Margin_Start": 0.4562195624085985,
        "Margin_Start_Source": "Last_Actual",
        "Margin_Start_Year": 2025,
        "COD_Basis": "Synthetic",
        "COD_Rating": "Aaa/AAA",
        "COD_Year": 2025,
        "COD_N": 10
    },
    "procter_gamble": {
        "Value_Per_Share": 138.7314197912333,
        "WACC": 0.06859727085610184,
        "EV": 349912522208.7438,
        "Low": 165.67290997311832,
        "High": 119.54592367383636,
        "Implied_Multiple": 13.437660512335537,
        "TV_Share": 0.6224540605026633,
        "Data_Filed": "2026-08-04",
        "RF_Date": "2026-08-19",
        "EBIT_Margin_Start": 0.24264391818138675,
        "Margin_Start_Source": "Last_Actual",
        "Margin_Start_Year": 2025,
        "COD_Basis": "Synthetic",
        "COD_Rating": "Aaa/AAA",
        "COD_Year": 2025,
        "COD_N": 10
    },
    "tesla": {
        "Value_Per_Share": 11.602225457231938,
        "WACC": 0.1125655849108643,
        "EV": 7630561891.296151,
        "Low": 14.574141623731101,
        "High": 10.166101943732011,
        "Implied_Multiple": 3.2999558475896067,
        "TV_Share": None,
        "Data_Filed": "2026-01-29",
        "RF_Date": "2026-08-19",
        "EBIT_Margin_Start": 0.04592573845001951,
        "Margin_Start_Source": "Last_Actual",
        "Margin_Start_Year": 2025,
        "COD_Basis": "Synthetic",
        "COD_Rating": "Aaa/AAA",
        "COD_Year": 2025,
        "COD_N": 10
    },
    "boeing": {
        "Value_Per_Share": 44.677033352728394,
        "WACC": 0.08035768255431033,
        "EV": 66947978401.46039,
        "Low": 65.45137566220734,
        "High": 30.284040851431147,
        "Implied_Multiple": 7.51868895491711,
        "TV_Share": 0.7236520181526642,
        "Data_Filed": "2026-01-30",
        "RF_Date": "2026-08-19",
        "EBIT_Margin_Start": 0.0478521847020556,
        "Margin_Start_Source": "Last_Actual_Flagged",
        "Margin_Start_Year": 2025,
        "COD_Basis": "IG_Floor+Below_Investment_Grade",
        "COD_Rating": "B2/B",
        "COD_Year": 2025,
        "COD_N": 10
    },
}

@pytest.fixture(scope = "module", params = sorted(GOLDEN), ids = sorted(GOLDEN))
def result(request):
    symbol = request.param
    value = dcf_value(symbol, START_YEAR, YEARS, FREQ, N_MONTHS, as_of = AS_OF)
    return (symbol, value)

@pytest.fixture(scope = "module", params = sorted(MC_GOLDEN), ids = sorted(MC_GOLDEN))
def mc_result(request):
    symbol = request.param
    value = monte_carlo(symbol, START_YEAR, YEARS, FREQ, N_MONTHS, as_of = AS_OF, draws = DRAWS, seed = SEED)
    return (symbol, value)

def test_value_per_share(result):
    sym = result[0]
    val = result[1]
    
    assert val["wacc"]["Value_Per_Share"] == pytest.approx(GOLDEN[sym]["Value_Per_Share"], rel = REL)

    
def test_wacc(result):
    sym = result[0]
    val = result[1]

    assert val["wacc"]["WACC"] == pytest.approx(GOLDEN[sym]["WACC"], rel = REL)

def test_ev(result):
    sym = result[0]
    val = result[1]

    assert val["wacc"]["EV"] == pytest.approx(GOLDEN[sym]["EV"], rel = REL)

def test_wacc_band(result):
    sym = result[0]
    val = result[1]
    low = val["wacc_low"]["Value_Per_Share"]
    base = val["wacc"]["Value_Per_Share"]
    high = val["wacc_high"]["Value_Per_Share"]

    assert low == pytest.approx(GOLDEN[sym]["Low"], rel = REL)
    assert high == pytest.approx(GOLDEN[sym]["High"], rel = REL)
    assert low > base > high
    
def test_terminal_block(result):
    sym = result[0]
    val = result[1]

    assert val["wacc"]["Implied_Multiple"] == pytest.approx(GOLDEN[sym]["Implied_Multiple"], rel = REL)
    if GOLDEN[sym]["TV_Share"] is None:
        assert val["wacc"]["TV_Share"] is None
    else: 
        assert val["wacc"]["TV_Share"] == pytest.approx(GOLDEN[sym]["TV_Share"], rel = REL)

def test_tv_share(result):
    sym = result[0]
    val = result[1]

    if sym == "tesla":
        assert val["wacc_low"]["TV_Share_Source"] == "PV_Explicit <= 0"
        assert val["wacc"]["TV_Share_Source"] == "PV_Explicit <= 0"
        assert val["wacc_high"]["TV_Share_Source"] == "PV_Explicit <= 0"
    else: 
        assert val["wacc_low"]["TV_Share_Source"] == "Calculated"
        assert val["wacc"]["TV_Share_Source"] == "Calculated"
        assert val["wacc_high"]["TV_Share_Source"] == "Calculated"
        
def test_data_filed(result):
    sym = result[0]
    val = result[1]

    assert val["wacc_low"]["Data_Filed"] == GOLDEN[sym]["Data_Filed"]
    assert val["wacc"]["Data_Filed"] == GOLDEN[sym]["Data_Filed"]
    assert val["wacc_high"]["Data_Filed"] == GOLDEN[sym]["Data_Filed"]
        
def test_rf_date(result):
    sym = result[0]
    val = result[1]

    assert val["wacc_low"]["RF_Date"] == GOLDEN[sym]["RF_Date"]
    assert val["wacc"]["RF_Date"] == GOLDEN[sym]["RF_Date"]
    assert val["wacc_high"]["RF_Date"] == GOLDEN[sym]["RF_Date"]

@pytest.mark.parametrize("freq", ["1mo", "1wk"])
def test_price_bound(freq):
    newest = datetime.strptime(get_prices(BOUND_SYMBOL, freq, 1, FUTURE)[0][0], "%Y-%m-%d")
    bound = PRICE_MAX_AGE_DAYS[freq]
    edge = datetime.strftime(newest + timedelta(days = bound), "%Y-%m-%d")
    stale = datetime.strftime(newest + timedelta(days = bound + 1), "%Y-%m-%d")

    assert price_reference(BOUND_SYMBOL, freq, edge)["Age"] == bound
    with pytest.raises(ValueError, match = "is older than"):
        price_reference(BOUND_SYMBOL, freq, stale)

def test_price_reference_absence():
    with pytest.raises(ValueError, match = "No price data"):
        price_reference(BOUND_SYMBOL, "1mo", "2000-01-01")

def test_margin_start(result):
    sym = result[0]
    val = result[1]
    
    assert val["wacc_low"]["EBIT_Margin_Start"] == GOLDEN[sym]["EBIT_Margin_Start"]
    assert val["wacc"]["EBIT_Margin_Start"] == GOLDEN[sym]["EBIT_Margin_Start"]
    assert val["wacc_high"]["EBIT_Margin_Start"] == GOLDEN[sym]["EBIT_Margin_Start"]
    
    assert val["wacc_low"]["Margin_Start_Source"] == GOLDEN[sym]["Margin_Start_Source"]
    assert val["wacc"]["Margin_Start_Source"] == GOLDEN[sym]["Margin_Start_Source"]
    assert val["wacc_high"]["Margin_Start_Source"] == GOLDEN[sym]["Margin_Start_Source"]
    
    assert val["wacc_low"]["Margin_Start_Year"] == GOLDEN[sym]["Margin_Start_Year"]
    assert val["wacc"]["Margin_Start_Year"] == GOLDEN[sym]["Margin_Start_Year"]
    assert val["wacc_high"]["Margin_Start_Year"] == GOLDEN[sym]["Margin_Start_Year"]

def test_margin_start_missing_operating_income():
    data = copy.deepcopy(get_data(GUARD_SYMBOL, START_YEAR))
    data[max(data)]["OperatingIncome"]["Value"] = None

    with pytest.raises(ValueError, match = "Operating Income"):
        project_fcf(data, YEARS, GUARD_ROIC)

def test_margin_start_zero_revenue():
    data = copy.deepcopy(get_data(GUARD_SYMBOL, START_YEAR))
    data[max(data)]["Revenue"]["Value"] = 0

    with pytest.raises(ValueError, match = "Revenue"):
        project_fcf(data, YEARS, GUARD_ROIC)

def test_margin_start_zero_operating_income():
    data = copy.deepcopy(get_data(GUARD_SYMBOL, START_YEAR))
    data[max(data)]["OperatingIncome"]["Value"] = 0.0
    fcf = project_fcf(data, YEARS, GUARD_ROIC, margin_base = "Last")

    assert fcf[min(fcf)]["Margin_Start"] == 0.0
    assert fcf[min(fcf)]["Margin_Start_Source"] == "Last_Actual"
    assert fcf[min(fcf)]["Margin_Start_Year"] == max(data)

def test_cod_evidence(result):
    sym = result[0]
    val = result[1]

    assert val["wacc_low"]["COD_Basis"] == GOLDEN[sym]["COD_Basis"]
    assert val["wacc"]["COD_Basis"] == GOLDEN[sym]["COD_Basis"]
    assert val["wacc_high"]["COD_Basis"] == GOLDEN[sym]["COD_Basis"]
    
    assert val["wacc_low"]["COD_Evidence"]["Rating"] == GOLDEN[sym]["COD_Rating"]
    assert val["wacc"]["COD_Evidence"]["Rating"] == GOLDEN[sym]["COD_Rating"]
    assert val["wacc_high"]["COD_Evidence"]["Rating"] == GOLDEN[sym]["COD_Rating"]
    
    assert val["wacc_low"]["COD_Evidence"]["Year"] == GOLDEN[sym]["COD_Year"]
    assert val["wacc"]["COD_Evidence"]["Year"] == GOLDEN[sym]["COD_Year"]
    assert val["wacc_high"]["COD_Evidence"]["Year"] == GOLDEN[sym]["COD_Year"]
    
    assert val["wacc_low"]["COD_Evidence"]["n"] == GOLDEN[sym]["COD_N"]
    assert val["wacc"]["COD_Evidence"]["n"] == GOLDEN[sym]["COD_N"]
    assert val["wacc_high"]["COD_Evidence"]["n"] == GOLDEN[sym]["COD_N"]

def test_cod_unavailable():
    data = copy.deepcopy(get_data(GUARD_SYMBOL, START_YEAR))
    
    for year in data:
        data[year]["InterestExpense"]["Value"] = None
    
    coverage = synthetic_cost_of_debt(data, RF_STUB)
    
    assert coverage["Source"] == "Unavailable"
    assert coverage["Coverage"] is None
    assert coverage["Year"] is None
    assert coverage["Cost_of_Debt"] is None
    assert coverage["n"] == 0

@pytest.mark.slow
def test_percentiles(mc_result):
    sym = mc_result[0]
    val = mc_result[1]

    assert val["Percentiles"][0.05] == pytest.approx(MC_GOLDEN[sym]["Percentiles"][0.05], rel = REL)
    assert val["Percentiles"][0.5] == pytest.approx(MC_GOLDEN[sym]["Percentiles"][0.5], rel = REL)
    assert val["Percentiles"][0.95] == pytest.approx(MC_GOLDEN[sym]["Percentiles"][0.95], rel = REL)
    
@pytest.mark.slow    
def test_mean(mc_result):
    sym = mc_result[0]
    val = mc_result[1]

    assert val["Mean"] == pytest.approx(MC_GOLDEN[sym]["Mean"], rel = REL)
    
@pytest.mark.slow    
def test_margin_range(mc_result):
    sym = mc_result[0]
    val = mc_result[1]

    assert val["Margin_Range"][0] == pytest.approx(MC_GOLDEN[sym]["Margin_Range"][0], rel = REL)
    assert val["Margin_Range"][1] == pytest.approx(MC_GOLDEN[sym]["Margin_Range"][1], rel = REL)
    assert val["Margin_Range"][2] == pytest.approx(MC_GOLDEN[sym]["Margin_Range"][2], rel = REL)

@pytest.mark.slow    
def test_wacc_sigma(mc_result):
    sym = mc_result[0]
    val = mc_result[1]
    
    assert val["WACC_Sigma"] == pytest.approx(MC_GOLDEN[sym]["WACC_Sigma"], rel = REL)

@pytest.mark.slow
def test_p_above_market(mc_result):
    sym = mc_result[0]
    val = mc_result[1]

    assert val["P_Above_Market"] == MC_GOLDEN[sym]["P_Above_Market"]

@pytest.mark.slow
def test_draw_accounting(mc_result):
    sym = mc_result[0]
    val = mc_result[1]

    assert val["Draws_OK"] + val["Draws_Failed"] == DRAWS
    assert val["Draws_OK"] == len(val["Draws"])
    assert sum(val["Failures"].values()) == val["Draws_Failed"]
