import serialize
import pytest
from serialize import serialize_company
from valuation import dcf_value, ASSUMPTIONS, MARGIN_BASES, NWC_OFFSETS, TERMINAL_GROWTHS, WACC_OFFSETS, N_MONTHS
from database import get_data
from model import driver_ratio, roic, effective_tax_rate, TERMINAL_GROWTH

TOP_KEYS = sorted(["Symbol", "As_Of", "Status", "Blocks_Failed", "Headline", "Assumptions", "Provenance",
                   "Quality", "Projection", "Grid", "Margin_Table", "NWC_Table", "Implied", "Ceiling", "Horizon"])
HEADLINE_KEYS = ["Value_Per_Share", "Market_Price", "Upside", "EV", "Equity_Value", "PV_Explicit", "PV_TV",
                 "TV_Share", "TV_Share_Source", "WACC", "WACC_Low", "WACC_High"]
PROJECTION_KEYS = sorted(["Year", "Is_Terminal", "Revenue", "EBIT", "EBIT_Margin", "NOPAT", "Tax_Rate", "D&A",
                          "CapEx", "dNWC", "Reinvestment", "Reinvestment_Rate", "FCF"])
ASSUMPTION_LABELS = ["Revenue Growth", "EBIT-Startmargin", "EBIT-Targetmargin", "D&A", "CapEx", "NWC",
                     "Terminal Growth", "Terminal ROIC", "WACC", "Taxrate"]
FAILED_BLOCKS = ["Grid", "Margin_Table", "NWC_Table", "Implied", "Ceiling", "Horizon"]
METRIC_LABELS = ["D&A", "CapEx", "NWC"]
TERMINAL_ONLY_NONE = ["D&A", "CapEx", "dNWC"]
AS_OF = "2026-08-19"
START_YEAR = 2016
YEARS = 10
FREQ = "1mo"
REL = 1e-9
FAIL_YEARS = 0
FAIL_START_YEAR = 2024
FAIL_YEARS_MESSAGE = "Years must be at least 1, got 0."
WACC_SOURCE_GOLDEN = {"apple": "1mo", "boeing": "1mo+2023", "microsoft": "1mo",
                      "procter_gamble": "1mo", "tesla": "1mo"}

def by_label(panel):
    return {row["Label"]: row for row in panel["Assumptions"]}

def metric_source(symbol, label):
    metrics = ASSUMPTIONS[symbol]["metrics"]
    return metrics[label] if metrics is not None and label in metrics else "Driver_Ratio"

def raise_value_error(*args, **kwargs):
    raise ValueError("forced")

@pytest.fixture(scope = "session")
def panels():
    return {symbol: serialize_company(symbol, START_YEAR, YEARS, FREQ, N_MONTHS, as_of = AS_OF)
            for symbol in sorted(ASSUMPTIONS)}

@pytest.fixture(scope = "session")
def bases():
    return {symbol: dcf_value(symbol, START_YEAR, YEARS, FREQ, N_MONTHS, as_of = AS_OF)
            for symbol in sorted(ASSUMPTIONS)}

@pytest.mark.parametrize("symbol", sorted(ASSUMPTIONS))
def test_top_level_shape(symbol, panels):
    panel = panels[symbol]

    assert sorted(panel) == TOP_KEYS
    assert panel["Symbol"] == symbol
    assert panel["As_Of"] == AS_OF
    assert panel["Status"] == "calculated"
    assert panel["Blocks_Failed"] == []

def test_error_return_matches_success_shape():
    out = serialize_company("apple", START_YEAR, FAIL_YEARS, FREQ, N_MONTHS, as_of = AS_OF)

    assert sorted(out) == TOP_KEYS
    assert out["Symbol"] == "apple"
    assert out["As_Of"] == AS_OF
    assert out["Status"] == FAIL_YEARS_MESSAGE
    assert out["Blocks_Failed"] == FAILED_BLOCKS
    for key in TOP_KEYS:
        if key in ("Symbol", "As_Of", "Status", "Blocks_Failed"):
            continue
        assert out[key] is None

