import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import mplfinance as mpf
import numpy as np

# ==========================================
# 1. 頁面設定
# ==========================================
st.set_page_config(layout="wide", page_title="Price Action 波段策略分析")
st.title("📈 雙時區 Price Action 策略 (仿影片邏輯)")
st.markdown("""
**策略核心 (基於影片歸納)：**
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
    sensitivity = st.slider("關鍵位敏感度 (數值越小線越少)", 1, 5, 2)
    st.markdown("---")
    st.info("提示：若找不到數據，請確認代號是否正確。")

# ==========================================
# 3. 核心運算函數
# ==========================================

def is_support(df, i):
    # 判斷是否為局部低點 (Fractal Low)
    cond1 = df['Low'][i] < df['Low'][i-1]
    cond2 = df['Low'][i] < df['Low'][i+1]
    cond3 = df['Low'][i+1] < df['Low'][i+2]
    cond4 = df['Low'][i-1] < df['Low'][i-2]
    return cond1 and cond2 and cond3 and cond4

def is_resistance(df, i):
    # 判斷是否為局部高點 (Fractal High)
    cond1 = df['High'][i] > df['High'][i-1]
    cond2 = df['High'][i] > df['High'][i+1]
    cond3 = df['High'][i+1] > df['High'][i+2]
    cond4 = df['High'][i-1] > df['High'][i-2]
    return cond1 and cond2 and cond3 and cond4

def find_levels(df):
    # 尋找關鍵支撐與壓力位
    levels = []
    # 使用平均蠟燭長度來過濾太近的線
    mean_candle_size = np.mean(df['High'] - df['Low'])
    
    for i in range(2, df.shape[0] - 2):
        if is_support(df, i):
            l = df['Low'][i]
            # 檢查是否已經有相近的線 (合併附近的支撐壓力)
            if np.sum([abs(l - x) < mean_candle_size * 2 for x in levels]) == 0:
                levels.append((i, l, "Support"))
        elif is_resistance(df, i):
            l = df['High'][i]
            if np.sum([abs(l - x) < mean_candle_size * 2 for x in levels]) == 0:
                levels.append((i, l, "Resistance"))
    return levels

def check_engulfing(open_curr, close_curr, open_prev, close_prev, trend_direction):
    # 判斷吞噬形態
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
        
        # 2. 抓取小時線並重組為 4小時線 (因為 yf 免費版 4h 不穩定)
        df_1h = yf.download(symbol, period="2mo", interval="1h", progress=False)
        
        # 處理 MultiIndex (yfinance 新版修正)
        if isinstance(df_daily.columns, pd.MultiIndex):
            df_daily.columns = df_daily.columns.get_level_values(0)
        if isinstance(df_1h.columns, pd.MultiIndex):
            df_1h.columns = df_1h.columns.get_level_values(0)
            
        if df_daily.empty or df_1h.empty:
            return None, None, None

        # 重採樣 1H -> 4H
        ohlc_dict = {
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last',
            'Volume': 'sum'
        }
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
            st.error(f"數據錯誤: {err}")
        elif df_d is not None:
            
            # --- A. 日線分析 (趨勢 & 關鍵位) ---
            levels = find_levels(df_d)
            current_price = df_d['Close'].iloc[-1]
            
            # 簡單趨勢過濾 (價格 vs 50MA)
            ma50 = df_d['Close'].rolling(50).mean().iloc[-1]
            trend = "UP" if current_price > ma50 else "DOWN"
            
            # 找出最近的關鍵位 (只顯示最近的 2 條線)
            level_prices = [l[1] for l in levels]
            level_prices.sort(key=lambda x: abs(x - current_price))
            nearby_levels = level_prices[:2]

            # --- B. 4H 分析 (入場訊號) ---
            # 取得最後兩根 4H K線
            curr_4h = df_4h.iloc[-1]
            prev_4h = df_4h.iloc[-2]
            
            signal = check_engulfing(
                curr_4h['Open'], curr_4h['Close'], 
                prev_4h['Open'], prev_4h['Close'], 
                trend
            )
            
            # 判斷價格是否靠近關鍵位 (Buffer 2%)
            is_near_level = False
            for lvl in nearby_levels:
                if abs(current_price - lvl) / current_price < 0.02: # 2% 誤差內
                    is_near_level = True
            
            final_decision = "觀望"
            if signal and is_near_level:
                final_decision = f"🔥 {signal} (且位於關鍵位附近)"
            elif signal:
                final_decision = f"⚠️ {signal} (但未緊貼日線關鍵位)"
            elif is_near_level:
                final_decision = "👀 價格回到關鍵位 (等待 4H 吞噬形態)"

            # --- C. 顯示結果 ---
            
            # 1. 文字報告
            st.markdown(f"### 🎯 分析結果：{final_decision}")
            col1, col2 = st.columns(2)
            with col1:
                st.info(f"**日線趨勢**：{'📈 上升 (價格 > 50MA)' if trend=='UP' else '📉 下跌 (價格 < 50MA)'}")
                st.metric("目前價格", f"{current_price:.2f}")
            with col2:
                st.warning(f"**最近關鍵阻力/支撐位**：\n {', '.join([f'{l:.2f}' for l in nearby_levels])}")
            
            st.markdown("---")

            # 2. 繪製圖表 (使用 mplfinance)
            st.subheader("1️⃣ 日線圖 (Daily) - 自動繪製關鍵位")
            
            # 準備畫線的資料 (hlines)
            hlines_data = [l[1] for l in levels]
            
            # 為了避免圖表太亂，我們只畫出距離目前價格最近的 5 條線
            hlines_data.sort(key=lambda x: abs(x - current_price))
            hlines_to_plot = hlines_data[:5]

            # 繪製日線
            fig_d, ax_d = mpf.plot(
                df_d.tail(100), # 只畫最近100天
                type='candle',
                style='yahoo',
                hlines=dict(hlines=hlines_to_plot, colors=['#FF9900']*len(hlines_to_plot), linestyle='-.', linewidths=1.5),
                title=f"{symbol} Daily Chart (Orange Lines = Key Levels)",
                returnfig=True,
                volume=False
            )
            st.pyplot(fig_d)
            
            st.subheader("2️⃣ 4小時圖 (4H) - 尋找吞噬形態")
            # 繪製 4H 線
            fig_4h, ax_4h = mpf.plot(
                df_4h.tail(50), # 只畫最近 50 根 4H K線
                type='candle',
                style='yahoo',
                title=f"{symbol} 4-Hour Chart (Entry Timeframe)",
                returnfig=True,
                volume=False
            )
            st.pyplot(fig_4h)
            
            st.caption("說明：橘色虛線代表程式識別出的日線級別『關鍵支撐/阻力位』(曾多次轉折處)。")

        else:
            st.error("無法分析，請重試。")
