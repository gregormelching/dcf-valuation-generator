import serialize
import pytest
from serialize import serialize_monte_carlo
from valuation import monte_carlo, ASSUMPTIONS, MC_BORDERS, MC_PERCENTILES, MC_MEDIAN, MC_SEED, N_MONTHS

TOP_KEYS = sorted(["Symbol", "As_Of", "Status", "Distribution", "Offset", "Inputs", "Reliability", "Draws"])
OFFSET_KEYS = sorted(["Base_Value_Per_Share", "Market_Price", "Median", "Median_Offset", "Mode_Position",
                      "P_Above_Market", "Mean"])
INPUT_KEYS = sorted(["WACC", "WACC_Sigma", "Margin_Low", "Margin_Mode", "Margin_High", "Margin_Bases_Used",
                     "Terminal_Growth_Borders", "Draws_Requested", "Seed"])
RELIABILITY_KEYS = sorted(["Draws_OK", "Draws_Failed", "Failures"])
DISTRIBUTION_KEYS = sorted(["Percentile", "Value"])
AS_OF = "2026-08-19"
START_YEAR = 2016
YEARS = 10
FREQ = "1mo"
REL = 1e-9
DRAWS = 200
SEED = MC_SEED
FAIL_YEARS = 0
FAIL_YEARS_MESSAGE = "Years must be at least 1, got 0."
MODE_GOLDEN = {"apple": "Interior", "boeing": "Min", "microsoft": "Interior",
               "procter_gamble": "Max", "tesla": "Min"}
EMPTY_FAILURES = {"WACC must be greater than Terminal Growth.": 7}
EMPTY_RESULT = {
    "As_Of": AS_OF, "Percentiles": None, "Mean": None, "P_Above_Market": None, "Draws_OK": 0, "Draws_Failed": 7,
    "WACC_Sigma": 0.004, "Margin_Range": (0.1, 0.2, 0.3), "Margin_Bases_Used": ["Driver_Ratio"],
    "Median_Offset": None, "Mode_Position": "Interior", "Base_Value_Per_Share": 100.0,
    "Market_Price": 200.0, "WACC": 0.09, "Seed": SEED, "Failures": EMPTY_FAILURES, "Draws": [],
}

def return_empty(*args, **kwargs):
    return dict(EMPTY_RESULT)

@pytest.fixture(scope = "session")
def panels():
    return {symbol: serialize_monte_carlo(symbol, START_YEAR, YEARS, FREQ, N_MONTHS, as_of = AS_OF,
                                          draws = DRAWS, seed = SEED)
            for symbol in sorted(ASSUMPTIONS)}

@pytest.fixture(scope = "session")
def raws():
    return {symbol: monte_carlo(symbol, START_YEAR, YEARS, FREQ, N_MONTHS, as_of = AS_OF,
                                draws = DRAWS, seed = SEED)
            for symbol in sorted(ASSUMPTIONS)}

@pytest.mark.parametrize("symbol", sorted(ASSUMPTIONS))
def test_top_level_shape(symbol, panels):
    panel = panels[symbol]

    assert sorted(panel) == TOP_KEYS
    assert panel["Symbol"] == symbol
    assert panel["As_Of"] == AS_OF
    assert panel["Status"] == "calculated"

@pytest.mark.parametrize("symbol", sorted(ASSUMPTIONS))
def test_as_of_comes_from_the_result(symbol, panels, raws):
    assert raws[symbol]["As_Of"] == AS_OF
    assert panels[symbol]["As_Of"] == raws[symbol]["As_Of"]

@pytest.mark.parametrize("symbol", sorted(ASSUMPTIONS))
def test_block_shapes(symbol, panels):
    panel = panels[symbol]

    assert sorted(panel["Offset"]) == OFFSET_KEYS
    assert sorted(panel["Inputs"]) == INPUT_KEYS
    assert sorted(panel["Reliability"]) == RELIABILITY_KEYS
    for row in panel["Distribution"]:
        assert sorted(row) == DISTRIBUTION_KEYS

@pytest.mark.parametrize("symbol", sorted(ASSUMPTIONS))
def test_distribution_matches_raw(symbol, panels, raws):
    distribution = panels[symbol]["Distribution"]
    raw = raws[symbol]["Percentiles"]

    assert [row["Percentile"] for row in distribution] == list(MC_PERCENTILES)
    for row in distribution:
        assert row["Value"] == raw[row["Percentile"]]

@pytest.mark.parametrize("symbol", sorted(ASSUMPTIONS))
def test_distribution_is_monotone(symbol, panels):
    values = [row["Value"] for row in panels[symbol]["Distribution"]]

    assert values == sorted(values)
    assert len(set(values)) == len(values)

@pytest.mark.parametrize("symbol", sorted(ASSUMPTIONS))
def test_offset_matches_raw(symbol, panels, raws):
    offset = panels[symbol]["Offset"]
    raw = raws[symbol]

    assert offset["Base_Value_Per_Share"] == raw["Base_Value_Per_Share"]
    assert offset["Market_Price"] == raw["Market_Price"]
    assert offset["Median"] == raw["Percentiles"][MC_MEDIAN]
    assert offset["Median_Offset"] == raw["Median_Offset"]
    assert offset["Mode_Position"] == raw["Mode_Position"]
    assert offset["P_Above_Market"] == raw["P_Above_Market"]
    assert offset["Mean"] == raw["Mean"]

