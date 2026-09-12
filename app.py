import sys
from flask import request, Flask, render_template, url_for, abort
from pathlib import Path

path = Path(__file__).resolve().parent / "logic"
sys.path.insert(0, str(path))

from valuation import MC_DRAWS, ASSUMPTIONS
from wacc_calculation import N_MONTHS
from serialize import serialize_company, serialize_monte_carlo
from model import MIN_YEARS, MIN_IC_REVENUE_SHARE

START_YEAR = 2016
YEARS = 10
FREQ = "1mo"
DEFAULT_AS_OF = "2026-08-19"
MC_PANEL_DRAWS = MC_DRAWS
MONEY_SCALES = ((1e12, "T"), (1e9, "B"), (1e6, "M"))
HIST_BINS = 24
PROJECTION_UNIT = (1e6, "$ in millions")
PROJECTION_ROWS = (
    ("Revenue", "Revenue", "money"),
    ("EBIT", "EBIT", "money"),
    ("EBIT margin", "EBIT_Margin", "pct"),
    ("Tax rate", "Tax_Rate", "pct"),
    ("NOPAT", "NOPAT", "money"),
    ("D&A", "D&A", "money"),
    ("CapEx", "CapEx", "money"),
    ("dNWC", "dNWC", "money"),
    ("Reinvestment", "Reinvestment", "money"),
    ("Reinvestment rate", "Reinvestment_Rate", "pct"),
    ("FCF", "FCF", "money"),
)
DESC_MARGIN_BASES = {
    "Driver_Ratio": "Driver ratio",
    "Mean_Last_Three": "Mean of last three",
    "Last": "Last reported"
}
DESC_IMP_LEVERS = {
    "ebit_margin": "EBIT margin",
    "wacc_offset": "WACC offset",
    "terminal_growth": "Terminal growth",
    "nwc_intensity": "NWC intensity",
    "revenue_growth": "Revenue growth"
}
VERDICT_BADGE = {
    "Plausible": "is-positive",
    "Implausible": "is-negative",
    "unreachable": "is-warning",
    "no_bracket": "is-warning",
}
DESC_ROIC = {
    "Consistent": "Consistent",
    "Implicit_ROIC < WACC": "Implicit ROIC is smaller than WACC",
    "Unavailable": "Unavailable"
}
ROIC_BADGE = {
    "Consistent": "is-positive",
    "Implicit_ROIC < WACC": "is-negative",
    "Unavailable": "is-warning"
}

app = Flask(__name__)

@app.route("/", methods = ["GET"])
def index():
    return render_template("index.html")
    
@app.route("/company/<symbol>", methods = ["GET"])
def company(symbol):
    if symbol not in ASSUMPTIONS:
        abort(404)
    panel = serialize_company(symbol, START_YEAR, YEARS, FREQ, N_MONTHS, as_of = request.args.get("as_of") or DEFAULT_AS_OF)
    return render_template("company.html", panel = panel, PROJECTION_ROWS = PROJECTION_ROWS, PROJECTION_UNIT = PROJECTION_UNIT, DESC_MARGIN_BASES = DESC_MARGIN_BASES, DESC_IMP_LEVERS = DESC_IMP_LEVERS, VERDICT_BADGE = VERDICT_BADGE, DESC_ROIC = DESC_ROIC, ROIC_BADGE = ROIC_BADGE, MIN_YEARS = MIN_YEARS, MIN_IC_REVENUE_SHARE = MIN_IC_REVENUE_SHARE)

def histogram(draws, offset, bins):
    if not draws: return None
    
    lo = min(draws)
    hi = max(draws)
    
    if hi == lo: return {
            "Bins": [{
                "Lower": lo,
                "Upper": hi,
                "Count": len(draws),
                "Share": 1.0
            }],
            "Low": lo,
            "High": hi,
            "Max_Count": len(draws),
            "Market_Position": None,
            "Base_Position": None
    }
    
    width = (hi - lo) / bins
    counts = [0] * bins
    
    for v in draws:
        idx = int((v - lo) / width)
        idx = min(idx, bins - 1)
        counts[idx] += 1
    
    max_count = max(counts)
    bin_list = []
    
    for i in range(bins):
        count = counts[i]
        bin_list.append({
            "Lower": lo + i * width,
            "Upper": lo + (i + 1) * width,
            "Count": count,
            "Share": count / max_count
        })
    
    def calc_position(price):
        if price is None: return None
        
        pos = (price - lo) / (hi - lo)
        if pos < 0 or pos > 1: return None
        
        return pos
    
    mp = offset["Market_Price"]
    bv = offset["Base_Value_Per_Share"]
    
    return {
        "Bins": bin_list,
        "Low": lo,
        "High": hi,
        "Max_Count": max_count,
        "Market_Position": calc_position(mp),
        "Base_Position": calc_position(bv),
    }
    
@app.route("/company/<symbol>/monte-carlo", methods = ["GET"])
def monte_carlo(symbol):
    if symbol not in ASSUMPTIONS:
        abort(404)
    panel = serialize_monte_carlo(symbol, START_YEAR, YEARS, FREQ, N_MONTHS, as_of = request.args.get("as_of") or DEFAULT_AS_OF, draws = MC_PANEL_DRAWS)
    hist = histogram(panel["Draws"], panel["Offset"], HIST_BINS)
    return render_template("_monte_carlo.html", mc = panel, hist = hist)

@app.template_filter("pct")
def pct(p):
    if p is None: return "N/A"
    else: return f"{p*100:.2f} %"

@app.template_filter("money")
def money(m):
    if m is None: return "N/A"
    sign = "-" if m < 0 else ""
    m = abs(m)
    for factor, suffix in MONEY_SCALES:
        if m >= factor:
            return f"{sign}${m / factor:,.2f} {suffix}"
    return f"{sign}${m:,.2f}"

@app.template_filter("signed")
def signed(s):
    if s is None: return "N/A"
    elif s > 0: return f"+{s*100:.2f} %"
    else: return f"{s*100:.2f} %"

@app.template_filter("unit")
def unit(u):
    if u is None: return "N/A"
    sign = "-" if u < 0 else ""
    return f"{sign}${abs(u) / PROJECTION_UNIT[0]:,.0f}"

@app.template_filter("multiple")
def multiple(m):
    if m is None: return "N/A"
    return f"{m:.2f}x"

@app.context_processor
def inject_symbols():
    return {"symbols": sorted(ASSUMPTIONS)}

if __name__ == '__main__':
    app.run(debug = True)
