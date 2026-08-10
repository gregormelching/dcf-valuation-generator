from parser import *

def validate_values(values: dict) -> dict:
    flags = {year: {metric_name: "" for metric_name in values[year]} for year in values}
    exceptions = ["OperatingIncome", "WorkingCapital"]
    
    for year in values:
        for metric_name in values[year]:
            if "Value" not in values[year][metric_name].keys(): flags[year][metric_name] = "missing"
            else:
                if metric_name not in exceptions and values[year][metric_name]["Value"] < 0: flags[year][metric_name] = "negative"
                else: flags[year][metric_name] = "valid"
                if year-1 in values.keys() and "Value" in values[year-1][metric_name].keys():
                    if not values[year-1][metric_name]["Value"] == 0:
                        if abs((values[year][metric_name]["Value"] - values[year-1][metric_name]["Value"])/abs(values[year-1][metric_name]["Value"])) > 0.5: flags[year][metric_name] = "outlier"
                    elif abs(values[year][metric_name]["Value"] - values[year-1][metric_name]["Value"]) > 0: flags[year][metric_name] = "outlier"

    return flags

if __name__ == "__main__":
    values = clean_values(get_values(4, "apple", metrics))
    print(validate_values(values))
