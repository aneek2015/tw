import pytest
import pandas as pd
import numpy as np
import os
import sqlite3
import requests
from app import StockAnalyzer, ETFAnalyzer, HistoryDB, get_yahoo_data

# === 測資與 Mock 準備 ===
@pytest.fixture
def sample_tech_df():
    # 產生 65 天的假股價資料 (大於 MA60 所需的 60 根 K 線)
    dates = pd.date_range(start="2025-01-01", periods=65, freq='D')
    np.random.seed(42)
    closes = np.linspace(100, 150, 65) + np.random.normal(0, 2, 65) # 模擬上升趨勢
    df = pd.DataFrame({
        'Date': dates,
        'Open': closes - 1,
        'High': closes + 2,
        'Low': closes - 2,
        'Close': closes,
        'Volume': np.random.randint(1000, 5000, 65)
    })
    df.set_index('Date', inplace=True)
    return df

@pytest.fixture
def mock_db():
    test_db = "test_history.db"
    db = HistoryDB(db_name=test_db)
    yield db
    # 測試後清理
    if os.path.exists(test_db):
        os.remove(test_db)

# === 核心邏輯測試 ===

def test_calculate_technicals(sample_tech_df):
    analyzer = StockAnalyzer("2330")
    analyzer.price_history = sample_tech_df
    
    tech_df = analyzer.calculate_technicals()
    
    # K線足夠時不應為 None
    assert tech_df is not None
    
    # 檢查是否有算出關鍵欄位
    expected_cols = ['MA5', 'MA20', 'MA60', 'RSI', 'MACD_Hist']
    for col in expected_cols:
        assert col in tech_df.columns
        
    # 因為前幾天沒有 MA60，檢查最後一筆的 MA60 應該要有值
    assert not np.isnan(tech_df['MA60'].iloc[-1])

def test_run_backtest(sample_tech_df):
    analyzer = StockAnalyzer("2330")
    analyzer.price_history = sample_tech_df
    
    backtest_res = analyzer.run_backtest("MA_Cross")
    
    assert backtest_res is not None
    assert 'total_return' in backtest_res
    assert 'win_rate' in backtest_res
    assert isinstance(backtest_res['total_return'], float)

def test_determine_verdict_buy():
    # 模擬多頭排列與基本面佳
    analyzer = StockAnalyzer("2330")
    
    tech_data = {
        'Close': [150],
        'MA20': [140],
        'MA60': [130],
        'RSI': [60],
        'MA60_Slope': [0.5],
        'MACD_Hist': [1.5]
    }
    tech_df = pd.DataFrame(tech_data)
    
    fund_data = {
        'valid': True,
        'metrics': {'EPS': 5.0, 'RevGrowth': 20},
        'valuation': {'PE': 12, 'Yield': 5}
    }
    
    verdict, v_class, reason = analyzer.determine_verdict(tech_df, fund_data)
    assert "Buy" in verdict

def test_db_insert(mock_db):
    mock_db.add_record(
        ticker="9999", name="測試股", price=100.0, 
        verdict="買入", reason="測試", eps=1.0, roe=2.0, pe=3.0
    )
    df = mock_db.get_all_records()
    
    assert len(df) == 1
    assert df.iloc[0]['ticker'] == "9999"
    assert df.iloc[0]['stock_name'] == "測試股"

# TWSE API 簡易測試 (只發一次 request)
def test_twse_api_live():
    requests.packages.urllib3.disable_warnings()
    url = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
    resp = requests.get(url, timeout=10, verify=False)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) > 0 # 確認至少有資料
