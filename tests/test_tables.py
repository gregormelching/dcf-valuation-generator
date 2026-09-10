import pytest
from database import get_data
from model import driver_ratio
from valuation import (
    sensitivity_grid, sensitivity_table, nwc_scenario, dcf_value,
    ASSUMPTIONS, MARGIN_BASES, NWC_OFFSETS, TERMINAL_GROWTHS, WACC_OFFSETS, TERMINAL_GROWTH,
)
from wacc_calculation import N_MONTHS

AS_OF = "2026-08-19"
START_YEAR = 2016
YEARS = 10
FREQ = "1mo"
REL = 1e-9
GRID_SYMBOL = "apple"
TABLE_SYMBOL = "apple"
NWC_SYMBOL = "boeing"
FAIL_SYMBOL = "procter_gamble"
FAIL_OFFSET = -0.03
FAIL_GROWTH = 0.035
GRID_KEYS = ["Implied_Multiple", "Implied_Multiple_Source", "Offset", "Status",
             "TV_Share", "Terminal_Growth", "Value_Per_Share", "WACC"]
TABLE_KEYS = ["EBIT_Margin_Target", "Implied_Multiple", "Implied_Multiple_Source", "Is_Base",
              "Margin_Base", "Market_Price", "Status", "TV_Share", "TV_Share_Source",
              "Upside", "Value_Per_Share", "WACC"]
NWC_KEYS = ["EBIT_Margin_Target", "Implied_Multiple", "Implied_Multiple_Source", "Is_Base",
            "Market_Price", "NWC_Intensity", "NWC_Offset", "Status", "TV_Share", "TV_Share_Source",
            "Upside", "Value_Per_Share", "WACC"]
TABLE_GOLDEN = {
    "Driver_Ratio":    121.24897806817407,
    "Mean_Last_Three": 128.17161739600098,
    "Last":            130.8040334148573,
}
NWC_GOLDEN = {
    -0.05:  52.753525441490126,
    -0.025: 51.58932357180245,
    0.0:    50.42512170211479,
    0.025:  49.26091983242711,
    0.05:   48.096717962739426,
}
NWC_BASE_INTENSITY = 0.2211

@pytest.fixture(scope = "module")
def grid():
    return sensitivity_grid(GRID_SYMBOL, START_YEAR, YEARS, FREQ, N_MONTHS, as_of = AS_OF)

@pytest.fixture(scope = "module")
def table():
    return sensitivity_table(TABLE_SYMBOL, START_YEAR, YEARS, FREQ, N_MONTHS, as_of = AS_OF)

@pytest.fixture(scope = "module")
def nwc():
    return nwc_scenario(NWC_SYMBOL, START_YEAR, YEARS, FREQ, N_MONTHS, as_of = AS_OF)

@pytest.fixture(scope = "module")
def base_dcf():
    return {symbol: dcf_value(symbol, START_YEAR, YEARS, FREQ, N_MONTHS, as_of = AS_OF)["wacc"]
            for symbol in (GRID_SYMBOL, TABLE_SYMBOL, NWC_SYMBOL)}

def test_grid_axes(grid):
    assert sorted(grid) == sorted((o, g) for o in WACC_OFFSETS for g in TERMINAL_GROWTHS)
    assert len(grid) == len(WACC_OFFSETS) * len(TERMINAL_GROWTHS)

def test_grid_cell_shape(grid):
    for key, cell in grid.items():
        assert sorted(cell) == GRID_KEYS
        assert (cell["Offset"], cell["Terminal_Growth"]) == key
        assert cell["Status"] == "calculated"

def test_grid_base_cell(grid, base_dcf):
    cell = grid[(0.0, TERMINAL_GROWTH)]
    base = base_dcf[GRID_SYMBOL]

    for key in ["Value_Per_Share", "WACC", "Implied_Multiple", "TV_Share"]:
        assert cell[key] == pytest.approx(base[key], rel = REL)
    assert cell["Implied_Multiple_Source"] == base["Implied_Multiple_Source"]

