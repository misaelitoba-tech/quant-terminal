import streamlit as st
import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pytz
import os
import plotly.graph_objects as go
import warnings

warnings.filterwarnings('ignore')

st.set_page_config(
    page_title='Santi imab | Quant Terminal Pro',
    page_icon='⚡',
    layout='wide',
    initial_sidebar_state='expanded'
)

st.markdown("""
<style>
    .stApp { background-color: #0B0E14; color: #E0E6ED; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    #MainMenu, footer {visibility: hidden;}
    .brand-header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255, 255, 255, 0.08); padding-bottom: 15px; margin-bottom: 25px; }
    .brand-title { font-size: 1.6rem; font-weight: 800; color: #FFFFFF; }
    .brand-title span { color: #00E676; }
    .brand-subtitle { font-size: 0.8rem; color: #788394; text-transform: uppercase; letter-spacing: 1px; }
    .quant-card { background: #131722; border: 1px solid #2A2E39; border-radius: 12px; padding: 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.4); }
    .card-label { font-size: 0.75rem; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; color: #788394; margin-bottom: 8px; }
    .card-value { font-size: 1.8rem; font-weight: 800; font-family: 'SF Mono', 'Fira Code', monospace; }
    .val-price { color: #2962FF; }
    .val-vah { color: #FF5252; }
    .val-poc { color: #BB86FC; }
    .val-val { color: #00E676; }
    .sub-info { font-size: 0.8rem; color: #B2B9C0; margin-top: 8px; }
    .section-head { font-size: 1.1rem; font-weight: 700; color: #FFFFFF; margin-top: 25px; margin-bottom: 12px; }
    .stButton>button { width: 100%; border-radius: 8px; font-weight: 600; background-color: #2962FF; color: white; border: none; }
    .stButton>button:hover { background-color: #1E4BD8; }
    
    /* Live Signal Cards */
    .signal-card-long { background: rgba(0, 230, 118, 0.05); border: 2px solid #00E676; border-radius: 12px; padding: 20px; }
    .signal-card-short { background: rgba(255, 82, 82, 0.05); border: 2px solid #FF5252; border-radius: 12px; padding: 20px; }
    .signal-card-triggered { background: rgba(255, 171, 0, 0.05); border: 2px solid #FFAB00; border-radius: 12px; padding: 20px; }
    .signal-title-long { font-size: 1.4rem; font-weight: 800; color: #00E676; margin-bottom: 5px; }
    .signal-title-short { font-size: 1.4rem; font-weight: 800; color: #FF5252; margin-bottom: 5px; }
    .signal-title-triggered { font-size: 1.4rem; font-weight: 800; color: #FFAB00; margin-bottom: 5px; }
</style>
""", unsafe_allow_html=True)

# Conexión resiliente libre de geobloqueo de IP en EE. UU.
@st.cache_resource
def get_working_exchange(symbol_name):
    exchanges_to_try = [
        ('okx', ccxt.okx({'enableRateLimit': True})),
        ('kraken', ccxt.kraken({'enableRateLimit': True})),
        ('coinbase', ccxt.coinbase({'enableRateLimit': True})),
        ('gate', ccxt.gate({'enableRateLimit': True}))
    ]
    
    for name, ex in exchanges_to_try:
        try:
            ex.fetch_ohlcv(symbol_name, timeframe='15m', limit=5)
            return ex, name.upper()
        except Exception:
            continue
            
    # Fallback por defecto a Kraken
    return ccxt.kraken({'enableRateLimit': True}), "KRAKEN (CLOUD SAFE)"

# Sidebar Global
st.sidebar.markdown('### ⚙️ Configuración Estrategia')
symbol = st.sidebar.text_input('Activo', 'BTC/USDT')
timeframe = st.sidebar.selectbox('Temporalidad Velas', ['5m', '15m'], index=1)
ny_window_only = st.sidebar.checkbox('Filtrar Sesión NY (09:30 - 12:00)', value=True)
use_ema = st.sidebar.checkbox('📈 Usar Filtro Tendencia (EMA 200)', value=True)
rr_ratio = st.sidebar.number_input('Ratio Risk:Reward (1:N)', value=2.0, step=0.5)
stop_loss_dist = st.sidebar.number_input('Stop Loss Distancia ($)', value=150.0, step=10.0)

