import streamlit as st
import ccxt
import pandas as pd
import mplfinance as mpf
import numpy as np
from datetime import datetime

# ==========================================
# 1. 頁面設定與策略邏輯說明
# ==========================================
st.set_page_config(layout="wide", page_title="Binance US PA 策略分析")
st.title("📈 雙時區 Price Action 策略 (Binance US)") 

# 詳細邏輯說明區塊
with st.expander("📖 點擊查看：關鍵位與吞噬形態的詳細判斷邏輯", expanded=True):
    st.markdown("""
    本策略僅專注於 **日線 (Daily)** 與 **4小時 (4H)** 的價格行為互動：

    #### 1. 日線關鍵位 (Key Levels) 怎麼找？
    程式自動識別 **Bill Williams Fractal (碎形)** 結構來定義支撐與阻力：
    *   **支撐位 (Support)**：尋找「V」型底。當某一根 K 線的最低價 (Low)，**低於** 左邊 2 根的最低價，且 **低於** 右邊 2 根的最低價。
    *   **阻力位 (Resistance)**：尋找「倒V」型頂。當某一根 K 線的最高價 (High)，**高於** 左邊 2 根的最高價，且 **高於** 右邊 2 根的最高價。
    > 這些點位代表市場曾經拒絕過的價格，具有較強的參考意義。

    #### 2. 4小時吞噬形態 (Engulfing) 怎麼判斷？
    當價格接近上述日線關鍵位時，在 4小時級別尋找反轉訊號：
    *   **🟢 多頭吞噬 (Bullish Engulfing)**：
        1. 前一根 K 線是下跌的 (收盤 < 開盤)。
        2. 當前 K 線是上漲的 (收盤 > 開盤)。
        3. 當前 K 線的實體 **完全包覆** 前一根的實體 (當前開盤 < 前收盤 且 當前收盤 > 前開盤)。
    *   **🔴 空頭吞噬 (Bearish Engulfing)**：
        1. 前一根 K 線是上漲的。
        2. 當前 K 線是下跌的。
        3. 當前 K 線的實體 **完全包覆** 前一根的實體。
    """)

st.info("💡 系統時間已自動轉換為 **台灣時間 (Asia/Taipei)**")

# ==========================================
# 2. 側邊欄輸入
# ==========================================
with st.sidebar:
    st.header("設定")
    symbol = st.text_input("輸入交易對", value="BTC/USDT")
    lookback_days = st.slider("日線回溯天數", 100, 730, 365, help="往回看多少天的歷史數據來尋找支撐壓力")
    st.markdown("---")
    st.caption("資料來源：Binance US")

# ==========================================
# 3. 核心運算函數
# ==========================================

def is_support(df, i):
    # 判斷是否為局部低點 (低於左邊2根與右邊2根)
    try:
        cond1 = df['Low'].iloc[i] < df['Low'].iloc[i-1]
        cond2 = df['Low'].iloc[i] < df['Low'].iloc[i+1]
        cond3 = df['Low'].iloc[i+1] < df['Low'].iloc[i+2]
        cond4 = df['Low'].iloc[i-1] < df['Low'].iloc[i-2]
        return cond1 and cond2 and cond3 and cond4
    except:
        return False

def is_resistance(df, i):
    # 判斷是否為局部高點 (高於左邊2根與右邊2根)
    try:
        cond1 = df['High'].iloc[i] > df['High'].iloc[i-1]
        cond2 = df['High'].iloc[i] > df['High'].iloc[i+1]
        cond3 = df['High'].iloc[i+1] > df['High'].iloc[i+2]
        cond4 = df['High'].iloc[i-1] > df['High'].iloc[i-2]
        return cond1 and cond2 and cond3 and cond4
    except:
        return False

def is_far_from_existing(l, levels, mean_candle_size):
    # 避免畫出太靠近的線 (過濾雜訊)
    if len(levels) == 0:
        return True
    for x in levels:
        if abs(l - x[1]) < mean_candle_size * 2: # 如果距離小於2倍平均K線長度，則忽略
            return False
    return True

