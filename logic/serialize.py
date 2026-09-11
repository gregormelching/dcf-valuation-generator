from valuation import dcf_value, sensitivity_grid, sensitivity_table, nwc_scenario, implied_assumptions, plausible_ceiling, implied_horizon, WACC_OFFSETS, TERMINAL_GROWTHS, MARGIN_BASES, NWC_OFFSETS, N_MONTHS, monte_carlo, MC_PERCENTILES, MC_BORDERS, MC_DRAWS, MC_SEED, MC_MEDIAN
from database import get_data
from model import roic, effective_tax_rate

def serialize_company(symbol: str, start_year: int, years: int, freq: str, n: int, as_of: str | None = None):
    try:
        dcf = dcf_value(symbol, start_year, years, freq, n, as_of = as_of)
    except ValueError as e:
        return {"Symbol": symbol, "As_Of": as_of, "Status": str(e), "Blocks_Failed": ["Grid", "Margin_Table", "NWC_Table", "Implied", "Ceiling", "Horizon"],
                "Headline": None, "Assumptions": None, "Provenance": None, "Quality": None,
                "Projection": None, "Grid": None, "Margin_Table": None, "NWC_Table": None,
                "Implied": None, "Ceiling": None, "Horizon": None}

    blocks = {}
    failed = []
    
    for name, fn in [("Grid", sensitivity_grid), ("Margin_Table", sensitivity_table), ("NWC_Table", nwc_scenario), ("Implied", implied_assumptions), ("Ceiling", plausible_ceiling), ("Horizon", implied_horizon)]:
        try:
            blocks[name] = fn(symbol, start_year, years, freq, n, as_of = as_of)
        except ValueError:
            blocks[name] = None
            failed.append(name)
            
    data = get_data(symbol, start_year, as_of)
    roi = roic(data)
    wacc = dcf["wacc"]
    
    blocks["Headline"] = {
        "Value_Per_Share": wacc["Value_Per_Share"],
        "Market_Price": wacc["Market_Price"],
        "Upside": wacc["Upside"],
        "EV": wacc["EV"],
        "Equity_Value": wacc["Equity_Value"],
        "PV_Explicit": wacc["PV_Explicit"],
        "PV_TV": wacc["PV_TV"],
        "TV_Share": wacc["TV_Share"],
        "TV_Share_Source": wacc["TV_Share_Source"],
        "WACC": wacc["WACC"],
        "WACC_Low": dcf["wacc_low"]["WACC"],
        "WACC_High": dcf["wacc_high"]["WACC"],
    }
    
    metrics = wacc["Metrics"].split("+")
    tax = effective_tax_rate(data)

    blocks["Assumptions"] = [
        {"Label": "Revenue Growth",  "Value": wacc["Revenue_Growth"],     "Unit": "pct", "Source": wacc["Revenue_Growth_Source"]},
        {"Label": "EBIT-Startmargin", "Value": wacc["EBIT_Margin_Start"],  "Unit": "pct", "Source": wacc["Margin_Start_Source"]},
        {"Label": "EBIT-Targetmargin",  "Value": wacc["EBIT_Margin_Target"], "Unit": "pct", "Source": wacc["Margin_Base"]},
        {"Label": "D&A",             "Value": wacc["DA_Margin"],          "Unit": "pct", "Source": metrics[0]},
        {"Label": "CapEx",           "Value": wacc["CapEx_Margin"],       "Unit": "pct", "Source": metrics[1]},
        {"Label": "NWC",             "Value": wacc["NWC_Intensity"],      "Unit": "pct", "Source": metrics[2]},
        {"Label": "Terminal Growth", "Value": wacc["Terminal_Growth"],    "Unit": "pct", "Source": wacc["Terminal_Growth_Source"]},
        {"Label": "Terminal ROIC",   "Value": wacc["Terminal_ROIC"],      "Unit": "pct", "Source": wacc["ROIC_Source"]},
        {"Label": "WACC",            "Value": wacc["WACC"],               "Unit": "pct", "Source": "+".join(wacc["Source"].split("+")[:-2])},
        {"Label": "Taxrate",      "Value": tax["Effective_Tax_Rate"],  "Unit": "pct", "Source": tax["Source"]},
    ]
    
    blocks["Provenance"] = {
        "Data_Filed": wacc["Data_Filed"],
        "Price_Date": wacc["Price_Date"],
        "Price_Age_Days": wacc["Price_Age_Days"],
        "RF_Date": wacc["RF_Date"],
        "COD_Basis": wacc["COD_Basis"],
        "COD_Alternative": wacc["COD_Alternative"],
        "COD_Evidence": wacc["COD_Evidence"],
        "MCap_Price_Date": wacc["MCap_Price_Date"],
        "MCap_Price_Age_Days": wacc["MCap_Price_Age_Days"],
        "Stub_Years": wacc["Stub_Years"],
        "Source": wacc["Source"]
    }
    
    blocks["Quality"] = {
        "ROIC_Consistency": wacc["ROIC_Consistency"],
        "Implicit_ROIC": wacc["Implicit_ROIC"],
        "Capital_Turnover": wacc["Capital_Turnover"],
        "Implied_Multiple": wacc["Implied_Multiple"],
        "Implied_Multiple_Source": wacc["Implied_Multiple_Source"],
        "IC_Last": roi["IC_Last"],
        "IC_Last_Year": roi["IC_Last_Year"],
        "ROIC_Median": roi["ROIC_Median"],
        "ROIC_Last": roi["ROIC_Last"],
        "ROIC_n": roi["n"],
        "ROIC_Source": roi["Source"],
        "ROIC_Excluded_Small_IC": roi["Excluded_Small_IC"]
    }
    
    proj = wacc["Projection"]
    last = max(proj)

    blocks["Projection"] = [
        {"Year": year, "Is_Terminal": year == last,
        "Revenue": proj[year]["Revenue"], "EBIT": proj[year]["EBIT"], "EBIT_Margin": proj[year]["EBIT_Margin"],
        "NOPAT": proj[year]["NOPAT"], "Tax_Rate": proj[year]["Tax_Rate"], "D&A": proj[year]["D&A"],
        "CapEx": proj[year]["CapEx"], "dNWC": proj[year]["dNWC"], "Reinvestment": proj[year]["Reinvestment"],
        "Reinvestment_Rate": proj[year]["Reinvestment_Rate"], "FCF": proj[year]["FCF"]}
        for year in sorted(proj)
    ]
    
    if blocks["Grid"] is not None:
        blocks["Grid"] = {
            "Offsets": list(WACC_OFFSETS),
            "Growths": list(TERMINAL_GROWTHS),
            "Rows": [[blocks["Grid"][(o, g)] for g in TERMINAL_GROWTHS] for o in WACC_OFFSETS],
        }
        
    if blocks["Margin_Table"] is not None:
        blocks["Margin_Table"] = [blocks["Margin_Table"][mb] for mb in MARGIN_BASES]
    if blocks["NWC_Table"] is not None:
        blocks["NWC_Table"] = [blocks["NWC_Table"][o] for o in NWC_OFFSETS]
    
    return {"Symbol": symbol, "As_Of": wacc["As_Of"], "Status": "calculated", "Blocks_Failed": failed, **blocks}

