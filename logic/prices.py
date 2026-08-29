import yfinance as yf
import pandas as pd
from datetime import datetime
from database import insert_prices, insert_raw_download, insert_rates, get_rate, get_prices
yf.config.debug.hide_exceptions = False
import requests as rq

RF_SERIES = "DGS10"
RF_MAX_AGE_DAYS = 10
SYMBOLS = {
    "apple": "AAPL",
    "boeing": "BA",
    "tesla": "TSLA",
    "microsoft": "MSFT",
    "procter_gamble": "PG",
    "market": "^GSPC"
}
PERIOD = "7y"
N_MONTHS = 61
N_WEEKS = 105
MAX_SPLIT_DROP = -0.6
FREQ = {
    "1mo": "ME",
    "1wk": "W-FRI"
}
PRICE_MAX_AGE_DAYS = {
    "1mo": 45,
    "1wk": 14
}

def price_reference(symbol: str, freq: str, as_of: str) -> dict: 
    try:
        row = get_prices(symbol, freq, 1, as_of)
    except ValueError:
        raise ValueError(f"No price data for {symbol} on or before {as_of}") from None

    age = (datetime.strptime(as_of, "%Y-%m-%d") - datetime.strptime(row[0][0], "%Y-%m-%d")).days
    if age > PRICE_MAX_AGE_DAYS[freq]:
        raise ValueError(f"Price data for {symbol} from {row[0][0]} is older than {PRICE_MAX_AGE_DAYS[freq]} (age: {age}). Please update the data.")
    
    return {"Price": row[0][1], "Date": row[0][0], "Age": age, "Source": freq, "As_Of": as_of}

def fetch_prices(symbol: str, freq: str) -> list:
    df = yf.Ticker(SYMBOLS[symbol]).history(period = PERIOD, interval = "1d", auto_adjust = True, actions = False)
    if "Adj Close" in df.columns or df.empty or "Close" not in df.columns: raise ValueError(f"No data found for symbol {symbol}")
    
    insert_raw_download(symbol, "1d", df.to_csv(), yf.__version__)
    df.index = df.index.tz_localize(None)
    
    closes = df["Close"].resample(FREQ[freq]).last().dropna()
    if closes.index[-1] > df.index[-1]: closes = closes[:-1]
    
    returns = closes.pct_change().dropna()
    if returns.min() <= MAX_SPLIT_DROP: raise ValueError("Data contains too much drop")
    
    if (freq == "1wk" and len(closes) < N_WEEKS) or (freq == "1mo" and len(closes) < N_MONTHS): raise ValueError("Not enough data for the calculation")
    
    rows = []
    for row in closes.items():
        rows.append((datetime.strftime(row[0], "%Y-%m-%d"), float(row[1])))
    
    insert_prices(symbol, freq, rows, 1)
    
    return rows
 
def fetch_rates(series):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
    response = rq.get(url)
    response.raise_for_status()
    text = response.text.strip().splitlines()[1:]
    rows = []
    
    for row in text:
        lst = row.split(",")
        if lst[1] == "": continue
        else: rows.append((lst[0], float(lst[1]) / 100))
    insert_rates(series, rows)
    return rows
 
def risk_free_rate(as_of = None):
    if as_of is None: as_of = datetime.now().strftime("%Y-%m-%d")
    row = get_rate(RF_SERIES, as_of)
    if row is not None: age = (datetime.strptime(as_of, "%Y-%m-%d") - datetime.strptime(row[0], "%Y-%m-%d")).days
    if row is None or age > RF_MAX_AGE_DAYS: 
        fetch_rates(RF_SERIES)
        row = get_rate(RF_SERIES, as_of)
    if row is None: raise ValueError("Risk free rate not found for the given date. Please try again later.")
    age = (datetime.strptime(as_of, "%Y-%m-%d") - datetime.strptime(row[0], "%Y-%m-%d")).days
    if age > RF_MAX_AGE_DAYS: raise ValueError(f"Risk free rate {row[0]} has expired. Please update your data and try again later.")
    
    return {"Risk_Free_Rate": row[1], "Date": row[0], "Source": f"FRED {RF_SERIES}", "Fetched_At": row[2], "As_Of": as_of}
 
if __name__ == "__main__":
    for s in SYMBOLS:
        fetch_prices(s, "1wk")
    print(price_reference("apple", "1mo", "2026-08-19"))