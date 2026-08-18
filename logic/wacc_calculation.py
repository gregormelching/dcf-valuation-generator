from database import get_data, get_prices
from model import MIN_YEARS, MARGINAL_TAX_RATE
import statistics as stats
import math
from validation import OUTLIER_RULES
from prices import N_MONTHS, risk_free_rate

EQUITY_RISK_PREMIUM = 0.0428
COD_START_YEAR = 2023
COD_FALLBACK_START_YEAR = 2018

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

def raw_beta(symbol: str, freq: str, n: int) -> dict:
    value = {"Beta": 0, "n": 0, "Correlation": 0, "Std_Error": 0, "Source": freq}
    
    stock = get_prices(symbol, freq, n)
    market = get_prices("market", freq, n)
    
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

def debt_to_equity(data: dict, symbol: str, year: int | None) -> float: 
    
    if year is None: debt_year = max(data)
    else: debt_year = year
    if data[debt_year]["Debt"]["Value"] in (0, None) or data[debt_year]["SharesOutstanding"]["Value"] in (0, None): raise ValueError("Missing Debt or SharesOutstanding value")
    
    prices = dict(get_prices(symbol, "1mo", N_MONTHS))
    
    if year is None: close = list(prices.items())[-1][1]
    else: close = [i[1] for i in prices.items() if i[0].startswith(f"{year}-12")][-1]
    
    market_cap = data[debt_year]["SharesOutstanding"]["Value"] * close
    
    return data[debt_year]["Debt"]["Value"] / market_cap

def adjusted_beta(data: dict, symbol: str, freq: str, n: int) -> dict:
    value = {"Beta": 0, "Beta_Raw": 0, "Beta_Unlevered": 0, "Beta_Relevered": 0, "DE_Window": 0, "DE_Current": 0, "n": 0, "Correlation": 0, "Std_Error": 0, "Source": ""}
    
    raw = raw_beta(symbol, freq, n)
    years = sorted(set([int(year[0].split("-")[0]) for year in get_prices(symbol, freq, n) if year[0].split("-")[1] == "12"]))
    de_window = stats.mean([debt_to_equity(data, symbol, year) for year in years])
    de_current = debt_to_equity(data, symbol, None)
    beta_u = raw["Beta"] / (1 + (1 - MARGINAL_TAX_RATE) * de_window)
    beta_rel = beta_u * (1 + (1 - MARGINAL_TAX_RATE) * de_current)
    beta_adj = 0.67 * beta_rel + 0.33
    
    value.update({"Beta": beta_adj, "Beta_Raw": raw["Beta"], "Beta_Unlevered": beta_u, "Beta_Relevered": beta_rel, "DE_Window": de_window, "DE_Current": de_current, "n": raw["n"], "Correlation": raw["Correlation"], "Std_Error": raw["Std_Error"], "Source": raw["Source"]})
    
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

def calc_wacc(data: dict, symbol: str, freq: str, n: int, erp: float = EQUITY_RISK_PREMIUM, as_of: str | None = None) -> dict:
    value = {"WACC": 0, "WACC_Low": 0, "WACC_High": 0, "Cost_of_Equity": 0, "Cost_of_Debt": 0, "Cost_of_Debt_After_Tax": 0, "Weight_Equity": 0, "Weight_Debt": 0, "Beta": 0, "Risk_Free_Rate": 0, "ERP": 0, "COD_Source": 0, "Source": "", "RF_Date": "", "RF_Fetched_At": ""}
    
    rf = risk_free_rate(as_of)
    beta = adjusted_beta(data, symbol, freq, n)
    cost_equity = cost_of_equity(beta, rf, erp)
    cost_debt = cost_of_debt(data, COD_START_YEAR)
    cod_source = COD_START_YEAR
    if cost_debt["Source"] == "Insufficient": 
        cost_debt = cost_of_debt(data, COD_FALLBACK_START_YEAR)
        cod_source = COD_FALLBACK_START_YEAR
    if cost_debt["Source"] == "Insufficient": raise ValueError("Insufficient Data")
    de = debt_to_equity(data, symbol, None)
    weight_equity = 1 / (1 + de)
    weight_debt = de / (1 + de)
    after_tax_debt = cost_debt["Cost_of_Debt"] * (1 - MARGINAL_TAX_RATE)
    wacc_low = weight_equity * cost_equity["CI_Low"] + weight_debt * after_tax_debt
    wacc_high = weight_equity * cost_equity["CI_High"] + weight_debt * after_tax_debt
    wacc = weight_equity * cost_equity["Cost_of_Equity"] + weight_debt * after_tax_debt
    
    value.update({"WACC": wacc, "WACC_High": wacc_high, "WACC_Low": wacc_low, "Cost_of_Equity": cost_equity["Cost_of_Equity"], "Cost_of_Debt": cost_debt["Cost_of_Debt"], "Cost_of_Debt_After_Tax": after_tax_debt, "Weight_Equity": weight_equity, "Weight_Debt": weight_debt, "Beta": beta["Beta"], "Risk_Free_Rate": rf["Risk_Free_Rate"], "ERP": erp, "COD_Source": cod_source, "Source": beta["Source"] + "+" + str(cod_source), "RF_Date": rf["Date"], "RF_Fetched_At": rf["Fetched_At"]})
        
    return value

if __name__ == "__main__":
    data = get_data("apple", 2016) 
    #print(cost_of_debt(data, 2018))
    #print(raw_beta("apple", "1mo", 61))
    #print(debt_to_equity(data, "apple", 2025))
    beta = adjusted_beta(data, "apple", "1mo", N_MONTHS)
    rf = risk_free_rate()
    #print(cost_of_equity(beta, rf, EQUITY_RISK_PREMIUM))
    print(calc_wacc(data, "apple", "1mo", N_MONTHS, EQUITY_RISK_PREMIUM))