@pytest.mark.parametrize("symbol", sorted(ASSUMPTIONS))
def test_median_offset_is_redundant(symbol, panels):
    offset = panels[symbol]["Offset"]

    assert offset["Median_Offset"] == pytest.approx(
        offset["Median"] / offset["Base_Value_Per_Share"] - 1, rel = REL)

@pytest.mark.parametrize("symbol", sorted(ASSUMPTIONS))
def test_inputs_unpack_margin_range(symbol, panels, raws):
    inputs = panels[symbol]["Inputs"]
    low, mode, high = raws[symbol]["Margin_Range"]

    assert inputs["Margin_Low"] == low
    assert inputs["Margin_Mode"] == mode
    assert inputs["Margin_High"] == high
    assert inputs["Margin_Low"] <= inputs["Margin_Mode"] <= inputs["Margin_High"]

@pytest.mark.parametrize("symbol", sorted(ASSUMPTIONS))
def test_inputs_match_raw(symbol, panels, raws):
    inputs = panels[symbol]["Inputs"]
    raw = raws[symbol]

    assert inputs["WACC"] == raw["WACC"]
    assert inputs["WACC_Sigma"] == raw["WACC_Sigma"]
    assert inputs["Margin_Bases_Used"] == raw["Margin_Bases_Used"]
    assert inputs["Terminal_Growth_Borders"] == list(MC_BORDERS)
    assert inputs["Draws_Requested"] == DRAWS
    assert inputs["Seed"] == SEED

@pytest.mark.parametrize("symbol", sorted(ASSUMPTIONS))
def test_mode_position_consistent_with_margins(symbol, panels):
    inputs = panels[symbol]["Inputs"]
    position = panels[symbol]["Offset"]["Mode_Position"]
    low = inputs["Margin_Low"]
    mode = inputs["Margin_Mode"]
    high = inputs["Margin_High"]

    if low == high:
        assert position == "Degenerate"
    elif mode == low:
        assert position == "Min"
    elif mode == high:
        assert position == "Max"
    else:
        assert position == "Interior"

    assert position == MODE_GOLDEN[symbol]

@pytest.mark.parametrize("symbol", sorted(ASSUMPTIONS))
def test_reliability_and_draws(symbol, panels, raws):
    reliability = panels[symbol]["Reliability"]
    draws = panels[symbol]["Draws"]
    raw = raws[symbol]

    assert reliability["Draws_OK"] == raw["Draws_OK"]
    assert reliability["Draws_Failed"] == raw["Draws_Failed"]
    assert reliability["Failures"] == raw["Failures"]
    assert reliability["Draws_OK"] + reliability["Draws_Failed"] == DRAWS
    assert len(draws) == reliability["Draws_OK"]
    assert draws == sorted(draws)

@pytest.mark.parametrize("symbol", sorted(ASSUMPTIONS))
def test_draws_bracket_the_percentiles(symbol, panels):
    draws = panels[symbol]["Draws"]
    values = [row["Value"] for row in panels[symbol]["Distribution"]]

    assert draws[0] <= values[0]
    assert values[-1] <= draws[-1]

def test_error_return_matches_success_shape():
    out = serialize_monte_carlo("apple", START_YEAR, FAIL_YEARS, FREQ, N_MONTHS, as_of = AS_OF,
                                draws = DRAWS, seed = SEED)

    assert sorted(out) == TOP_KEYS
    assert out["Symbol"] == "apple"
    assert out["As_Of"] == AS_OF
    assert out["Status"] == FAIL_YEARS_MESSAGE
    for key in TOP_KEYS:
        if key in ("Symbol", "As_Of", "Status"):
            continue
        assert out[key] is None

def test_empty_distribution(monkeypatch):
    monkeypatch.setattr(serialize, "monte_carlo", return_empty)
    out = serialize_monte_carlo("apple", START_YEAR, YEARS, FREQ, N_MONTHS, as_of = AS_OF,
                                draws = DRAWS, seed = SEED)

    assert out["Status"] == "calculated"
    assert sorted(out) == TOP_KEYS
    assert out["Distribution"] is None
    assert out["Offset"]["Median"] is None
    assert out["Offset"]["Median_Offset"] is None
    assert out["Offset"]["Mean"] is None
    assert out["Offset"]["P_Above_Market"] is None
    assert out["Reliability"]["Draws_OK"] == 0
    assert out["Reliability"]["Draws_Failed"] == 7
    assert out["Reliability"]["Failures"] == EMPTY_FAILURES
    assert out["Draws"] == []
    assert out["Inputs"]["Margin_Low"] == 0.1
    assert out["Inputs"]["Margin_Mode"] == 0.2
    assert out["Inputs"]["Margin_High"] == 0.3
