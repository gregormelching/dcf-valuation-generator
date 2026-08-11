from pathlib import Path
import sqlite3
from database import get_data
from parser import companies
import statistics as stats
from validation import OUTLIER_RULES

storage_path = Path(Path(__file__).parent.parent.joinpath("storage"))
TAX_WINDOW_START = 2018
MARGINAL_TAX_RATE = 0.25
MIN_YEARS = 3
    
def effective_tax_rate(data):
    value = {"Rate": 0, "n": 0, "Source": ""}
    rates = []
    for year in data: 
        if len(data[year]["Tax"]["Flag"]) != 0 or (data[year]["Tax"]["Value"] is None or data[year]["PretaxIncome"]["Value"] is None):
            continue
        tax_rate = data[year]["Tax"]["Value"] / data[year]["PretaxIncome"]["Value"]
        rates.append(tax_rate)
    if len(rates) < MIN_YEARS: 
        value.update({"Rate": MARGINAL_TAX_RATE, "n": len(rates), "Source": "Fallback"})
    else:
        median = round(stats.median(rates), 4)
        value.update({"Rate": median, "n": len(rates), "Source": "Median"})
    return value

def driver_ratio(data, metric):
    value = {"Ratio": 0, "n": 0, "Source": ""}
    nono = [0, None]
    ratios = []
    for year in data:
        flags = [flag for flag in data[year][metric]["Flag"]]
        if data[year][metric]["Value"] in nono or data[year]["Revenue"]["Value"] in nono: continue
        if OUTLIER_RULES[metric][0] == "yoy" and "outlier" in flags: 
            flags.remove("outlier")
        if len(flags) != 0: continue
        
        driver_ratio = data[year][metric]["Value"] / data[year]["Revenue"]["Value"]
        ratios.append(driver_ratio)
        
    if len(ratios) >= MIN_YEARS: 
        median = round(stats.median(ratios), 4)
        value.update({"Ratio": median, "n": len(ratios), "Source": "Median"}) 
    else: 
        median = None   
        value.update({"Ratio": median, "n": len(ratios), "Source": "Insufficient"})
    return value

  
if __name__ == "__main__":
    for c in companies:
        data = get_data(c, 2016)
        print(f"{c}: {effective_tax_rate(data)}")
        print(f"{c}: {driver_ratio(data, "WorkingCapital")}")