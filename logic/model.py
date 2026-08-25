from pathlib import Path
from database import get_data
from parser import companies
import statistics as stats
from validation import OUTLIER_RULES

TAX_WINDOW_START = 2018
MARGINAL_TAX_RATE = 0.25
MIN_YEARS = 3
TERMINAL_GROWTH = 0.025
    
def effective_tax_rate(data):
    value = {"Effective_Tax_Rate": 0, "n": 0, "Source": ""}
    rates = []
    for year in data: 
        if year < TAX_WINDOW_START: continue
        if len(data[year]["Tax"]["Flag"]) != 0 or (data[year]["Tax"]["Value"] is None or data[year]["PretaxIncome"]["Value"] is None):
            continue
        tax_rate = data[year]["Tax"]["Value"] / data[year]["PretaxIncome"]["Value"]
        rates.append(tax_rate)
    if len(rates) < MIN_YEARS: 
        value.update({"Effective_Tax_Rate": MARGINAL_TAX_RATE, "n": len(rates), "Source": "Fallback"})
    else:
        median = round(stats.median(rates), 4)
        value.update({"Effective_Tax_Rate": median, "n": len(rates), "Source": "Median"})
    return value

def driver_ratio(data, metric):
    value = {"Driver_Ratio": 0, "n": 0, "Source": "", "Mean_Last_Three": 0, "Years": []}
    ratios = []
    clean = []
    for year in sorted(data):
        flags = [flag for flag in data[year][metric]["Flag"]]
        if data[year][metric]["Value"] is None or data[year]["Revenue"]["Value"] in (0, None): continue
        if OUTLIER_RULES[metric][0] == "yoy" and "outlier" in flags: 
            flags.remove("outlier")
        if len(flags) != 0: continue
        
        d_ratio = data[year][metric]["Value"] / data[year]["Revenue"]["Value"]
        clean.append(year)
        ratios.append(d_ratio)
        
    if len(ratios) >= MIN_YEARS: 
        median = round(stats.median(ratios), 4)
        mean = round(stats.mean(ratios[-3:]), 4)
        value.update({"Driver_Ratio": median, "n": len(ratios), "Source": "Median", "Mean_Last_Three": mean, "Years": clean}) 
    else: 
        median = None   
        value.update({"Driver_Ratio": median, "n": len(ratios), "Source": "Insufficient", "Mean_Last_Three": None, "Years": clean})
    return value

def growth_rate(data: dict) -> dict:
    value = {"Growth_Rate_Median": 0, "Growth_Rate_Mean": 0, "Mean_Last_Three": 0, "n": 0, "Source": ""}
    years = sorted(data)
    growth_rates = []
    for year in years:
        if year + 1 not in data: continue
        flags = [flag for flag in data[year]["Revenue"]["Flag"] if flag != "outlier"]
        flags_next = [flag for flag in data[year+1]["Revenue"]["Flag"] if flag != "outlier"]
        if len(flags) != 0 or len(flags_next) != 0: continue
        if data[year]["Revenue"]["Value"] in (0, None) or data[year+1]["Revenue"]["Value"] in (0, None): continue
        yoy_growth = (data[year+1]["Revenue"]["Value"] - data[year]["Revenue"]["Value"]) / data[year]["Revenue"]["Value"]
        growth_rates.append(yoy_growth)
    if len (growth_rates) >= MIN_YEARS:
        median = round(stats.median(growth_rates), 4)
        mean = round(stats.mean(growth_rates), 4)
        mean_last_three = round(stats.mean(growth_rates[-3:]), 4)
        value.update({"Growth_Rate_Median": median, "Growth_Rate_Mean": mean, "Mean_Last_Three": mean_last_three, "n": len(growth_rates), "Source": "Calculated"})
    else: value.update({"Growth_Rate_Median": None, "Growth_Rate_Mean": None, "Mean_Last_Three": None,"n": len(growth_rates), "Source": "Insufficient"})
    return value
  
def project_revenue(data: dict, years: int, base: str = "Growth_Rate_Median", terminal_growth: float = TERMINAL_GROWTH) -> dict:
    last_year = sorted(data)[-1]
    projected_years = range(last_year + 1, last_year + 1 + years)
    value = {year: {"Growth_Rate": 0, "Revenue": 0} for year in projected_years}
    growth_rates = growth_rate(data)
    if base not in ["Growth_Rate_Median", "Mean_Last_Three", "Growth_Rate_Mean"]: raise ValueError(f"Unknown base: {base}")
    if growth_rates[base] is not None: growth = growth_rates[base]
    else: raise ValueError(f"{base} is not defined")
    rev = data[sorted(data)[-1]]["Revenue"]["Value"]
    i = 0
    
    for year in projected_years:
        i += 1
        g_t = round(growth + (terminal_growth - growth) * i/len(projected_years), 4)
        rev *= (1 + g_t)
        value[year].update({"Growth_Rate": g_t, "Revenue": rev, "Source": base})
    
    return value

