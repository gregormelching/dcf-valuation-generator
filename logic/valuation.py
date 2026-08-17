from model import project_fcf, TERMINAL_GROWTH, roic
from datetime import datetime
from wacc_calculation import calc_wacc, N_MONTHS
from database import get_data

def terminal_value(fcf: dict, wacc: float, method: str, exit_multiple: float):
    last_explicit = sorted(fcf)[-2]
    tv_row = sorted(fcf)[-1]
    
    if wacc <= TERMINAL_GROWTH: raise ValueError("WACC must be greater than Terminal Growth.")

    gordon_tv = fcf[tv_row]["FCF"] / (wacc - TERMINAL_GROWTH)
    ebitda = fcf[last_explicit]["EBIT"] + fcf[last_explicit]["D&A"]
    
    if method == "gordon":
        tv = gordon_tv
        source = {"Terminal_Growth": TERMINAL_GROWTH}
    elif method == "multiple":
        if exit_multiple is None: raise ValueError("Exit Multiple must be provided.")
        tv = ebitda * exit_multiple
        source = {"Multiple": exit_multiple}
    else: raise ValueError("Invalid method.")
    
    return {"Terminal_Value": tv, "Implied_Multiple": gordon_tv / ebitda, "Method": method, "Source": source}
    

def dcf_value(symbol: str, start_year: int, years: int, freq: str, n: int, base: str = "Growth_Rate_Median", method: str = "gordon", exit_multiple: float | None = None, as_of: str | None = None, terminal_roic: float | None = None, margin_base: str = "Driver_Ratio") -> dict:
    value = {}
    if as_of is None: as_of = datetime.now()
    else: as_of = datetime.strptime(as_of, "%Y-%m-%d")
    data = get_data(symbol, start_year)
    wacc_calc = calc_wacc(data, symbol, freq, n)
    wacc = wacc_calc["WACC"]
    wacc_low = wacc_calc["WACC_Low"]
    wacc_high = wacc_calc["WACC_High"]
    waccs = [("wacc_low", wacc_low), ("wacc", wacc), ("wacc_high", wacc_high)]
    wacc_source = wacc_calc["Source"]
    last_year = max(data)
    fye = datetime.strptime(data[last_year]["Revenue"]["End"], "%Y-%m-%d")
    stub = (as_of - fye).days / 365.25
            
    for w in waccs:
        t_roic = terminal_roic
        roic_source = "Assumption"
        if terminal_roic is None: 
            t_roic = w[1]
            roic_source = "WACC"
        fcf = project_fcf(data, years, t_roic, base, margin_base)
        PV_Explicit = 0
        
        for i, row in enumerate(sorted(fcf)[:-1], start = 1):
            d_factor = (1 + w[1]) ** (i - 0.5)
            d_fcf = fcf[row]["FCF"] / d_factor
            PV_Explicit += d_fcf
        tv = terminal_value(fcf, w[1], method, exit_multiple)
        PV_tv = tv["Terminal_Value"] / ((1 + w[1]) ** (years - 0.5))
        tv_share = PV_tv / (PV_Explicit + PV_tv)
        ev = (PV_Explicit + PV_tv) * ((1 + w[1]) ** stub)
        if data[last_year]["Debt"]["Value"] in (0, None) or data[last_year]["Cash"]["Value"] in (0, None) or data[last_year]["SharesOutstanding"]["Value"] in (0, None): raise ValueError("Debt, Cash and SharesOutstanding can't equal zero or None.")
        equity = ev - data[last_year]["Debt"]["Value"] + data[last_year]["Cash"]["Value"]
        value_per_share = equity / data[last_year]["SharesOutstanding"]["Value"]
        
        value[w[0]] = {"EV": ev, "Equity_Value": equity, "Value_Per_Share": value_per_share, "PV_Explicit": PV_Explicit, "PV_TV": PV_tv, "WACC": w[1], "TV_Share": tv_share, "Implied_Multiple": tv["Implied_Multiple"], "Source": f"{wacc_source}+{base}+{method}", "Stub_Years": stub, "As_Of": datetime.strftime(as_of, "%Y-%m-%d"), "Terminal_ROIC": t_roic, "ROIC_Source": roic_source, "Margin_Base": margin_base, "EBIT_Margin_Target": fcf[max(fcf)]["EBIT_Margin"]}
        
    return value

if __name__ == "__main__": 
    print(dcf_value("apple", 2016, 10, "1mo", N_MONTHS, "Growth_Rate_Median", "gordon", terminal_roic = 0.20))