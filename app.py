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
    symbol = st.text_input("輸入代號 (如 BTC-USD, AAPL, 2330.TW)", value="BTC-USD")
    
    st.markdown("---")
    st.subheader("策略參數")
    ma_period = st.number_input("日線趨勢均線 (MA)", value=50, min_value=10)
    kd_threshold = st.number_input("4H KD 低檔買進區 (<數值)", value=30, max_value=50)

# ==========================================
# 3. 核心邏輯函數 (修正了 Truth Value 錯誤)
# ==========================================
def fetch_and_analyze(symbol):
    try:
        # 1. 抓取日線數據 (判斷大趨勢)
        df_day = yf.download(symbol, period="1y", interval="1d", progress=False)
        
        # 2. 抓取小時線數據 (模擬 4H/短線 找買點)
        df_intraday = yf.download(symbol, period="1mo", interval="1h", progress=False)

        # --- 修正重點 A: 處理 yfinance 可能回傳的多層索引 (MultiIndex) ---
        if isinstance(df_day.columns, pd.MultiIndex):
            df_day.columns = df_day.columns.get_level_values(0)
        if isinstance(df_intraday.columns, pd.MultiIndex):
            df_intraday.columns = df_intraday.columns.get_level_values(0)

        # 檢查數據是否為空
        if df_day.empty or df_intraday.empty:
            return None, None, "❌ 抓不到數據，請確認代號是否正確"

        # --- 步驟 A: 日線邏輯 ---
        # 計算 SMA
        df_day['MA_Trend'] = ta.sma(df_day['Close'], length=ma_period)
        
        # 取得最新一天的收盤價與 MA (修正重點 B: 使用 .iloc[-1].item() 強制轉為純數字)
        try:
            current_price = df_day['Close'].iloc[-1]
            # 如果是 Series (單一值但帶索引)，轉為 float
            if isinstance(current_price, pd.Series):
                current_price = float(current_price.iloc[0])
            else:
                current_price = float(current_price)

            current_ma = df_day['MA_Trend'].iloc[-1]
            if isinstance(current_ma, pd.Series):
                current_ma = float(current_ma.iloc[0])
            else:
                current_ma = float(current_ma)
        except:
            # 萬一數據不足導致無法計算
            return None, None, "⚠️ 數據計算錯誤，可能是歷史資料不足"
        
        # 判斷趨勢
        trend_bool = current_price > current_ma
        trend_status = "🟢 多頭 (看漲)" if trend_bool else "🔴 空頭 (看跌)"

        # --- 步驟 B: 小時線/4H 邏輯 ---
        # 計算 KD 指標
        k_period = 9
        d_period = 3
        stoch = ta.stoch(df_intraday['High'], df_intraday['Low'], df_intraday['Close'], k=k_period, d=d_period)
        
        # 把計算結果合併回去
        df_intraday = pd.concat([df_intraday, stoch], axis=1)
        
        # 取得 KD 值 (修正重點 C: 確保取出來的是純數字)
        # STOCHk 和 STOCHd 通常在最後兩欄
        def get_scalar(series_val):
            if isinstance(series_val, pd.Series):
                return float(series_val.iloc[0])
            return float(series_val)

        latest_k = get_scalar(df_intraday.iloc[-1, -2])
        latest_d = get_scalar(df_intraday.iloc[-1, -1])
        prev_k = get_scalar(df_intraday.iloc[-2, -2])
        prev_d = get_scalar(df_intraday.iloc[-2, -1])

        # 判斷是否黃金交叉
        # 現在 K > D 且 之前 K < D
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

    except Exception as e:
        # 捕捉所有異常並回傳
        return None, None, f"程式內部錯誤: {str(e)}"

# ==========================================
# 4. 執行與顯示
# ==========================================
if st.button("開始分析", type="primary"):
    with st.spinner("正在連線至交易所抓取數據並計算..."):
        result, df_d, df_h = fetch_and_analyze(symbol)
        
        if result:
            # 顯示結果
            st.markdown(f"### 🎯 最終建議：{result['advice']}")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("1. 日線趨勢分析")
                st.metric("目前價格", f"{result['price']:.2f}")
                st.metric(f"{ma_period}日均線 (MA)", f"{result['ma']:.2f}")
                st.info(f"趨勢判定：{result['trend']}")
                st.line_chart(df_d[['Close', 'MA_Trend']])

            with col2:
                st.subheader("2. 短線進場分析 (KD指標)")
                st.metric("K值", f"{result['k']:.2f}")
                st.metric("D值", f"{result['d']:.2f}")
                st.info(f"訊號判定：{result['signal']}")
                # 畫 KD 線 (只畫最近 100 根)
                if df_h is not None and df_h.shape[1] > 2:
                    st.line_chart(df_h.iloc[-100:, -2:]) 
        
        else:
            # 顯示 fetch_and_analyze 回傳的錯誤訊息
            st.error(df_h) # 這裡借用第三個回傳值顯示錯誤訊息

st.markdown("---")
st.caption("說明：本工具使用 yfinance 數據，依據 MA 與 KD 指標進行機械化判定。")
