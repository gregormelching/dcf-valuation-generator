import pytest 
import copy
from datetime import datetime, timedelta
import valuation
from valuation import dcf_value, monte_carlo, plausible_ceiling, implied_horizon, implied_assumptions, IMPLIED_GROWTH_BOUNDS
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
CUT_M = "2026-06-30"
GUARD_ROIC = 0.3
LEVER_SUBSET = ("ebit_margin", "wacc_offset", "nwc_intensity")
HORIZON_BOUNDS = (1, 30)
HORIZON_COMPARATOR = 15
HORIZON_ANCHOR = 15
HORIZON_WIDE_BOUNDS = (1, 100)
HORIZON_WIDE_REQUIRED = {"boeing": 63, "procter_gamble": 94}
GROWTH_NARROW_BOUNDS = (-0.5, 1.0)
GROWTH_NARROW_SYMBOL = "tesla"

MC_GOLDEN = {
    "apple": {
        "Percentiles": {0.05: 115.32827672285855, 0.25: 121.86097669513538, 0.5: 126.79245309023625, 0.75: 132.84987803628803, 0.95: 142.170015151978},
        "Mean": 127.61767249115182,
        "P_Above_Market": 0.0,
        "WACC_Sigma": 0.004157942544885411,
        "Margin_Range": (0.2881, 0.311, 0.31970799762591884),
    },
    "boeing": {
        "Percentiles": {0.05: 15.248428138828391, 0.25: 32.06959660816732, 0.5: 45.87207167403301, 0.75: 61.11895578073862, 0.95: 82.89884078172176},
        "Mean": 47.277310931820935,
        "P_Above_Market": 0.0,
        "WACC_Sigma": 0.005015380997594274,
        "Margin_Range": (0.0186, 0.0478521847020556, 0.0698),
    },
    "microsoft": {
        "Percentiles": {0.05: 283.63379664802875, 0.25: 306.205569372218, 0.5: 322.7371639237955, 0.75: 343.1881302978105, 0.95: 374.3588931167545},
        "Mean": 325.64915037837113,
        "P_Above_Market": 0.0,
        "WACC_Sigma": 0.004902805237750883,
        "Margin_Range": (0.4168, 0.4568, 0.4678081840892722),
    },
    "procter_gamble": {
        "Percentiles": {0.05: 111.29796297264421, 0.25: 121.82697978837552, 0.5: 130.23697222400176, 0.75: 141.2925639298535, 0.95: 159.17228728114924},
        "Mean": 132.45788612686601,
        "P_Above_Market": 0.1905,
        "WACC_Sigma": 0.0037599663784301704,
        "Margin_Range": (0.2211, 0.2301, 0.2301),
    },
    "tesla": {
        "Percentiles": {0.05: 15.18281696008148, 0.25: 16.736233495784997, 0.5: 18.3049895700006, 0.75: 20.305798421934632, 0.95: 23.73032097667353},
        "Mean": 18.73482152266893,
        "P_Above_Market": 0.0,
        "WACC_Sigma": 0.012612017977356962,
        "Margin_Range": (0.04592573845001951, 0.04592573845001951, 0.0953),
    },
}

