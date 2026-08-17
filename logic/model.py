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
    value = {"Driver_Ratio": 0, "n": 0, "Source": ""}
    ratios = []
    for year in data:
        flags = [flag for flag in data[year][metric]["Flag"]]
        if data[year][metric]["Value"] is None or data[year]["Revenue"]["Value"] in (0, None): continue
        if OUTLIER_RULES[metric][0] == "yoy" and "outlier" in flags: 
            flags.remove("outlier")
        if len(flags) != 0: continue
        
        d_ratio = data[year][metric]["Value"] / data[year]["Revenue"]["Value"]
        ratios.append(d_ratio)
        
    if len(ratios) >= MIN_YEARS: 
        median = round(stats.median(ratios), 4)
        value.update({"Driver_Ratio": median, "n": len(ratios), "Source": "Median"}) 
    else: 
        median = None   
        value.update({"Driver_Ratio": median, "n": len(ratios), "Source": "Insufficient"})
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
  
def project_revenue(data: dict, years: int, base: str = "Growth_Rate_Median") -> dict:
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
        g_t = round(growth + (TERMINAL_GROWTH - growth) * i/len(projected_years), 4)
        rev *= (1 + g_t)
        value[year].update({"Growth_Rate": g_t, "Revenue": rev, "Source": base})
    
    return value

def project_fcf(data: dict, years: int, terminal_roic: float, base: str = "Growth_Rate_Median") -> dict:
    last_year = sorted(data)[-1]
    projected_years = range(last_year + 1, last_year + 1 + years)
    value = {year: {"Revenue": 0, "EBIT": 0, "NOPAT": 0, "D&A": 0, "CapEx": 0, "dNWC": 0, "FCF": 0, "EBIT_Margin": "", "Reinvestment": 0, "Reinvestment_Rate": 0, "Terminal_ROIC": 0, "Tax_Rate": 0} for year in range(last_year + 1, last_year + 2 + years)}
    EBIT_MARGIN = driver_ratio(data, "OperatingIncome")["Driver_Ratio"]
    D_AND_A_MARGIN = driver_ratio(data, "D&A")["Driver_Ratio"]
    CAP_EX_MARGIN = driver_ratio(data, "CapEx")["Driver_Ratio"]
    DNWC_MARGIN = driver_ratio(data, "WorkingCapital")["Driver_Ratio"]
    if terminal_roic <= TERMINAL_GROWTH: raise ValueError("Terminal ROIC must be greater than terminal growth")
    t = effective_tax_rate(data)["Effective_Tax_Rate"]
    if None in [EBIT_MARGIN, D_AND_A_MARGIN, CAP_EX_MARGIN, DNWC_MARGIN]: raise ValueError("Missing data for EBIT, D&A, CapEx, or Working Capital")
    rev = project_revenue(data, years, base)
    if data[last_year]["OperatingIncome"]["Value"] is not None and data[last_year]["Revenue"]["Value"] not in (0, None): LAST_EBIT_MARGIN = data[last_year]["OperatingIncome"]["Value"] / data[last_year]["Revenue"]["Value"]
    else: raise ValueError("Missing data for Operating Income or Revenue")
    i = 0
    
    for year in projected_years:
        i += 1
        m_t = LAST_EBIT_MARGIN + (EBIT_MARGIN - LAST_EBIT_MARGIN) * i / len(projected_years)
        t_t = t + (MARGINAL_TAX_RATE - t) * i / len(projected_years)
        cur_rev = rev[year]["Revenue"]
        ebit = cur_rev * m_t
        nopat = ebit * (1 - t_t)
        da = cur_rev * D_AND_A_MARGIN
        capex = cur_rev * CAP_EX_MARGIN
        dnwc = cur_rev * DNWC_MARGIN
        fcf = nopat + da - capex - dnwc
        value[year].update({"Revenue": cur_rev, "EBIT": ebit, "NOPAT": nopat, "D&A": da, "CapEx": capex, "dNWC": dnwc, "FCF": fcf, "EBIT_Margin": m_t, "Tax_Rate": t_t})
        
        if i == years:
            cur_rev = rev[year]["Revenue"] * (1 + TERMINAL_GROWTH)
            ebit = cur_rev * EBIT_MARGIN
            nopat = ebit * (1- MARGINAL_TAX_RATE)
            da = None
            capex = None
            dnwc = None
            reinvestment_rate = TERMINAL_GROWTH / terminal_roic
            reinvestment = nopat * reinvestment_rate
            fcf = nopat - reinvestment
            value[year+1].update({"Revenue": cur_rev, "EBIT": ebit, "NOPAT": nopat, "D&A": da, "CapEx": capex, "dNWC": dnwc, "FCF": fcf, "Flag": "TV", "EBIT_Margin": EBIT_MARGIN, "Reinvestment": reinvestment, "Reinvestment_Rate": reinvestment_rate, "Terminal_ROIC": terminal_roic, "Tax_Rate": MARGINAL_TAX_RATE})
    
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
    data = get_data("apple", 2016)
    print(roic(data))