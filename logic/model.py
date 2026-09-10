from pathlib import Path
from database import get_data
from parser import companies
import statistics as stats
from validation import OUTLIER_RULES

TAX_WINDOW_START = 2018
MARGINAL_TAX_RATE = 0.25
MIN_YEARS = 3
COMPARATOR_WINDOW = 3
MIN_IC_REVENUE_SHARE = 0.05
TERMINAL_GROWTH = 0.025
    
def flags_clean(data: dict, year: int, metric: str) -> bool:
    if data[year][metric]["Value"] is None: return False
    flags = [flag for flag in data[year][metric]["Flag"]]
    if OUTLIER_RULES[metric][0] == "yoy" and "outlier" in flags: flags.remove("outlier")
    return len(flags) == 0

def effective_tax_rate(data):
    value = {"Effective_Tax_Rate": 0, "n": 0, "Source": ""}
    rates = []
    for year in data:
        if year < TAX_WINDOW_START: continue
        if not flags_clean(data, year, "Tax") or not flags_clean(data, year, "PretaxIncome"):
            continue
        if data[year]["PretaxIncome"]["Value"] == 0: continue
        tax_rate = data[year]["Tax"]["Value"] / data[year]["PretaxIncome"]["Value"]
        rates.append(tax_rate)
    if len(rates) < MIN_YEARS: 
        value.update({"Effective_Tax_Rate": MARGINAL_TAX_RATE, "n": len(rates), "Source": "Fallback"})
    else:
        median = round(stats.median(rates), 4)
        value.update({"Effective_Tax_Rate": median, "n": len(rates), "Source": "Median"})
    return value

def driver_ratio(data, metric):
    value = {"Driver_Ratio": 0, "n": 0, "Source": "", "Mean_Last_Three": 0, "Mean_Last_Three_Source": "", "Mean_Last_Three_Years": [], "Years": []}
    ratios = []
    clean = []
    for year in sorted(data):
        if data[year]["Revenue"]["Value"] in (0, None): continue
        if not flags_clean(data, year, metric): continue

        d_ratio = data[year][metric]["Value"] / data[year]["Revenue"]["Value"]
        clean.append(year)
        ratios.append(d_ratio)

    if len(ratios) >= MIN_YEARS:
        median = round(stats.median(ratios), 4)
        window = clean[-COMPARATOR_WINDOW:]
        if window[-1] - window[0] == COMPARATOR_WINDOW - 1:
            mean = round(stats.mean(ratios[-COMPARATOR_WINDOW:]), 4)
            mean_source = "Calculated"
        else:
            mean = None
            mean_source = "Not_Contiguous"
            window = []
        value.update({"Driver_Ratio": median, "n": len(ratios), "Source": "Median", "Mean_Last_Three": mean, "Mean_Last_Three_Source": mean_source, "Mean_Last_Three_Years": window, "Years": clean})
    else:
        median = None
        value.update({"Driver_Ratio": median, "n": len(ratios), "Source": "Insufficient", "Mean_Last_Three": None, "Mean_Last_Three_Source": "Insufficient", "Mean_Last_Three_Years": [], "Years": clean})
    return value

def rolling_means(pairs, k):
    if k < 1: raise ValueError(f"Window must be at least 1, got {k}.")
    value = []
    pairs = sorted(pairs)
    for i in range(len(pairs) - k + 1):
        w = pairs[i:i+k]
        if w[-1][0] - w[0][0] != k - 1: continue
        value.append(stats.mean([v for _, v in w]))
    return value

