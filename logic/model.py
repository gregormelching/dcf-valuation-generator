from pathlib import Path
import sqlite3
from database import get_data
from parser import companies
import statistics as stats

storage_path = Path(Path(__file__).parent.parent.joinpath("storage"))
TAX_WINDOW_START = 2018
MARGINAL_TAX_RATE = 0.25
    
def effective_tax_rate(data):
    value = {"Rate": 0, "n": 0, "Source": ""}
    rates = []
    for year in data: 
        if len(data[year]["Tax"]["Flag"]) != 0 or (data[year]["Tax"]["Value"] is None or data[year]["PretaxIncome"]["Value"] is None):
            continue
        tax_rate = data[year]["Tax"]["Value"] / data[year]["PretaxIncome"]["Value"]
        rates.append(tax_rate)
    if len(rates) < 3: 
        value.update({"Rate": MARGINAL_TAX_RATE, "n": len(rates), "Source": "Fallback"})
    else:
        median = round(stats.median(rates), 3)
        value.update({"Rate": median, "n": len(rates), "Source": "Median"})
    return value
     
if __name__ == "__main__":
    for c in companies:
        data = get_data(c, 2018)
        print(effective_tax_rate(data))