def project_fcf(data: dict, years: int, terminal_roic: float, base: str = "Growth_Rate_Median", margin_base: str = "Driver_Ratio", metrics: dict = None, terminal_growth: float = TERMINAL_GROWTH, nwc_intensity: float | None = None) -> dict:
    last_year = sorted(data)[-1]
    if metrics is None: metrics = {}

    keys = metrics.keys()
    projected_years = range(last_year + 1, last_year + 1 + years)
    value = {year: {"Revenue": 0, "EBIT": 0, "NOPAT": 0, "D&A": 0, "CapEx": 0, "dNWC": 0, "FCF": 0, "EBIT_Margin": "", "Reinvestment": 0, "Reinvestment_Rate": 0, "Terminal_ROIC": 0, "Tax_Rate": 0} for year in range(last_year + 1, last_year + 2 + years)}
    if any(key not in ["D&A", "NWC", "CapEx"] or metrics[key] not in ["Driver_Ratio", "Mean_Last_Three"] for key in keys): raise ValueError(f"Unkown metric: {[key for key in keys if key not in ["D&A", "NWC", "CapEx"]]}")
    if margin_base not in ["Driver_Ratio", "Mean_Last_Three", "Last"]: raise ValueError(f"Unknown margin_base: {margin_base}")
    LAST_EBIT_MARGIN = data[last_year]["OperatingIncome"]["Value"] / data[last_year]["Revenue"]["Value"]
    if margin_base == "Last": EBIT_MARGIN = LAST_EBIT_MARGIN
    else:  EBIT_MARGIN = driver_ratio(data, "OperatingIncome")[margin_base]
    
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
    rev = project_revenue(data, years, base, terminal_growth)
    i = 0
    prev_rev = data[last_year]["Revenue"]["Value"]
    
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
        fcf = nopat + da - capex - dnwc
        value[year].update({"Revenue": cur_rev, "EBIT": ebit, "NOPAT": nopat, "D&A": da, "CapEx": capex, "dNWC": dnwc, "FCF": fcf, "EBIT_Margin": m_t, "Tax_Rate": t_t, "Margin_Base": margin_base, "Metrics": da_str+"+"+cap_ex_str+"+"+nwc_str})
        prev_rev = cur_rev
        
        if i == years:
            cur_rev = rev[year]["Revenue"] * (1 + terminal_growth)
            ebit = cur_rev * EBIT_MARGIN
            nopat = ebit * (1- MARGINAL_TAX_RATE)
            da = None
            capex = None
            dnwc = None
            reinvestment_rate = terminal_growth / terminal_roic
            reinvestment = nopat * reinvestment_rate
            fcf = nopat - reinvestment
            value[year+1].update({"Revenue": cur_rev, "EBIT": ebit, "NOPAT": nopat, "D&A": da, "CapEx": capex, "dNWC": dnwc, "FCF": fcf, "Flag": "TV", "EBIT_Margin": EBIT_MARGIN, "Reinvestment": reinvestment, "Reinvestment_Rate": reinvestment_rate, "Terminal_ROIC": terminal_roic, "Tax_Rate": MARGINAL_TAX_RATE, "Margin_Base": margin_base})
        
    return value
    
def roic(data: dict) -> dict:
    value = {"ROIC_Median": 0, "ROIC_Last": 0, "IC_Last": 0, "n": 0, "Source": ""}
    dct = {}
    t = effective_tax_rate(data)["Effective_Tax_Rate"]
    roics = []
    source = "Median"
    
    for year in sorted(data):
        debt = data[year]["Debt"]["Value"]
        cash = data[year]["Cash"]["Value"]
        equity = data[year]["Equity"]["Value"]
        opinc = data[year]["OperatingIncome"]["Value"]
        vals = [debt, cash, equity, opinc]
        nos = [None]
        if any(map(lambda v: v in vals, nos)): continue
        
        ic = debt + equity - cash
        nopat = opinc * (1 - t)
        dct[year] = {"IC": ic, "NoPat": nopat}
    
    for year in dct:
        if year-1 not in dct.keys(): continue
        if dct[year-1]["IC"] <= 0:
            source = "Insufficient"
            continue
        roic_t = dct[year]["NoPat"] / dct[year-1]["IC"]
        roics.append(roic_t)
    if len(roics) >= MIN_YEARS and source != "Insufficient": 
        median = stats.median(roics)
        last = roics[-1]
    else:
        median = None
        last = None
        
    value.update({"ROIC_Median": median, "ROIC_Last": last, "IC_Last": dct.get(max(data), {}).get("IC"), "n": len(roics), "Source": source})    
    return value

if __name__ == "__main__":
    data = get_data("microsoft", 2016)
    print(project_fcf(data, 10, roic(data)["ROIC_Median"]))