def test_error_return_insufficient_data():
    out = serialize_company("apple", FAIL_START_YEAR, YEARS, FREQ, N_MONTHS, as_of = AS_OF)

    assert sorted(out) == TOP_KEYS
    assert out["Status"] == "Insufficient Data"
    assert out["Blocks_Failed"] == FAILED_BLOCKS

@pytest.mark.parametrize("symbol", sorted(ASSUMPTIONS))
def test_headline_matches_dcf(symbol, panels, bases):
    headline = panels[symbol]["Headline"]
    dcf = bases[symbol]

    assert sorted(headline) == sorted(HEADLINE_KEYS)
    for key in HEADLINE_KEYS:
        if key in ("WACC_Low", "WACC_High"):
            continue
        assert headline[key] == dcf["wacc"][key]

    assert headline["WACC_Low"] == dcf["wacc_low"]["WACC"]
    assert headline["WACC_High"] == dcf["wacc_high"]["WACC"]
    assert headline["WACC_Low"] < headline["WACC"] < headline["WACC_High"]

@pytest.mark.parametrize("symbol", sorted(ASSUMPTIONS))
def test_assumptions_order_and_shape(symbol, panels):
    panel = panels[symbol]

    assert [row["Label"] for row in panel["Assumptions"]] == ASSUMPTION_LABELS
    for row in panel["Assumptions"]:
        assert sorted(row) == ["Label", "Source", "Unit", "Value"]
        assert row["Unit"] == "pct"

@pytest.mark.parametrize("symbol", sorted(ASSUMPTIONS))
def test_assumption_metric_sources(symbol, panels):
    rows = by_label(panels[symbol])
    data = get_data(symbol, START_YEAR, AS_OF)

    for label in METRIC_LABELS:
        source = metric_source(symbol, label)

        assert rows[label]["Source"] == source
        assert rows[label]["Value"] == pytest.approx(driver_ratio(data, label)[source], rel = REL)

@pytest.mark.parametrize("symbol", sorted(ASSUMPTIONS))
def test_assumption_tax_rate(symbol, panels):
    rows = by_label(panels[symbol])
    tax = effective_tax_rate(get_data(symbol, START_YEAR, AS_OF))

    assert rows["Taxrate"]["Value"] == tax["Effective_Tax_Rate"]
    assert rows["Taxrate"]["Source"] == tax["Source"]

@pytest.mark.parametrize("symbol", sorted(ASSUMPTIONS))
def test_wacc_row_source_strips_two_segments(symbol, panels, bases):
    rows = by_label(panels[symbol])
    source = bases[symbol]["wacc"]["Source"]

    assert rows["WACC"]["Source"] == "+".join(source.split("+")[:-2])
    assert rows["WACC"]["Source"] == WACC_SOURCE_GOLDEN[symbol]

@pytest.mark.parametrize("symbol", sorted(ASSUMPTIONS))
def test_projection_shape(symbol, panels):
    projection = panels[symbol]["Projection"]
    years = [row["Year"] for row in projection]

    assert len(projection) == YEARS + 1
    assert years == sorted(years)
    assert len(set(years)) == len(years)
    assert [row["Is_Terminal"] for row in projection] == [False] * YEARS + [True]

    for row in projection:
        assert sorted(row) == PROJECTION_KEYS
        for key in TERMINAL_ONLY_NONE:
            if row["Is_Terminal"]:
                assert row[key] is None
            else:
                assert row[key] is not None

@pytest.mark.parametrize("symbol", sorted(ASSUMPTIONS))
def test_projection_matches_dcf(symbol, panels, bases):
    projection = panels[symbol]["Projection"]
    base = bases[symbol]["wacc"]["Projection"]

    assert [row["Year"] for row in projection] == sorted(base)
    for row in projection:
        for key in row:
            if key in ("Year", "Is_Terminal"):
                continue
            assert row[key] == base[row["Year"]][key]

