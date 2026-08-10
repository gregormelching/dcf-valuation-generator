from parser import *

def validate_values(values: dict) -> dict:
    flags = {year: {metric_name: "" for metric_name in values[year]} for year in values}
    exceptions = ["OperatingIncome", "WorkingCapital"]
    
    for year in values:
        for metric_name in values[year]:
            if "Value" not in values[year][metric_name].keys(): flags[year][metric_name] = "missing"
            elif metric_name not in exceptions and values[year][metric_name]["Value"] < 0: flags[year][metric_name] = "negative"
            else: flags[year][metric_name] = "valid"
    return flags

if __name__ == "__main__":
    values = clean_values(get_values(1, "jpmorgan", metrics))
    print(validate_values(values))