def find_levels(df):
    levels = []
    # 計算平均 K 線實體大小，用於過濾太近的線
    mean_candle_size = np.mean(df['High'] - df['Low'])
    
    # 遍歷數據 (扣除前後保留區間)
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
    # 強制轉為浮點數
    open_curr, close_curr = float(open_curr), float(close_curr)
    open_prev, close_prev = float(open_prev), float(close_prev)

    # 1. 多頭吞噬 (Bullish): 發生在上升趨勢中回調，或底部
    # 邏輯: 昨天跌(黑/紅), 今天漲(白/綠), 且今天的實體包住昨天的實體
    if trend_direction in ["UP", "RANGE"]:
        if (close_prev < open_prev): # 昨收黑
            if (close_curr > open_curr): # 今收紅
                if (close_curr > open_prev) and (open_curr < close_prev): # 實體包覆
                    return "🟢 多頭吞噬 (Bullish Engulfing)"
    
    # 2. 空頭吞噬 (Bearish): 發生在下跌趨勢中反彈，或頂部
    # 邏輯: 昨天漲, 今天跌, 且今天的實體包住昨天的實體
    if trend_direction in ["DOWN", "RANGE"]:
        if (close_prev > open_prev): # 昨收紅
            if (close_curr < open_curr): # 今收黑
                if (close_curr < open_prev) and (open_curr > close_prev): # 實體包覆
                    return "🔴 空頭吞噬 (Bearish Engulfing)"
    
    return None