def growth_rate(data: dict) -> dict:
    value = {"Growth_Rate_Median": 0, "Growth_Rate_Mean": 0, "Mean_Last_Three": 0, "Mean_Last_Three_Source": "", "Mean_Last_Three_Years": [], "n": 0, "Source": "", "Rates": [], "Years": []}
    years = sorted(data)
    growth_rates = []
    clean = []
    for year in years:
        if year + 1 not in data: continue
        flags = [flag for flag in data[year]["Revenue"]["Flag"] if flag != "outlier"]
        flags_next = [flag for flag in data[year+1]["Revenue"]["Flag"] if flag != "outlier"]
        if len(flags) != 0 or len(flags_next) != 0: continue
        if data[year]["Revenue"]["Value"] in (0, None) or data[year+1]["Revenue"]["Value"] in (0, None): continue
        yoy_growth = (data[year+1]["Revenue"]["Value"] - data[year]["Revenue"]["Value"]) / data[year]["Revenue"]["Value"]
        growth_rates.append(yoy_growth)
        clean.append(year)
    if len (growth_rates) >= MIN_YEARS:
        median = round(stats.median(growth_rates), 4)
        mean = round(stats.mean(growth_rates), 4)
        window = clean[-COMPARATOR_WINDOW:]
        if window[-1] - window[0] == COMPARATOR_WINDOW - 1:
            mean_last_three = round(stats.mean(growth_rates[-COMPARATOR_WINDOW:]), 4)
            mean_source = "Calculated"
        else:
            mean_last_three = None
            mean_source = "Not_Contiguous"
            window = []
        value.update({"Growth_Rate_Median": median, "Growth_Rate_Mean": mean, "Mean_Last_Three": mean_last_three, "Mean_Last_Three_Source": mean_source, "Mean_Last_Three_Years": window, "n": len(growth_rates), "Source": "Calculated", "Rates": growth_rates, "Years": clean})
    else: value.update({"Growth_Rate_Median": None, "Growth_Rate_Mean": None, "Mean_Last_Three": None, "Mean_Last_Three_Source": "Insufficient", "Mean_Last_Three_Years": [], "n": len(growth_rates), "Source": "Insufficient", "Rates": growth_rates, "Years": clean})
    return value
  
def project_revenue(data: dict, years: int, base: str = "Growth_Rate_Median", terminal_growth: float = TERMINAL_GROWTH, revenue_growth: float | None = None) -> dict:
    if years < 1: raise ValueError(f"Years must be at least 1, got {years}.")
    last_year = sorted(data)[-1]
    projected_years = range(last_year + 1, last_year + 1 + years)
    value = {year: {"Growth_Rate": 0, "Revenue": 0} for year in projected_years}
    growth_rates = growth_rate(data)
    if revenue_growth is None:
        if base not in ["Growth_Rate_Median", "Mean_Last_Three", "Growth_Rate_Mean"]: raise ValueError(f"Unknown base: {base}")
        if growth_rates[base] is not None: growth = growth_rates[base]
        else: raise ValueError(f"{base} is not defined")
    else:
        growth = revenue_growth
        base = "Override"
        if type(growth) not in (int, float): raise ValueError("Growth is not an integer or float.")
    rev = data[sorted(data)[-1]]["Revenue"]["Value"]
    i = 0
    
    for year in projected_years:
        i += 1
        g_t = round(growth + (terminal_growth - growth) * i/len(projected_years), 4)
        rev *= (1 + g_t)
        value[year].update({"Growth_Rate": g_t, "Growth_Rate_Base": growth, "Revenue": rev, "Source": base})
    
    return value

