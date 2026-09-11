import sys
from flask import request, Flask, render_template, url_for, abort
from pathlib import Path

path = Path(__file__).resolve().parent / "logic"
sys.path.insert(0, str(path))

from valuation import MC_DRAWS, ASSUMPTIONS
from wacc_calculation import N_MONTHS
from serialize import serialize_company

START_YEAR = 2016
YEARS = 10
FREQ = "1mo"
DEFAULT_AS_OF = "2026-08-19"
MC_PANEL_DRAWS = MC_DRAWS
MONEY_SCALES = ((1e12, "T"), (1e9, "B"), (1e6, "M"))

app = Flask(__name__)

@app.route("/", methods = ["GET"])
def index():
    return render_template("index.html")
    
@app.route("/company/<symbol>", methods = ["GET"])
def company(symbol):
    if symbol not in ASSUMPTIONS:
        abort(404)
    panel = serialize_company(symbol, START_YEAR, YEARS, FREQ, N_MONTHS, as_of = request.args.get("as_of") or DEFAULT_AS_OF)
    return render_template("company.html", panel = panel)

@app.template_filter("pct")
def pct(p):
    if p is None: return "N/A"
    else: return f"{p*100:.2f} %"

@app.template_filter("money")
def money(m):
    if m is None: return "N/A"
    for factor, suffix in MONEY_SCALES:
        if abs(m) >= factor:
            return f"${m / factor:,.2f} {suffix}"
    return f"${m:,.2f}"

@app.template_filter("signed")
def signed(s):
    if s is None: return "N/A"
    elif s > 0: return f"+{s*100:.2f} %"
    else: return f"{s*100:.2f} %"

@app.context_processor
def inject_symbols():
    return {"symbols": sorted(ASSUMPTIONS)}

if __name__ == '__main__':
    app.run(debug = True)
