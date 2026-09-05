from database import get_data, get_prices
from datetime import datetime
from model import MIN_YEARS, MARGINAL_TAX_RATE
import statistics as stats
import math
from validation import OUTLIER_RULES
from prices import N_MONTHS, risk_free_rate, price_reference

EQUITY_RISK_PREMIUM = 0.0428
COD_START_YEAR = 2023
COD_FALLBACK_START_YEAR = 2018
SPREADS = [
    (-100000.0, 0.199999, "D2/D", 0.1900),
    (0.2, 0.649999, "C2/C", 0.1600),
    (0.65, 0.799999, "Ca2/CC", 0.1261),
    (0.8, 1.249999, "Caa/CCC", 0.0885),
    (1.25, 1.499999, "B3/B-", 0.0509),
    (1.5, 1.749999, "B2/B", 0.0321),
    (1.75, 1.999999, "B1/B+", 0.0275),
    (2.0, 2.2499999, "Ba2/BB", 0.0184),
    (2.25, 2.49999, "Ba1/BB+", 0.0138),
    (2.5, 2.999999, "Baa2/BBB", 0.0111),
    (3.0, 4.249999, "A3/A-", 0.0089),
    (4.25, 5.499999, "A2/A", 0.0078),
    (5.5, 6.499999, "A1/A+", 0.0070),
    (6.5, 8.499999, "Aa2/AA", 0.0055),
    (8.5, 100000.0, "Aaa/AAA", 0.0040),
]
INVESTMENT_GRADE = 2.5

def synthetic_rating(coverage: float) -> dict:
    for low, high, rating, spread in SPREADS:
        if low <= coverage <= high:
            return {"Rating": rating, "Spread": spread, "Source": "Damodaran large cap"}
    raise ValueError(f"Coverage ratio {coverage} outside the spread table.")

def cost_of_debt(data: dict, start_year: int = COD_START_YEAR) -> dict:
    value = {"Cost_of_Debt": 0, "n": 0, "Source": ""}
    costs = []
    
    for year in data: 
        if year < start_year: continue
        flags_IE = [flag for flag in data[year]["InterestExpense"]["Flag"]]
        flags_D = [flag for flag in data[year]["Debt"]["Flag"]]
        if data[year]["InterestExpense"]["Value"] is None or data[year]["Debt"]["Value"] in (None, 0): continue
        if OUTLIER_RULES["InterestExpense"][0] == "yoy" and "outlier" in flags_IE:
            flags_IE.remove("outlier")
        if OUTLIER_RULES["Debt"][0] == "yoy" and "outlier" in flags_D:
            flags_D.remove("outlier")
        if len(flags_IE) != 0 or len(flags_D) != 0: continue
        if year-1 in data and data[year-1]["Debt"]["Value"] is not None: middle = (data[year]["Debt"]["Value"] + data[year-1]["Debt"]["Value"]) / 2
        else: middle = data[year]["Debt"]["Value"]
        costs.append(data[year]["InterestExpense"]["Value"] / middle)
     
    if len(costs) >= MIN_YEARS:
        value.update({"Cost_of_Debt": stats.median(costs), "n": len(costs), "Source": "Calculated"})   
    else: 
        value.update({"Cost_of_Debt": None, "n": len(costs), "Source": "Insufficient"})
    return value

def raw_beta(symbol: str, freq: str, n: int, as_of: str) -> dict:
    value = {"Beta": 0, "n": 0, "Correlation": 0, "Std_Error": 0, "Source": freq}
    
    stock = get_prices(symbol, freq, n, as_of)
    market = get_prices("market", freq, n, as_of)
    
    if False in [stock[i][0] == market[i][0] for i in range(len(stock))]: raise ValueError("Stock and market must have the same date")

    market_returns = [((market[i][1] / market[i-1][1]) - 1) for i in range(1, len(market))]
    stock_returns = [((stock[i][1] / stock[i-1][1]) - 1) for i in range(1, len(stock))]
    
    slope, intercept = stats.linear_regression(market_returns, stock_returns)
    beta = slope
    corr = stats.correlation(market_returns, stock_returns)
    
    x_mean = stats.mean(market_returns)
    sum_sq_resid = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(market_returns, stock_returns))
    sum_sq_x_diff = sum((x - x_mean) ** 2 for x in market_returns)
    
    num_returns = len(market_returns)
    se = math.sqrt(sum_sq_resid / (num_returns - 2) / sum_sq_x_diff)
        
    value.update({"Beta": round(beta, 3), "Correlation": round(corr, 3), "Std_Error": round(se, 3), "n": num_returns})
    return value