GOLDEN = {
    "apple": {
        "Value_Per_Share": 128.17161739600098,
        "WACC": 0.09032896943021052,
        "EV": 1860146063224.2512,
        "Low": 143.95323614619946,
        "High": 115.87434640848096,
        "Implied_Multiple": 9.41545108964314,
        "TV_Share": 0.5137391684092479,
        "Data_Filed": "2025-10-31",
        "RF_Date": "2026-08-19",
        "EBIT_Margin_Start": 0.31970799762591884,
        "Margin_Start_Source": "Last_Actual",
        "Margin_Start_Year": 2025,
        "COD_Basis": "Synthetic",
        "COD_Rating": "Aaa/AAA",
        "COD_Year": 2023,
        "COD_N": 8,
        "ROIC_Consistency": "Consistent",
        "Implicit_ROIC": 1.2148617875596905,
        "Capital_Turnover": 5.2084106647789525
    },
    "microsoft": {
        "Value_Per_Share": 328.3642752010715,
        "WACC": 0.09155341740072441,
        "EV": 2365386863124.8,
        "Low": 386.4106239417062,
        "High": 285.17757601629074,
        "Implied_Multiple": 8.87350279649868,
        "TV_Share": 0.6097092117858973,
        "Data_Filed": "2026-07-29",
        "RF_Date": "2026-08-19",
        "EBIT_Margin_Start": 0.4678081840892722,
        "Margin_Start_Source": "Last_Actual",
        "Margin_Start_Year": 2026,
        "COD_Basis": "Synthetic",
        "COD_Rating": "Aaa/AAA",
        "COD_Year": 2026,
        "COD_N": 11,
        "ROIC_Consistency": "Consistent",
        "Implicit_ROIC": 0.26873642486859894,
        "Capital_Turnover": 0.7844028746894307
    },
    "procter_gamble": {
        "Value_Per_Share": 131.79067292750094,
        "WACC": 0.06860383894985718,
        "EV": 330534597152.33014,
        "Low": 159.43447402137065,
        "High": 112.12405019947484,
        "Implied_Multiple": 13.39994806860309,
        "TV_Share": 0.6456210727606307,
        "Data_Filed": "2026-08-04",
        "RF_Date": "2026-08-19",
        "EBIT_Margin_Start": 0.22690504641970768,
        "Margin_Start_Source": "Last_Actual",
        "Margin_Start_Year": 2026,
        "COD_Basis": "Synthetic",
        "COD_Rating": "Aaa/AAA",
        "COD_Year": 2026,
        "COD_N": 11,
        "ROIC_Consistency": "Consistent",
        "Implicit_ROIC": 0.20798970628721578,
        "Capital_Turnover": 1.2052134219163597
    },
    "tesla": {
        "Value_Per_Share": 15.70870332668901,
        "WACC": 0.1125655849108643,
        "EV": 23039840790.23504,
        "Low": 19.220661798669237,
        "High": 13.816664864238733,
        "Implied_Multiple": 3.2999558475896067,
        "TV_Share": 0.7472993843224384,
        "Data_Filed": "2026-01-29",
        "RF_Date": "2026-08-19",
        "EBIT_Margin_Start": 0.04592573845001951,
        "Margin_Start_Source": "Last_Actual",
        "Margin_Start_Year": 2025,
        "COD_Basis": "Synthetic",
        "COD_Rating": "Aaa/AAA",
        "COD_Year": 2025,
        "COD_N": 10,
        "ROIC_Consistency": "Implicit_ROIC < WACC",
        "Implicit_ROIC": 0.06427015221417262,
        "Capital_Turnover": 1.8659152618487096
    },
    "boeing": {
        "Value_Per_Share": 50.42512170211479,
        "WACC": 0.08035768255431033,
        "EV": 71462222894.20242,
        "Low": 71.4352463870118,
        "High": 35.81026443039082,
        "Implied_Multiple": 7.51868895491711,
        "TV_Share": 0.677939164489497,
        "Data_Filed": "2026-01-30",
        "RF_Date": "2026-08-19",
        "EBIT_Margin_Start": 0.0478521847020556,
        "Margin_Start_Source": "Last_Actual_Flagged",
        "Margin_Start_Year": 2025,
        "COD_Basis": "IG_Floor+Below_Investment_Grade",
        "COD_Rating": "B2/B",
        "COD_Year": 2025,
        "COD_N": 10,
        "ROIC_Consistency": "Consistent",
        "Implicit_ROIC": 0.11920315591433801,
        "Capital_Turnover": 3.3214270614543087
    },
}