exchange, ex_name = get_working_exchange(symbol)

# Header
ny_tz = pytz.timezone('America/New_York')
now_ny_str = datetime.now(ny_tz).strftime('%H:%M:%S EST')
st.markdown(f'''
<div class="brand-header">
    <div>
        <div class="brand-title">Santi imab <span>Terminal Pro</span></div>
        <div class="brand-subtitle">Order Flow & Institutional Volume Profile Terminal</div>
    </div>
    <div><span class="status-badge-active">● CONNECTED ({ex_name} | {now_ny_str})</span></div>
</div>
''', unsafe_allow_html=True)

tab_live, tab_backtest = st.tabs(["🔴 Monitoreo En Vivo (Live Engine)", "🧪 Backtester Histórico"])

def calculate_value_area(df_slice, target_ratio=0.70):
    if df_slice.empty: return None, None, None
    prices = df_slice['close'].round().tolist()
    volumes = df_slice['volume'].tolist()
    profile = {}
    for p, v in zip(prices, volumes):
        profile[p] = profile.get(p, 0.0) + v
    
    s = pd.Series(profile).sort_index()
    if s.empty: return None, None, None
    poc = s.idxmax()
    total_vol = s.sum()
    target_vol = total_vol * target_ratio
    poc_idx = s.index.get_loc(poc)
    accumulated_vol = s.iloc[poc_idx]
    low_idx, high_idx = poc_idx, poc_idx
    
    while accumulated_vol < target_vol:
        vol_above = s.iloc[high_idx + 1] if high_idx + 1 < len(s) else 0
        vol_below = s.iloc[low_idx - 1] if low_idx - 1 >= 0 else 0
        if vol_above == 0 and vol_below == 0: break
        if vol_above >= vol_below:
            accumulated_vol += vol_above
            high_idx += 1
        else:
            accumulated_vol += vol_below
            low_idx -= 1
    return poc, s.index[high_idx], s.index[low_idx]

