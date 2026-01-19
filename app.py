import streamlit as st
import ccxt
import pandas as pd
import mplfinance as mpf
import numpy as np
from datetime import datetime
from streamlit_autorefresh import st_autorefresh # 需安裝此套件

# ==========================================
# 1. 頁面設定與策略邏輯說明
# ==========================================
st.set_page_config(layout="wide", page_title="Binance US PA 策略監控")
st.title("📈 雙時區 PA 策略自動監控 (Binance US)") 

# 詳細邏輯說明區塊
with st.expander("📖 點擊查看：策略邏輯與自動監控說明", expanded=False):
    st.markdown("""
    #### 自動監控模式說明：
    1. 請在側邊欄勾選 **「🔄 啟用每2小時自動更新」**。
    2. **瀏覽器分頁必須保持開啟**，程式才會定時運作。
    3. 若偵測到訊號，將會播放提示音並彈出訊息。
    *(注意：部分瀏覽器可能會阻擋自動播放聲音，請確保您有點擊過頁面)*

    #### 策略邏輯：
    *   **日線關鍵位**：Fractal (左2右2) 支撐/阻力。
    *   **4H 吞噬形態**：實體包覆實體 (Engulfing) 且配合日線趨勢。
    """)

# ==========================================
# 2. 側邊欄設定 & 自動刷新邏輯
# ==========================================
with st.sidebar:
    st.header("設定")
    symbol = st.text_input("輸入交易對", value="BTC/USDT")
    lookback_days = st.slider("日線回溯天數", 100, 730, 365)
    
    st.markdown("---")
    st.header("⏰ 自動監控設定")
    # 這裡設定自動刷新
    enable_auto = st.checkbox("🔄 啟用每 2 小時自動更新", value=False)
    
    # 用於測試的選項 (正式使用請無視)
    test_mode = st.checkbox("🧪 測試模式 (縮短為 30 秒更新)", value=False, help="勾選後更新頻率變為30秒，方便測試聲音")

    status_text = st.empty()

# 設定刷新頻率
if enable_auto:
    # 如果是測試模式 30秒(30000ms)，否則 2小時(7200000ms)
    interval_time = 30 * 1000 if test_mode else 2 * 60 * 60 * 1000
    
    count = st_autorefresh(interval=interval_time, key="data_refresh")
    status_text.success(f"監控中... 已刷新 {count} 次")
else:
    status_text.info("手動模式")

# ==========================================
# 3. 核心功能函數 (聲音與算法)
# ==========================================

def play_sound():
    """
    在瀏覽器播放提示音 (使用 HTML5 Audio)
    """
    # 這裡使用一個線上的短音效 URL (清脆的叮咚聲)
    sound_url = "https://assets.mixkit.co/active_storage/sfx/2869/2869-preview.mp3"
    
    # 透過 HTML 隱藏標籤自動播放
    audio_html = f"""
        <audio autoplay="true">
        <source src="{sound_url}" type="audio/mp3">
        </audio>
    """
    st.markdown(audio_html, unsafe_allow_html=True)

def is_support(df, i):
    try:
        cond1 = df['Low'].iloc[i] < df['Low'].iloc[i-1]
        cond2 = df['Low'].iloc[i] < df['Low'].iloc[i+1]
        cond3 = df['Low'].iloc[i+1] < df['Low'].iloc[i+2]
        cond4 = df['Low'].iloc[i-1] < df['Low'].iloc[i-2]
        return cond1 and cond2 and cond3 and cond4
    except:
        return False

def is_resistance(df, i):
    try:
        cond1 = df['High'].iloc[i] > df['High'].iloc[i-1]
        cond2 = df['High'].iloc[i] > df['High'].iloc[i+1]
        cond3 = df['High'].iloc[i+1] > df['High'].iloc[i+2]
        cond4 = df['High'].iloc[i-1] > df['High'].iloc[i-2]
        return cond1 and cond2 and cond3 and cond4
    except:
        return False

def is_far_from_existing(l, levels, mean_candle_size):
    if len(levels) == 0:
        return True
    for x in levels:
        if abs(l - x[1]) < mean_candle_size * 2:
            return False
    return True

def find_levels(df):
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
    open_curr, close_curr = float(open_curr), float(close_curr)
    open_prev, close_prev = float(open_prev), float(close_prev)

    if trend_direction in ["UP", "RANGE"]:
        if (close_prev < open_prev): # 昨收黑
            if (close_curr > open_curr): # 今收紅
                if (close_curr > open_prev) and (open_curr < close_prev):
                    return "🟢 多頭吞噬 (Bullish)"
    
    if trend_direction in ["DOWN", "RANGE"]:
        if (close_prev > open_prev): # 昨收紅
            if (close_curr < open_curr): # 今收黑
                if (close_curr < open_prev) and (open_curr > close_prev):
                    return "🔴 空頭吞噬 (Bearish)"
    return None

