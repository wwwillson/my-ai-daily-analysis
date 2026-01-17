import streamlit as st
import yfinance as yf
import pandas as pd
import mplfinance as mpf
import numpy as np

# ==========================================
# 1. 頁面設定
# ==========================================
st.set_page_config(layout="wide", page_title="Price Action 波段策略分析")
# 修改 1: 移除標題中的 (仿影片邏輯)
st.title("📈 雙時區 Price Action 策略") 
st.markdown("""
**策略核心：**
1. **日線 (Daily)**：識別趨勢，自動尋找並畫出「關鍵支撐/阻力位」(Key Levels)。
2. **4小時 (4H)**：在關鍵位附近尋找「吞噬形態 (Engulfing)」作為入場確認。
""")

# ==========================================
# 2. 側邊欄輸入
# ==========================================
with st.sidebar:
    st.header("設定")
    symbol = st.text_input("輸入代號 (如 BTC-USD, NVDA, 2330.TW)", value="BTC-USD")
    lookback_days = st.slider("日線回溯天數 (找支撐壓力用)", 100, 730, 365)
    st.markdown("---")
    st.info("提示：若找不到數據，請確認代號是否正確。")

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

def fetch_data(symbol, days):
    try:
        # 1. 抓取日線
        df_daily = yf.download(symbol, period=f"{days}d", interval="1d", progress=False)
        
        # 2. 抓取小時線並重組為 4小時線
        df_1h = yf.download(symbol, period="1mo", interval="1h", progress=False)
        
        if isinstance(df_daily.columns, pd.MultiIndex):
            df_daily.columns = df_daily.columns.get_level_values(0)
        if isinstance(df_1h.columns, pd.MultiIndex):
            df_1h.columns = df_1h.columns.get_level_values(0)
            
        if df_daily.empty or df_1h.empty:
            return None, None, "抓取不到數據，請確認代號或市場是否開盤。"

        # 重採樣 1H -> 4H
        ohlc_dict = {
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last',
            'Volume': 'sum'
        }
        df_1h.index = pd.to_datetime(df_1h.index)
        df_4h = df_1h.resample('4h').agg(ohlc_dict).dropna()

        return df_daily, df_4h, None

    except Exception as e:
        return None, None, str(e)

# ==========================================
# 4. 分析與顯示邏輯
# ==========================================
if st.button("🚀 開始智能分析", type="primary"):
    with st.spinner("正在進行雙時區結構運算..."):
        df_d, df_4h, err = fetch_data(symbol, lookback_days)
        
        if err:
            st.error(f"錯誤: {err}")
        elif df_d is not None and not df_d.empty:
            
            # --- A. 日線分析 (趨勢 & 關鍵位) ---
            levels = find_levels(df_d)
            current_price = float(df_d['Close'].iloc[-1])
            
            ma50 = df_d['Close'].rolling(50).mean().iloc[-1]
            trend = "UP" if current_price > float(ma50) else "DOWN"
            
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
                st.info(f"**日線趨勢**：{'📈 上升 (價格 > 50MA)' if trend=='UP' else '📉 下跌 (價格 < 50MA)'}")
                st.metric("目前價格", f"{current_price:.2f}")
            with col2:
                if nearby_levels:
                    st.warning(f"**最近關鍵阻力/支撐位**：\n {', '.join([f'{l:.2f}' for l in nearby_levels])}")
                else:
                    st.warning("**最近關鍵阻力/支撐位**：尚未識別到明顯關鍵位")
            
            st.markdown("---")

            # 1. 繪製日線圖
            st.subheader("1️⃣ 日線圖 (Daily) - 自動繪製關鍵位")
            if level_prices:
                hlines_to_plot = level_prices[:5] # 日線圖畫出最近5條
                fig_d, ax_d = mpf.plot(
                    df_d.tail(100),
                    type='candle',
                    style='yahoo',
                    hlines=dict(hlines=hlines_to_plot, colors=['#FF9900']*len(hlines_to_plot), linestyle='-.', linewidths=1.5),
                    title=f"{symbol} Daily Chart (Key Levels)",
                    returnfig=True,
                    volume=False
                )
                st.pyplot(fig_d)
            else:
                fig_d, ax_d = mpf.plot(
                    df_d.tail(100), type='candle', style='yahoo', title=f"{symbol} Daily Chart", returnfig=True, volume=False
                )
                st.pyplot(fig_d)
            
            # 2. 繪製 4H 圖 (修改 2: 在 4H 圖上畫出最接近的那一條線)
            st.subheader("2️⃣ 4小時圖 (4H) - 尋找吞噬形態")
            
            if closest_level:
                fig_4h, ax_4h = mpf.plot(
                    df_4h.tail(50),
                    type='candle',
                    style='yahoo',
                    # 在這裡畫出最接近的那一條關鍵位
                    hlines=dict(hlines=[closest_level], colors=['#FF9900'], linestyle='--', linewidths=2.0),
                    title=f"{symbol} 4-Hour Chart (With Closest Daily Key Level)",
                    returnfig=True,
                    volume=False
                )
                st.pyplot(fig_4h)
                st.caption(f"說明：橘色虛線 ({closest_level:.2f}) 為目前最接近的日線級別關鍵位，請觀察 K 線是否在此處形成形態。")
            else:
                fig_4h, ax_4h = mpf.plot(
                    df_4h.tail(50),
                    type='candle',
                    style='yahoo',
                    title=f"{symbol} 4-Hour Chart",
                    returnfig=True,
                    volume=False
                )
                st.pyplot(fig_4h)

        else:
            st.error("無法分析，請重試或更換代號。")