def test_grid_failed_cell(grid):
    failed = sensitivity_grid(FAIL_SYMBOL, START_YEAR, YEARS, FREQ, N_MONTHS, as_of = AS_OF,
                              offset = (FAIL_OFFSET,), growths = (FAIL_GROWTH,))
    cell = failed[(FAIL_OFFSET, FAIL_GROWTH)]

    assert sorted(cell) == GRID_KEYS
    assert cell["Status"] == "WACC must be greater than Terminal Growth."
    for key in ["Value_Per_Share", "Implied_Multiple", "Implied_Multiple_Source", "TV_Share", "WACC"]:
        assert cell[key] is None
    assert (cell["Offset"], cell["Terminal_Growth"]) == (FAIL_OFFSET, FAIL_GROWTH)

def test_table_rows(table):
    assert sorted(table) == sorted(MARGIN_BASES)
    for margin_base, row in table.items():
        assert sorted(row) == TABLE_KEYS
        assert row["Margin_Base"] == margin_base
        assert row["Status"] == "calculated"

def test_table_golden(table):
    for margin_base, value_per_share in TABLE_GOLDEN.items():
        assert table[margin_base]["Value_Per_Share"] == pytest.approx(value_per_share, rel = REL)

def test_table_base_row(table, base_dcf):
    base = base_dcf[TABLE_SYMBOL]
    flagged = [mb for mb in table if table[mb]["Is_Base"]]

    assert flagged == [ASSUMPTIONS[TABLE_SYMBOL]["margin_base"]]
    assert table[flagged[0]]["Value_Per_Share"] == pytest.approx(base["Value_Per_Share"], rel = REL)
    assert table[flagged[0]]["EBIT_Margin_Target"] == pytest.approx(base["EBIT_Margin_Target"], rel = REL)

def test_table_failed_row():
    failed = sensitivity_table("boeing", START_YEAR, YEARS, FREQ, N_MONTHS, as_of = AS_OF,
                               margin_bases = ("Mean_Last_Three",))
    row = failed["Mean_Last_Three"]

    assert sorted(row) == TABLE_KEYS
    assert row["Status"] == "Missing data for EBIT, D&A, CapEx, or Working Capital"
    assert row["Margin_Base"] == "Mean_Last_Three"
    for key in ["Value_Per_Share", "EBIT_Margin_Target", "Implied_Multiple", "Implied_Multiple_Source",
                "TV_Share", "TV_Share_Source", "Market_Price", "Upside", "WACC"]:
        assert row[key] is None

def test_nwc_rows(nwc):
    assert sorted(nwc) == sorted(NWC_OFFSETS)
    for offset, row in nwc.items():
        assert sorted(row) == NWC_KEYS
        assert row["NWC_Offset"] == offset
        assert row["NWC_Intensity"] == pytest.approx(NWC_BASE_INTENSITY + offset, rel = REL)
        assert row["Status"] == "calculated"

def test_nwc_golden(nwc):
    for offset, value_per_share in NWC_GOLDEN.items():
        assert nwc[offset]["Value_Per_Share"] == pytest.approx(value_per_share, rel = REL)

def test_nwc_base_row(nwc, base_dcf):
    base = base_dcf[NWC_SYMBOL]
    flagged = [o for o in nwc if nwc[o]["Is_Base"]]

    assert flagged == [0.0]
    assert nwc[0.0]["Value_Per_Share"] == pytest.approx(base["Value_Per_Share"], rel = REL)

def test_nwc_higher_intensity_lowers_value(nwc):
    values = [nwc[i]["Value_Per_Share"] for i in sorted(nwc)]

    assert values == sorted(values, reverse = True)

@pytest.mark.parametrize("symbol", sorted(ASSUMPTIONS))
def test_nwc_anchored_for_every_symbol(symbol):
    metrics = ASSUMPTIONS[symbol]["metrics"]
    nwc_str = metrics["NWC"] if metrics is not None and "NWC" in metrics else "Driver_Ratio"
    base = driver_ratio(get_data(symbol, START_YEAR, AS_OF), "NWC")[nwc_str]
    table = nwc_scenario(symbol, START_YEAR, YEARS, FREQ, N_MONTHS, as_of = AS_OF)
    flagged = [o for o in table if table[o]["Is_Base"]]

    assert flagged == [0.0]
    assert table[0.0]["NWC_Intensity"] == pytest.approx(base, rel = REL)