def fetch_binance_data(symbol, days):
    try:
        exchange = ccxt.binanceus({'enableRateLimit': True})
        ohlcv_d = exchange.fetch_ohlcv(symbol, timeframe='1d', limit=days)
        if not ohlcv_d: return None, None, "抓取不到日線"
        df_d = pd.DataFrame(ohlcv_d, columns=['timestamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
        df_d['timestamp'] = pd.to_datetime(df_d['timestamp'], unit='ms').dt.tz_localize('UTC').dt.tz_convert('Asia/Taipei')
        df_d.set_index('timestamp', inplace=True)

        ohlcv_4h = exchange.fetch_ohlcv(symbol, timeframe='4h', limit=100)
        if not ohlcv_4h: return None, None, "抓取不到 4H 數據"
        df_4h = pd.DataFrame(ohlcv_4h, columns=['timestamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
        df_4h['timestamp'] = pd.to_datetime(df_4h['timestamp'], unit='ms').dt.tz_localize('UTC').dt.tz_convert('Asia/Taipei')
        df_4h.set_index('timestamp', inplace=True)

        return df_d, df_4h, None
    except Exception as e:
        return None, None, f"API 錯誤: {str(e)}"

# ==========================================
# 4. 主執行邏輯 (按鈕 或 自動刷新 都會觸發)
# ==========================================

# 觸發條件：點擊按鈕 OR 啟用自動更新
run_analysis = st.sidebar.button("🚀 立即手動分析", type="primary") or enable_auto

if run_analysis:
    with st.spinner(f"正在分析 {symbol} ..."):
        df_d, df_4h, err = fetch_binance_data(symbol, lookback_days)
        
        if err:
            st.error(f"錯誤: {err}")
        elif df_d is not None and not df_d.empty:
            
            # --- 運算邏輯 ---
            levels = find_levels(df_d)
            current_price = float(df_d['Close'].iloc[-1])
            
            if len(df_d) >= 50:
                ma50 = df_d['Close'].rolling(50).mean().iloc[-1]
                trend = "UP" if current_price > float(ma50) else "DOWN"
            else:
                trend = "RANGE"
            
            level_prices = [l[1] for l in levels]
            nearby_levels = []
            closest_level = None
            if level_prices:
                level_prices.sort(key=lambda x: abs(x - current_price))
                nearby_levels = level_prices[:2]
                closest_level = nearby_levels[0]

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
            
            # 判斷是否在關鍵位附近 (1.5%)
            is_near_level = False
            for lvl in nearby_levels:
                if abs(current_price - lvl) / current_price < 0.015: 
                    is_near_level = True
            
            # --- 判斷結論與觸發通知 ---
            notify_msg = None
            
            if signal and is_near_level:
                final_decision = f"🔥 強烈訊號：{signal} 且在關鍵位!"
                decision_color = "red" if "空頭" in signal else "green"
                notify_msg = f"注意！{symbol} 出現 {signal} 且位於關鍵位附近"
                
            elif signal:
                final_decision = f"⚠️ 訊號：{signal} (未緊貼關鍵位)"
                decision_color = "orange"
                # 可選：如果只要強烈訊號才叫，這裡就不要賦值給 notify_msg
                notify_msg = f"提醒：{symbol} 出現 {signal}"
                
            elif is_near_level:
                final_decision = "👀 價格觸及關鍵位，等待形態"
                decision_color = "blue"
            else:
                final_decision = "💤 觀望中"
                decision_color = "gray"

            # --- 觸發通知 (聲音 + Toast) ---
            if notify_msg:
                st.toast(notify_msg, icon="🔔") # 右下角彈出通知
                play_sound() # 播放聲音
                # 在畫面最上方也顯示醒目提示
                st.warning(f"🔔 {datetime.now().strftime('%H:%M')} - {notify_msg}")

            # --- UI 顯示 ---
            st.markdown(f"### 🎯 結論：:{decision_color}[{final_decision}]")
            
            c1, c2, c3 = st.columns(3)
            c1.metric("價格", f"{current_price:.2f}")
            c2.metric("趨勢", trend)
            if nearby_levels:
                c3.warning(f"關鍵位: {nearby_levels[0]:.2f}")
            
            st.markdown("---")
            
            # 繪圖 (使用 base_mpf_style 修正樣式)
            mc = mpf.make_marketcolors(up='#00ff00', down='#ff0000', inherit=True)
            s  = mpf.make_mpf_style(marketcolors=mc, base_mpf_style='nightclouds')
            
            # Daily Chart
            st.subheader("1️⃣ 日線結構")
            if level_prices:
                fig_d, ax_d = mpf.plot(
                    df_d.tail(100), type='candle', style=s,
                    hlines=dict(hlines=level_prices[:5], colors=['#FF9900']*len(level_prices[:5]), linestyle='-.', linewidths=1.0),
                    returnfig=True, volume=False, datetime_format='%Y-%m-%d', tight_layout=True
                )
                st.pyplot(fig_d)
            
            # 4H Chart
            st.subheader("2️⃣ 4H 入場訊號")
            if closest_level:
                fig_4h, ax_4h = mpf.plot(
                    df_4h.tail(40), type='candle', style=s,
                    hlines=dict(hlines=[closest_level], colors=['#FF9900'], linestyle='--', linewidths=2.0),
                    title=f"{symbol} 4H (Updated: {df_4h.index[-1].strftime('%H:%M')})",
                    returnfig=True, volume=False, datetime_format='%m-%d %H:%M', tight_layout=True
                )
                st.pyplot(fig_4h)
            else:
                 fig_4h, ax_4h = mpf.plot(
                    df_4h.tail(40), type='candle', style=s,
                    title=f"{symbol} 4H", returnfig=True, volume=False, tight_layout=True
                )
                 st.pyplot(fig_4h)

        else:
            st.error("無法分析，請確認交易對。")
