import pandas as pd
import numpy as np

def calculate_technicals(price_history: pd.DataFrame) -> pd.DataFrame:
    """計算技術指標 (MA, BB, RSI, MACD)"""
    df = price_history.copy()
    if len(df) < 60:
        return None

    # 移動平均線與斜率
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['MA60'] = df['Close'].rolling(window=60).mean()
    df['MA20_Slope'] = df['MA20'].diff()
    df['MA60_Slope'] = df['MA60'].diff()

    # RSI
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    # MACD
    exp12 = df['Close'].ewm(span=12, adjust=False).mean()
    exp26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD_DIF'] = exp12 - exp26
    df['MACD_Signal'] = df['MACD_DIF'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['MACD_DIF'] - df['MACD_Signal']
    
    # Bollinger Bands
    df['BB_Mid'] = df['Close'].rolling(window=20).mean()
    df['BB_Std'] = df['Close'].rolling(window=20).std()
    df['BB_Up'] = df['BB_Mid'] + (2 * df['BB_Std'])
    df['BB_Low'] = df['BB_Mid'] - (2 * df['BB_Std'])

    return df

def run_backtest_logic(df: pd.DataFrame, strategy_type: str = "MA_Cross", **kwargs) -> dict:
    """執行基礎回測並計算績效"""
    if df is None or len(df) == 0:
        return None

    df['Position'] = 0
    df['Signal'] = 0
    
    if "MA_Cross" in strategy_type:
        fast_window = kwargs.get('fast_ma', 5)
        slow_window = kwargs.get('slow_ma', 20)
        fast_col = f'MA_Test_{fast_window}'
        slow_col = f'MA_Test_{slow_window}'
        
        df[fast_col] = df['Close'].rolling(window=fast_window).mean()
        df[slow_col] = df['Close'].rolling(window=slow_window).mean()
        
        df['Signal'] = np.where(df[fast_col] > df[slow_col], 1, -1)
        df['Position'] = np.where(df[fast_col] > df[slow_col], 1, 0)
        
    elif "RSI_Reversal" in strategy_type:
        rsi_low = kwargs.get('rsi_low', 30)
        rsi_high = kwargs.get('rsi_high', 70)
        conditions = [(df['RSI'] < rsi_low), (df['RSI'] > rsi_high)]
        choices = [1, 0]
        df['Position'] = np.select(conditions, choices, default=np.nan)
        df['Position'] = df['Position'].ffill().fillna(0)
        
    elif "MACD_Hist" in strategy_type:
        df['Signal'] = np.where(df['MACD_Hist'] > 0, 1, -1)
        df['Position'] = np.where(df['MACD_Hist'] > 0, 1, 0)

    df['Daily_Ret'] = df['Close'].pct_change()
    
    # 加入交易成本計算估計
    commission = kwargs.get('commission', 0.002) # 預設單邊 0.2% (手續費+滑價)
    df['Trade'] = df['Position'].diff().abs()
    trade_costs = df['Trade'] * commission
    
    df['Strategy_Ret'] = df['Position'].shift(1) * df['Daily_Ret'] - trade_costs.fillna(0)
    df['Cum_Ret'] = (1 + df['Strategy_Ret']).cumprod()
    df['Benchmark_Ret'] = (1 + df['Daily_Ret']).cumprod()
    
    if df['Cum_Ret'].empty:
        return None
    
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
