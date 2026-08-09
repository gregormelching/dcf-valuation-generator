import requests
import json
from prettytable import PrettyTable
from datetime import datetime

table = PrettyTable()
table.field_names = ["Company", "Revenue", "Operating Income"]

companies = {
    "apple": "0000320193",
    "jpmorgan": "0000019617",
    "boeing": "0000012927",
    "tesla": "0001318605",
}

REVENUE_TAGS = ["Revenues",  "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"]
OPERATING_INCOME_TAGS = ["OperatingIncomeLoss"]


def get_response(cik):
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    response = requests.get(url, headers={"User-Agent": "Gregor Melching gregor.melching.2401@gmail.com"})
    response.raise_for_status()
    return response.json()


def save_data():
    for company in companies: 
        data = get_response(companies[company])
        with open(f"{company}.json", "w") as f:
            json.dump(data, f)
            
def get_latest_values():
    save_data()
    latest_values = {"apple": {}, "boeing": {}, "tesla": {}, "jpmorgan": {}}
    for company in companies:
        with open(f"{company}.json", "r") as f:
            data = json.load(f)
            max = datetime.strptime("2000-01-01", "%Y-%m-%d")
            for tag in REVENUE_TAGS + OPERATING_INCOME_TAGS:
                if tag in data["facts"]["us-gaap"]:
                    for entry in data["facts"]["us-gaap"][tag]["units"]["USD"]:
                        
                        end = datetime.strptime(entry["end"], "%Y-%m-%d")
                        start = datetime.strptime(entry["start"], "%Y-%m-%d")
                        diff = end - start
                        
                        if max.year <= end.year and diff.days > 350 and entry["form"] == "10-K":
                            max = end
                            
                            if tag in REVENUE_TAGS:
                                latest_values[company]["Revenue"] = entry["val"]
                            elif  tag in OPERATING_INCOME_TAGS:
                                latest_values[company]["OperatingIncome"] = entry["val"]                
    return latest_values

company_data = get_latest_values()

print(company_data)
for company in companies: 
    keys = [key for key in company_data[company].keys()]
    if "OperatingIncome" not in keys:
        company_data[company]["OperatingIncome"] = "NaN"
    if "Revenue" not in keys:
        company_data[company]["Revenue"] = "NaN"
        
    table.add_row([company, company_data[company]["Revenue"], company_data[company]["OperatingIncome"]])
    
print(table)