def project_fcf(data: dict, years: int, terminal_roic: float, base: str = "Growth_Rate_Median", margin_base: str = "Driver_Ratio", metrics: dict = None, terminal_growth: float = TERMINAL_GROWTH, nwc_intensity: float | None = None, ebit_margin: float | None = None, revenue_growth: float | None = None) -> dict:
    if years < 1: raise ValueError(f"Years must be at least 1, got {years}.")
    last_year = sorted(data)[-1]
    if metrics is None: metrics = {}
    keys = metrics.keys()
    
    projected_years = range(last_year + 1, last_year + 1 + years)
    value = {year: {"Revenue": 0, "EBIT": 0, "NOPAT": 0, "D&A": 0, "CapEx": 0, "dNWC": 0, "FCF": 0, "EBIT_Margin": "", "Reinvestment": 0, "Reinvestment_Rate": 0, "Terminal_ROIC": 0, "Tax_Rate": 0} for year in range(last_year + 1, last_year + 2 + years)}
    unknown_keys = [key for key in keys if key not in ["D&A", "NWC", "CapEx"]]
    if unknown_keys: raise ValueError(f"Unknown metric: {unknown_keys}")
    unknown_values = [metrics[key] for key in keys if metrics[key] not in ["Driver_Ratio", "Mean_Last_Three"]]
    if unknown_values: raise ValueError(f"Unknown metric base: {unknown_values}")
    if margin_base not in ["Driver_Ratio", "Mean_Last_Three", "Last"]: raise ValueError(f"Unknown margin_base: {margin_base}")
    
    last_OI = data[last_year]["OperatingIncome"]
    last_REV = data[last_year]["Revenue"]
    
    if last_OI["Value"] is None: raise ValueError(f"Operating Income from {last_year} is None.")
    if last_REV["Value"] in (0, None): raise ValueError(f"Revenue from {last_year} is None or 0.")
    
    LAST_EBIT_MARGIN = last_OI["Value"] / last_REV["Value"]
    if margin_base == "Last": EBIT_MARGIN = LAST_EBIT_MARGIN
    else:  EBIT_MARGIN = driver_ratio(data, "OperatingIncome")[margin_base]
    
    if len(last_OI["Flag"]) == 0: MARGIN_START_SOURCE = "Last_Actual"
    else: MARGIN_START_SOURCE = "Last_Actual_Flagged"
    
    if ebit_margin is not None:
        if not isinstance(ebit_margin, (float, int)): raise ValueError(f"Ebit Margin must be a number or float")
        EBIT_MARGIN = ebit_margin
        margin_base = "Override"
    
    default = "Driver_Ratio"
    if "D&A" in keys: da_str = metrics.get("D&A") 
    else: da_str = default
    if "CapEx" in keys: cap_ex_str = metrics.get("CapEx") 
    else: cap_ex_str = default
    if "NWC" in keys: nwc_str = metrics.get("NWC") 
    else: nwc_str = default

    D_AND_A_MARGIN = driver_ratio(data, "D&A")[da_str]
    CAP_EX_MARGIN = driver_ratio(data, "CapEx")[cap_ex_str]
    NWC_INTENSITY = driver_ratio(data, "NWC")[nwc_str]
    if nwc_intensity is not None:
        if not isinstance(nwc_intensity, (int, float)): raise ValueError(f"Invalid type for NWC intensity: {type(nwc_intensity)}")
        NWC_INTENSITY = nwc_intensity
        nwc_str = "Override"
            
    if terminal_roic <= terminal_growth: raise ValueError("Terminal ROIC must be greater than terminal growth")
    t = effective_tax_rate(data)["Effective_Tax_Rate"]
    if None in [EBIT_MARGIN, D_AND_A_MARGIN, CAP_EX_MARGIN, NWC_INTENSITY]: raise ValueError("Missing data for EBIT, D&A, CapEx, or Working Capital")
    rev = project_revenue(data, years, base, terminal_growth, revenue_growth)
    i = 0
    prev_rev = data[last_year]["Revenue"]["Value"]
    reinvestment_rate = terminal_growth / terminal_roic
    acc_net_reinvest = 0        
        
    for year in projected_years:
        i += 1
        m_t = LAST_EBIT_MARGIN + (EBIT_MARGIN - LAST_EBIT_MARGIN) * i / len(projected_years)
        t_t = t + (MARGINAL_TAX_RATE - t) * i / len(projected_years)
        cur_rev = rev[year]["Revenue"]
        ebit = cur_rev * m_t
        nopat = ebit * (1 - t_t)
        da = cur_rev * D_AND_A_MARGIN
        capex = cur_rev * CAP_EX_MARGIN
        dnwc = (cur_rev - prev_rev) * NWC_INTENSITY
        net_reinvest_1 = capex + dnwc - da
        net_reinvest_2 = reinvestment_rate * nopat
        w = i / len(projected_years)
        net_reinvest = net_reinvest_1 * (1 - w) + net_reinvest_2 * w
        acc_net_reinvest += net_reinvest
        fcf = nopat - net_reinvest
        rrate = net_reinvest / nopat if nopat != 0 else None
        value[year].update({"Revenue": cur_rev, "EBIT": ebit, "NOPAT": nopat, "D&A": da, "CapEx": capex, "dNWC": dnwc, "FCF": fcf, "EBIT_Margin": m_t, "Tax_Rate": t_t, "Margin_Base": margin_base, "Margin_Start": LAST_EBIT_MARGIN, "Margin_Start_Year": last_year, "Margin_Start_Source": MARGIN_START_SOURCE, "Metrics": da_str+"+"+cap_ex_str+"+"+nwc_str, "Reinvestment": net_reinvest, "Reinvestment_Rate": rrate, "Growth_Rate_Source": rev[year]["Source"], "DA_Margin": D_AND_A_MARGIN, "CapEx_Margin": CAP_EX_MARGIN, "NWC_Intensity": NWC_INTENSITY, "Revenue_Growth": rev[year]["Growth_Rate_Base"]})
        prev_rev = cur_rev
        
        if i == years:
            r = roic(data)["IC_Last"]
            cap_basis = r + acc_net_reinvest if r is not None else None
            cur_rev = rev[year]["Revenue"] * (1 + terminal_growth)
            ebit = cur_rev * EBIT_MARGIN
            nopat = ebit * (1- MARGINAL_TAX_RATE)
            implicit_roic = nopat / cap_basis if cap_basis is not None else None
            cap_turnover = cur_rev / cap_basis if cap_basis is not None else None
            da = None
            capex = None
            dnwc = None
            reinvestment = nopat * reinvestment_rate
            fcf = nopat - reinvestment
            value[year+1].update({"Revenue": cur_rev, "EBIT": ebit, "NOPAT": nopat, "D&A": da, "CapEx": capex, "dNWC": dnwc, "FCF": fcf, "Flag": "TV", "EBIT_Margin": EBIT_MARGIN, "Reinvestment": reinvestment, "Reinvestment_Rate": reinvestment_rate, "Terminal_ROIC": terminal_roic, "Tax_Rate": MARGINAL_TAX_RATE, "Margin_Base": margin_base, "Margin_Start": LAST_EBIT_MARGIN, "Margin_Start_Year": last_year, "Margin_Start_Source": MARGIN_START_SOURCE, "Implicit_ROIC": implicit_roic, "Capital_Turnover": cap_turnover})
        
    return value
    
