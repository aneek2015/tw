import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from FinMind.data import DataLoader
from datetime import datetime, timedelta
import asyncio
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
import warnings

# 忽略憑證警告
warnings.filterwarnings("ignore", message="Unverified HTTPS request")

# --- 1. 定義單一來源擷取邏輯 (加上重試機制) ---

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
@st.cache_data(ttl=900, show_spinner=False)
def get_yahoo_data_sync(ticker_symbol):
    return _get_yahoo_data_sync_inner(ticker_symbol)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _get_yahoo_data_sync_inner(ticker_symbol):
    try:
        stock = yf.Ticker(ticker_symbol)
        df = stock.history(period="1y")
        
        # 容錯: 如果上市沒有資料，嘗試上櫃
        if df.empty:
            ticker_symbol = ticker_symbol.replace(".TW", ".TWO")
            stock = yf.Ticker(ticker_symbol)
            df = stock.history(period="1y")
        
        if df.empty: return None, None, None, None, None, None
        
        # 時區處理
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        
        info = stock.info
        divs = stock.dividends
        if divs.index.tz is not None:
            divs.index = divs.index.tz_localize(None)

        try: financials = stock.financials
        except: financials = pd.DataFrame()
        
        try: cashflow = stock.cashflow
        except: cashflow = pd.DataFrame()

        return df, info, ticker_symbol, divs, financials, cashflow
    except Exception as e:
        print(f"yfinance error for {ticker_symbol}: {e}")
        return None, None, None, None, None, None

@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=3))
def get_finmind_chips_sync(raw_ticker):
    try:
        dl = DataLoader()
        start_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
        df = dl.taiwan_stock_institutional_investors(
            stock_id=raw_ticker,
            start_date=start_date
        )
        if df.empty: return None
        
        df['net'] = df['buy'] - df['sell']
        df_daily = df.groupby('date')[['buy', 'sell', 'net']].sum().reset_index()
        return df_daily
    except Exception as e:
        print(f"FinMind API error for {raw_ticker}: {e}")
        return None

# 非同步 TWSE 請求
async def fetch_twse_data_async(raw_ticker):
    url = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
    try:
        async with httpx.AsyncClient(verify=False, timeout=10) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data_list = resp.json()
                target = next((x for x in data_list if x["Code"] == raw_ticker), None)
                if target:
                    def clean(v): 
                        try: return float(v.replace(",", ""))
                        except: return 0.0
                    return {
                        "source": "TWSE (官方)",
                        "PE": clean(target["PEratio"]),
                        "Yield": clean(target["DividendYield"]),
                        "PB": clean(target["PBratio"])
                    }
    except Exception as e:
        print(f"TWSE API error for {raw_ticker}: {e}")
    
    # 備案 (可後續補上 TPEx 上櫃嘗試)
    return None

# --- 2. 封裝外部非同步層以供 Streamlit (同步環境) 呼叫 ---

async def _fetch_all_data_async(raw_ticker, yf_ticker_name):
    """平行執行網路請求"""
    loop = asyncio.get_event_loop()
    
    # 使用 run_in_executor 讓同步的 (YF, FinMind) 能被非同步等待
    task_yf = loop.run_in_executor(None, _get_yahoo_data_sync_inner, yf_ticker_name)
    task_finmind = loop.run_in_executor(None, get_finmind_chips_sync, raw_ticker)
    task_twse = asyncio.create_task(fetch_twse_data_async(raw_ticker))
    
    # 並發等待三個 API 回應
    results = await asyncio.gather(task_yf, task_finmind, task_twse)
    return results

@st.cache_data(ttl=900, show_spinner=False)
def fetch_all_data(raw_ticker, yf_ticker_name):
    """
    提供給 Streamlit 的進入點。
    由於 Streamlit 原本並非非同步環境，會以 asyncio.run() 包裝執行。
    """
    try:
        # 如果已經在事件迴圈中 (如 pytest)，需要特別處理 (nest_asyncio)
        import nest_asyncio
        nest_asyncio.apply()
    except ImportError:
        pass
    
    return asyncio.run(_fetch_all_data_async(raw_ticker, yf_ticker_name))
