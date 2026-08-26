from model import project_fcf, TERMINAL_GROWTH, driver_ratio
from datetime import datetime
from wacc_calculation import calc_wacc, N_MONTHS
from database import get_data, get_prices
import random

ASSUMPTIONS = {
    "apple": {
        "base": "Growth_Rate_Median",
        "terminal_roic": 0.2,
        "margin_base": "Mean_Last_Three",
        "metrics": {"D&A": "Mean_Last_Three","CapEx": "Mean_Last_Three", "NWC": "Mean_Last_Three"}
    },
    "procter_gamble": {
        "base": "Growth_Rate_Median",
        "terminal_roic": 0.2,
        "margin_base": "Mean_Last_Three",
        "metrics": {"D&A": "Mean_Last_Three","CapEx": "Mean_Last_Three", "NWC": "Mean_Last_Three"}
    },
    "tesla": {
        "base": "Mean_Last_Three",
        "terminal_roic": 0.12,
        "margin_base": "Last",
        "metrics": None
    },
    "boeing": {
        "base": "Mean_Last_Three",
        "terminal_roic": 0.15,
        "margin_base": "Last",
        "metrics": {"CapEx": "Mean_Last_Three"}
    },
    "microsoft": {
        "base": "Growth_Rate_Median",
        "terminal_roic": 0.2,
        "margin_base": "Mean_Last_Three",
        "metrics": {"CapEx": "Mean_Last_Three"}
    },
}

WACC_OFFSETS = (-0.02, -0.01, 0.0, 0.01, 0.02)
TERMINAL_GROWTHS = (0.015, 0.02, 0.025, 0.03, 0.035)
NWC_INTENSITIES = (0.0282, 0.1686, 0.2092, 0.2211, 0.4368)
MARGIN_BASES = ("Driver_Ratio", "Mean_Last_Three", "Last")
MARKET_PRICE_FREQ = "1wk"
MC_DRAWS = 2000
MC_SEED = 12345
MC_Z = 1.96
MC_PERCENTILES = (0.05, 0.25, 0.5, 0.75, 0.95)
MC_BORDERS = (min(TERMINAL_GROWTHS), TERMINAL_GROWTH, max(TERMINAL_GROWTHS))

def resolve_assumptions(symbol: str, base: str | None = None, terminal_roic: float | None = None, margin_base: str | None = None, metrics: dict | None = None, terminal_growth: float = TERMINAL_GROWTH) -> dict:
    if symbol not in ASSUMPTIONS: raise ValueError(f"Symbol {symbol} is not in ASSUMPTIONS.")
    
    settings = dict(ASSUMPTIONS[symbol])
    
    for k, v in [("base", base), ("terminal_roic", terminal_roic), ("margin_base", margin_base), ("metrics", metrics)]:
        if v is None: continue
        settings[k] = v
    
    settings["metrics"] = dict(settings["metrics"]) if settings["metrics"] is not None else None
    
    if settings["base"] not in ["Growth_Rate_Median", "Growth_Rate_Mean", "Mean_Last_Three"]: raise ValueError(f"{settings["base"]} not found in valid bases.")
    if settings["margin_base"] not in ["Driver_Ratio", "Mean_Last_Three", "Last"]: raise ValueError(f"{settings["margin_base"]} not found in valid margin bases.")
    if not isinstance(settings["terminal_roic"], (int, float)) or settings["terminal_roic"] <= terminal_growth: raise ValueError(f"Terminal ROIC {settings["terminal_roic"]} is not valid.")
    if settings["metrics"] is not None and any(key not in ["D&A", "CapEx", "NWC"] for key in settings["metrics"]): raise ValueError(f"Invalid metric key in {sorted(settings["metrics"])}.")
    if settings["metrics"] is not None and any(value not in ["Driver_Ratio", "Mean_Last_Three"] for value in settings["metrics"].values()): raise ValueError(f"Invalid metric value in {sorted(settings["metrics"].values())}.")

    return settings

