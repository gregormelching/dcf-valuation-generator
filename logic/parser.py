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
    ],
    "SharesDated": [
        "EntityCommonStockSharesOutstanding",
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
                      "Fed": ["DeferredFederalIncomeTaxExpenseBenefit"],
                      "For": ["DeferredForeignIncomeTaxExpenseBenefit"],
                      "St": ["DeferredStateAndLocalIncomeTaxExpenseBenefit"],
            },
}
TAX_TAGS = {
    "Tax": ["IncomeTaxExpenseBenefit"]
}
PRETAX_TAGS = {
    "PretaxIncome": [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    ],
    "Domestic": ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic"],
    "Foreign":  ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesForeign"]

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
EQUITY_TAGS = {
    "Equity": ["StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
               "StockholdersEquity"]
}
NWC_LEVEL_TAGS = {
    "Receivables": ["AccountsReceivableNetCurrent"],
    "Inventory": ["InventoryNet", "InventoryNetOfAllowancesCustomerAdvancesAndProgressBillings"],
    "Payables": ["AccountsPayableCurrent"],
    "DeferredRev": ["ContractWithCustomerLiabilityCurrent", "DeferredRevenueCurrent"]
}
NWC_LEVEL_SIGNS = {
    "Receivables": 1,
    "Inventory": 1,
    "Payables": -1,
    "DeferredRev": -1
}
SLOT_SIGNS = {
    "WorkingCapital": WC_SIGNS,
    "NWC": NWC_LEVEL_SIGNS
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
    "Equity": EQUITY_TAGS,
    "NWC": NWC_LEVEL_TAGS
    }
units = ["USD", "shares"]   
sec_layers = ["us-gaap", "dei"]                 
storage_path = Path(Path(__file__).parent.parent.joinpath("storage"))

def select_wc(slots):
    return [s for s in WORKING_CAPITAL_TAGS if slots[s]]

def select_cash(slots):
    return [s for s in CASH_TAGS if slots[s]]

def select_debt(slots):
    chosen = [s for s in DEBT_TAGS if slots[s]]
    if "CommercialPaper" in chosen and not slots["DebtCurrent"].get("Tag") == "LongTermDebtCurrent": chosen.remove("CommercialPaper")
    return chosen

def select_pretax(slots):
    if slots["PretaxIncome"]: return ["PretaxIncome"]
    if slots["Domestic"] and slots["Foreign"]: return ["Domestic", "Foreign"]
    return []

def select_deferred_taxes(slots):
    if slots["DeferredTaxes"]: return ["DeferredTaxes"]
    if slots["Fed"] and slots["For"] and slots["St"]: return ["Fed", "For", "St"]
    return []

def select_shares(slots):
    if slots["SharesDated"]: return ["SharesDated"]
    if slots["SharesOutstanding"]: return ["SharesOutstanding"]
    return []

def select_nwc_level(slots):
    return [s for s in NWC_LEVEL_TAGS if slots[s]]

SLOT_SELECTORS = {
    "WorkingCapital": select_wc,
    "Cash": select_cash,
    "Debt": select_debt,
    "PretaxIncome": select_pretax,
    "DeferredTaxes": select_deferred_taxes,
    "SharesOutstanding": select_shares,
    "NWC": select_nwc_level
}

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
    last_n_years = [year for year in range(cur_year - n, cur_year + 1)]
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
                                               
                                        if slot_name == "SharesDated": endyear = entry.get("fy")
                                        else: endyear = end.year
                                        if endyear not in years or entry["form"] != "10-K": continue
                                        slot = values[endyear][metric_name][slot_name]

                                        if is_yearly and (not slot or (slot["Tag"] == tag and entry["filed"] > slot["Filed"])):
                                                values[endyear][metric_name][slot_name].update({"Value": entry["val"], "Tag": tag, "Form": entry["form"], "End": end.strftime("%Y-%m-%d"), "Filed": entry["filed"]})
    return values

def clean_values(values: dict) -> dict:
    for year in values:
        for metric_name in values[year]:
            if metric_name in SLOT_SELECTORS:
                slots = values[year][metric_name]
                chosen = SLOT_SELECTORS[metric_name](slots)
                if not chosen: continue
                total = sum(slots[s]["Value"] * SLOT_SIGNS.get(metric_name, {}).get(s, 1) for s in chosen)
                tags = [slots[s]["Tag"] for s in chosen]
                ends = [slots[s]["End"] for s in chosen]
                forms = [slots[s]["Form"] for s in chosen]
                filed = [slots[s]["Filed"]for s in chosen       ]
                slots.update({"Value": total, "Tag": "+".join(tags), "End": max(ends), "Form": "+".join(dict.fromkeys(forms)), "Filed": max(filed)})
            elif len(values[year][metric_name]) == 1:
                values[year][metric_name] = values[year][metric_name][metric_name]
    return values
                
if __name__ == "__main__":
    for c in companies:
        save_data(c)