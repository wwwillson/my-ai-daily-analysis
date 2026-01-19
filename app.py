import streamlit as st
import ccxt
import pandas as pd
import mplfinance as mpf
import numpy as np
from datetime import datetime

# ==========================================
# 1. 頁面設定
# ==========================================
st.set_page_config(layout="wide", page_title="Binance US PA 策略分析")
st.title("📈 雙時區 Price Action 策略 (Binance US)") 
st.markdown("""
**策略核心：**
1. **日線 (Daily)**：識別趨勢，自動尋找並畫出「關鍵支撐/阻力位」(Key Levels)。
2. **4小時 (4H)**：在關鍵位附近尋找「吞噬形態 (Engulfing)」作為入場確認。
3. **時區**：所有時間已轉換為 **台灣時間 (Asia/Taipei)**。
""")

# ==========================================
# 2. 側邊欄輸入
# ==========================================
with st.sidebar:
    st.header("設定")
    symbol = st.text_input("輸入交易對 (如 BTC/USDT, ETH/USD)", value="BTC/USDT")
    lookback_days = st.slider("日線回溯天數 (找支撐壓力用)", 100, 730, 365)
    st.markdown("---")
    st.info("提示：Binance US 代號通常為 'XXX/USDT' 或 'XXX/USD'。")

# ==========================================
# 3. 核心運算函數
# ==========================================

def is_support(df, i):
    # 判斷是否為局部低點 (Fractal Low)
    try:
        cond1 = df['Low'].iloc[i] < df['Low'].iloc[i-1]
        cond2 = df['Low'].iloc[i] < df['Low'].iloc[i+1]
        cond3 = df['Low'].iloc[i+1] < df['Low'].iloc[i+2]
        cond4 = df['Low'].iloc[i-1] < df['Low'].iloc[i-2]
        return cond1 and cond2 and cond3 and cond4
    except:
        return False

def is_resistance(df, i):
    # 判斷是否為局部高點 (Fractal High)
    try:
        cond1 = df['High'].iloc[i] > df['High'].iloc[i-1]
        cond2 = df['High'].iloc[i] > df['High'].iloc[i+1]
        cond3 = df['High'].iloc[i+1] > df['High'].iloc[i+2]
        cond4 = df['High'].iloc[i-1] > df['High'].iloc[i-2]
        return cond1 and cond2 and cond3 and cond4
    except:
        return False

def is_far_from_existing(l, levels, mean_candle_size):
    # 輔助函數：檢查是否與現有線條太近
    if len(levels) == 0:
        return True
    for x in levels:
        if abs(l - x[1]) < mean_candle_size * 2:
            return False
    return True

def find_levels(df):
    # 尋找關鍵支撐與壓力位
    levels = []
    mean_candle_size = np.mean(df['High'] - df['Low'])
    
    for i in range(2, df.shape[0] - 2):
        if is_support(df, i):
            l = float(df['Low'].iloc[i])
            if is_far_from_existing(l, levels, mean_candle_size):
                levels.append((i, l, "Support"))
                
        elif is_resistance(df, i):
            l = float(df['High'].iloc[i])
            if is_far_from_existing(l, levels, mean_candle_size):
                levels.append((i, l, "Resistance"))
    return levels

def check_engulfing(open_curr, close_curr, open_prev, close_prev, trend_direction):
    # 判斷吞噬形態
    open_curr, close_curr = float(open_curr), float(close_curr)
    open_prev, close_prev = float(open_prev), float(close_prev)

    # 1. 多頭吞噬 (Bullish Engulfing) - 在上升趨勢或支撐位
    if trend_direction in ["UP", "RANGE"]:
        if (close_curr > open_curr) and (close_prev < open_prev): # 今紅昨黑
            if (close_curr > open_prev) and (open_curr < close_prev): # 實體包覆
                return "🟢 多頭吞噬 (買入訊號)"
    
    # 2. 空頭吞噬 (Bearish Engulfing) - 在下跌趨勢或壓力位
    if trend_direction in ["DOWN", "RANGE"]:
        if (close_curr < open_curr) and (close_prev > open_prev): # 今黑昨紅
            if (close_curr < open_prev) and (open_curr > close_prev): # 實體包覆
                return "🔴 空頭吞噬 (賣出訊號)"
    
    return None