LEVER_GOLDEN = {
    "apple": {
        "Ceiling_Value_Per_Share": 518.2860449212727,
        "Reachable": True,
        "Dominant": "revenue_growth",
        "Contribution": {"ebit_margin": 12.35640437010261, "wacc_offset": 93.78770821904072, "terminal_growth": 137.44068718594974, "nwc_intensity": 1.7951853936707494, "revenue_growth": 323.09084750155364},
        "Required": {"ebit_margin": 0.8990223714016288, "wacc_offset": -0.04030137217503402, "terminal_growth": 0.046499000000000006, "nwc_intensity": -0.5, "revenue_growth": 0.3144374999999999},
        "Closable": ["revenue_growth"],
        "Subset_Ceiling": 147.27088806925747,
        "Subset_Reachable": False,
    },
    "boeing": {
        "Ceiling_Value_Per_Share": 947.9779101825865,
        "Reachable": True,
        "Dominant": "ebit_margin",
        "Contribution": {"ebit_margin": 575.2605357784505, "wacc_offset": 301.4671974904327, "terminal_growth": 364.1075469174086, "nwc_intensity": 34.919941153752234, "revenue_growth": 558.6193243098663},
        "Required": {"ebit_margin": 0.15198542490722722, "wacc_offset": -0.03594572240676071, "terminal_growth": 0.046499000000000006, "nwc_intensity": -0.5, "revenue_growth": 0.46572222222222226},
        "Closable": [],
        "Subset_Ceiling": 234.32689495767704,
        "Subset_Reachable": True,
    },
    "microsoft": {
        "Ceiling_Value_Per_Share": 617.1353189793824,
        "Reachable": True,
        "Dominant": "terminal_growth",
        "Contribution": {"ebit_margin": 13.274953217676853, "wacc_offset": 134.35735147640418, "terminal_growth": 169.5895287439804, "nwc_intensity": 1.9718786506431343, "revenue_growth": 72.70878485773505},
        "Required": {"ebit_margin": 0.7288428473149087, "wacc_offset": -0.02162481794219997, "terminal_growth": 0.046499000000000006, "nwc_intensity": -0.5, "revenue_growth": 0.2620555555555556},
        "Closable": [],
        "Subset_Ceiling": 395.94696203772105,
        "Subset_Reachable": False,
    },
    "procter_gamble": {
        "Ceiling_Value_Per_Share": 425.4419274410573,
        "Reachable": True,
        "Dominant": "terminal_growth",
        "Contribution": {"ebit_margin": 21.120261922172972, "wacc_offset": 142.7200758682891, "terminal_growth": 221.64147455330738, "nwc_intensity": 0.17763070111482193, "revenue_growth": 76.63545462416073},
        "Required": {"ebit_margin": 0.254995722019965, "wacc_offset": -0.003741321563905657, "terminal_growth": 0.030303482669126254, "nwc_intensity": -0.5, "revenue_growth": 0.04794444444444444},
        "Closable": ["revenue_growth", "terminal_growth", "wacc_offset"],
        "Subset_Ceiling": 167.41023182200834,
        "Subset_Reachable": True,
    },
    "tesla": {
        "Ceiling_Value_Per_Share": 708.8814891787182,
        "Reachable": True,
        "Dominant": "revenue_growth",
        "Contribution": {"ebit_margin": 507.2371915550159, "wacc_offset": 297.74125313019334, "terminal_growth": 123.11475214909865, "nwc_intensity": 11.583774407670717, "revenue_growth": 651.0604499301935},
        "Required": {"ebit_margin": 0.95, "wacc_offset": -0.06284502967524463, "terminal_growth": 0.046499000000000006, "nwc_intensity": -0.5, "revenue_growth": 1.2878333333333334},
        "Closable": [],
        "Subset_Ceiling": 49.36470799560835,
        "Subset_Reachable": False,
    },
}

