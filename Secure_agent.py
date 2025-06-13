# secure_agent.py (public-ready with .env support)

import os
import datetime
import time
import pandas as pd
import requests
import pytz
from ib_insync import *
from dotenv import load_dotenv

# === LOAD ENV === #
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
CSV_LOG_PATH = "gap_fill_trades.csv"

ib = IB()
ib.connect('127.0.0.1', 7497, clientId=1)

watchlist = ["RIVN", "LYFT", "WULF", "NET", "OKTA"]

def send_telegram_alert(message):
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
        requests.post(url, data=payload)

def wait_until_market_open():
    eastern = pytz.timezone('US/Eastern')
    now = datetime.datetime.now(tz=eastern)
    target = now.replace(hour=9, minute=30, second=0, microsecond=0)
    if now >= target:
        return
    time.sleep((target - now).total_seconds())

def run_gap_fill(symbol):
    contract = Stock(symbol, 'SMART', 'USD')
    ib.qualifyContracts(contract)

    bars = ib.reqHistoricalData(contract, endDateTime='', durationStr='2 D',
                                barSizeSetting='1 day', whatToShow='TRADES', useRTH=True)
    if len(bars) < 2:
        return

    prev_close = bars[-2].close
    ticker = ib.reqMktData(contract, '', False, False)
    ib.sleep(5)
    open_price = ticker.last if ticker.last else ticker.close
    ib.cancelMktData(contract)

    gap_pct = (open_price - prev_close) / prev_close
    if abs(gap_pct) < 0.01:
        return

    direction = -1 if gap_pct > 0 else 1
    entry = open_price
    target = prev_close
    stop = entry + direction * -1 * entry * 0.005

    entry_data = {
        "symbol": symbol,
        "date": str(datetime.date.today()),
        "entry": entry,
        "target": target,
        "stop": stop,
        "direction": "SHORT" if direction == -1 else "LONG",
        "gap_pct": round(gap_pct*100, 2)
    }
    msg = (f"{symbol} GAP {entry_data['direction']}\n"
           f"Gap: {entry_data['gap_pct']}%\nEntry: {entry:.2f}\nTarget: {target:.2f}\nStop: {stop:.2f}")
    send_telegram_alert(msg)

    df = pd.DataFrame([entry_data])
    df.to_csv(CSV_LOG_PATH, mode='a', header=not os.path.exists(CSV_LOG_PATH), index=False)

if __name__ == "__main__":
    wait_until_market_open()
    for ticker in watchlist:
        try:
            run_gap_fill(ticker)
        except Exception as e:
            send_telegram_alert(f"❌ {ticker} error: {str(e)}")
    ib.disconnect()