def debt_to_equity(data: dict, symbol: str, year: int | None, as_of: str) -> float: 
    
    if year is None: debt_year = max(data)
    else: debt_year = year
    if data[debt_year]["Debt"]["Value"] in (0, None) or data[debt_year]["SharesOutstanding"]["Value"] in (0, None): raise ValueError("Missing Debt or SharesOutstanding value")
    
    if year is None: close = price_reference(symbol, "1mo", as_of)["Price"]
    else: 
        prices = dict(get_prices(symbol, "1mo", N_MONTHS, as_of))
        close = [i[1] for i in prices.items() if i[0].startswith(f"{year}-12")][-1]
    
    market_cap = data[debt_year]["SharesOutstanding"]["Value"] * close
    
    return data[debt_year]["Debt"]["Value"] / market_cap

def adjusted_beta(data: dict, symbol: str, freq: str, n: int, as_of: str) -> dict:
    value = {"Beta": 0, "Beta_Raw": 0, "Beta_Unlevered": 0, "Beta_Relevered": 0, "DE_Window": 0, "DE_Current": 0, "n": 0, "Correlation": 0, "Std_Error": 0, "Source": "", "DE_Years": []}
    
    raw = raw_beta(symbol, freq, n, as_of)
    years = sorted(set([int(year[0].split("-")[0]) for year in get_prices(symbol, freq, n, as_of) if year[0].split("-")[1] == "12"]))
    years = [y for y in years if y in data]
    if len(years) == 0: raise ValueError(f"No valid entries for {symbol}.")
    de_window = stats.mean([debt_to_equity(data, symbol, year, as_of) for year in years])
    de_current = debt_to_equity(data, symbol, None, as_of)
    beta_u = raw["Beta"] / (1 + (1 - MARGINAL_TAX_RATE) * de_window)
    beta_rel = beta_u * (1 + (1 - MARGINAL_TAX_RATE) * de_current)
    beta_adj = 0.67 * beta_rel + 0.33
    
    value.update({"Beta": beta_adj, "Beta_Raw": raw["Beta"], "Beta_Unlevered": beta_u, "Beta_Relevered": beta_rel, "DE_Window": de_window, "DE_Current": de_current, "n": raw["n"], "Correlation": raw["Correlation"], "Std_Error": raw["Std_Error"], "Source": raw["Source"], "DE_Years": years})
    
    return value

def cost_of_equity(beta: dict, rf: dict, erp: float = EQUITY_RISK_PREMIUM) -> dict:
    
    if beta["Beta"] is None or rf["Risk_Free_Rate"] is None: raise ValueError("Beta or RFR not a valid value.")
    
    value = {"Cost_of_Equity": 0, "Beta": 0, "Risk_Free_Rate": rf["Risk_Free_Rate"], "ERP": erp, "CI_Low": 0, "CI_High": 0, "Source": beta["Source"], "Std_Error_adj": 0}
    
    capm = rf["Risk_Free_Rate"] + beta["Beta"] * erp
    k = 0.67 * (1 + (1 - MARGINAL_TAX_RATE) * beta["DE_Current"]) / (1 + (1 - MARGINAL_TAX_RATE) * beta["DE_Window"])
    std_error_adj = k * beta["Std_Error"]
    ci_low = rf["Risk_Free_Rate"] + (beta["Beta"] - 1.96 * std_error_adj) * erp
    ci_high = rf["Risk_Free_Rate"] + (beta["Beta"] + 1.96 * std_error_adj) * erp
    
    value.update({"Cost_of_Equity": capm, "CI_Low": ci_low, "CI_High": ci_high, "Beta": beta["Beta"], "Std_Error_adj": std_error_adj})
    
    return value

def synthetic_cost_of_debt(data: dict, rf: dict) -> dict:
    value = {}
    candidates = []    
    
    for year in data:
        
        oi = data[year]["OperatingIncome"]
        ie = data[year]["InterestExpense"]
        flags_OI = [flag for flag in oi["Flag"]]
        flags_IE = [flag for flag in ie["Flag"]]
        
        if ie["Value"] in (0, None) or oi["Value"] is None: continue
        if OUTLIER_RULES["InterestExpense"][0] == "yoy" and "outlier" in flags_IE:
            flags_IE.remove("outlier")
        if OUTLIER_RULES["OperatingIncome"][0] == "margin_change_pp" and "outlier" in flags_OI:
            flags_OI.remove("outlier")
        if len(flags_OI) != 0 or len(flags_IE) != 0: continue
        
        candidates.append(year)
    
    if len(candidates) == 0: coverage = {"Coverage": None, "Year": None, "n": 0, "Source": "Unavailable"}
    else: 
        last_year = max(candidates)
        cov_ratio = data[last_year]["OperatingIncome"]["Value"] / data[last_year]["InterestExpense"]["Value"]
        coverage = {"Coverage": cov_ratio, "Year": last_year, "n": len(candidates), "Source": "Calculated"}
        if coverage["Coverage"] < INVESTMENT_GRADE: coverage.update({"Source": "Below_Investment_Grade"})
    
    if coverage["Source"] == "Unavailable": 
        synth_cost = None
        rating = None
        spread = None
    else:    
        spread_entry = synthetic_rating(coverage["Coverage"])
        spread = spread_entry["Spread"]
        rating = spread_entry["Rating"]
        synth_cost = rf["Risk_Free_Rate"] + spread

    value.update({"Cost_of_Debt": synth_cost, "Rating": rating, "Spread": spread})
    
    return value | coverage

