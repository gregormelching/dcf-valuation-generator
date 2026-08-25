import pytest 
from valuation import dcf_value
from wacc_calculation import N_MONTHS

AS_OF = "2026-08-19"
START_YEAR = 2016
YEARS = 10
FREQ = "1mo"
REL = 1e-9

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

def test_rf_date(result):
    sym = result[0]
    val = result[1]

    assert val["wacc_low"]["RF_Date"] == GOLDEN[sym]["RF_Date"]
    assert val["wacc"]["RF_Date"] == GOLDEN[sym]["RF_Date"]
    assert val["wacc_high"]["RF_Date"] == GOLDEN[sym]["RF_Date"]