def terminal_value(fcf: dict, wacc: float, method: str, exit_multiple: float, terminal_growth: float = TERMINAL_GROWTH):
    last_explicit = sorted(fcf)[-2]
    tv_row = sorted(fcf)[-1]
    
    if wacc <= terminal_growth: raise ValueError("WACC must be greater than Terminal Growth.")

    gordon_tv = fcf[tv_row]["FCF"] / (wacc - terminal_growth)
    ebitda = fcf[last_explicit]["EBIT"] + fcf[last_explicit]["D&A"]
    
    if method == "gordon":
        tv = gordon_tv
        source = {"Terminal_Growth": terminal_growth}
    elif method == "multiple":
        if exit_multiple is None: raise ValueError("Exit Multiple must be provided.")
        tv = ebitda * exit_multiple
        source = {"Multiple": exit_multiple}
    else: raise ValueError("Invalid method.")
    
    return {"Terminal_Value": tv, "Implied_Multiple": gordon_tv / ebitda, "Method": method, "Source": source}
    

def dcf_value(symbol: str, start_year: int, years: int, freq: str, n: int, base: str = None, method: str = "gordon", exit_multiple: float | None = None, as_of: str | None = None, terminal_roic: float | None = None, margin_base: str | None = None, metrics: dict | None = None, terminal_growth: float = TERMINAL_GROWTH, wacc_offset: float = 0.0, nwc_intensity: float | None = None, ebit_margin: float | None = None) -> dict:
    settings = resolve_assumptions(symbol, base, terminal_roic, margin_base, metrics, terminal_growth)
    base = settings["base"]
    terminal_roic = settings["terminal_roic"]
    margin_base = settings["margin_base"]
    metrics = settings["metrics"]
    value = {}
    as_of_str = as_of
    if as_of is None: as_of = datetime.now()
    else: as_of = datetime.strptime(as_of, "%Y-%m-%d")
    
    data = get_data(symbol, start_year)
    wacc_calc = calc_wacc(data, symbol, freq, n, as_of = as_of_str)
    wacc = wacc_calc["WACC"] + wacc_offset
    wacc_low = wacc_calc["WACC_Low"] + wacc_offset
    wacc_high = wacc_calc["WACC_High"] + wacc_offset
    waccs = [("wacc_low", wacc_low), ("wacc", wacc), ("wacc_high", wacc_high)]
    wacc_source = wacc_calc["Source"]
    last_year = max(data)
    fye = datetime.strptime(data[last_year]["Revenue"]["End"], "%Y-%m-%d")
    stub = (as_of - fye).days / 365.25
    filed = [data[year][metric_name]["Filed"] for year in data for metric_name in data[year] if data[year][metric_name]["Filed"] is not None]
    data_filed = max(filed) if filed else None
    as_of_key = datetime.strftime(as_of, "%Y-%m-%d")
    price_date, market_price = get_prices(symbol, MARKET_PRICE_FREQ, 1, as_of_key)[-1]
    price_age = (as_of - datetime.strptime(price_date, "%Y-%m-%d")).days
            
    for w in waccs:
        t_roic = terminal_roic
        roic_source = "Assumption"
        if terminal_roic is None: 
            t_roic = w[1]
            roic_source = "WACC"
        fcf = project_fcf(data, years, t_roic, base, margin_base, metrics, terminal_growth, nwc_intensity, ebit_margin = ebit_margin)
        PV_Explicit = 0
        
        for i, row in enumerate(sorted(fcf)[:-1], start = 1):
            d_factor = (1 + w[1]) ** (i - 0.5)
            d_fcf = fcf[row]["FCF"] / d_factor
            PV_Explicit += d_fcf
        tv = terminal_value(fcf, w[1], method, exit_multiple, terminal_growth)
        PV_tv = tv["Terminal_Value"] / ((1 + w[1]) ** (years - 0.5))
        ev = (PV_Explicit + PV_tv) * ((1 + w[1]) ** stub)
        if data[last_year]["Debt"]["Value"] in (0, None) or data[last_year]["Cash"]["Value"] in (0, None) or data[last_year]["SharesOutstanding"]["Value"] in (0, None): raise ValueError("Debt, Cash and SharesOutstanding can't equal zero or None.")
        equity = ev - data[last_year]["Debt"]["Value"] + data[last_year]["Cash"]["Value"]
        value_per_share = equity / data[last_year]["SharesOutstanding"]["Value"]
        
        tv_share = None
        tv_share_source = "Calculated"
        
        if PV_Explicit > 0 and PV_tv > 0: 
            tv_share = PV_tv / (PV_Explicit + PV_tv)
        else: tv_share_source = " and ".join([name for name, pv in [("PV_Explicit", PV_Explicit), ("PV_tv", PV_tv)] if pv <= 0]) + " <= 0"

        value[w[0]] = {"EV": ev, "Equity_Value": equity, "Value_Per_Share": value_per_share, "PV_Explicit": PV_Explicit, "PV_TV": PV_tv, "WACC": w[1], "Implied_Multiple": tv["Implied_Multiple"], "Source": f"{wacc_source}+{base}+{method}", "Stub_Years": stub, "As_Of": datetime.strftime(as_of, "%Y-%m-%d"), "Terminal_ROIC": t_roic, "ROIC_Source": roic_source, "Margin_Base": fcf[min(fcf)]["Margin_Base"], "EBIT_Margin_Target": fcf[max(fcf)]["EBIT_Margin"], "TV_Share_Source": tv_share_source, "Metrics": fcf[min(fcf)]["Metrics"], "TV_Share": tv_share, "Data_Filed": data_filed, "Terminal_Growth": terminal_growth, "WACC_Offset": wacc_offset, "Market_Price": market_price, "Price_Date": price_date, "Price_Age_Days": price_age, "Upside": value_per_share / market_price - 1, "NWC_Intensity": nwc_intensity, "RF_Date": wacc_calc["RF_Date"]}
        
    return value

