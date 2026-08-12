from database import get_data
from model import MIN_YEARS
import statistics as stats
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

def cost_of_equity(beta, rf, erp) -> dict:
    return

if __name__ == "__main__":
    data = get_data("apple", 2016) 
    print(cost_of_debt(data, 2018))