# --- TAB 1: LIVE MONITORING ---
with tab_live:
    mx_tz = pytz.timezone('America/Mexico_City')
    now_mx_str = datetime.now(mx_tz).strftime('%I:%M %p CDMX')
    
    st.markdown('<div class="section-head">📡 Estado del Mercado & Nivel Institucional Actual</div>', unsafe_allow_html=True)
    if st.button("🔄 Actualizar Datos En Vivo"):
        st.rerun()

    try:
        ohlcv_live = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=300)
        df_live = pd.DataFrame(ohlcv_live, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df_live['datetime'] = pd.to_datetime(df_live['timestamp'], unit='ms', utc=True)
        df_live['ema200'] = df_live['close'].ewm(span=200, adjust=False).mean()
        
        current_price = df_live['close'].iloc[-1]
        current_ema = df_live['ema200'].iloc[-1]
        
        poc_live, vah_live, val_live = calculate_value_area(df_live.tail(96))
        
        lc1, lc2, lc3, lc4 = st.columns(4)
        lc1.markdown(f'<div class="quant-card"><div class="card-label">Precio En Vivo</div><div class="card-value val-price">${current_price:,.2f}</div><div class="sub-info">{symbol} ({ex_name})</div></div>', unsafe_allow_html=True)
        lc2.markdown(f'<div class="quant-card"><div class="card-label">VAH (Techo Liquidez)</div><div class="card-value val-vah">${vah_live if vah_live else 0:,.2f}</div><div class="sub-info">Resistencia 70% VA</div></div>', unsafe_allow_html=True)
        lc3.markdown(f'<div class="quant-card"><div class="card-label">POC (Point of Control)</div><div class="card-value val-poc">${poc_live if poc_live else 0:,.2f}</div><div class="sub-info">Máxima Acumulación</div></div>', unsafe_allow_html=True)
        lc4.markdown(f'<div class="quant-card"><div class="card-label">VAL (Piso Liquidez)</div><div class="card-value val-val">${val_live if val_live else 0:,.2f}</div><div class="sub-info">Soporte 70% VA</div></div>', unsafe_allow_html=True)

        st.markdown('<div class="section-head">⚡ Orden Sugerida para la Sesión</div>', unsafe_allow_html=True)
        
        is_bullish = current_price > current_ema
        
        if is_bullish and val_live:
            entry_p = val_live
            sl_p = entry_p - stop_loss_dist
            tp_p = entry_p + (stop_loss_dist * rr_ratio)
            
            is_triggered = current_price <= entry_p
            card_class = "signal-card-triggered" if is_triggered else "signal-card-long"
            title_class = "signal-title-triggered" if is_triggered else "signal-title-long"
            title_text = f"⚠️ ORDEN ACTIVADA (LONG) 🕒 {now_mx_str}" if is_triggered else f"⏳ ORDEN PENDIENTE: BUY LIMIT (LONG) 🕒 {now_mx_str}"
            status_desc = "📈 El precio ya tocó el nivel de entrada. El trade está en desarrollo." if is_triggered else "📉 Esperando que el precio retroceda al VAL para activar la orden."
            
            st.markdown(f'''
            <div class="{card_class}">
                <div class="{title_class}">{title_text}</div>
                <p><strong>Estado:</strong> {status_desc}<br>
                <strong>Tendencia Institucional:</strong> ALCISTA (Precio sobre EMA 200: ${current_ema:,.2f})</p>
                <hr style="border-color: rgba(255,255,255,0.1);">
                <div style="display: flex; justify-content: space-between; font-size: 1.1rem; font-family: monospace;">
                    <div>📌 <strong>Entrada Limit (VAL):</strong> ${entry_p:,.2f}</div>
                    <div>🛑 <strong>Stop Loss:</strong> ${sl_p:,.2f}</div>
                    <div>🎯 <strong>Take Profit:</strong> ${tp_p:,.2f}</div>
                </div>
            </div>
            ''', unsafe_allow_html=True)
            
        elif not is_bullish and vah_live:
            entry_p = vah_live
            sl_p = entry_p + stop_loss_dist
            tp_p = entry_p - (stop_loss_dist * rr_ratio)
            
            is_triggered = current_price >= entry_p
            card_class = "signal-card-triggered" if is_triggered else "signal-card-short"
            title_class = "signal-title-triggered" if is_triggered else "signal-title-short"
            title_text = f"⚠️ ORDEN ACTIVADA (SHORT) 🕒 {now_mx_str}" if is_triggered else f"⏳ ORDEN PENDIENTE: SELL LIMIT (SHORT) 🕒 {now_mx_str}"
            status_desc = "📉 El precio ya tocó el nivel de entrada. El trade está en desarrollo." if is_triggered else "📈 Esperando que el precio suba al VAH para activar la orden."
            
            st.markdown(f'''
            <div class="{card_class}">
                <div class="{title_class}">{title_text}</div>
                <p><strong>Estado:</strong> {status_desc}<br>
                <strong>Tendencia Institucional:</strong> BAJISTA (Precio bajo EMA 200: ${current_ema:,.2f})</p>
                <hr style="border-color: rgba(255,255,255,0.1);">
                <div style="display: flex; justify-content: space-between; font-size: 1.1rem; font-family: monospace;">
                    <div>📌 <strong>Entrada Limit (VAH):</strong> ${entry_p:,.2f}</div>
                    <div>🛑 <strong>Stop Loss:</strong> ${sl_p:,.2f}</div>
                    <div>🎯 <strong>Take Profit:</strong> ${tp_p:,.2f}</div>
                </div>
            </div>
            ''', unsafe_allow_html=True)
        else:
            st.warning("Calculando niveles de volumen del día...")

    except Exception as e:
        st.error(f"Error conectando con el proveedor de datos: {e}")

# --- TAB 2: HISTORICAL BACKTESTING ---
with tab_backtest:
    st.sidebar.markdown('---')
    st.sidebar.markdown('### 🧪 Filtros Backtest')
    days_back = st.sidebar.slider('Días Históricos a Auditar', min_value=15, max_value=90, value=90)
    run_backtest = st.sidebar.button('🚀 Ejecutar Backtest Completo')

    def fetch_complete_ohlcv(symbol, tf, days):
        now = datetime.now(pytz.UTC)
        start_dt = now - timedelta(days=days + 7) 
        since = int(start_dt.timestamp() * 1000)
        all_ohlcv = []
        
        while True:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe=tf, since=since, limit=1000)
            if not ohlcv: break
            all_ohlcv.extend(ohlcv)
            since = ohlcv[-1][0] + 1
            if ohlcv[-1][0] >= int(now.timestamp() * 1000): break
            
        df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df.drop_duplicates(subset=['timestamp'], inplace=True)
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
        df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
        
        real_start = now - timedelta(days=days)
        df = df[df['datetime'] >= real_start].copy()
        
        ny_tz = pytz.timezone('America/New_York')
        df['datetime_ny'] = df['datetime'].dt.tz_convert(ny_tz)
        df['date_ny'] = df['datetime_ny'].dt.date
        df['time_ny'] = df['datetime_ny'].dt.time
        return df

    def execute_historical_backtest(symbol, days, tf, filter_ny, rr, sl_dist, use_ema_filter):
        try:
            df = fetch_complete_ohlcv(symbol, tf, days)
            trades = []
            unique_dates = df['date_ny'].unique()
            
            for d in unique_dates:
                day_df = df[df['date_ny'] == d]
                if len(day_df) < 15: continue
                
                poc, vah, val = calculate_value_area(day_df)
                if not poc or not vah or not val: continue
                
                in_trade = False
                
                for i, row in day_df.iterrows():
                    if in_trade: continue
                    
                    if filter_ny:
                        t = row['time_ny']
                        if not (datetime.strptime('09:30', '%H:%M').time() <= t <= datetime.strptime('12:00', '%H:%M').time()):
                            continue
                    
                    tol = sl_dist * 0.5
                    ema_val = row['ema200']
                    
                    trend_long_ok = (row['close'] > ema_val) if use_ema_filter else True
                    trend_short_ok = (row['close'] < ema_val) if use_ema_filter else True
                    
                    if abs(row['low'] - val) <= tol and row['close'] >= val and trend_long_ok:
                        entry = row['close']
                        tp = entry + (sl_dist * rr)
                        sl = entry - sl_dist
                        
                        future_df = day_df[day_df['timestamp'] > row['timestamp']]
                        for _, f_row in future_df.iterrows():
                            if f_row['high'] >= tp:
                                trades.append({'Fecha': row['datetime_ny'].strftime('%Y-%m-%d %H:%M'), 'Tipo': 'LONG en VAL', 'Entrada': entry, 'Result': 'WIN', 'PnL': (sl_dist * rr)})
                                break
                            elif f_row['low'] <= sl:
                                trades.append({'Fecha': row['datetime_ny'].strftime('%Y-%m-%d %H:%M'), 'Tipo': 'LONG en VAL', 'Entrada': entry, 'Result': 'LOSS', 'PnL': -sl_dist})
                                break

                    elif abs(row['high'] - vah) <= tol and row['close'] <= vah and trend_short_ok:
                        entry = row['close']
                        tp = entry - (sl_dist * rr)
                        sl = entry + sl_dist
                        
                        future_df = day_df[day_df['timestamp'] > row['timestamp']]
                        for _, f_row in future_df.iterrows():
                            if f_row['low'] <= tp:
                                trades.append({'Fecha': row['datetime_ny'].strftime('%Y-%m-%d %H:%M'), 'Tipo': 'SHORT en VAH', 'Entrada': entry, 'Result': 'WIN', 'PnL': (sl_dist * rr)})
                                break
                            elif f_row['high'] >= sl:
                                trades.append({'Fecha': row['datetime_ny'].strftime('%Y-%m-%d %H:%M'), 'Tipo': 'SHORT en VAH', 'Entrada': entry, 'Result': 'LOSS', 'PnL': -sl_dist})
                                break
                            
            return pd.DataFrame(trades)
        except Exception as e:
            st.error(f"Error en backtest: {e}")
            return pd.DataFrame()

    if run_backtest:
        with st.spinner(f'Descargando datos, calculando EMA 200 y Volume Profile...'):
            backtest_df = execute_historical_backtest(symbol, days_back, timeframe, ny_window_only, rr_ratio, stop_loss_dist, use_ema)
            st.session_state['backtest_df'] = backtest_df

    if 'backtest_df' in st.session_state and not st.session_state['backtest_df'].empty:
        df_res = st.session_state['backtest_df']
        total_trades = len(df_res)
        wins = len(df_res[df_res['Result'] == 'WIN'])
        losses = len(df_res[df_res['Result'] == 'LOSS'])
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0
        total_pnl = df_res['PnL'].sum()

        st.markdown('<div class="section-head">📊 Resultados del Backtest Histórico Completo</div>', unsafe_allow_html=True)
        sc1, sc2, sc3, sc4 = st.columns(4)
        sc1.markdown(f'<div class="quant-card"><div class="card-label">Win Rate Real</div><div class="card-value" style="color:{"#00E676" if win_rate>=35 else "#FF5252"};">{win_rate:.1f}%</div><div class="sub-info">{wins} W / {losses} L</div></div>', unsafe_allow_html=True)
        sc2.markdown(f'<div class="quant-card"><div class="card-label">Total Trades Auditados</div><div class="card-value">{total_trades}</div><div class="sub-info">En {days_back} días</div></div>', unsafe_allow_html=True)
        sc3.markdown(f'<div class="quant-card"><div class="card-label">PnL Acumulado Real</div><div class="card-value" style="color:{"#00E676" if total_pnl>=0 else "#FF5252"};">${total_pnl:,.2f} USD</div><div class="sub-info">R:R 1:{rr_ratio}</div></div>', unsafe_allow_html=True)
        sc4.markdown(f'<div class="quant-card"><div class="card-label">Profit Factor</div><div class="card-value">{(wins*(stop_loss_dist*rr_ratio))/(losses*stop_loss_dist) if losses>0 else 0:.2f}</div><div class="sub-info">Factor de Beneficio</div></div>', unsafe_allow_html=True)

        st.markdown('<div class="section-head">📈 Curva de PnL Completa</div>', unsafe_allow_html=True)
        cumulative_pnl = np.insert(np.cumsum(df_res['PnL'].values), 0, 0)
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=list(range(len(cumulative_pnl))),
            y=cumulative_pnl,
            mode='lines+markers',
            line=dict(color='#00E676' if cumulative_pnl[-1] >= 0 else '#FF5252', width=3),
            marker=dict(size=7, color='#0B0E14', line=dict(width=2, color='#00E676' if cumulative_pnl[-1] >= 0 else '#FF5252'))
        ))
        fig.update_layout(
            paper_bgcolor='#131722',
            plot_bgcolor='#131722',
            font=dict(color='#E0E6ED'),
            margin=dict(l=20, r=20, t=20, b=20),
            height=320,
            xaxis=dict(showgrid=False, title='Operaciones Auditadas'),
            yaxis=dict(showgrid=True, gridcolor='#2A2E39', title='Ganancia / Pérdida (USD)', zeroline=True, zerolinecolor='#404552')
        )
        st.plotly_chart(fig, use_container_width=True)

        st.markdown('<div class="section-head">📋 Registro Detallado de Trades Reales</div>', unsafe_allow_html=True)
        st.dataframe(df_res, use_container_width=True)
    else:
        st.info('👈 Selecciona los días en la barra lateral y presiona "🚀 Ejecutar Backtest Completo".')