def sensitivity_grid(symbol: str, start_year: int, years: int, freq: str, n: int, as_of: str | None = None, offset: tuple = WACC_OFFSETS, growths: tuple = TERMINAL_GROWTHS):
    grid = {}
    
    for o in offset:
        for g in growths:
            try: 
                dcf = dcf_value(symbol, start_year, years, freq, n, as_of = as_of, terminal_growth = g, wacc_offset = o)
                dct = {
                    "Value_Per_Share": dcf["wacc"]["Value_Per_Share"],
                    "Implied_Multiple": dcf["wacc"]["Implied_Multiple"],
                    "TV_Share": dcf["wacc"]["TV_Share"],
                    "WACC": dcf["wacc"]["WACC"],
                    "Terminal_Growth": g,
                    "Offset": o,
                    "Status": "calculated"
                }
            except ValueError as e:
                dct = {
                    "Value_Per_Share": None,
                    "Implied_Multiple": None,
                    "TV_Share": None,
                    "WACC": None,
                    "Terminal_Growth": g,
                    "Offset": o,
                    "Status": str(e)
                }
            grid[(o, g)] = dct
    
    return grid

def sensitivity_table(symbol: str, start_year: int, years: int, freq: str, n: int, as_of: str | None = None, margin_bases: tuple = MARGIN_BASES):
    table = {}
    
    for mb in margin_bases:
        is_base = mb == ASSUMPTIONS[symbol]["margin_base"]
        try:
            dcf = dcf_value(symbol, start_year, years, freq, n, as_of = as_of, margin_base = mb)
            wacc = dcf["wacc"]
            dct = {
                "Value_Per_Share": wacc["Value_Per_Share"],
                "EBIT_Margin_Target": wacc["EBIT_Margin_Target"],
                "Implied_Multiple": wacc["Implied_Multiple"],
                "TV_Share": wacc["TV_Share"],
                "TV_Share_Source": wacc["TV_Share_Source"],
                "Market_Price": wacc["Market_Price"],
                "Upside": wacc["Upside"],
                "WACC": wacc["WACC"],
                "Margin_Base": mb,
                "Is_Base": is_base,
                "Status": "calculated"
            }
        except ValueError as e:
            dct = {
                "Value_Per_Share": None,
                "EBIT_Margin_Target": None,
                "Implied_Multiple": None,
                "TV_Share": None,
                "TV_Share_Source": None,
                "Market_Price": None,
                "Upside": None,
                "WACC": None,
                "Margin_Base": mb,
                "Is_Base": is_base,
                "Status": str(e)
            }
        table[mb] = dct
    return table

