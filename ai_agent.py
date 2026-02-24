import google.generativeai as genai
import pandas as pd

def generate_ai_report_stream(api_key: str, data: dict):
    """
    使用 Google Gemini API 產生串流式的投資分析報告
    """
    genai.configure(api_key=api_key)
    # 使用 gemini-1.5-flash 作為快速回答模型
    model = genai.GenerativeModel("gemini-1.5-flash")
    
    ticker = data.get('ticker', '未知')
    name = data.get('name', '未知')
    verdict = data.get('verdict', '無')
    reason = data.get('verdict_reason', '無')
    
    fund_data = data.get('fund_data', {})
    metrics = fund_data.get('metrics', {})
    valuation = fund_data.get('valuation', {})
    chips = fund_data.get('chips', {})
    
    tech_df = data.get('tech_df')
    if isinstance(tech_df, pd.DataFrame) and not tech_df.empty:
        last_px = tech_df['Close'].iloc[-1]
        ma20 = tech_df['MA20'].iloc[-1]
        ma60 = tech_df['MA60'].iloc[-1]
    else:
        last_px = ma20 = ma60 = "N/A"

    prompt = f"""
    你現在是一位有著華爾街避險基金與台灣券商自營部背景的「頂級 AI 投資教練」。
    你的任務是用【繁體中文】且帶有專業、堅定、但易懂的語氣，為投資人寫一份「個股健檢與操作建議戰略報告」。
    請避免使用空泛的廢話，直接切入核心：指出優勢、點出致命風險，並給出具體的防禦或進攻策略（例如停損應該設在何處）。

    【股票基本資訊】
    - 代號與名稱：{ticker} {name}
    - 系統初判訊號：{verdict} (理由：{reason})

    【盤面與技術資訊】
    - 最新收盤價：{last_px}
    - 月線(MA20)：{ma20}
    - 季線(MA60)：{ma60}

    【基本面與籌碼資訊】
    - 近期EPS：{metrics.get('EPS', 'N/A')}
    - 本益比(PE)：{valuation.get('PE', 'N/A')}
    - 營收成長率：{metrics.get('RevGrowth', 'N/A')}%
    - 近5日法人淨買賣超：{chips.get('net_buy_5d', 'N/A')} 張

    請依照以下結構撰寫報告：
    1. 🎯 **戰略總結** (以一句話形容目前該股票的處境)
    2. 📈 **優勢與底氣** (點出數據中表現好的地方)
    3. ⚠️ **隱患與風險警示** (點出本益比過高、跌破均線或法人倒貨等致命傷)
    4. 🛡️ **戰術執行沙盤推演** (給出具體建議：如果是空手該不該買？如果持有該在哪裡防守停損？)
    """

    try:
        response = model.generate_content(prompt, stream=True)
        for chunk in response:
            if chunk.text:
                yield chunk.text
    except Exception as e:
        yield f"⚠️ **AI 引擎呼叫失敗**。可能原因：API Key 無效或網路逾時。\n\n詳細錯誤訊息：`{str(e)}`"
