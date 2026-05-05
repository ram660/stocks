# Stock Analysis Dashboard with Advanced Options Analytics

A professional Streamlit-based stock analysis application that provides real-time technical signals and deep options chain analytics.

## 🚀 Key Features

### 1. 📊 Technical Signals Engine

- **18+ Indicators**: RSI, MACD, EMA Crosses, Bollinger Bands, VWAP, and more.
- **Verdict Scoring**: Integrated scoring system providing `BUY`, `SELL`, `WATCH`, or `HOLD` recommendations.
- **Chart Patterns**: Automated detection of Double Tops/Bottoms.

### 2. 🧠 Advanced Options Analytics

- **IV Rank / Percentile**: Gauge if options are cheap or expensive.
- **Expected Move**: ATM straddle-implied ±$ move for each expiry.
- **Black-Scholes Greeks**: Live Delta, Gamma, Theta, and Vega heatmaps.
- **Gamma Exposure (GEX)**: Visualize market maker positioning and gamma flip levels.
- **Strategy Scanner**: Suggested trades (Covered Calls, Iron Condors, etc.) with live P&L profiles.
- **Options Flow**: Unusual activity detection (Vol/OI > 1.5x) and Bull/Bear $ premium flow.

## 🛠️ Setup & Installation

1. **Clone the repository**:

   ```bash
   git clone https://github.com/ram660/stocks.git
   cd stocks
   ```

2. **Install dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

3. **Run the app**:
   ```bash
   streamlit run app.py
   ```

## ⚙️ Configuration

Edit `config.py` to:

- Toggle technical indicators on/off.
- Adjust signal weights.
- Add your **Finnhub API Key** for real-time (v.s. delayed) quotes.

---

Built with Python, Streamlit, and Plotly.