def calc_wacc(data: dict, symbol: str, freq: str, n: int, erp: float = EQUITY_RISK_PREMIUM, as_of: str | None = None) -> dict:
    value = {"WACC": 0, "WACC_Low": 0, "WACC_High": 0, "Cost_of_Equity": 0, "Cost_of_Debt": 0, "Cost_of_Debt_After_Tax": 0, "Weight_Equity": 0, "Weight_Debt": 0, "Beta": 0, "Risk_Free_Rate": 0, "ERP": 0, "COD_Source": 0, "Source": "", "RF_Date": "", "RF_Fetched_At": ""}
    if as_of is None: as_of = datetime.now().strftime("%Y-%m-%d")
    rf = risk_free_rate(as_of)
    beta = adjusted_beta(data, symbol, freq, n, as_of)
    cost_equity = cost_of_equity(beta, rf, erp)
    synth = synthetic_cost_of_debt(data, rf)
    fallback = cost_of_debt(data, COD_START_YEAR)
    
    if synth["Source"] == "Calculated":
        cod_basis = "Synthetic"
        cod_alternative = fallback["Cost_of_Debt"]
        if fallback["Source"] == "Insufficient": cod_alternative = cost_of_debt(data, COD_FALLBACK_START_YEAR)["Cost_of_Debt"]
        cod_source = None
        cod_realised = cod_alternative
        cod_used = synth["Cost_of_Debt"]
    else: 
        cost_debt = fallback
        cod_source = COD_START_YEAR    
        if cost_debt["Source"] == "Insufficient": 
            cost_debt = cost_of_debt(data, COD_FALLBACK_START_YEAR)
            cod_source = COD_FALLBACK_START_YEAR
        if cost_debt["Source"] == "Insufficient": raise ValueError("Insufficient Data")
        cod_realised = cost_debt["Cost_of_Debt"]
        cod_border = rf["Risk_Free_Rate"] + synthetic_rating(INVESTMENT_GRADE)["Spread"]
        cod_alternative = synth["Cost_of_Debt"]
        
        if cod_border > cod_realised: 
            cod_used = cod_border
            cod_basis = f"IG_Floor+{synth["Source"]}"
        else:
            cod_used = cod_realised
            cod_basis = f"Realised_Fallback+{synth["Source"]}"
    cod_evidence = {"Rating": synth["Rating"], "Coverage": synth["Coverage"], "Year": synth["Year"], "n": synth["n"], "Realised": cod_realised}
        
    de = debt_to_equity(data, symbol, None, as_of)
    weight_equity = 1 / (1 + de)
    weight_debt = de / (1 + de)
    after_tax_debt = cod_used * (1 - MARGINAL_TAX_RATE)
    wacc_low = weight_equity * cost_equity["CI_Low"] + weight_debt * after_tax_debt
    wacc_high = weight_equity * cost_equity["CI_High"] + weight_debt * after_tax_debt
    wacc = weight_equity * cost_equity["Cost_of_Equity"] + weight_debt * after_tax_debt
    ref_data = price_reference(symbol, "1mo", as_of)

    value.update({"WACC": wacc, "WACC_High": wacc_high, "WACC_Low": wacc_low, "Cost_of_Equity": cost_equity["Cost_of_Equity"], "Cost_of_Debt": cod_used, "Cost_of_Debt_After_Tax": after_tax_debt, "Weight_Equity": weight_equity, "Weight_Debt": weight_debt, "Beta": beta["Beta"], "Risk_Free_Rate": rf["Risk_Free_Rate"], "ERP": erp, "COD_Source": cod_source, "Source": beta["Source"] + "+" + str(cod_source) if cod_source is not None else beta["Source"], "RF_Date": rf["Date"], "RF_Fetched_At": rf["Fetched_At"], "COD_Basis": cod_basis, "COD_Alternative": cod_alternative, "COD_Evidence": cod_evidence, "MCap_Price_Date": ref_data["Date"], "MCap_Price_Age_Days": ref_data["Age"]})
        
    return value

if __name__ == "__main__":
    as_of = "2026-08-19"
    data = get_data("apple", 2016) 
    beta = adjusted_beta(data, "apple", "1mo", N_MONTHS, as_of = as_of)
    rf = risk_free_rate(as_of)
    print(calc_wacc(data, "apple", "1mo", N_MONTHS, as_of = as_of))