def roic(data: dict) -> dict:
    value = {"ROIC_Median": 0, "ROIC_Last": 0, "IC_Last": 0, "IC_Last_Year": None, "n": 0, "Source": "", "Years": [], "Excluded_Small_IC": 0}
    ic = {}
    nopat = {}
    t = effective_tax_rate(data)["Effective_Tax_Rate"]
    roics = []
    clean = []
    excluded = 0

    for year in sorted(data):
        if all(flags_clean(data, year, m) for m in ["Debt", "Cash", "Equity"]):
            ic[year] = data[year]["Debt"]["Value"] + data[year]["Equity"]["Value"] - data[year]["Cash"]["Value"]
        if flags_clean(data, year, "OperatingIncome"):
            nopat[year] = data[year]["OperatingIncome"]["Value"] * (1 - t)

    for year in sorted(nopat):
        if year-1 not in ic or ic[year-1] <= 0: continue
        rev = data[year-1]["Revenue"]["Value"]
        if rev in (0, None) or ic[year-1] / rev < MIN_IC_REVENUE_SHARE:
            excluded += 1
            continue
        roics.append(nopat[year] / ic[year-1])
        clean.append(year)
    if len(roics) >= MIN_YEARS:
        median = stats.median(roics)
        last = roics[-1]
        source = "Median"
    else:
        median = None
        last = None
        source = "Insufficient"

    ic_last_year = max(ic) if ic else None
    value.update({"ROIC_Median": median, "ROIC_Last": last, "IC_Last": ic.get(ic_last_year), "IC_Last_Year": ic_last_year, "n": len(roics), "Source": source, "Years": clean, "Excluded_Small_IC": excluded})
    return value

if __name__ == "__main__":
    data = get_data("microsoft", 2016)
