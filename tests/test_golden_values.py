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
        "Value_Per_Share": 132.93314018502642,
        "WACC": 0.09025112725090859,
        "EV": 1930504004772.4358,
        "Low": 148.9387279796099,
        "High": 120.43441028667516,
        "Implied_Multiple": 9.42668337424583,
        "TV_Share": 0.4959109494244441,
        "Data_Filed": "2025-10-31"
    },
    "microsoft": {
        "Value_Per_Share": 286.7702755785626,
        "WACC": 0.09182378514718367,
        "EV": 2064792170927.136,
        "Low": 333.95661481697067,
        "High": 251.68040963847812,
        "Implied_Multiple": 8.798608692948864,
        "TV_Share": 0.611432704705746,
        "Data_Filed": "2026-07-29"
    },
    "procter_gamble": {
        "Value_Per_Share": 142.97501416331895,
        "WACC": 0.06724483047851787,
        "EV": 359852596672.5545,
        "Low": 171.84813810612897,
        "High": 122.6425845006934,
        "Implied_Multiple": 13.867858348408992,
        "TV_Share": 0.6312886378125676,
        "Data_Filed": "2026-08-04"
    },
    "tesla": {
        "Value_Per_Share": 11.580145700129227,
        "WACC": 0.11284298255371317,
        "EV": 7547709104.544979,
        "Low": 14.525248530457889,
        "High": 10.154654815360814,
        "Implied_Multiple": 3.289534981323289,
        "TV_Share": None,
        "Data_Filed": "2026-01-29"
    },
    "boeing": {
        "Value_Per_Share": 48.00817099277191,
        "WACC": 0.07849922737698098,
        "EV": 69564077673.44485,
        "Low": 70.45075697938258,
        "High": 32.65389007866942,
        "Implied_Multiple": 7.779873033642834,
        "TV_Share": 0.7317169399674108,
        "Data_Filed": "2026-01-30"
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
        