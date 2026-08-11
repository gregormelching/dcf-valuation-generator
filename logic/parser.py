import requests
import json
from datetime import datetime
from pathlib import Path

companies = {
    "apple": "0000320193",
    "boeing": "0000012927",
    "tesla": "0001318605",
    "microsoft": "0000789019",
    "procter_gamble": "0000080424",
}

REVENUE_TAGS = {
    "Revenue": [
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "SalesRevenueNet",
    ]
}
OPERATING_INCOME_TAGS = {
    "OperatingIncome": [
        "OperatingIncomeLoss",
    ]
}
DA_TAGS = {
    "D&A": [
        "DepreciationDepletionAndAmortization",
        "DepreciationAndAmortization",
        "DepreciationAmortizationAndAccretionNet",
        "Depreciation",
    ]
}
CAPEX_TAGS = {
    "CapEx": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
        "PaymentsForCapitalImprovements",
    ]
}
SHARES_OUTSTANDING_TAGS = {
    "SharesOutstanding": [
        "WeightedAverageNumberOfDilutedSharesOutstanding",
        "WeightedAverageNumberOfSharesOutstandingBasic",
    ]
}
WORKING_CAPITAL_TAGS = {
    "Receivables":      ["IncreaseDecreaseInAccountsReceivable"],
    "Inventory":        ["IncreaseDecreaseInInventories"],
    "Payables":         ["IncreaseDecreaseInAccountsPayableAndAccruedLiabilities",
                            "IncreaseDecreaseInAccountsPayable"],
    "DeferredRevenue":  ["IncreaseDecreaseInContractWithCustomerLiability",
                            "IncreaseDecreaseInDeferredRevenue"],
}
WC_SIGNS = {
    "Receivables": 1,
    "Inventory": 1,
    "Payables": -1,
    "DeferredRevenue": -1
}
RECON_TAGS = {
    "OCF": {"OCF":["NetCashProvidedByUsedInOperatingActivities",
                    "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"], 
            },
    "NetIncome": {"NetIncome": ["NetIncomeLoss",
                                "ProfitLoss"],
            },
    "SBC": {"SBC": ["ShareBasedCompensation",
                    "AllocatedShareBasedCompensationExpense"],
            },
    "DeferredTaxes": {"DeferredTaxes": ["DeferredIncomeTaxExpenseBenefit",
                                        "DeferredIncomeTaxesAndTaxCredits"], 
            },
}
TAX_TAGS = {
    "Tax": ["IncomeTaxExpenseBenefit"]
}
PRETAX_TAGS = {
    "PretaxIncome": [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    ]
}
INTEREST_TAGS = {
    "InterestExpense": [
        "InterestExpense",
        "InterestExpenseDebt",
        "InterestAndDebtExpense",
        "InterestExpenseNonoperating",
    ]
}
DEBT_TAGS = {
    "DebtNoncurrent": ["LongTermDebtNoncurrent", "LongTermDebt", "LongTermDebtAndCapitalLeaseObligations"],
    "DebtCurrent": ["DebtCurrent", "LongTermDebtCurrent"],
    "CommercialPaper": ["CommercialPaper"],
}
CASH_TAGS = {
    "Cash": ["CashAndCashEquivalentsAtCarryingValue",
             "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",],
    "ShortTermInv": [
        "ShortTermInvestments",
        "MarketableSecuritiesCurrent",
        "AvailableForSaleSecuritiesDebtSecuritiesCurrent",
        "AvailableForSaleSecuritiesCurrent"
    ],
    "LongTermInv": [
        "MarketableSecuritiesNoncurrent",
        "AvailableForSaleSecuritiesDebtSecuritiesNoncurrent",
        "AvailableForSaleSecuritiesNoncurrent",
        "LongTermInvestments"
    ],
}
metrics = {
    "Revenue": REVENUE_TAGS,
    "OperatingIncome": OPERATING_INCOME_TAGS,
    "D&A": DA_TAGS, "CapEx": CAPEX_TAGS,
    "SharesOutstanding": SHARES_OUTSTANDING_TAGS,
    "WorkingCapital": WORKING_CAPITAL_TAGS,
    "Cash": CASH_TAGS,
    "Debt": DEBT_TAGS,
    "PretaxIncome": PRETAX_TAGS,
    "InterestExpense": INTEREST_TAGS,
    "Tax": TAX_TAGS,
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
            values[year] = {metric_name: {key: {} for key in metric_tags[metric_name]} for metric_name in metric_tags} 
        
        for sec_layer in sec_layers:
            for unit in units:
                for metric_name, slots in metric_tags.items(): 
                    for slot_name, tag_list in slots.items():   
                        for tag in tag_list:     
                            if tag in data["facts"][sec_layer]:
                                if unit in data["facts"][sec_layer][tag]["units"]:
                                    for entry in data["facts"][sec_layer][tag]["units"][unit]:
                                        
                                        end = datetime.strptime(entry["end"], "%Y-%m-%d")
                                        
                                        if "start" in entry.keys():
                                                
                                            start = datetime.strptime(entry["start"], "%Y-%m-%d")
                                            is_yearly = (end - start).days > 350
                                        
                                        else: 
                                            is_yearly = True        
                                        
                                        if end.year not in years or entry["form"] != "10-K": continue
                                        slot = values[end.year][metric_name][slot_name]

                                        if is_yearly and (not slot or (slot["Tag"] == tag and entry["filed"] > slot["Filed"])):
                                                values[end.year][metric_name][slot_name].update({"Value": entry["val"], "Tag": tag, "Form": entry["form"], "End": end.strftime("%Y-%m-%d"), "Filed": entry["filed"]})
    return values

def clean_values(values: dict) -> dict:
    for year in values:
        sum_wc = 0
        sum_cash = 0
        sum_debt = 0
        debt_tags = []
        debt_ends = []
        cash_tags = []
        cash_ends = []
        wc_tags = []
        wc_ends = []
        data_wc = False
        data_cash = False
        data_debt = False
        for metric_name in values[year]:
            if metric_name == "WorkingCapital": 
                for slot in values[year]["WorkingCapital"]:
                    if values[year]["WorkingCapital"][slot]:
                        sum_wc += (values[year]["WorkingCapital"][slot]["Value"] * WC_SIGNS[slot])
                        data_wc = True
                        wc_tags.append(values[year][metric_name][slot]["Tag"])
                        wc_ends.append(values[year][metric_name][slot]["End"])
                        wc_form = values[year][metric_name][slot]["Form"]
            if metric_name == "Cash":
                for slot in values[year]["Cash"]:
                    if values[year]["Cash"][slot]:
                        sum_cash += values[year]["Cash"][slot]["Value"]
                        data_cash = True
                        cash_tags.append(values[year][metric_name][slot]["Tag"])
                        cash_ends.append(values[year][metric_name][slot]["End"])
                        cash_form = values[year][metric_name][slot]["Form"]
            if metric_name == "Debt":
                for slot in values[year]["Debt"]:
                    if values[year]["Debt"][slot]:
                        if slot == "CommercialPaper":
                            if not values[year]["Debt"]["DebtCurrent"]["Tag"] == "LongTermDebtCurrent": continue
                        sum_debt += values[year]["Debt"][slot]["Value"]
                        data_debt = True
                        debt_tags.append(values[year][metric_name][slot]["Tag"])
                        debt_ends.append(values[year][metric_name][slot]["End"])
                        debt_form = values[year][metric_name][slot]["Form"]
            if len(values[year][metric_name]) == 1:
                values[year][metric_name] = values[year][metric_name][metric_name]

        if data_wc: values[year]["WorkingCapital"].update({"Value": sum_wc, "Tag": "+".join(wc_tags), "End": max(wc_ends), "Form": wc_form})
        if data_cash: values[year]["Cash"].update({"Value": sum_cash, "Tag": "+".join(cash_tags), "End": max(cash_ends), "Form": cash_form})
        if data_debt: values[year]["Debt"].update({"Value": sum_debt, "Tag": "+".join(debt_tags), "End": max(debt_ends), "Form": debt_form})

    return values
                
if __name__ == "__main__":
    apple_vals = clean_values(get_values(1, "microsoft", metrics))
    print(apple_vals)