def fetch_binance_data(symbol, days):
    """
    使用 CCXT 抓取 Binance US 數據並轉換為台灣時間
    """
    try:
        # 初始化 Binance US
        exchange = ccxt.binanceus({
            'enableRateLimit': True,
        })
        
        # 檢查代號是否存在 (非必要，但可增加穩定性)
        # exchange.load_markets() 

        # ---------------------------
        # 1. 抓取日線 (Daily)
        # ---------------------------
        # Binance 最多一次抓 1000 根，通常夠用
        ohlcv_d = exchange.fetch_ohlcv(symbol, timeframe='1d', limit=days)
        if not ohlcv_d:
            return None, None, "抓取不到日線數據，請確認代號 (例如 BTC/USDT)。"
            
        df_d = pd.DataFrame(ohlcv_d, columns=['timestamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
        # 轉換時間戳記 -> UTC -> 台灣時間
        df_d['timestamp'] = pd.to_datetime(df_d['timestamp'], unit='ms').dt.tz_localize('UTC').dt.tz_convert('Asia/Taipei')
        df_d.set_index('timestamp', inplace=True)

        # ---------------------------
        # 2. 抓取 4小時線 (4H)
        # ---------------------------
        # Binance 原生支援 4h，不需要 Resample
        ohlcv_4h = exchange.fetch_ohlcv(symbol, timeframe='4h', limit=100) # 抓最近 100 根 4H
        if not ohlcv_4h:
            return None, None, "抓取不到 4H 數據。"
            
        df_4h = pd.DataFrame(ohlcv_4h, columns=['timestamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
        # 轉換時間戳記 -> UTC -> 台灣時間
        df_4h['timestamp'] = pd.to_datetime(df_4h['timestamp'], unit='ms').dt.tz_localize('UTC').dt.tz_convert('Asia/Taipei')
        df_4h.set_index('timestamp', inplace=True)

        return df_d, df_4h, None

    except Exception as e:
        return None, None, f"API 錯誤: {str(e)}"

# ==========================================
# 4. 分析與顯示邏輯
# ==========================================
if st.button("🚀 開始智能分析", type="primary"):
    with st.spinner(f"正在連線 Binance US 獲取 {symbol} 數據..."):
        df_d, df_4h, err = fetch_binance_data(symbol, lookback_days)
        
        if err:
            st.error(f"錯誤: {err}")
        elif df_d is not None and not df_d.empty:
            
            # --- A. 日線分析 (趨勢 & 關鍵位) ---
            levels = find_levels(df_d)
            current_price = float(df_d['Close'].iloc[-1])
            
            # 確保數據足夠計算 MA50
            if len(df_d) >= 50:
                ma50 = df_d['Close'].rolling(50).mean().iloc[-1]
                trend = "UP" if current_price > float(ma50) else "DOWN"
            else:
                trend = "RANGE"
                ma50 = 0
            
            level_prices = [l[1] for l in levels]
            nearby_levels = []
            
            # 找出最近的關鍵位
            closest_level = None
            if level_prices:
                level_prices.sort(key=lambda x: abs(x - current_price))
                nearby_levels = level_prices[:2]
                closest_level = nearby_levels[0] # 取得最接近的一條

            # --- B. 4H 分析 (入場訊號) ---
            if len(df_4h) >= 2:
                curr_4h = df_4h.iloc[-1]
                prev_4h = df_4h.iloc[-2]
                signal = check_engulfing(
                    curr_4h['Open'], curr_4h['Close'], 
                    prev_4h['Open'], prev_4h['Close'], 
                    trend
                )
            else:
                signal = None
            
            # 判斷價格是否靠近關鍵位 (Buffer 2%)
            is_near_level = False
            for lvl in nearby_levels:
                if abs(current_price - lvl) / current_price < 0.02: 
                    is_near_level = True
            
            final_decision = "觀望"
            if signal and is_near_level:
                final_decision = f"🔥 {signal} (且位於關鍵位附近)"
            elif signal:
                final_decision = f"⚠️ {signal} (但未緊貼日線關鍵位)"
            elif is_near_level:
                final_decision = "👀 價格回到關鍵位 (等待 4H 吞噬形態)"

            # --- C. 顯示結果 ---
            st.markdown(f"### 🎯 分析結果：{final_decision}")
            col1, col2 = st.columns(2)
            with col1:
                trend_str = '📈 上升' if trend=='UP' else '📉 下跌'
                if trend == "RANGE": trend_str = "↔️ 震盪/數據不足"
                st.info(f"**日線趨勢 (vs 50MA)**：{trend_str}")
                st.metric("目前價格 (USDT/USD)", f"{current_price:.2f}")
            with col2:
                if nearby_levels:
                    st.warning(f"**最近關鍵阻力/支撐位**：\n {', '.join([f'{l:.2f}' for l in nearby_levels])}")
                else:
                    st.warning("**最近關鍵阻力/支撐位**：尚未識別到明顯關鍵位")
            
            st.markdown("---")

            # 定義 MPF 樣式，適配 Streamlit 深色主題
            mc = mpf.make_marketcolors(up='#00ff00', down='#ff0000', inherit=True)
            s  = mpf.make_mpf_style(marketcolors=mc, style='nightclouds')

            # 1. 繪製日線圖
            st.subheader("1️⃣ 日線圖 (Daily) - 台灣時間")
            if level_prices:
                hlines_to_plot = level_prices[:5] # 日線圖畫出最近5條
                fig_d, ax_d = mpf.plot(
                    df_d.tail(100),
                    type='candle',
                    style=s,
                    hlines=dict(hlines=hlines_to_plot, colors=['#FF9900']*len(hlines_to_plot), linestyle='-.', linewidths=1.0),
                    title=f"{symbol} Daily Chart (Taiwan Time)",
                    returnfig=True,
                    volume=False,
                    datetime_format='%Y-%m-%d', # 日線格式
                    tight_layout=True
                )
                st.pyplot(fig_d)
            else:
                fig_d, ax_d = mpf.plot(
                    df_d.tail(100), type='candle', style=s, title=f"{symbol} Daily Chart", returnfig=True, volume=False, tight_layout=True
                )
                st.pyplot(fig_d)
            
            # 2. 繪製 4H 圖
            st.subheader("2️⃣ 4小時圖 (4H) - 台灣時間")
            
            # 準備在 4H 圖上的標題，加上時間
            latest_time = df_4h.index[-1].strftime('%Y-%m-%d %H:%M')
            
            if closest_level:
                fig_4h, ax_4h = mpf.plot(
                    df_4h.tail(50),
                    type='candle',
                    style=s,
                    hlines=dict(hlines=[closest_level], colors=['#FF9900'], linestyle='--', linewidths=1.5),
                    title=f"{symbol} 4H Chart (Last: {latest_time})",
                    returnfig=True,
                    volume=False,
                    datetime_format='%m-%d %H:%M', # 4H 顯示月-日 時:分
                    tight_layout=True
                )
                st.pyplot(fig_4h)
                st.caption(f"說明：橘色虛線 ({closest_level:.2f}) 為目前最接近的日線級別關鍵位。")
            else:
                fig_4h, ax_4h = mpf.plot(
                    df_4h.tail(50),
                    type='candle',
                    style=s,
                    title=f"{symbol} 4H Chart (Last: {latest_time})",
                    returnfig=True,
                    volume=False,
                    datetime_format='%m-%d %H:%M',
                    tight_layout=True
                )
                st.pyplot(fig_4h)

        else:
            st.error("無法分析，請確認交易對是否正確 (Binance US 需大寫且包含計價幣，如 BTC/USDT)。")
