import streamlit as st
import yfinance as yf
from FinMind.data import DataLoader
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import time
import sqlite3
import requests
import threading
from datetime import datetime, timedelta

# ---------------------------------------------------------
# 1. 頁面配置與深色系 CSS
# ---------------------------------------------------------
st.set_page_config(page_title="簡易台股判斷(Pro)", layout="wide")

st.markdown("""
    <style>
    /* 全域設定 */
    .big-font { font-size:28px !important; font-weight: bold; color: #FFFFFF; }
    .sub-font { font-size:16px !important; color: #DDDDDD; }
    
    /* 資訊卡片容器 */
    .status-card {
        background-color: #262730;
        padding: 25px;
        border-radius: 12px;
        border: 1px solid #444;
        margin-bottom: 25px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }

    /* 健檢專用卡片 */
    .health-card {
        background-color: #1E1E1E;
        padding: 20px;
        border-radius: 10px;
        border-left: 5px solid #ff4b4b;
        margin-bottom: 15px;
    }
    
    /* 訊號燈與標籤樣式 */
    .signal-box {
        display: inline-block;
        padding: 5px 15px;
        border-radius: 8px;
        font-weight: bold;
        font-size: 20px;
        margin-top: 10px;
        border: 1px solid rgba(255,255,255,0.2);
    }
    
    /* 趨勢顏色定義 (紅漲綠跌) */
    .sig-buy { background-color: #590000; color: #ff4b4b; border-color: #ff4b4b; } 
    .sig-sell { background-color: #003300; color: #00c07c; border-color: #00c07c; } 
    .sig-hold { background-color: #002244; color: #4e8cff; border-color: #4e8cff; } 
    .sig-wait { background-color: #333333; color: #aaaaaa; border-color: #aaaaaa; } 

    .trend-up { color: #ff4b4b !important; font-weight: bold; }
    .trend-down { color: #00c07c !important; font-weight: bold; }
    .trend-neutral { color: #aaaaaa !important; font-weight: bold; }
    
    /* 說明區塊 */
    .logic-box {
        background-color: #1E1E1E;
        padding: 15px;
        border-left: 4px solid #FFD700;
        margin-bottom: 10px;
        color: #E0E0E0;
    }
    </style>
    """, unsafe_allow_html=True)

# ---------------------------------------------------------
# 2. 資料庫管理模組
# ---------------------------------------------------------