@pytest.mark.parametrize("symbol", sorted(ASSUMPTIONS))
def test_grid_orientation(symbol, panels):
    panel = panels[symbol]
    grid = panel["Grid"]
    offsets = grid["Offsets"]
    growths = grid["Growths"]
    rows = grid["Rows"]

    assert offsets == list(WACC_OFFSETS)
    assert growths == list(TERMINAL_GROWTHS)
    assert len(rows) == len(offsets)
    for row in rows:
        assert len(row) == len(growths)

    for i, offset in enumerate(offsets):
        for j, growth in enumerate(growths):
            assert rows[i][j]["Offset"] == offset
            assert rows[i][j]["Terminal_Growth"] == growth

    centre = rows[offsets.index(0.0)][growths.index(TERMINAL_GROWTH)]

    assert centre["Value_Per_Share"] == pytest.approx(panel["Headline"]["Value_Per_Share"], rel = REL)
    assert centre["WACC"] == pytest.approx(panel["Headline"]["WACC"], rel = REL)

@pytest.mark.parametrize("symbol", sorted(ASSUMPTIONS))
def test_margin_table_order(symbol, panels):
    panel = panels[symbol]
    table = panel["Margin_Table"]

    assert [row["Margin_Base"] for row in table] == list(MARGIN_BASES)

    flagged = [row for row in table if row["Is_Base"]]

    assert len(flagged) == 1
    assert flagged[0]["Margin_Base"] == ASSUMPTIONS[symbol]["margin_base"]
    assert flagged[0]["Value_Per_Share"] == pytest.approx(panel["Headline"]["Value_Per_Share"], rel = REL)

    for row in table:
        if row["Status"] != "calculated":
            assert row["Value_Per_Share"] is None
            assert not row["Is_Base"]

@pytest.mark.parametrize("symbol", sorted(ASSUMPTIONS))
def test_nwc_table_order(symbol, panels):
    panel = panels[symbol]
    table = panel["NWC_Table"]

    assert [row["NWC_Offset"] for row in table] == list(NWC_OFFSETS)

    flagged = [row for row in table if row["Is_Base"]]

    assert len(flagged) == 1
    assert flagged[0]["NWC_Offset"] == 0.0
    assert flagged[0]["Value_Per_Share"] == pytest.approx(panel["Headline"]["Value_Per_Share"], rel = REL)
    assert flagged[0]["NWC_Intensity"] == pytest.approx(by_label(panel)["NWC"]["Value"], rel = REL)

@pytest.mark.parametrize("symbol", sorted(ASSUMPTIONS))
def test_quality_matches_roic(symbol, panels):
    quality = panels[symbol]["Quality"]
    measured = roic(get_data(symbol, START_YEAR, AS_OF))

    assert quality["IC_Last"] == measured["IC_Last"]
    assert quality["IC_Last_Year"] == measured["IC_Last_Year"]
    assert quality["ROIC_Median"] == measured["ROIC_Median"]
    assert quality["ROIC_Last"] == measured["ROIC_Last"]
    assert quality["ROIC_n"] == measured["n"]
    assert quality["ROIC_Source"] == measured["Source"]
    assert quality["ROIC_Excluded_Small_IC"] == measured["Excluded_Small_IC"]

def test_block_failure_is_isolated(monkeypatch):
    monkeypatch.setattr(serialize, "plausible_ceiling", raise_value_error)
    out = serialize_company("apple", START_YEAR, YEARS, FREQ, N_MONTHS, as_of = AS_OF)

    assert out["Status"] == "calculated"
    assert out["Blocks_Failed"] == ["Ceiling"]
    assert out["Ceiling"] is None
    for name in FAILED_BLOCKS:
        if name == "Ceiling":
            continue
        assert out[name] is not None
