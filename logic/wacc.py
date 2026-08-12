from database import get_data, get_prices
from model import MIN_YEARS
import statistics as stats
import math
from validation import OUTLIER_RULES

def cost_of_debt(data: dict, start_year: int = 2023) -> dict:
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

def cost_of_equity(beta, rf, erp) -> dict:
    return

if __name__ == "__main__":
    data = get_data("apple", 2016) 
    print(cost_of_debt(data, 2018))
    print(raw_beta("apple", "1mo", 61))