class HistoryDB:
    def __init__(self, db_name="stock_history.db"):
        self.db_name = db_name
        self.lock = threading.Lock()
        self.init_db()

    def init_db(self):
        with self.lock:
            conn = sqlite3.connect(self.db_name, check_same_thread=False, timeout=10)
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS history
                         (id INTEGER PRIMARY KEY AUTOINCREMENT,
                          analysis_date TEXT,
                          ticker TEXT,
                          stock_name TEXT,
                          close_price REAL,
                          verdict TEXT,
                          reason TEXT,
                          eps REAL,
                          roe REAL,
                          pe REAL)''')
            conn.commit()
            conn.close()

    def add_record(self, ticker, name, price, verdict, reason, eps, roe, pe):
        with self.lock:
            conn = sqlite3.connect(self.db_name, check_same_thread=False, timeout=10)
            c = conn.cursor()
            date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            eps = eps if eps else 0.0
            roe = roe if roe else 0.0
            pe = pe if pe else 0.0
            c.execute("INSERT INTO history (analysis_date, ticker, stock_name, close_price, verdict, reason, eps, roe, pe) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                      (date_str, ticker, name, price, verdict, reason, eps, roe, pe))
            conn.commit()
            conn.close()

    def get_all_records(self):
        with self.lock:
            conn = sqlite3.connect(self.db_name, check_same_thread=False, timeout=10)
            df = pd.read_sql_query("SELECT * FROM history ORDER BY id DESC", conn)
            conn.close()
            return df

    def delete_record(self, record_id):
        with self.lock:
            conn = sqlite3.connect(self.db_name, check_same_thread=False, timeout=10)
            c = conn.cursor()
            c.execute("DELETE FROM history WHERE id=?", (record_id,))
            conn.commit()
            conn.close()

db = HistoryDB()

# ---------------------------------------------------------
# 3. 三引擎核心數據處理 (整合快取與時區修復)
# ---------------------------------------------------------

@st.cache_data(ttl=300)
def get_yahoo_data(ticker_symbol):
    try:
        stock = yf.Ticker(ticker_symbol)
        df = stock.history(period="1y")
        
        if df.empty:
            ticker_symbol = ticker_symbol.replace(".TW", ".TWO")
            stock = yf.Ticker(ticker_symbol)
            df = stock.history(period="1y")
        
        if df.empty: return None, None, None, None, None, None
        
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

@st.cache_data(ttl=1800)
def get_twse_data(raw_ticker):
    try:
        url = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
        resp = requests.get(url, timeout=3)
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
    return None

@st.cache_data(ttl=3600)
def get_finmind_chips(raw_ticker):
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

class StockAnalyzer:
    def __init__(self, ticker_input):
        self.raw_ticker = ticker_input.strip().upper().replace(".TW", "").replace(".TWO", "")
        self.yf_ticker_name = f"{self.raw_ticker}.TW"
        self.price_history = pd.DataFrame()
        self.stock_name = "未知"
        self.info = {}
        self.chips_df = pd.DataFrame()
        self.dividends = pd.Series(dtype=float)
        self.financials = pd.DataFrame()
        self.cashflow = pd.DataFrame()

    def run_analysis(self):
        df, info, real_ticker, divs, financials, cashflow = get_yahoo_data(self.yf_ticker_name)
        if df is None: return False
        
        self.price_history = df
        self.info = info
        self.yf_ticker_name = real_ticker 
        self.stock_name = info.get('longName', info.get('shortName', self.raw_ticker))
        self.dividends = divs
        self.financials = financials
        self.cashflow = cashflow
        
        self.chips_df = get_finmind_chips(self.raw_ticker)
        
        return True

    def calculate_technicals(self):
        df = self.price_history.copy()
        if len(df) < 60: return None

        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['MA60'] = df['Close'].rolling(window=60).mean()
        df['MA20_Slope'] = df['MA20'].diff()
        df['MA60_Slope'] = df['MA60'].diff()

        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, adjust=False).mean()
        loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))

        exp12 = df['Close'].ewm(span=12, adjust=False).mean()
        exp26 = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD_DIF'] = exp12 - exp26
        df['MACD_Signal'] = df['MACD_DIF'].ewm(span=9, adjust=False).mean()
        df['MACD_Hist'] = df['MACD_DIF'] - df['MACD_Signal']
        
        df['BB_Mid'] = df['Close'].rolling(window=20).mean()
        df['BB_Std'] = df['Close'].rolling(window=20).std()
        df['BB_Up'] = df['BB_Mid'] + (2 * df['BB_Std'])
        df['BB_Low'] = df['BB_Mid'] - (2 * df['BB_Std'])

        return df

    def get_fundamentals(self):
        twse_val = get_twse_data(self.raw_ticker)
        
        pe = twse_val['PE'] if twse_val else self.info.get('trailingPE', 0)
        pb = twse_val['PB'] if twse_val else self.info.get('priceToBook', 0)
        dy = twse_val['Yield'] if twse_val else (self.info.get('dividendYield', 0) * 100 if self.info.get('dividendYield') else 0)
        source = twse_val['source'] if twse_val else "Yahoo Finance (預估)"

        net_buy_5d = 0
        if self.chips_df is not None and not self.chips_df.empty:
            net_buy_5d = self.chips_df.tail(5)['net'].sum() // 1000

        vol_ma5 = 0
        if not self.price_history.empty and len(self.price_history) >= 5:
            vol_ma5 = self.price_history['Volume'].rolling(5).mean().iloc[-1]
            
        vol_trend = "縮量"
        if not self.price_history.empty and self.price_history['Volume'].iloc[-1] > vol_ma5:
            vol_trend = "放量"

        inst_hold = self.info.get('heldPercentInstitutions', 0)
        if inst_hold: inst_hold *= 100

        dividend_data = None
        if self.dividends is not None and not self.dividends.empty:
            cutoff_date = datetime.now() - timedelta(days=365*5)
            recent_divs = self.dividends[self.dividends.index > cutoff_date]
            last_10 = self.dividends.sort_index(ascending=False).head(10)
            avg_div = last_10.mean() if not last_10.empty else 0
            dividend_data = {'history': last_10, 'count_5y': len(recent_divs), 'avg': avg_div}

        return {
            "valid": True,
            "metrics": {
                'EPS': self.info.get('trailingEps', 0) if self.info.get('trailingEps') is not None else 0,
                'ROE': self.info.get('returnOnEquity', 0) * 100 if self.info.get('returnOnEquity') is not None else 0,
                'RevGrowth': self.info.get('revenueGrowth', 0) * 100 if self.info.get('revenueGrowth') is not None else 0,
                'DebtRatio': self.info.get('debtToEquity', 0) if self.info.get('debtToEquity') is not None else 0
            },
            "valuation": {'PE': pe, 'PB': pb, 'Yield': dy, 'source': source},
            "chips": {'net_buy_5d': net_buy_5d, 'vol_trend': vol_trend, 'inst_hold': inst_hold},
            "rates": {
                'gross': self.info.get('grossMargins', 0)*100 if self.info.get('grossMargins') is not None else 0,
                'op': self.info.get('operatingMargins', 0)*100 if self.info.get('operatingMargins') is not None else 0,
                'net': self.info.get('profitMargins', 0)*100 if self.info.get('profitMargins') is not None else 0
            },
            "dividend": dividend_data
        }

    def run_backtest(self, strategy_type="MA_Cross"):
        df = self.calculate_technicals()
        if df is None: return None

        df['Position'] = 0
        df['Signal'] = 0
        
        if "MA_Cross" in strategy_type:
            df['Signal'] = np.where(df['MA5'] > df['MA20'], 1, -1)
            df['Position'] = np.where(df['MA5'] > df['MA20'], 1, 0)
        elif "RSI_Reversal" in strategy_type:
            conditions = [(df['RSI'] < 30), (df['RSI'] > 70)]
            choices = [1, 0]
            df['Position'] = np.select(conditions, choices, default=np.nan)
            df['Position'] = df['Position'].ffill().fillna(0)

        df['Daily_Ret'] = df['Close'].pct_change()
        df['Strategy_Ret'] = df['Position'].shift(1) * df['Daily_Ret']
        df['Cum_Ret'] = (1 + df['Strategy_Ret']).cumprod()
        df['Benchmark_Ret'] = (1 + df['Daily_Ret']).cumprod()
        
        if df['Cum_Ret'].empty: return None
        
        total_ret = (df['Cum_Ret'].iloc[-1] - 1) * 100
        benchmark_ret = (df['Benchmark_Ret'].iloc[-1] - 1) * 100
        
        has_pos = df[df['Position'].shift(1) == 1]
        win_rate = 0
        if len(has_pos) > 0:
            win_rate = len(has_pos[has_pos['Strategy_Ret'] > 0]) / len(has_pos) * 100
        
        return {
            'total_return': total_ret,
            'benchmark_return': benchmark_ret,
            'win_rate': win_rate,
            'equity_curve': df[['Cum_Ret', 'Benchmark_Ret']]
        }

    def determine_verdict(self, tech_df, fund_data):
        if tech_df is None: return "資料不足", "sig-wait", "K線數據過少"
        last = tech_df.iloc[-1]
        close = last['Close']
        ma20 = last['MA20']
        ma60 = last['MA60']
        rsi = last['RSI']
        slope = last['MA60_Slope']
        
        if rsi > 80: return "🟢 獲利了結 (Sell)", "sig-sell", "RSI 過熱 (>80)"
        if close < ma60 and slope < 0: return "🟢 獲利了結 (Sell)", "sig-sell", "跌破季線且下彎"

        score = 0
        if fund_data['valid']:
            if fund_data['metrics']['EPS'] > 0: score += 1
            if fund_data['valuation']['PE'] and 0 < fund_data['valuation']['PE'] < 20: score += 1
            if fund_data['metrics']['RevGrowth'] > 0: score += 1

        bull = close > ma20 and close > ma60
        momentum = last['MACD_Hist'] > 0
        
        if bull and momentum and score >= 2: return "🔴 適合買入 (Buy)", "sig-buy", "趨勢多頭 + 基本面佳"
        if bull: return "🔵 繼續持有 (Hold)", "sig-hold", "股價沿均線上漲"
        return "⚪ 暫時觀望 (Wait)", "sig-wait", "趨勢不明或體質轉弱"

# --- ETF 專用分析器 (基於報告優化) ---
class ETFAnalyzer:
    def __init__(self, ticker_input):
        self.raw_ticker = ticker_input.strip().upper().replace(".TW", "").replace(".TWO", "")
        self.yf_ticker_name = f"{self.raw_ticker}.TW"
        self.ticker = yf.Ticker(self.yf_ticker_name)
        self.data = {}
    
    def fetch_data(self):
        try:
            # 1. 價格與基礎資訊
            df, info, _, _, _, _ = get_yahoo_data(self.yf_ticker_name)
            if df is None or info is None: return False
            
            # 2. 持股與權重
            try:
                holdings = self.ticker.funds_data.top_holdings
                holdings_df = pd.DataFrame(holdings) if holdings is not None and not holdings.empty else pd.DataFrame()
                sector_weights = self.ticker.funds_data.sector_weightings
            except:
                holdings_df = pd.DataFrame()
                sector_weights = {}

            # 3. 關鍵指標計算 (依據報告)
            # AUM (Net Assets)
            total_assets = info.get('totalAssets', 0)
            
            # 費用率 (Expense Ratio) - YF 欄位可能為 annualReportExpenseRatio
            expense_ratio = info.get('annualReportExpenseRatio', 0)
            if expense_ratio is None: expense_ratio = 0
            
            # 折溢價 (Premium/Discount)
            # YF info 有時有 navPrice，若無則無法精確計算
            current_price = df['Close'].iloc[-1]
            nav_price = info.get('navPrice')
            premium_discount = 0
            if nav_price and nav_price > 0:
                premium_discount = ((current_price - nav_price) / nav_price) * 100

            # 4. ETF 類型判斷 (根據名稱)
            name = info.get('longName', self.raw_ticker)
            etf_type = "一般市值型"
            if "高股息" in name or "高息" in name: etf_type = "高股息型"
            elif "債" in name: etf_type = "債券型"
            elif "50" in name and "反" not in name: etf_type = "市值型"

            self.data = {
                'price_history': df,
                'info': info,
                'holdings': holdings_df,
                'sectors': sector_weights,
                'name': name,
                'metrics': {
                    'AUM': total_assets,
                    'ExpenseRatio': expense_ratio,
                    'Premium': premium_discount,
                    'NAV': nav_price,
                    'Yield': info.get('yield', 0),
                    'Type': etf_type
                }
            }
            return True
        except Exception as e:
            print(f"ETF Data Error: {e}")
            return False

    def generate_report(self):
        """根據報告邏輯生成評語"""
        m = self.data['metrics']
        report = []
        
        # 1. 規模檢核
        if m['AUM'] > 2000000000: # 20億
            report.append("✅ **規模安全**：資產大於 20 億，無下市風險，流動性通常較佳。")
        else:
            report.append("⚠️ **規模偏小**：資產小於 20 億，需留意流動性與清算風險。")
            
        # 2. 成本檢核
        if m['ExpenseRatio'] < 0.005: # 0.5%
            report.append("✅ **成本低廉**：內扣費用 < 0.5%，適合長期持有。")
        elif m['ExpenseRatio'] > 0.01:
            report.append("❌ **成本過高**：內扣費用 > 1%，長期持有將嚴重侵蝕複利，建議重新評估。")
        else:
            report.append("ℹ️ **成本尚可**：費用介於 0.5% - 1% 之間。")

        # 3. 折溢價檢核
        if abs(m['Premium']) < 0.3:
            report.append(f"✅ **價格合理**：折溢價 {m['Premium']:.2f}% 在合理範圍 (±0.3%)。")
        elif m['Premium'] > 1.0:
            report.append(f"⚠️ **溢價過高**：目前溢價 {m['Premium']:.2f}%，買進成本偏高，建議等待收斂。")
        
        # 4. 策略檢核
        if m['Type'] == "高股息型":
            report.append("ℹ️ **高股息提醒**：此類 ETF 週轉率通常較高，且需留意二代健保補充保費 (單筆>2萬或全年累計) 的稅務影響。")
        
        return report

# ---------------------------------------------------------
# 4. UI 邏輯控制
# ---------------------------------------------------------

if 'analysis_result' not in st.session_state:
    st.session_state['analysis_result'] = None
if 'etf_result' not in st.session_state:
    st.session_state['etf_result'] = None

with st.sidebar:
    st.title("功能選單")
    page = st.radio("前往頁面", ["📊 深度個股儀表板", "📊 ETF 戰情室", "🗄️ 歷史資料庫", "📖 策略邏輯白皮書"])
    
    st.markdown("---")
    if page == "📊 深度個股儀表板":
        st.header("🔍 個股搜尋")
        ticker_input = st.text_input("輸入代號 (如 2330)", "2330", key="stock_input")
        run_btn = st.button("啟動全域掃描", type="primary", key="stock_btn")
    elif page == "📊 ETF 戰情室":
        st.header("🔍 ETF 搜尋")
        etf_input = st.text_input("輸入代號 (如 0050)", "0050", key="etf_input")
        etf_btn = st.button("分析 ETF", type="primary", key="etf_btn")

# --- 頁面: 個股儀表板 ---
if page == "📊 深度個股儀表板":
    st.title("🕵️ 台股 AI 深度戰情室 (Pro)")

    if run_btn:
        progress_text = "[0%] 初始化三引擎架構..."
        my_bar = st.progress(0, text=progress_text)
        
        analyzer = StockAnalyzer(ticker_input)
        
        my_bar.progress(20, text="[20%] YF+FinMind: 下載數據中 (已啟用快取)...")
        success = analyzer.run_analysis()
        
        if not success:
            my_bar.progress(100, text="[100%] 查無資料")
            st.error(f"❌ 找不到代號 {ticker_input}")
            st.session_state['analysis_result'] = None
        else:
            my_bar.progress(50, text="[50%] 運算技術指標與籌碼分布...")
            tech_df = analyzer.calculate_technicals()
            fund_data = analyzer.get_fundamentals()
            
            my_bar.progress(80, text="[80%] 執行策略回測模擬...")
            backtest_res = analyzer.run_backtest("MA_Cross")
            
            my_bar.progress(95, text="[95%] AI 綜合決策...")
            verdict, verdict_class, verdict_reason = analyzer.determine_verdict(tech_df, fund_data)
            time.sleep(0.2)
            
            my_bar.progress(100, text="[100%] 完成！")
            time.sleep(0.2)
            my_bar.empty()

            st.session_state['analysis_result'] = {
                'ticker': analyzer.raw_ticker,
                'name': analyzer.stock_name,
                'price_history': analyzer.price_history,
                'chips_df': analyzer.chips_df,
                'tech_df': tech_df,
                'fund_data': fund_data,
                'backtest_res': backtest_res,
                'verdict': verdict,
                'verdict_class': verdict_class,
                'verdict_reason': verdict_reason,
                'analyzer': analyzer
            }

    if st.session_state['analysis_result']:
        data = st.session_state['analysis_result']
        analyzer = data['analyzer']
        
        stock_name = data['name']
        current_price = data['price_history']['Close'].iloc[-1]
        prev_price = data['price_history']['Close'].iloc[-2]
        change = current_price - prev_price
        pct = (change / prev_price) * 100
        trend_class = "trend-up" if change > 0 else ("trend-down" if change < 0 else "trend-neutral")
        sign = "+" if change > 0 else ""

        st.markdown(f"""
        <div class="status-card">
            <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                <div>
                    <div class="sub-font">股票代號 | 名稱</div>
                    <div class="big-font" style="margin-bottom: 5px;">{data['ticker']} | {stock_name}</div>
                    <div>
                        <span style="font-size: 42px; line-height: 1;" class="{trend_class}">{current_price:.2f}</span>
                        <span style="font-size: 22px; margin-left: 15px;" class="{trend_class}">
                            {sign}{change:.2f} ({sign}{pct:.2f}%)
                        </span>
                    </div>
                    <div class="sub-font" style="margin-top: 5px; font-size: 12px;">資料來源: YF / FinMind / TWSE (Auto-Cached)</div>
                </div>
                <div style="text-align: right; max-width: 400px;">
                    <div class="sub-font">AI 投資總結</div>
                    <div class="signal-box {data['verdict_class']}">{data['verdict']}</div>
                    <div style="margin-top: 8px; color: #BBB; font-size: 14px;">
                        <i>"{data['verdict_reason']}"</i>
                    </div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        col_save, col_dummy = st.columns([1, 4])
        with col_save:
            if st.button("💾 儲存此筆分析"):
                m = data['fund_data'].get('metrics', {})
                v = data['fund_data'].get('valuation', {})
                db.add_record(
                    ticker=data['ticker'], name=data['name'], price=current_price, 
                    verdict=data['verdict'], reason=data['verdict_reason'], 
                    eps=m.get('EPS'), roe=m.get('ROE'), pe=v.get('PE')
                )
                st.success(f"✅ 已存檔！")

        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📊 專業K線", "🏢 基本面", "🌊 估值河流", "🏥 體質健檢", "🎯 投資分析", "🧪 策略回測"])

        with tab1:
            tech_df = data['tech_df']
            chips_df = data['chips_df']
            
            fig = make_subplots(rows=4, cols=1, shared_xaxes=True, 
                                vertical_spacing=0.03, 
                                row_heights=[0.5, 0.15, 0.15, 0.2],
                                subplot_titles=(f'{stock_name} 股價走勢', '成交量', '法人買賣超 (FinMind)', 'RSI 強弱'))

            fig.add_trace(go.Candlestick(x=tech_df.index,
                            open=tech_df['Open'], high=tech_df['High'],
                            low=tech_df['Low'], close=tech_df['Close'], name='K線',
                            increasing_line_color='#ff4b4b', decreasing_line_color='#00c07c'), row=1, col=1)
            fig.add_trace(go.Scatter(x=tech_df.index, y=tech_df['MA20'], name='MA20', line=dict(color='#FFD700', width=1)), row=1, col=1)
            fig.add_trace(go.Scatter(x=tech_df.index, y=tech_df['MA60'], name='MA60', line=dict(color='#FF4500', width=1)), row=1, col=1)
            fig.add_trace(go.Scatter(x=tech_df.index, y=tech_df['BB_Up'], name='BB Up', line=dict(color='rgba(255,255,255,0.3)', width=1, dash='dot'), showlegend=False), row=1, col=1)
            fig.add_trace(go.Scatter(x=tech_df.index, y=tech_df['BB_Low'], name='BB Low', line=dict(color='rgba(255,255,255,0.3)', width=1, dash='dot'), showlegend=False), row=1, col=1)

            colors_vol = ['#ff4b4b' if c >= o else '#00c07c' for c, o in zip(tech_df['Close'], tech_df['Open'])]
            fig.add_trace(go.Bar(x=tech_df.index, y=tech_df['Volume'], name='Volume', marker_color=colors_vol), row=2, col=1)

            if chips_df is not None and not chips_df.empty:
                chips_df['date'] = pd.to_datetime(chips_df['date'])
                
                chips_date_naive = chips_df['date'].dt.tz_localize(None) if chips_df['date'].dt.tz is not None else chips_df['date']
                tech_idx_naive = tech_df.index.tz_localize(None) if tech_df.index.tz is not None else tech_df.index
                
                mask = (chips_date_naive >= tech_idx_naive[0]) & (chips_date_naive <= tech_idx_naive[-1])
                sliced_chips = chips_df.loc[mask]
                
                colors_chips = ['#ff4b4b' if v > 0 else '#00c07c' for v in sliced_chips['net']]
                fig.add_trace(go.Bar(x=sliced_chips['date'], y=sliced_chips['net'], name='法人淨買賣', marker_color=colors_chips), row=3, col=1)
            else:
                fig.add_annotation(text="無籌碼數據", xref="x domain", yref="y domain", x=0.5, y=0.5, row=3, col=1)

            fig.add_trace(go.Scatter(x=tech_df.index, y=tech_df['RSI'], name='RSI', line=dict(color='#BA55D3')), row=4, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="red", row=4, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="green", row=4, col=1)

            fig.update_layout(template="plotly_dark", height=800, xaxis_rangeslider_visible=False, hovermode="x unified")
            st.plotly_chart(fig, use_container_width=True)

        with tab2:
            fd = data['fund_data']
            if fd['valid']:
                m = fd['metrics']
                r = fd['rates']
                c1, c2, c3, c4 = st.columns(4)
                
                eps_val = m.get('EPS')
                c1.metric("EPS (TTM)", f"{eps_val:.2f} 元" if eps_val is not None else "N/A")
                c2.metric("ROE", f"{m.get('ROE', 0):.2f}%")
                c3.metric("營收年增率", f"{m.get('RevGrowth', 0):.2f}%", delta_color="inverse")
                c4.metric("負債比率", f"{m.get('DebtRatio', 0):.2f}", delta_color="inverse")
                
                st.markdown("---")
                st.subheader("📊 財報三率 (YF)")
                rc1, rc2, rc3 = st.columns(3)
                rc1.metric("毛利率", f"{r['gross']:.2f}%")
                rc2.metric("營利率", f"{r['op']:.2f}%")
                rc3.metric("淨利率", f"{r['net']:.2f}%")
            else:
                st.warning("⚠️ 財報數據不完整。")

        with tab3:
            fd = data['fund_data']
            val = fd['valuation']
            pe = val.get('PE', 0)
            if fd['valid'] and pe > 0:
                st.subheader(f"🌊 隱含本益比帶 (目前 PE: {pe:.2f})")
                st.caption("採固定倍數推算，非傳統歷史滾動 PE 河流圖")
                implied_eps = current_price / pe
                df_river = data['tech_df'].reset_index()
                
                fig_river = go.Figure()
                fig_river.add_trace(go.Scatter(x=df_river['Date'], y=df_river['Close'], mode='lines', name='股價', line=dict(color='white', width=3)))
                
                multipliers = [10, 15, 20, 25]
                colors = ['#00FF00', '#FFFF00', '#FFA500', '#FF0000']
                labels = ['便宜 (10x)', '合理 (15x)', '昂貴 (20x)', '瘋狂 (25x)']
                
                for mult, col, lab in zip(multipliers, colors, labels):
                    line_val = [implied_eps * mult] * len(df_river)
                    fig_river.add_trace(go.Scatter(x=df_river['Date'], y=line_val, mode='lines', name=lab, line=dict(color=col, dash='dash', width=1)))
                
                fig_river.update_layout(template="plotly_dark", height=500)
                st.plotly_chart(fig_river, use_container_width=True)
            else:
                st.info("缺乏有效 PE 數據。")

        with tab4:
            fd = data['fund_data']
            if not fd['valid']:
                st.error("⚠️ 無法取得健檢數據。")
            else:
                val = fd['valuation']
                st.markdown(f"### 1. 價格與估值 (來源: {val['source']})")
                st.markdown('<div class="health-card">', unsafe_allow_html=True)
                c1, c2, c3 = st.columns(3)
                c1.metric("本益比 (PE)", f"{val['PE']:.2f}" if val['PE'] else "N/A", "便宜" if val['PE'] and val['PE'] < 15 else "合理/昂貴", delta_color="inverse")
                c2.metric("股價淨值比 (PB)", f"{val['PB']:.2f}" if val['PB'] else "N/A", "便宜 (<1.5)" if val['PB'] and val['PB'] < 1.5 else "偏高", delta_color="inverse")
                c3.metric("現金殖利率", f"{val['Yield']:.2f}%", "優 (>4%)" if val['Yield'] > 4 else "普", delta_color="normal")
                st.markdown('</div>', unsafe_allow_html=True)

                chips = fd['chips']
                st.markdown("### 2. 籌碼健康度")
                st.markdown('<div class="health-card">', unsafe_allow_html=True)
                c1, c2, c3 = st.columns(3)
                net = chips['net_buy_5d']
                c1.metric("近五日法人買賣超", f"{net} 張", "買超" if net > 0 else "賣超", delta_color="normal")
                c2.metric("外資持股比", f"{chips.get('inst_hold', 0):.2f}%" if chips.get('inst_hold') else "N/A")
                c3.metric("成交量趨勢", chips['vol_trend'])
                st.markdown('</div>', unsafe_allow_html=True)

                div = fd.get('dividend')
                st.markdown("### 3. 近期配息")
                st.markdown('<div class="health-card">', unsafe_allow_html=True)
                if div:
                    c1, c2 = st.columns(2)
                    c1.metric("近五年配息次數", f"{div['count_5y']} 次")
                    c2.metric("平均股利", f"{div['avg']:.2f} 元")
                    st.dataframe(div['history'].to_frame(name="現金股利"), use_container_width=True)
                else:
                    st.info("查無配息紀錄。")
                st.markdown('</div>', unsafe_allow_html=True)

        with tab5:
            st.subheader("🎯 雙軌制投資框架分析報告")
            st.caption("基於獨立財務與技術均線的進場判斷系統 (備註：此判斷邏輯為獨立分析引擎，與上方 AI 總結模型為分開運行，建議兩者互相參照對比)")
            
            # --- 一、財務表現定量過濾 ---
            st.markdown("### [一、財務表現定量過濾]")
            info = analyzer.info
            fin = analyzer.financials
            cf = analyzer.cashflow
            
            c1, c2, c3 = st.columns(3)
            # 1. 營收規模
            rev = info.get('totalRevenue', 0)
            rev_usd = (rev / 32) if rev else 0
            rev_pass = "🟢 通過" if rev_usd > 100000000 else "🔴 未通過"
            c1.metric("營收規模 (>1億美元)", f"{rev_pass}", f"約 {rev_usd/1e8:.2f} 億鎂", delta_color="normal" if rev_usd > 100000000 else "inverse")
            
            # 2. 營收增長率
            rev_growth = info.get('revenueGrowth', 0)
            rev_growth_pct = rev_growth * 100 if rev_growth else 0
            if 15 <= rev_growth_pct <= 20: g_label = "🟢 完美黃金區間"
            elif rev_growth_pct > 40: g_label = "🔴 危險 (超高速增長)"
            elif rev_growth_pct < 10: g_label = "🔴 警告 (增長瓶頸)"
            else: g_label = "🟡 一般範圍"
            c2.metric("營收增長率 (15-20%)", f"{rev_growth_pct:.2f}%", g_label, delta_color="off")
            
            # 3. 利潤與現金流
            try: ebit = fin.loc['EBIT'].iloc[0] if 'EBIT' in fin.index else info.get('ebitda', 0)
            except: ebit = 0
            try:
                ocf = cf.loc['Operating Cash Flow'].iloc[0] if 'Operating Cash Flow' in cf.index else 0
                fcf = cf.loc['Free Cash Flow'].iloc[0] if 'Free Cash Flow' in cf.index else 0
            except: ocf, fcf = 0, 0
            
            ebit_pass = "🟢 Pass" if ebit > 0 else "🔴 Fail"
            ocf_pass = "🟢 Pass" if ocf > 0 else "🔴 Fail"
            fcf_pass = "🟢 Pass" if fcf > 0 else "🔴 Fail"
            c3.markdown(f"**營業利潤 (EBIT > 0)**: {ebit_pass}  \n**營運現金流 (OCF > 0)**: {ocf_pass}  \n**自由現金流 (FCF > 0)**: {fcf_pass}")

            st.markdown("---")
            # --- 二、市場估值與預期心理 ---
            st.markdown("### [二、市場估值與預期心理]")
            ps = info.get('priceToSalesTrailing12Months', 0)
            pb = info.get('priceToBook', 0)
            sc1, sc2 = st.columns(2)
            sc1.metric("市銷率 (PS)", f"{ps:.2f}" if ps else "N/A")
            sc2.metric("市淨率 (PB)", f"{pb:.2f}" if pb else "N/A")
            st.info("💡 **指標解讀**：若高於歷史平均或同業，代表市場預期已極度樂觀，後續財報容錯率極低。")

            st.markdown("---")
            # --- 三、技術面戰術執行 (趨勢時鐘) ---
            st.markdown("### [三、技術面戰術執行 (趨勢時鐘)]")
            
            if len(data['price_history']) < 60:
                st.warning("歷史股價資料不足 60 天，無法計算趨勢時鐘。")
            else:
                hist = data['price_history']
                curr_p = hist['Close'].iloc[-1]
                m20 = hist['Close'].rolling(window=20).mean().iloc[-1]
                m60 = hist['Close'].rolling(window=60).mean().iloc[-1]
                m20_prev = hist['Close'].rolling(window=20).mean().iloc[-6]
                
                ma20_slope = (m20 - m20_prev) / m20_prev * 100
                dist_to_ma20 = (curr_p - m20) / m20 * 100
                
                c_status = ""
                box_color = ""
                if dist_to_ma20 > 15 and ma20_slope > 2:
                    c_status = "12點至1點鐘方向 🔴 (危險區域：極端樂觀拋物線暴漲，嚴禁追高，應準備獲利了結)"
                    box_color = "error"
                elif curr_p > m20 and m20 > m60 and ma20_slope > 0:
                    c_status = "2點鐘方向 🟢 (黃金操作區：趨勢健康，這是本框架唯一許可的建倉方位)"
                    box_color = "success"
                elif abs(ma20_slope) < 1.5 and abs(curr_p - m20)/m20 < 0.05:
                    c_status = "3點鐘方向 🟡 (觀望區域：橫盤震盪中，市場缺乏方向感)"
                    box_color = "warning"
                elif curr_p < m20 and ma20_slope < 0 and dist_to_ma20 > -15:
                    c_status = "4點鐘方向 🔴 (迴避區域：緩跌格局，嚴禁以抄底為由買入)"
                    box_color = "error"
                elif curr_p < m20 and dist_to_ma20 <= -15:
                    c_status = "5點至6點鐘方向 🔴 (災難區域：垂直崩潰，伴隨恐慌拋售，絕對禁止介入)"
                    box_color = "error"
                else:
                    c_status = "趨勢過渡期 (需開啟線圖人工確認)"
                    box_color = "info"
                    
                st.markdown(f"**趨勢時鐘定位：** {c_status}")
                tc1, tc2, tc3 = st.columns(3)
                tc1.metric("現價", f"{curr_p:.2f}")
                tc2.metric("月線 (MA20)", f"{m20:.2f}")
                tc3.metric("季線 (MA60)", f"{m60:.2f}")

                if box_color == "success":
                    st.success("💡 **【戰術執行指令】**\n\n符合條件！請開啟看盤軟體尋找下方「歷史籌碼峰」，在其支撐位附近掛單買入。\n並務必將不可妥協的「底線(停損)」設立於籌碼峰下方，若跌破無條件平倉！")
                elif box_color == "error" or box_color == "warning":
                    st.error("💡 **【戰術執行指令】**\n\n目前不符合 2 點鐘黃金操作區的買入標準，建議觀望或尋找其他標的。")
                else:
                    st.info("💡 **【戰術執行指令】**\n\n目前處於趨勢過渡期，方向不明確。建議縮小資金規模或場外觀望。")

        with tab6:
            st.subheader("🧪 歷史策略回測")
            st.caption("使用過去一年數據模擬策略表現 (⚠️ 註：未計入交易成本，且訊號依賴當日收盤價，存在前視偏差)")
            
            strat = st.selectbox("選擇策略", ["MA_Cross (黃金交叉)", "RSI_Reversal (RSI反轉)"])
            
            if st.button("執行回測"):
                res = analyzer.run_backtest(strat)
                if res:
                    c1, c2, c3 = st.columns(3)
                    c1.metric("策略總報酬", f"{res['total_return']:.2f}%", delta_color="normal")
                    c2.metric("大盤(持有)報酬", f"{res['benchmark_return']:.2f}%")
                    c3.metric("持有正報酬率", f"{res['win_rate']:.1f}%")
                    
                    st.line_chart(res['equity_curve'])
                    st.success("回測完成！注意：過去績效不代表未來表現。")
                else:
                    st.error("回測失敗，數據不足。")

# --- 頁面: ETF 戰情室 (優化版) ---
elif page == "📊 ETF 戰情室":
    st.title("🛡️ ETF 戰情室 (長期持有評估)")

    if etf_btn:
        progress_text = "初始化 ETF 數據引擎..."
        etf_bar = st.progress(0, text=progress_text)
        
        etf_engine = ETFAnalyzer(etf_input)
        
        etf_bar.progress(30, text="下載 ETF 淨值與持股明細...")
        success = etf_engine.fetch_data()
        
        if not success:
            etf_bar.progress(100, text="失敗")
            st.error(f"❌ 查無 ETF 資料: {etf_input} (可能是代號錯誤或 Yahoo Finance 無數據)")
            st.session_state['etf_result'] = None
        else:
            etf_bar.progress(90, text="分析報告生成中...")
            etf_engine.generate_report() # 可擴充自動生成報告
            time.sleep(0.5)
            
            etf_bar.progress(100, text="完成")
            time.sleep(0.2)
            etf_bar.empty()
            st.session_state['etf_result'] = etf_engine.data
            # 保存 analyzer 實例以調用方法
            st.session_state['etf_analyzer'] = etf_engine 

    if st.session_state['etf_result']:
        data = st.session_state['etf_result']
        m = data['metrics']
        
        # Header Info
        info = data['info']
        price_history = data['price_history']
        current_price = price_history['Close'].iloc[-1]
        change = current_price - price_history['Close'].iloc[-2]
        
        trend_class = "trend-up" if change > 0 else "trend-down"
        sign = "+" if change > 0 else ""

        st.markdown(f"""
        <div class="status-card">
            <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                <div>
                    <div class="sub-font">ETF 代號 | 名稱 | 類型</div>
                    <div class="big-font" style="margin-bottom: 5px;">{data['name']} <span style="font-size:16px; color:#aaa;">({m['Type']})</span></div>
                    <div>
                        <span style="font-size: 42px; line-height: 1;" class="{trend_class}">{current_price:.2f}</span>
                        <span style="font-size: 22px; margin-left: 15px;" class="{trend_class}">
                            {sign}{change:.2f} ({sign}{(change/price_history['Close'].iloc[-2]*100):.2f}%)
                        </span>
                    </div>
                </div>
                <div style="text-align: right;">
                    <div class="sub-font">總資產規模 (AUM)</div>
                    <div class="big-font">{m['AUM'] / 100000000:.2f} 億</div>
                    <div class="sub-font" style="margin-top:5px;">費用率: {m['ExpenseRatio']*100:.2f}% | 殖利率: {m['Yield']*100:.2f}%</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        t1, t2, t3, t4 = st.tabs(["📋 長期持有健檢", "📈 走勢與折溢價", "📦 持股透視", "策略說明"])

        with t1:
            st.subheader("長期持有適格性評估 (Checklist)")
            if 'etf_analyzer' in st.session_state:
                engine = st.session_state['etf_analyzer']
                report = engine.generate_report()
                for line in report:
                    st.write(line)
            else:
                st.write("請重新分析以產生報告。")

        with t2:
            st.subheader("價格走勢與折溢價監控")
            
            # 使用 Subplots 顯示價格與折溢價 (如果 NAV 存在)
            rows = 2 if m['NAV'] and m['NAV'] > 0 else 1
            fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3] if rows==2 else [1])
            
            # K線
            fig.add_trace(go.Candlestick(x=price_history.index,
                            open=price_history['Open'], high=price_history['High'],
                            low=price_history['Low'], close=price_history['Close'], name='K線',
                            increasing_line_color='#ff4b4b', decreasing_line_color='#00c07c'), row=1, col=1)
            
            # MA
            ma60 = price_history['Close'].rolling(60).mean()
            fig.add_trace(go.Scatter(x=price_history.index, y=ma60, name='季線 (MA60)', line=dict(color='#FF4500')), row=1, col=1)

            # 折溢價儀表 (僅當日) - 這裡改為顯示歷史折溢價可能較難 (需歷史 NAV)，故僅顯示當日數據文字
            if m['NAV']:
                st.metric("即時預估折溢價", f"{m['Premium']:.2f}%", "溢價 (貴)" if m['Premium'] > 0 else "折價 (便宜)", delta_color="inverse")
                st.caption(f"參考淨值 (NAV): {m['NAV']:.2f} (注意：Yahoo Finance 淨值更新可能有延遲)")

            fig.update_layout(template="plotly_dark", height=500, xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)

        with t3:
            c1, c2 = st.columns([2, 1])
            with c1:
                holdings = data['holdings']
                if not holdings.empty:
                    st.subheader("前十大成分股")
                    st.dataframe(holdings, use_container_width=True)
                else:
                    st.warning("⚠️ 無法取得詳細持股數據。")
            
            with c2:
                sectors = data['sectors']
                if sectors:
                    st.subheader("產業配置")
                    sec_df = pd.DataFrame(list(sectors.items()), columns=['Sector', 'Weight'])
                    fig_pie = px.pie(sec_df, values='Weight', names='Sector', hole=0.4, template="plotly_dark")
                    st.plotly_chart(fig_pie, use_container_width=True)

        with t4:
            st.markdown("""
            ### 關於此評估模型
            本頁面依據 **《台股ETF長期持有評估指南》** 設計，重點關注：
            1. **規模安全**：資產 < 20 億者存在清算風險，不宜長期存股。
            2. **成本控管**：總費用率是長期報酬的隱形殺手，市值型應 < 0.5%。
            3. **折溢價風險**：溢價 > 1% 代表買貴了，需等待收斂。
            4. **稅務效率**：高股息 ETF 雖有現金流，但週轉率高且易受二代健保補充保費影響，資產累積期建議優先考慮市值型 (如 0050, 006208)。
            """)

# ---------------------------------------------------------
# 頁面 2: 歷史資料庫
# ---------------------------------------------------------
elif page == "🗄️ 歷史資料庫":
    st.title("🗄️ 投資決策歷史紀錄")
    df_history = db.get_all_records()
    
    if df_history.empty:
        st.info("目前尚無紀錄。")
    else:
        col1, col2 = st.columns(2)
        with col1: st.metric("總紀錄筆數", len(df_history))
        with col2: st.metric("最近一次分析", df_history['analysis_date'].iloc[0])
        st.markdown("---")
        df_display = df_history.rename(columns={'id': '編號', 'analysis_date': '日期', 'ticker': '代號', 'stock_name': '名稱', 'close_price': '價位', 'verdict': '建議'})
        st.dataframe(df_display, use_container_width=True)
        c1, c2 = st.columns(2)
        with c1:
            del_id = st.selectbox("刪除編號", df_history['id'].tolist())
            if st.button("刪除"):
                db.delete_record(del_id)
                st.rerun()
        with c2:
            csv = df_display.to_csv(index=False).encode('utf-8-sig')
            st.download_button("下載 CSV", csv, "history.csv", "text/csv")

# ---------------------------------------------------------
# 頁面 3: 策略說明 (白皮書)
# ---------------------------------------------------------
elif page == "📖 策略邏輯白皮書":
    st.title("📖 AI 策略與全方位數據處理白皮書")
    
    try:
        with open("數據處理說明.MD", "r", encoding="utf-8") as f:
            markdown_content = f.read()
        st.markdown(markdown_content)
    except FileNotFoundError:
        st.error("無法找到 `數據處理說明.MD` 檔案，請確認檔案是否存在於專案根目錄中。")
    except Exception as e:
        st.error(f"讀取文件時發生錯誤: {e}")