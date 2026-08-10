import requests
import json
from datetime import datetime
from pathlib import Path

companies = {
    "apple": "0000320193",
    "jpmorgan": "0000019617",
    "boeing": "0000012927",
    "tesla": "0001318605",
}

REVENUE_TAGS = [
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "SalesRevenueNet",
    ]
OPERATING_INCOME_TAGS = [
    "OperatingIncomeLoss",
    ]
DA_TAGS = [
    "DepreciationDepletionAndAmortization",
    "DepreciationAndAmortization",
    "DepreciationAmortizationAndAccretionNet",
    "Depreciation",
]
CAPEX_TAGS = [
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PaymentsToAcquireProductiveAssets",
    "PaymentsForCapitalImprovements",
]
SHARES_OUTSTANDING_TAGS = [
    "WeightedAverageNumberOfDilutedSharesOutstanding",
    "WeightedAverageNumberOfSharesOutstandingBasic",
]
WORKING_CAPITAL_TAGS = [
    "IncreaseDecreaseInAccountsReceivable",
    "IncreaseDecreaseInInventories",
    "IncreaseDecreaseInAccountsPayable",
    "IncreaseDecreaseInAccountsPayableAndAccruedLiabilities",
    "IncreaseDecreaseInAccruedLiabilities",
]
metrics = {
    "Revenue": REVENUE_TAGS,
    "OperatingIncome": OPERATING_INCOME_TAGS,
    "D&A": DA_TAGS, "CapEx": CAPEX_TAGS,
    "SharesOutstanding": SHARES_OUTSTANDING_TAGS,
    "WorkingCapital": WORKING_CAPITAL_TAGS,
    }
units = ["USD", "shares"]   
sec_layers = ["us-gaap", "dei"]                 
storage_path = Path(Path(__file__).parent.parent.joinpath("storage"))

def get_response(cik):
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    response = requests.get(url, headers={"User-Agent": "Gregor Melching gregor.melching.2401@gmail.com"})
    response.raise_for_status()
    return response.json()


def save_data(c: str) -> None:
    data = get_response(companies[c])
    with open(storage_path / f"{c}.json", "w") as f:
        json.dump(data, f)
            
def get_last_n_years(n: int) -> list:
    cur_year = datetime.now().year
    last_n_years = [year for year in range(cur_year - n, cur_year)]
    return last_n_years   
    
def get_values(n: int, company: str, metric_tags: dict) -> dict:
    years = get_last_n_years(n)
    values = {}
    
    with open(storage_path / f"{company}.json", "r") as f:
        data = json.load(f)

        for year in years: 
            values[year] = {metric: {} for metric in metric_tags}
        
        for sec_layer in sec_layers:
            for unit in units:
                for metric, names in metric_tags.items():
                    for name in names: 
                        if name in data["facts"][sec_layer]:
                            if unit in data["facts"][sec_layer][name]["units"]:
                                for entry in data["facts"][sec_layer][name]["units"][unit]:
                                        
                                    end = datetime.strptime(entry["end"], "%Y-%m-%d")
                                    start = datetime.strptime(entry["start"], "%Y-%m-%d")
                                    diff = end - start
                                        
                                    if diff.days > 350 and entry["form"] == "10-K" and end.year in years and not values[end.year][metric]:
                                        values[end.year][metric].update({"Value": entry["val"], "Tag": name, "Form": entry["form"], "End": end.strftime("%Y-%m-%d")})
                                    
    return values

if __name__ == "__main__":
    save_data("apple")
    print(get_values(1, "apple", metrics))