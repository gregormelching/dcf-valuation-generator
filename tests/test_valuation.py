import pytest
from database import get_data
from model import project_fcf
from valuation import terminal_value, resolve_assumptions, TERMINAL_GROWTH
from wacc_calculation import calc_wacc, N_MONTHS

def val_dct(fcf, ebit, da):
    return {"FCF": fcf, "EBIT": ebit, "D&A": da}

SYMBOL = "apple"
AS_OF = "2026-08-19"
START_YEAR = 2016
YEARS = 10
FREQ = "1mo"
REL = 1e-9
FCF_ROWS = {
    2031: val_dct(110.0, 0.0, 0.0),
    2030: val_dct(90.0, 100.0, 25.0),
    2029: val_dct(1.0, 999.0, 999.0),
}
WACC = 0.10
GROWTH = 0.02

@pytest.fixture(scope = "module")
def real_fcf():
    data = get_data(SYMBOL, START_YEAR, AS_OF)
    wacc = calc_wacc(data, SYMBOL, FREQ, N_MONTHS, as_of = AS_OF)["WACC"]
    settings = resolve_assumptions(SYMBOL, terminal_growth = TERMINAL_GROWTH)
    fcf = project_fcf(data, YEARS, settings["terminal_roic"], settings["base"], settings["margin_base"], settings["metrics"], TERMINAL_GROWTH, None)
    
    return wacc, fcf

def test_tv_gordon():
    tv = terminal_value(FCF_ROWS, WACC, "gordon", None, GROWTH)
    
    assert tv["Terminal_Value"] == pytest.approx(1375.0, rel = REL)
    assert tv["Implied_Multiple"] == pytest.approx(11.0, rel = REL)
    assert tv["Source"] == {"Terminal_Growth": GROWTH}
    assert tv["Method"] == "gordon"
    assert tv["Implied_Multiple_Source"] == "Calculated"
    
def test_tv_multiple():
    tv = terminal_value(FCF_ROWS, WACC, "multiple", 8.0, GROWTH)
    
    assert tv["Terminal_Value"] == pytest.approx(1000.0, rel = REL)
    assert tv["Implied_Multiple"] == pytest.approx(11.0, rel = REL)
    assert tv["Source"] == {"Multiple": 8.0}
    assert tv["Method"] == "multiple"
    assert tv["Implied_Multiple_Source"] == "Calculated"
    
@pytest.mark.parametrize("wacc, method, exit_multiple, growth, message", [
    (0.02,  "gordon",   None, 0.025,  "WACC must be greater than Terminal Growth"),
    (0.025, "gordon",   None, 0.025,  "WACC must be greater than Terminal Growth"),
    (WACC,  "multiple", None, GROWTH, "Exit Multiple must be provided"),
    (WACC,  "exit",     8.0,  GROWTH, "Invalid method"),
])
def test_tv_raises(wacc, method, exit_multiple, growth, message):
    with pytest.raises(ValueError, match = message):
        terminal_value(FCF_ROWS, wacc, method, exit_multiple, growth)

@pytest.mark.parametrize("wacc, method, exit_multiple, growth, terminal", [
    (WACC, "gordon", None, GROWTH, 1375.0),
    (WACC, "multiple", 8.0, GROWTH, 0.0),
])
def test_ebitda_zero(wacc, method, exit_multiple, growth, terminal):
    fcf_alt = {2031: val_dct(110.0, 999.0, 999.0), 2030: val_dct(90.0, 0.0, 0.0)}
    tv = terminal_value(fcf_alt, wacc, method, exit_multiple, growth)

    assert tv["Terminal_Value"] == pytest.approx(terminal, rel = REL)
    assert tv["Implied_Multiple"] == None
    assert tv["Implied_Multiple_Source"] == "EBITDA <= 0"
    
def test_ebitda_neg():
    fcf_alt = {2031: val_dct(110.0, 999.0, 999.0), 2030: val_dct(90.0, -200.0, 25.0)}
    tv = terminal_value(fcf_alt, WACC, "gordon", None, GROWTH)

    assert tv["Terminal_Value"] == pytest.approx(1375.0, rel = REL)
    assert tv["Implied_Multiple"] == None
    assert tv["Implied_Multiple_Source"] == "EBITDA <= 0"

def test_real_fcf(real_fcf):
    wacc, fcf = real_fcf
    tv = terminal_value(fcf, wacc, "gordon", None, TERMINAL_GROWTH)
    
    assert sorted(fcf) == list(range(2026, 2037))
    assert tv["Terminal_Value"] == pytest.approx(2011707660197.802, rel = REL)
    assert tv["Implied_Multiple"] == pytest.approx(9.41545108964314, rel = REL)
    assert tv["Implied_Multiple_Source"] == "Calculated"