def serialize_monte_carlo(symbol: str, start_year: int, years: int, freq: str, n: int, as_of: str | None = None, draws: int = MC_DRAWS, seed: int = MC_SEED):
    try:
        mc = monte_carlo(symbol, start_year, years, freq, n, as_of = as_of, draws = draws, seed = seed)
    except ValueError as e:
        return {"Symbol": symbol, "As_Of": as_of, "Status": str(e), "Distribution": None, "Offset": None, "Inputs": None, "Reliability": None, "Draws": None}
    
    percentiles = mc["Percentiles"]
    distribution = None
    median = None

    if percentiles is not None:
        distribution = [{"Percentile": p, "Value": percentiles[p]} for p in MC_PERCENTILES]
        median = percentiles[MC_MEDIAN]
        
    margin_low, margin_mode, margin_high = mc["Margin_Range"]
    
    return {
        "Symbol": symbol,
        "As_Of": as_of,
        "Status": "calculated",
        "Distribution": distribution,
        "Offset": {
            "Base_Value_Per_Share": mc["Base_Value_Per_Share"],
            "Market_Price": mc["Market_Price"],
            "Median": median,
            "Median_Offset": mc["Median_Offset"],
            "Mode_Position": mc["Mode_Position"],
            "P_Above_Market": mc["P_Above_Market"],
            "Mean": mc["Mean"],
        },
        "Inputs": {
            "WACC": mc["WACC"],
            "WACC_Sigma": mc["WACC_Sigma"],
            "Margin_Low": margin_low,
            "Margin_Mode": margin_mode,
            "Margin_High": margin_high,
            "Margin_Bases_Used": mc["Margin_Bases_Used"],
            "Terminal_Growth_Borders": list(MC_BORDERS),
            "Draws_Requested": draws,
            "Seed": seed,
        },
        "Reliability": {
            "Draws_OK": mc["Draws_OK"],
            "Draws_Failed": mc["Draws_Failed"],
            "Failures": mc["Failures"],
        },
        "Draws": mc["Draws"],
    }


if __name__ == "__main__":
    print(serialize_company("apple", 2016, 10, "1mo", N_MONTHS, as_of = "2026-08-19"))
    print(serialize_monte_carlo("apple", 2016, 10, "1mo", N_MONTHS, as_of = "2026-08-19", draws = 200))