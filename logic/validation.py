from parser import *

OUTLIER_RULES = {
    "Revenue":              ("yoy", 0.4),
    "D&A":                  ("yoy", 0.3),
    "CapEx":                ("yoy", 0.5), 
    "SharesOutstanding":    ("yoy", 0.1),
    "OperatingIncome":      ("margin_change_pp", 0.07),
    "WorkingCapital":       ("pct_of_revenue", 0.1),
    "Tax":                  ("effective_rate", 0.4),
    "PretaxIncome":         ("margin_change_pp", 0.1),
    "InterestExpense":      ("yoy", 0.5),
    "Debt":                 ("yoy", 0.5),
    "Cash":                 ("yoy", 0.5),
    "Equity":               ("yoy", 0.5),
    "NWC":                  ("yoy", 0.5)
}

RECON_TOLERANCE = 0.03

def validate_values(values: dict) -> dict:
    flags = {year: {metric_name: [] for metric_name in values[year]} for year in values}
    exceptions = ["OperatingIncome", "WorkingCapital", "Tax", "PretaxIncome", "Equity", "NWC"]
    
    for year in values:
        for metric_name in values[year]:
            if "Value" not in values[year][metric_name].keys(): flags[year][metric_name].append("missing")
            else:
                if metric_name not in exceptions and values[year][metric_name]["Value"] < 0: flags[year][metric_name].append("negative")
                rev_ok = "Value" in values[year]["Revenue"].keys() and not values[year]["Revenue"]["Value"] == 0
                pre_ok = "Value" in values[year]["PretaxIncome"].keys() and not values[year]["PretaxIncome"]["Value"] == 0

                if OUTLIER_RULES[metric_name][0] == "pct_of_revenue":
                    if not rev_ok: flags[year][metric_name].append("unchecked")
                    elif abs(values[year][metric_name]["Value"] / values[year]["Revenue"]["Value"]) > OUTLIER_RULES[metric_name][1]: flags[year][metric_name].append("outlier")

                if OUTLIER_RULES[metric_name][0] == "effective_rate":
                    if not pre_ok or values[year]["PretaxIncome"]["Value"] < 0: flags[year][metric_name].append("unchecked")
                    elif values[year][metric_name]["Value"] / values[year]["PretaxIncome"]["Value"] > OUTLIER_RULES[metric_name][1] or values[year][metric_name]["Value"] / values[year]["PretaxIncome"]["Value"] < 0: flags[year][metric_name].append("outlier")
                
                if year-1 in values.keys() and "Value" in values[year-1][metric_name].keys():
                    prev_rev_ok = "Value" in values[year-1]["Revenue"].keys() and not values[year-1]["Revenue"]["Value"] == 0

                    if OUTLIER_RULES[metric_name][0] == "yoy":
                        if values[year-1][metric_name]["Value"] == 0: flags[year][metric_name].append("unchecked")
                        elif abs(values[year][metric_name]["Value"] - values[year-1][metric_name]["Value"]) / abs(values[year-1][metric_name]["Value"]) > OUTLIER_RULES[metric_name][1]: flags[year][metric_name].append("outlier")
                    elif OUTLIER_RULES[metric_name][0] == "margin_change_pp":
                        if not (rev_ok and prev_rev_ok): flags[year][metric_name].append("unchecked")
                        else:
                            marge_t = values[year][metric_name]["Value"] / values[year]["Revenue"]["Value"]
                            marge_t1 = values[year-1][metric_name]["Value"] / values[year-1]["Revenue"]["Value"]
                            if abs(marge_t - marge_t1) > OUTLIER_RULES[metric_name][1]: flags[year][metric_name].append("outlier")
    return flags

def reconcile_working_capital(values: dict, recon_values: dict) -> dict:
    reconciled = {year: {} for year in values}
    
    for year in values:
        if year not in recon_values: continue
        needed = [recon_values[year]["NetIncome"], recon_values[year]["OCF"], values[year]["D&A"], recon_values[year]["SBC"], values[year]["WorkingCapital"], recon_values[year]["DeferredTaxes"], values[year]["Revenue"]]
        if any("Value" not in c for c in needed): continue
        if needed[6]["Value"] == 0: continue
        
        NetIncome = needed[0]["Value"]
        Ocf = needed[1]["Value"]
        D_and_A = needed[2]["Value"]
        Sbc = needed[3]["Value"]
        own = needed[4]["Value"]
        DeferredTaxes = needed[5]["Value"]
        implicit = NetIncome + D_and_A + Sbc + DeferredTaxes - Ocf
        residuum = implicit - own
        residuum_pct = residuum / needed[6]["Value"]
        
        reconciled[year].update({"Residuum": residuum, "Residuum_pct": residuum_pct, "Own": own, "Implicit": implicit})

    return reconciled
    
def check_recon_tolerance(flags: dict, rec_wc: dict) -> dict:
    for year in rec_wc:
        if len(rec_wc[year]) == 0: flags[year]["WorkingCapital"].append("recon_unchecked")
        elif abs(rec_wc[year]["Residuum_pct"]) > RECON_TOLERANCE: flags[year]["WorkingCapital"].append("recon_gap")
    return flags
    
if __name__ == "__main__":
    rec_values = clean_values(get_values(3, "apple", RECON_TAGS))
    values = clean_values(get_values(3, "apple", metrics))
    rec_wc = reconcile_working_capital(values, rec_values)
    flags = validate_values(values)
    print(check_recon_tolerance(flags, rec_wc))
