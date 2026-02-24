import yfinance as yf
import pandas as pd

def dual_track_analysis(stock_ticker):
    # 台股代號請加上 .TW (例如台積電為 2330.TW)
    ticker_symbol = f"{stock_ticker}.TW" if not stock_ticker.endswith(".TW") and not stock_ticker.endswith(".TWO") else stock_ticker
    ticker = yf.Ticker(ticker_symbol)
    
    try:
        info = ticker.info
    except:
        return f"無法取得 {ticker_symbol} 的數據，請確認代號是否正確。"
        
    print(f"==================================================")
    print(f"【 {info.get('shortName', ticker_symbol)} ({ticker_symbol}) 雙軌制投資框架分析報告 】")
    print(f"==================================================")
    
    # ---------------- 財務定量過濾 ----------------
    print("\n[一、財務表現定量過濾]")
    # 營收規模 (約略換算美元)
    rev = info.get('totalRevenue', 0)
    rev_usd = (rev / 32) if rev else 0
    print(f"1. 營收規模 (>1億美元): {'🟢 通過' if rev_usd > 100000000 else '🔴 未通過'} (約 {rev_usd/1e8:.2f} 億美元)")
    
    # 營收增長率
    rev_growth = info.get('revenueGrowth', 0)
    rev_growth_pct = rev_growth * 100 if rev_growth else 0
    print(f"2. 營收增長率 (15%-20%黃金區間): {rev_growth_pct:.2f}%", end=" ")
    if 15 <= rev_growth_pct <= 20:
        print("🟢 (完美黃金區間)")
    elif rev_growth_pct > 40:
        print("🔴 (危險：超高速增長，需警惕失控風險)")
    elif rev_growth_pct < 10:
        print("🔴 (警告：增長可能遭遇瓶頸)")
    else:
        print("🟡 (非黃金區間，但屬一般範圍)")
        
    # 利潤與現金流
    financials = ticker.financials
    cashflow = ticker.cashflow
    
    try:
        ebit = financials.loc['EBIT'].iloc[0] if 'EBIT' in financials.index else info.get('ebitda', 0)
    except: ebit = 0
    try:
        ocf = cashflow.loc['Operating Cash Flow'].iloc[0] if 'Operating Cash Flow' in cashflow.index else 0
        fcf = cashflow.loc['Free Cash Flow'].iloc[0] if 'Free Cash Flow' in cashflow.index else 0
    except: ocf, fcf = 0, 0
        
    print(f"3. 營業利潤 (EBIT > 0): {'🟢 通過' if ebit > 0 else '🔴 未通過'}")
    print(f"4. 營運現金流 (OCF > 0): {'🟢 通過' if ocf > 0 else '🔴 未通過'}")
    print(f"5. 自由現金流 (FCF > 0): {'🟢 通過' if fcf > 0 else '🔴 未通過'}")
    
    # ---------------- 市場估值預期 ----------------
    print("\n[二、市場估值與預期心理]")
    ps = info.get('priceToSalesTrailing12Months', 0)
    pb = info.get('priceToBook', 0)
    print(f"• 市銷率 (PS): {ps:.2f} | 市淨率 (PB): {pb:.2f}")
    print("  (指標解讀：若高於歷史平均或同業，代表市場預期已極度樂觀，後續財報容錯率極低)")
    
    # ---------------- 趨勢時鐘分析 ----------------
    print("\n[三、技術面戰術執行 (趨勢時鐘)]")
    hist = ticker.history(period="6mo")
    if len(hist) < 60:
        print("歷史股價資料不足以計算季線。")
        return
        
    hist['MA20'] = hist['Close'].rolling(window=20).mean() # 月線
    hist['MA60'] = hist['Close'].rolling(window=60).mean() # 季線
    current_price = hist['Close'].iloc[-1]
    ma20 = hist['MA20'].iloc[-1]
    ma60 = hist['MA60'].iloc[-1]
    
    # 簡單斜率與乖離率判斷
    ma20_slope = (ma20 - hist['MA20'].iloc[-6]) / hist['MA20'].iloc[-6] * 100
    dist_to_ma20 = (current_price - ma20) / ma20 * 100
    
    clock_status = ""
    if dist_to_ma20 > 15 and ma20_slope > 2:
        clock_status = "12點至1點鐘方向 🔴 (危險區域：極端樂觀拋物線暴漲，嚴禁追高，應準備獲利了結)"
    elif current_price > ma20 and ma20 > ma60 and ma20_slope > 0:
        clock_status = "2點鐘方向 🟢 (黃金操作區：趨勢健康，這是本框架唯一許可的建倉方位)"
    elif abs(ma20_slope) < 1.5 and abs(current_price - ma20)/ma20 < 0.05:
        clock_status = "3點鐘方向 🟡 (觀望區域：橫盤震盪中，市場缺乏方向感)"
    elif current_price < ma20 and ma20_slope < 0 and dist_to_ma20 > -15:
        clock_status = "4點鐘方向 🔴 (迴避區域：緩跌格局，嚴禁以抄底為由買入)"
    elif current_price < ma20 and dist_to_ma20 <= -15:
        clock_status = "5點至6點鐘方向 🔴 (災難區域：垂直崩潰，伴隨恐慌拋售，絕對禁止介入)"
    else:
        clock_status = "趨勢過渡期 (需開啟線圖人工確認)"
        
    print(f"• 現價: {current_price:.2f} | 月線: {ma20:.2f} | 季線: {ma60:.2f}")
    print(f"• 趨勢時鐘定位：{clock_status}")
    print("\n💡【戰術執行指令】")
    if "2點鐘方向" in clock_status:
        print("符合條件！請開啟看盤軟體尋找下方「歷史籌碼峰」，在其支撐位附近掛單買入。")
        print("並務必將不可妥協的「底線(停損)」設立於籌碼峰下方，若跌破無條件平倉！")
    else:
        print("目前不符合 2 點鐘黃金操作區的買入標準，建議觀望或尋找其他標的。")

# 執行範例：分析台積電
dual_track_analysis("2330")