HORIZON_GOLDEN = {
    "apple": {
        "Required_Years": None,
        "Ratio": None,
        "Verdict": "unreachable",
        "Status": "unreachable",
        "Direction": "up",
        "Best_Year": 30,
        "Best_Value": 168.07045762035057,
        "Anchor": 139.71402429765308,
        "Gap": -0.5810426552984793,
    },
    "boeing": {
        "Required_Years": None,
        "Ratio": None,
        "Verdict": "unreachable",
        "Status": "unreachable",
        "Direction": "up",
        "Best_Year": 30,
        "Best_Value": 107.13712601611122,
        "Anchor": 63.480673544284315,
        "Gap": -0.7823407342311874,
    },
    "microsoft": {
        "Required_Years": 23,
        "Ratio": 1.5333333333333334,
        "Verdict": "Implausible",
        "Status": "solved",
        "Direction": "up",
        "Best_Year": 30,
        "Best_Value": 603.2363699832133,
        "Anchor": 389.91297225355964,
        "Gap": -0.3359256540603588,
    },
    "procter_gamble": {
        "Required_Years": None,
        "Ratio": None,
        "Verdict": "unreachable",
        "Status": "unreachable",
        "Direction": "up",
        "Best_Year": 30,
        "Best_Value": 137.28497315491944,
        "Anchor": 133.4334396342254,
        "Gap": -0.08826931757094636,
    },
    "tesla": {
        "Required_Years": None,
        "Ratio": None,
        "Verdict": "unreachable",
        "Status": "unreachable",
        "Direction": "down",
        "Best_Year": 1,
        "Best_Value": 18.67059538344373,
        "Anchor": 14.443866543459722,
        "Gap": -0.954104350860684,
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

@pytest.fixture(scope = "module", params = sorted(LEVER_GOLDEN), ids = sorted(LEVER_GOLDEN))
def l_result(request):
    symbol = request.param
    value = plausible_ceiling(symbol, START_YEAR, YEARS, FREQ, N_MONTHS, AS_OF)
    return (symbol, value)    

@pytest.fixture(scope = "module", params = sorted(HORIZON_GOLDEN), ids = sorted(HORIZON_GOLDEN))
def h_result(request):
    symbol = request.param
    value = implied_horizon(symbol, START_YEAR, YEARS, FREQ, N_MONTHS, as_of = AS_OF)
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

def test_terminal_consistency(result):
    sym = result[0]
    val = result[1]

    assert val["wacc"]["Implicit_ROIC"] == pytest.approx(GOLDEN[sym]["Implicit_ROIC"], rel = REL)
    assert val["wacc"]["Capital_Turnover"] == pytest.approx(GOLDEN[sym]["Capital_Turnover"], rel = REL)
    assert val["wacc_low"]["Implicit_ROIC"] == pytest.approx(GOLDEN[sym]["Implicit_ROIC"], rel = REL)
    assert val["wacc_high"]["Implicit_ROIC"] == pytest.approx(GOLDEN[sym]["Implicit_ROIC"], rel = REL)

def test_roic_consistency(result):
    sym = result[0]
    val = result[1]

    assert val["wacc_low"]["ROIC_Consistency"] == GOLDEN[sym]["ROIC_Consistency"]
    assert val["wacc"]["ROIC_Consistency"] == GOLDEN[sym]["ROIC_Consistency"]
    assert val["wacc_high"]["ROIC_Consistency"] == GOLDEN[sym]["ROIC_Consistency"]

def test_tv_share(result):
    sym = result[0]
    val = result[1]

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

def test_terminal_growth():
    dcf = dcf_value(GUARD_SYMBOL, START_YEAR, 10, "1mo", N_MONTHS, terminal_growth = 0.05, as_of = "2026-08-19")
    
    assert dcf["wacc_low"]["Terminal_Growth"] == pytest.approx(0.0465, rel = REL)
    assert dcf["wacc"]["Terminal_Growth"] == pytest.approx(0.0465, rel = REL)
    assert dcf["wacc_high"]["Terminal_Growth"] == pytest.approx(0.0465, rel = REL)
    
    assert dcf["wacc_low"]["Terminal_Growth_Source"] == "Terminal growth ceiling"
    assert dcf["wacc"]["Terminal_Growth_Source"] == "Terminal growth ceiling"
    assert dcf["wacc_high"]["Terminal_Growth_Source"] == "Terminal growth ceiling"
    
    dcf = dcf_value(GUARD_SYMBOL, START_YEAR, 10, "1mo", N_MONTHS, as_of = "2026-08-19")
    
    assert dcf["wacc_low"]["Terminal_Growth_Source"] == "Assumption from TERMINAL_GROWTH"
    assert dcf["wacc"]["Terminal_Growth_Source"] == "Assumption from TERMINAL_GROWTH"
    assert dcf["wacc_high"]["Terminal_Growth_Source"] == "Assumption from TERMINAL_GROWTH"
    
    
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
    data = copy.deepcopy(get_data(GUARD_SYMBOL, START_YEAR, AS_OF))
    data[max(data)]["OperatingIncome"]["Value"] = None

    with pytest.raises(ValueError, match = "Operating Income"):
        project_fcf(data, YEARS, GUARD_ROIC)

def test_margin_start_zero_revenue():
    data = copy.deepcopy(get_data(GUARD_SYMBOL, START_YEAR, AS_OF))
    data[max(data)]["Revenue"]["Value"] = 0

    with pytest.raises(ValueError, match = "Revenue"):
        project_fcf(data, YEARS, GUARD_ROIC)

def test_margin_start_zero_operating_income():
    data = copy.deepcopy(get_data(GUARD_SYMBOL, START_YEAR, AS_OF))
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
    data = copy.deepcopy(get_data(GUARD_SYMBOL, START_YEAR, AS_OF))
    
    for year in data:
        data[year]["InterestExpense"]["Value"] = None
    
    coverage = synthetic_cost_of_debt(data, RF_STUB)
    
    assert coverage["Source"] == "Unavailable"
    assert coverage["Coverage"] is None
    assert coverage["Year"] is None
    assert coverage["Cost_of_Debt"] is None
    assert coverage["n"] == 0

def test_data_vintage():
    cut_data = get_data("microsoft", START_YEAR, CUT_M)
    as_of_data = get_data("microsoft", START_YEAR, AS_OF)

    assert max(cut_data) == 2025
    assert max(as_of_data) == 2026
    assert cut_data[2025]["Revenue"]["Value"] is not None
    
def test_vintage_keeps_missing():
    data = get_data(GUARD_SYMBOL, START_YEAR, AS_OF)
    
    assert "InterestExpense" in data[2025].keys()
    assert data[2025]["InterestExpense"]["Value"] is None

def test_cvps(l_result):
    sym = l_result[0]
    val = l_result[1]
    
    assert val["Ceiling_Value_Per_Share"] == pytest.approx(LEVER_GOLDEN[sym]["Ceiling_Value_Per_Share"], rel = REL)
    assert val["Status"] == "solved"
    assert val["Reachable"] is LEVER_GOLDEN[sym]["Reachable"]
    
def test_dominant_lever(l_result):
    sym = l_result[0]
    val = l_result[1]
    
    dominant = max(val["Levers"], key = lambda lev: val["Levers"][lev]["Contribution"])
    
    assert dominant == LEVER_GOLDEN[sym]["Dominant"]

def test_lever_detail(l_result):
    sym = l_result[0]
    val = l_result[1]
    
    for lev in LEVER_GOLDEN[sym]["Contribution"]:
        assert val["Levers"][lev]["Contribution"] == pytest.approx(LEVER_GOLDEN[sym]["Contribution"][lev], rel = REL)
    
    for lev in LEVER_GOLDEN[sym]["Required"]:
        assert val["Levers"][lev]["Required"] == pytest.approx(LEVER_GOLDEN[sym]["Required"][lev], rel = REL)

def test_sup_add(l_result):
    val = l_result[1]
    
    sum_contribs = sum([val["Levers"][lev]["Contribution"] for lev in val["Levers"]])
    
    assert sum_contribs > (val["Ceiling_Value_Per_Share"] - val["Value_Per_Share"])

def test_subset(l_result):
    sym = l_result[0]
    val = plausible_ceiling(sym, START_YEAR, YEARS, FREQ, N_MONTHS, AS_OF, levers = LEVER_SUBSET)
    
    assert val["Ceiling_Value_Per_Share"] == pytest.approx(LEVER_GOLDEN[sym]["Subset_Ceiling"], rel = REL)
    assert val["Reachable"] is LEVER_GOLDEN[sym]["Subset_Reachable"]
    assert len(val["Levers"]) == 3

def test_closable(l_result):
    sym = l_result[0]
    val = l_result[1]
    
    assert val["Closable"] == LEVER_GOLDEN[sym]["Closable"]
    assert val["Levers"]["nwc_intensity"]["Status"] == "unreachable"
    assert val["Levers"]["nwc_intensity"]["Ratio"] is None

def test_horizon_required(h_result):
    sym = h_result[0]
    val = h_result[1]

    assert val["Required_Years"] == HORIZON_GOLDEN[sym]["Required_Years"]
    assert val["Status"] == HORIZON_GOLDEN[sym]["Status"]
    assert val["Verdict"] == HORIZON_GOLDEN[sym]["Verdict"]

    if HORIZON_GOLDEN[sym]["Ratio"] is None:
        assert val["Ratio"] is None
    else:
        assert val["Ratio"] == pytest.approx(HORIZON_GOLDEN[sym]["Ratio"], rel = REL)

def test_horizon_direction(h_result):
    sym = h_result[0]
    val = h_result[1]

    assert val["Direction"] == HORIZON_GOLDEN[sym]["Direction"]
    assert val["Best_Year"] == HORIZON_GOLDEN[sym]["Best_Year"]
    assert val["Best_Value"] == pytest.approx(HORIZON_GOLDEN[sym]["Best_Value"], rel = REL)

def test_horizon_curve(h_result):
    sym = h_result[0]
    val = h_result[1]

    assert len(val["Curve"]) == HORIZON_BOUNDS[1] - HORIZON_BOUNDS[0] + 1
    assert val["Failures"] == {}
    assert val["Curve"][YEARS] == pytest.approx(GOLDEN[sym]["Value_Per_Share"], rel = REL)
    assert val["Curve"][YEARS] == pytest.approx(val["Value_Per_Share"], rel = REL)
    assert val["Curve"][HORIZON_ANCHOR] == pytest.approx(HORIZON_GOLDEN[sym]["Anchor"], rel = REL)
    assert val["Gap"] == pytest.approx(HORIZON_GOLDEN[sym]["Gap"], rel = REL)

def test_horizon_comparator_visible(h_result):
    val = h_result[1]

    assert val["Bounds"] == HORIZON_BOUNDS
    assert val["Comparator"] == HORIZON_COMPARATOR
    assert val["Comparator_Source"] is not None
    assert val["Base_Years"] == YEARS

def test_horizon_bounds_guard():
    with pytest.raises(ValueError):
        implied_horizon(BOUND_SYMBOL, START_YEAR, YEARS, FREQ, N_MONTHS, as_of = AS_OF, bounds = (0, 5))

    with pytest.raises(ValueError):
        implied_horizon(BOUND_SYMBOL, START_YEAR, YEARS, FREQ, N_MONTHS, as_of = AS_OF, bounds = (10, 5))

@pytest.mark.slow
def test_horizon_bounds_decide():
    for sym in HORIZON_WIDE_REQUIRED:
        val = implied_horizon(sym, START_YEAR, YEARS, FREQ, N_MONTHS, as_of = AS_OF, bounds = HORIZON_WIDE_BOUNDS)

        assert HORIZON_GOLDEN[sym]["Status"] == "unreachable"
        assert val["Status"] == "solved"
        assert val["Required_Years"] == HORIZON_WIDE_REQUIRED[sym]
        assert val["Verdict"] == "Implausible"

def test_implied_assumptions(h_result):
    sym = h_result[0]

    imp_asp = implied_assumptions(sym, START_YEAR, YEARS, FREQ, N_MONTHS, as_of = AS_OF)
    
    assert imp_asp["Levers"]["revenue_growth"]["Status"] == "solved"
    assert imp_asp["Levers"]["revenue_growth"]["Required"] < IMPLIED_GROWTH_BOUNDS[1]
    assert imp_asp["Levers"]["revenue_growth"]["Required"] > IMPLIED_GROWTH_BOUNDS[0]
    

def test_tesla(monkeypatch):
    monkeypatch.setattr(valuation, "IMPLIED_GROWTH_BOUNDS", GROWTH_NARROW_BOUNDS)
    imp_asp = implied_assumptions(GROWTH_NARROW_SYMBOL, START_YEAR, YEARS, FREQ, N_MONTHS, as_of = AS_OF)
     
    assert imp_asp["Levers"]["revenue_growth"]["Status"] == "unreachable"
    assert imp_asp["Levers"]["revenue_growth"]["Required"] == 1.0
    assert imp_asp["Levers"]["revenue_growth"]["Ratio"] is None

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
