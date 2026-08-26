import pytest 
from valuation import dcf_value, monte_carlo
from wacc_calculation import N_MONTHS

AS_OF = "2026-08-19"
START_YEAR = 2016
YEARS = 10
FREQ = "1mo"
REL = 1e-9
DRAWS = 2000
SEED = 12345

MC_GOLDEN = {
    "apple": {
        "Percentiles": {0.05: 119.68165662036753, 0.25: 126.67846911637066, 0.5: 132.0549687114854, 0.75: 138.4535670055825, 0.95: 148.35364458330798},
        "Mean": 132.87252657242456,
        "P_Above_Market": 0.0,
        "WACC_Sigma": 0.004157942544885411,
        "Margin_Range": (0.2881, 0.311, 0.31970799762591884),
    },
    "boeing": {
        "Percentiles": {0.05: 10.525922004067287, 0.25: 28.665822950061298, 0.5: 43.383082655109284, 0.75: 59.966901179276135, 0.95: 83.68168784611444},
        "Mean": 45.08001783012066,
        "P_Above_Market": 0.0,
        "WACC_Sigma": 0.005015380997594274,
        "Margin_Range": (0.0186, 0.0478521847020556, 0.0698),
    },
    "microsoft": {
        "Percentiles": {0.05: 253.30901238559494, 0.25: 272.1938255594725, 0.5: 286.7280681124347, 0.75: 304.42527193370665, 0.95: 332.0827976343321},
        "Mean": 289.24113681309524,
        "P_Above_Market": 0.0,
        "WACC_Sigma": 0.004901827056874809,
        "Margin_Range": (0.4159, 0.4401, 0.4562195624085985),
    },
    "procter_gamble": {
        "Percentiles": {0.05: 123.8214594125936, 0.25: 135.4147881347369, 0.5: 145.31487150328533, 0.75: 157.69816207190578, 0.95: 178.84621301741208},
        "Mean": 147.73554932950893,
        "P_Above_Market": 0.5165,
        "WACC_Sigma": 0.003759716864892804,
        "Margin_Range": (0.2209, 0.2281, 0.24264391818138675),
    },
    "tesla": {
        "Percentiles": {0.05: 11.383458435628654, 0.25: 12.768689799617022, 0.5: 14.358917920983682, 0.75: 16.366842218213144, 0.95: 19.811374128550597},
        "Mean": 14.788374552624214,
        "P_Above_Market": 0.0,
        "WACC_Sigma": 0.012612017977356959,
        "Margin_Range": (0.04592573845001951, 0.04592573845001951, 0.0953),
    },
}

GOLDEN = {
    "apple": {
        "Value_Per_Share": 133.44106525333228,
        "WACC": 0.08995747953161094,
        "EV": 1938009284879.2722,
        "Low": 149.59995602555952,
        "High": 120.83715459465307,
        "Implied_Multiple": 9.469297775133125,
        "TV_Share": 0.4973754873996333,
        "Data_Filed": "2025-10-31",
        "RF_Date": "2026-08-19"
    },
    "microsoft": {
        "Value_Per_Share": 288.01770203385166,
        "WACC": 0.09152748645648522,
        "EV": 2074064499314.8662,
        "Low": 335.670332283555,
        "High": 252.62692050731164,
        "Implied_Multiple": 8.837795747421366,
        "TV_Share": 0.6127997614864084,
        "Data_Filed": "2026-07-29",
        "RF_Date": "2026-08-19"
    },
    "procter_gamble": {
        "Value_Per_Share": 143.86212939293225,
        "WACC": 0.06697258808201786,
        "EV": 361930550092.97125,
        "Low": 173.14932899749473,
        "High": 123.28632225609375,
        "Implied_Multiple": 13.957807983721354,
        "TV_Share": 0.6330847958177995,
        "Data_Filed": "2026-08-04",
        "RF_Date": "2026-08-19"
    },
    "tesla": {
        "Value_Per_Share": 11.603865968690068,
        "WACC": 0.11254506249381475,
        "EV": 7636717798.961755,
        "Low": 14.57777856563369,
        "High": 10.166951960086344,
        "Implied_Multiple": 3.300729427140757,
        "TV_Share": None,
        "Data_Filed": "2026-01-29",
        "RF_Date": "2026-08-19"
    },
    "boeing": {
        "Value_Per_Share": 48.41719056990017,
        "WACC": 0.07827978063775556,
        "EV": 69885300010.54968,
        "Low": 71.06976492152138,
        "High": 32.943199671951476,
        "Implied_Multiple": 7.8119164795501685,
        "TV_Share": 0.7326744961458926,
        "Data_Filed": "2026-01-30",
        "RF_Date": "2026-08-19"
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
