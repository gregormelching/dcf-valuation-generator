import yfinance as yf
import pandas as pd
from datetime import datetime
from database import insert_prices, insert_raw_download
yf.config.debug.hide_exceptions = False
import requests as rq

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
    if freq == "1mo": closes = closes.iloc[-N_MONTHS:]
    elif freq == "1wk": closes = closes.iloc[-N_WEEKS:]
    
    rows = []
    for row in closes.items():
        rows.append((datetime.strftime(row[0], "%Y-%m-%d"), float(row[1])))
    
    insert_prices(symbol, freq, rows, 1)
    
    return rows
 
def risk_free_rate():
    value = {"Risk_Free_Rate": 0, "Date": "", "Source": "FRED DGS10"}
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10"
    response = rq.get(url)
    response.raise_for_status()
    
    text = response.text.strip().splitlines()[1:]
    for row in reversed(text):
        lst = row.split(",")
        if lst[1] == "": continue
        rate = float(lst[1]) / 100
        date = datetime.strptime(lst[0], "%Y-%m-%d")
        today = datetime.now()
        if (today - date).days > RF_MAX_AGE_DAYS: raise ValueError(f"Data from {date.strftime("%Y-%m-%d")} is too old. Please try again later.")
        value.update({"Risk_Free_Rate": rate, "Date": date.strftime("%Y-%m-%d")})

        
        break
    
    return value
 
if __name__ == "__main__":
    print(risk_free_rate())