def fetch_binance_data(symbol, days):
    try:
        exchange = ccxt.binanceus({'enableRateLimit': True})
        
        # 1. 抓取日線
        ohlcv_d = exchange.fetch_ohlcv(symbol, timeframe='1d', limit=days)
        if not ohlcv_d:
            return None, None, "抓取不到日線，請確認代號 (如 BTC/USDT)"
        df_d = pd.DataFrame(ohlcv_d, columns=['timestamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
        df_d['timestamp'] = pd.to_datetime(df_d['timestamp'], unit='ms').dt.tz_localize('UTC').dt.tz_convert('Asia/Taipei')
        df_d.set_index('timestamp', inplace=True)

        # 2. 抓取 4小時線
        ohlcv_4h = exchange.fetch_ohlcv(symbol, timeframe='4h', limit=100)
        if not ohlcv_4h:
            return None, None, "抓取不到 4H 數據"
        df_4h = pd.DataFrame(ohlcv_4h, columns=['timestamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
        df_4h['timestamp'] = pd.to_datetime(df_4h['timestamp'], unit='ms').dt.tz_localize('UTC').dt.tz_convert('Asia/Taipei')
        df_4h.set_index('timestamp', inplace=True)

        return df_d, df_4h, None
    except Exception as e:
        return None, None, f"API 錯誤: {str(e)}"

# ==========================================
# 4. 分析與顯示邏輯
# ==========================================
if st.button("🚀 開始智能分析", type="primary"):
    with st.spinner(f"正在連線 Binance US 分析 {symbol} ..."):
        df_d, df_4h, err = fetch_binance_data(symbol, lookback_days)
        
        if err:
            st.error(f"錯誤: {err}")
        elif df_d is not None and not df_d.empty:
            
            # --- 分析計算 ---
            levels = find_levels(df_d)
            current_price = float(df_d['Close'].iloc[-1])
            
            # 計算 50MA 判斷大趨勢
            if len(df_d) >= 50:
                ma50 = df_d['Close'].rolling(50).mean().iloc[-1]
                trend = "UP" if current_price > float(ma50) else "DOWN"
            else:
                trend = "RANGE"
            
            # 找出最近的關鍵位
            level_prices = [l[1] for l in levels]
            nearby_levels = []
            closest_level = None
            
            if level_prices:
                level_prices.sort(key=lambda x: abs(x - current_price))
                nearby_levels = level_prices[:2]
                closest_level = nearby_levels[0]

            # 判斷 4H 吞噬訊號
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
            
            # 判斷價格是否在關鍵位附近 (容錯率 1.5%)
            is_near_level = False
            for lvl in nearby_levels:
                if abs(current_price - lvl) / current_price < 0.015: 
                    is_near_level = True
            
            # 生成結論
            if signal and is_near_level:
                final_decision = f"🔥 發現訊號：{signal} (且位於關鍵位附近)"
                decision_color = "red" if "空頭" in signal else "green"
            elif signal:
                final_decision = f"⚠️ 發現訊號：{signal} (但未緊貼關鍵位)"
                decision_color = "orange"
            elif is_near_level:
                final_decision = "👀 價格回到關鍵位，請密切關注 4H 是否出現吞噬形態"
                decision_color = "blue"
            else:
                final_decision = "💤 目前位於中間地帶，無動作"
                decision_color = "gray"

            # --- 顯示結果 UI ---
            st.markdown(f"### 🎯 分析結論：:{decision_color}[{final_decision}]")
            
            c1, c2, c3 = st.columns(3)
            c1.metric("目前價格", f"{current_price:.2f}")
            c1.caption(f"數據更新: {df_4h.index[-1].strftime('%m-%d %H:%M')}")
            
            c2.metric("日線趨勢 (vs 50MA)", "📈 上升趨勢" if trend == "UP" else "📉 下跌趨勢")
            
            if nearby_levels:
                c3.warning(f"最近支撐/阻力：\n{nearby_levels[0]:.2f}")
            else:
                c3.info("附近無明顯結構")

            st.markdown("---")

            # --- 繪圖設定 (修正 Bug 的地方) ---
            # 定義顏色：上漲綠色，下跌紅色
            mc = mpf.make_marketcolors(up='#00ff00', down='#ff0000', inherit=True)
            # 修正：使用 base_mpf_style 而不是 style
            s  = mpf.make_mpf_style(marketcolors=mc, base_mpf_style='nightclouds')

            # 1. 繪製日線圖
            st.subheader("1️⃣ 日線圖 (Daily) - 結構總覽")
            if level_prices:
                # 只畫出最近的 5 條線，避免圖表太亂
                hlines_to_plot = level_prices[:5] 
                fig_d, ax_d = mpf.plot(
                    df_d.tail(100),
                    type='candle',
                    style=s,
                    hlines=dict(hlines=hlines_to_plot, colors=['#FF9900']*len(hlines_to_plot), linestyle='-.', linewidths=1.0),
                    title=f"{symbol} Daily Levels",
                    returnfig=True,
                    volume=False,
                    datetime_format='%Y-%m-%d',
                    tight_layout=True
                )
                st.pyplot(fig_d)
            else:
                fig_d, ax_d = mpf.plot(
                    df_d.tail(100), type='candle', style=s, title=f"{symbol} Daily", returnfig=True, volume=False
                )
                st.pyplot(fig_d)
            
            # 2. 繪製 4H 圖
            st.subheader("2️⃣ 4小時圖 (4H) - 進場觀察")
            latest_time_str = df_4h.index[-1].strftime('%m-%d %H:%M')
            
            if closest_level:
                fig_4h, ax_4h = mpf.plot(
                    df_4h.tail(40), # 放大看最近 40 根
                    type='candle',
                    style=s,
                    # 在 4H 圖上也畫出那條最重要的日線關鍵位
                    hlines=dict(hlines=[closest_level], colors=['#FF9900'], linestyle='--', linewidths=2.0),
                    title=f"{symbol} 4H Price Action (Last: {latest_time_str})",
                    returnfig=True,
                    volume=False,
                    datetime_format='%m-%d %H:%M',
                    tight_layout=True
                )
                st.pyplot(fig_4h)
                st.caption(f"橘色虛線 ({closest_level:.2f}) 為來自日線的關鍵位。若 K 線在此處出現「吞噬」，勝率較高。")
            else:
                fig_4h, ax_4h = mpf.plot(
                    df_4h.tail(40),
                    type='candle',
                    style=s,
                    title=f"{symbol} 4H Price Action",
                    returnfig=True,
                    volume=False,
                    datetime_format='%m-%d %H:%M',
                    tight_layout=True
                )
                st.pyplot(fig_4h)

        else:
            st.error("無法分析，請確認交易對 (如 BTC/USDT)。")
