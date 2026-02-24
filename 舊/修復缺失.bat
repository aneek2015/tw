@echo off
chcp 65001
cls

echo ==========================================================
echo 正在為「台股 AI 深度操盤室 (三引擎旗艦版)」準備環境...
echo ==========================================================
echo.

echo [1/3] 更新 pip...
python -m pip install --upgrade pip

echo.
echo [2/3] 安裝核心套件 (整合 yfinance, FinMind, requests)...
python -m pip install streamlit yfinance FinMind pandas numpy plotly tqdm requests

echo.
echo [3/3] 驗證安裝...
python -c "import yfinance; import FinMind; import requests; print('三引擎模組驗證成功！')"

echo.
echo ==========================================================
echo ✅ 環境安裝完畢！
echo 請執行 streamlit run app.py
echo ==========================================================
echo.
pause