def nwc_scenario(symbol: str, start_year: int, years: int, freq: str, n: int, as_of: str | None = None, nwc_intensities: tuple = NWC_INTENSITIES):
    table = {}
    
    metrics = ASSUMPTIONS[symbol]["metrics"]
    nwc_str = metrics["NWC"] if metrics is not None and "NWC" in metrics else "Driver_Ratio"
    
    d  = driver_ratio(get_data(symbol, start_year), "NWC")[nwc_str]    
    for i in nwc_intensities:
        is_intensity = abs(i - d) < 1e-9
        try:
            dcf = dcf_value(symbol, start_year, years, freq, n, as_of = as_of, nwc_intensity = i)
            wacc = dcf["wacc"]
            dct = {
                "Value_Per_Share": wacc["Value_Per_Share"],
                "EBIT_Margin_Target": wacc["EBIT_Margin_Target"],
                "Implied_Multiple": wacc["Implied_Multiple"],
                "TV_Share": wacc["TV_Share"],
                "TV_Share_Source": wacc["TV_Share_Source"],
                "Market_Price": wacc["Market_Price"],
                "Upside": wacc["Upside"],
                "WACC": wacc["WACC"],
                "NWC_Intensity": i,
                "Is_Base": is_intensity,
                "Status": "calculated"
            }
        except ValueError as e:
            dct = {
                "Value_Per_Share": None,
                "EBIT_Margin_Target": None,
                "Implied_Multiple": None,
                "TV_Share": None,
                "TV_Share_Source": None,
                "Market_Price": None,
                "Upside": None,
                "WACC": None,
                "NWC_Intensity": i,
                "Is_Base": is_intensity,
                "Status": str(e)
            }
        table[i] = dct
    return table

def monte_carlo(symbol: str, start_year: int, years: int, freq: str, n: int, as_of: str | None = None, draws: int = MC_DRAWS, seed: int = MC_SEED):
    dcf = dcf_value(symbol, start_year, years, freq, n, as_of = as_of)
    
    vps = dcf["wacc"]["Value_Per_Share"]
    mp = dcf["wacc"]["Market_Price"]
    wacc = dcf["wacc"]["WACC"]
    wacc_low = dcf["wacc_low"]["WACC"]
    wacc_high = dcf["wacc_high"]["WACC"]
    
    sigma = (wacc_high - wacc_low) / (2 * MC_Z)
    margins = {}
    
    for mb in MARGIN_BASES:
        dcf_mb = dcf_value(symbol, start_year, years, freq, n, margin_base = mb, as_of = as_of)
        margins[mb] = dcf_mb["wacc"]["EBIT_Margin_Target"]
        
    m_low = min(margins.values())
    m_high = max(margins.values())
    m_mode = margins[ASSUMPTIONS[symbol]["margin_base"]]    
    rng = random.Random(seed)
    values = []    
    fails = {}
        
    for _ in range(draws):
        w_draw= rng.gauss(wacc, sigma)
        g = rng.triangular(MC_BORDERS[0], MC_BORDERS[2], MC_BORDERS[1])
        em = rng.triangular(m_low, m_high, m_mode)
        
        try:
            dcf_i = dcf_value(symbol, start_year, years, freq, n, as_of = as_of, terminal_growth = g, wacc_offset = w_draw - wacc, ebit_margin = em)
            values.append(dcf_i["wacc"]["Value_Per_Share"])
        except ValueError as e:
            fails[str(e)] = fails.get(str(e), 0) + 1
    
    values.sort()
    percentiles = None
    
    if values:
        percentiles = {}
        for p in MC_PERCENTILES:
            k = (len(values) - 1) * p
            f = int(k)
            c = min(f + 1, len(values) - 1)
            val = values[f] + (values[c] - values[f]) * (k - f)
            percentiles.update({p: val})
        
    mean = sum(values) / len(values) if len(values) > 0 else None
    p_above_market = sum(1 for v in values if v > mp) / len(values) if len(values) > 0 else None
    draws_ok = len(values)
    draws_failed = sum(fails.values())
    margin_range = (m_low, m_mode, m_high)
    
    return {"Percentiles": percentiles, "Mean": mean, "P_Above_Market": p_above_market, "Draws_OK": draws_ok, "Draws_Failed": draws_failed, "WACC_Sigma": sigma, "Margin_Range": margin_range, "Base_Value_Per_Share": vps, "Market_Price": mp, "WACC": wacc, "Seed": seed, "Failures": fails}

if __name__ == "__main__":
    symbol = "apple"
    print(monte_carlo(symbol, 2016, 10, "1mo", N_MONTHS, as_of = "2026-08-19"))
