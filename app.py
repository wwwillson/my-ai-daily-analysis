import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta

# ==========================================
# 1. 頁面設定
# ==========================================
st.set_page_config(layout="wide", page_title="硬派演算法 K線分析")
st.title("⚡ 雙時區演算法交易訊號 (無 AI 版)")
st.markdown("此工具不依賴 AI 圖片辨識，而是直接抓取數據進行數學邏輯運算。")

# ==========================================
# 2. 側邊欄：使用者輸入
# ==========================================
with st.sidebar:
    st.header("參數設定")
    # 讓使用者輸入代號，例如 BTC-USD 或 2330.TW
    symbol = st.text_input("輸入代號 (如 BTC-USD, AAPL, 2330.TW)", value="BTC-USD")
    
    st.markdown("---")
    st.subheader("策略參數")
    ma_period = st.number_input("日線趨勢均線 (MA)", value=50, min_value=10)
    kd_threshold = st.number_input("4H KD 低檔買進區 (<數值)", value=30, max_value=50)

# ==========================================
# 3. 核心邏輯函數 (這就是你寫在程式裡的判斷)
# ==========================================
def fetch_and_analyze(symbol):
    # 1. 抓取日線數據 (判斷大趨勢)
    # yfinance 免費版限制：4H 數據較難抓，我們用 1H (小時線) 聚合或直接用 1H 當作進場週期
    # 這裡為了展示，我們抓取最近 1 年的日線
    df_day = yf.download(symbol, period="1y", interval="1d", progress=False)
    
    # 2. 抓取小時線數據 (模擬較短週期找買點)
    # yfinance 只提供最近 730 天的小時級別數據
    df_intraday = yf.download(symbol, period="1mo", interval="1h", progress=False)

    if df_day.empty or df_intraday.empty:
        return None, None, "❌ 抓不到數據，請確認代號是否正確"

    # --- 步驟 A: 日線邏輯 (寫死) ---
    # 計算 SMA (移動平均線)
    df_day['MA_Trend'] = ta.sma(df_day['Close'], length=ma_period)
    
    # 取得最新一天的收盤價與 MA
    current_price = df_day['Close'].iloc[-1]
    current_ma = df_day['MA_Trend'].iloc[-1]
    
    # 判斷趨勢
    trend_status = "🟢 多頭 (看漲)" if current_price > current_ma else "🔴 空頭 (看跌)"
    trend_bool = True if current_price > current_ma else False

    # --- 步驟 B: 小時線/4H 邏輯 (寫死) ---
    # 計算 KD 指標 (Stoch)
    k_period = 9
    d_period = 3
    
    # pandas_ta 會回傳 STOCHk 和 STOCHd
    stoch = ta.stoch(df_intraday['High'], df_intraday['Low'], df_intraday['Close'], k=k_period, d=d_period)
    
    # 把計算結果合併回去
    df_intraday = pd.concat([df_intraday, stoch], axis=1)
    
    # 取得最新的 K 和 D 值
    # 欄位名稱通常是 STOCHk_9_3_3 和 STOCHd_9_3_3 (視套件版本而定，這裡用 iloc 取比較保險)
    latest_k = df_intraday.iloc[-1, -2] # 倒數第二欄通常是 K
    latest_d = df_intraday.iloc[-1, -1] # 倒數第一欄通常是 D
    prev_k = df_intraday.iloc[-2, -2]
    prev_d = df_intraday.iloc[-2, -1]

    # 判斷是否黃金交叉 (現在 K > D 且 之前 K < D) 且 在低檔區
    is_gold_cross = (latest_k > latest_d) and (prev_k < prev_d)
    is_low_level = latest_k < kd_threshold
    
    entry_signal = "無訊號"
    if is_gold_cross and is_low_level:
        entry_signal = "🚀 黃金交叉 (買點出現!)"
    elif is_low_level:
        entry_signal = "⚠️ 進入超賣區 (等待交叉)"
    else:
        entry_signal = "觀望中"

    # --- 綜合建議 ---
    advice = ""
    if trend_bool and (is_gold_cross and is_low_level):
        advice = "🔥 強烈建議買進 (趨勢向上 + 短線起漲)"
    elif not trend_bool:
        advice = "⛔ 日線趨勢向下，不建議做多"
    else:
        advice = "👀 趨勢向上，但短線尚未出現明確買訊"

    return {
        "price": current_price,
        "ma": current_ma,
        "trend": trend_status,
        "k": latest_k,
        "d": latest_d,
        "signal": entry_signal,
        "advice": advice
    }, df_day, df_intraday

# ==========================================
# 4. 執行與顯示
# ==========================================
if st.button("開始分析", type="primary"):
    with st.spinner("正在連線至交易所抓取數據並計算..."):
        try:
            result, df_d, df_h = fetch_and_analyze(symbol)
            
            if result:
                # 顯示大字報結果
                st.markdown(f"### 🎯 最終建議：{result['advice']}")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("1. 日線趨勢分析")
                    st.metric("目前價格", f"{result['price']:.2f}")
                    st.metric(f"{ma_period}日均線 (MA)", f"{result['ma']:.2f}")
                    st.info(f"趨勢判定：{result['trend']}")
                    # 畫圖
                    st.line_chart(df_d[['Close', 'MA_Trend']])

                with col2:
                    st.subheader("2. 短線進場分析 (KD指標)")
                    st.metric("K值", f"{result['k']:.2f}")
                    st.metric("D值", f"{result['d']:.2f}")
                    st.info(f"訊號判定：{result['signal']}")
                    # 畫 KD 線 (只畫最近 100 根 bar 以免太密)
                    st.line_chart(df_h.iloc[-100:, -2:]) 
            
            else:
                st.error("分析失敗，請檢查代號")
                
        except Exception as e:
            st.error(f"程式發生錯誤: {e}")

st.markdown("---")
st.caption("說明：本工具使用 yfinance 數據，依據 MA 與 KD 指標進行機械化判定。")
