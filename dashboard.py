import streamlit as st
import pandas as pd
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from range import (
    run_backtest,
    backtest_summary,
    generate_trade_log,
    trade_statistics,
    performance_breakdown,
    simulate_viop_portfolio,
)

# Sayfa Genişlik ve Tema Ayarları
st.set_page_config(
    page_title="BIST ORB Breakout Dashboard",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Premium Arayüz İçin CSS Enjeksiyonu
st.markdown("""
<style>
    /* Premium Font ve Arka Plan İyileştirmeleri */
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Outfit', sans-serif;
    }
    
    /* Neon Glow Gradient Title */
    .dashboard-title {
        background: linear-gradient(90deg, #c084fc 0%, #6366f1 50%, #38bdf8 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 2.75rem;
        font-weight: 800;
        letter-spacing: -0.03em;
        margin-bottom: 2px;
        text-shadow: 0 0 40px rgba(168, 85, 247, 0.15);
    }
    
    /* Alt Başlık */
    .custom-subtitle {
        color: #94a3b8;
        font-size: 1.15rem;
        font-weight: 400;
        margin-top: -5px;
        margin-bottom: 30px;
    }
    
    /* Özel Kartlar (KPI Cards) */
    .kpi-container {
        display: flex;
        gap: 16px;
        margin-bottom: 30px;
        flex-wrap: wrap;
    }
    
    .kpi-card {
        flex: 1;
        min-width: 220px;
        padding: 24px;
        border-radius: 16px;
        background: linear-gradient(135deg, rgba(15, 23, 42, 0.75) 0%, rgba(9, 13, 22, 0.95) 100%);
        border: 1px solid rgba(255, 255, 255, 0.05);
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.4);
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        position: relative;
        overflow: hidden;
    }
    
    .kpi-card::before {
        content: "";
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 4px;
    }
    
    .kpi-card:hover {
        transform: translateY(-4px);
        box-shadow: 0 15px 45px -10px rgba(168, 85, 247, 0.25);
        border: 1px solid rgba(255, 255, 255, 0.15);
    }
    
    .kpi-title {
        font-size: 0.75rem;
        color: #64748b;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        margin-bottom: 10px;
    }
    
    .kpi-value {
        font-size: 2rem;
        font-weight: 800;
        color: #f8fafc;
        margin: 0;
        letter-spacing: -0.02em;
        text-shadow: 0 0 24px rgba(255, 255, 255, 0.1);
    }
    
    /* Sol Sınır Glow Efektleri */
    .border-blue::before { background: linear-gradient(90deg, #38bdf8, #6366f1); }
    .border-green::before { background: linear-gradient(90deg, #34d399, #059669); }
    .border-red::before { background: linear-gradient(90deg, #f87171, #dc2626); }
    .border-amber::before { background: linear-gradient(90deg, #fbbf24, #d97706); }
    .border-purple::before { background: linear-gradient(90deg, #c084fc, #818cf8); }
</style>
""", unsafe_allow_html=True)

st.markdown('<h1 class="dashboard-title">⚡ BIST - ORB Breakout Dashboard</h1>', unsafe_allow_html=True)
st.markdown("<p class='custom-subtitle'>Kaldıraçlı VIOP ve Hisse İlk 15 Dk. Kanal Kırılım Stratejisi & Gelişmiş Portföy Analitiği</p>", unsafe_allow_html=True)

# Örnek BIST Tickers Listesi
BIST_TICKERS = [
    "THYAO.IS", "EREGL.IS", "ASELS.IS", "AKBNK.IS", "GARAN.IS", 
    "TUPRS.IS", "SAHOL.IS", "KCHOL.IS", "SISE.IS", "BIMAS.IS", "ULKER.IS", "BRSAN.IS", "TKFEN.IS", "HALKB.IS", "YKBNK.IS",
    "ISCTR.IS", "ASTOR.IS", "AEFES.IS", "SASA.IS", "HEKTS.IS", "KRDMD.IS", "TOASO.IS", "PETKM.IS", "ENJSA.IS", "EKGYO.IS",
    "TUPRS.IS", "FROTO.IS"
    
]

# SİDEBAR - AYARLAR
st.sidebar.header("⚙️ Genel Ayarlar")
custom_list = st.sidebar.text_area(
    "İzleme Listesi (.IS uzantılı, virgülle ayrılmış)",
    value=", ".join(BIST_TICKERS),
    help="Örnek: THYAO.IS, GARAN.IS, TUPRS.IS",
    height=120
)

range_start = st.sidebar.time_input("ORB Başlangıç Saati", value=datetime.strptime("10:00", "%H:%M").time())
range_end = st.sidebar.time_input("ORB Bitiş Saati", value=datetime.strptime("10:15", "%H:%M").time())
interval_label = st.sidebar.selectbox("Veri Aralığı (Bar)", ["1 dk", "5 dk", "60 dk"], index=0)
show_only_signals = st.sidebar.checkbox("Sadece AL/SAT Sinyali Verenleri Göster", value=False)
allow_short = st.sidebar.checkbox("Açığa Satış Aktif (VIOP/Short)", value=True)
strict_end_bar = st.sidebar.checkbox("10:15 Barı Zorunlu (Matriks Uyumlu)", value=True)
execution_mode = st.sidebar.selectbox(
    "Sinyal Uygulama Modu",
    ["Aynı bar (Anlık Sinyal Eşleşmesi)", "Sonraki bar (Backtest Gerçekçi)"],
    index=1,
)

st.sidebar.markdown("---")
st.sidebar.header("💰 Risk & Komisyon Ayarları")
quantity = st.sidebar.number_input("Pozisyon Büyüklüğü (Lot/Adet)", min_value=1.0, value=100.0, step=1.0)
commission_bps = st.sidebar.number_input("Komisyon Oranı (bps - Onbinde)", min_value=0.0, value=5.0, step=0.5, help="Örn: Onbinde 5 komisyon = 5 bps")
slippage_bps = st.sidebar.number_input("Fiyat Kayması (bps - Onbinde)", min_value=0.0, value=2.0, step=0.5, help="Örn: Onbinde 2 kayma = 2 bps")

st.sidebar.markdown("---")
st.sidebar.header("📈 VIOP Portföy Ayarları")
viop_starting_balance = st.sidebar.number_input("VIOP Başlangıç Bakiyesi (TL)", min_value=1000.0, value=100000.0, step=5000.0)
viop_margin_pct = st.sidebar.slider("VIOP Teminat Oranı (%)", min_value=5, max_value=100, value=20, step=5, help="Örn: Hisse pozisyon değerinin %20'si kadar teminat bağlanır (5x kaldıraç).")
viop_commission_bps = st.sidebar.number_input("VIOP Komisyon Oranı (bps - Onbinde)", min_value=0.0, value=1.0, step=0.1, help="Örn: Onbinde 1 = 1.0 bps")
viop_slippage_bps = st.sidebar.number_input("VIOP Fiyat Kayması (bps - Onbinde)", min_value=0.0, value=5.0, step=0.5, help="Örn: Onbinde 5 = 5.0 bps")

if st.sidebar.button("🗑️ Önbelleği Temizle"):
    st.cache_data.clear()
    st.rerun()

# YARDIMCI FONKSİYONLAR
def parse_tickers(raw_value: str) -> list[str]:
    symbols = [s.strip().upper() for s in raw_value.split(",") if s.strip()]
    normalized = []
    for s in symbols:
        normalized.append(s if s.endswith(".IS") else f"{s}.IS")
    return list(dict.fromkeys(normalized))

def get_interval_and_period(label: str) -> tuple[str, str]:
    mapping = {
        "1 dk": ("1m", "7d"),
        "5 dk": ("5m", "60d"),
        "60 dk": ("60m", "730d"),
    }
    return mapping.get(label, ("1m", "7d"))

def get_orb_lookback(start_time: str, end_time: str, interval: str) -> int:
    start_dt = datetime.strptime(start_time, "%H:%M")
    end_dt = datetime.strptime(end_time, "%H:%M")
    total_minutes = max(int((end_dt - start_dt).total_seconds() // 60), 1)

    step_map = {"1m": 1, "5m": 5, "60m": 60}
    step = step_map.get(interval, 1)
    return max((total_minutes + step - 1) // step, 1)

# Paralel Veri Çekme ve Hesaplama Fonksiyonu
def extract_ticker_data(bulk_df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if bulk_df.empty:
        return pd.DataFrame()
    try:
        if isinstance(bulk_df.columns, pd.MultiIndex):
            if ticker in bulk_df.columns.levels[0]:
                df = bulk_df[ticker].copy()
            elif ticker in bulk_df.columns.levels[1]:
                df = bulk_df.xs(ticker, axis=1, level=1).copy()
            else:
                return pd.DataFrame()
        else:
            df = bulk_df.copy()
            
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)
            
        df = df.dropna(subset=["Close"]).copy()
        return df
    except Exception:
        return pd.DataFrame()


def safe_applymap(styler, func, subset=None):
    if hasattr(styler, "map"):
        return styler.map(func, subset=subset)
    else:
        return styler.applymap(func, subset=subset)


@st.cache_data(ttl=60)
def fetch_and_analyze_parallel(
    tickers: list[str],
    start_time: str,
    end_time: str,
    interval: str,
    period: str,
    allow_short_enabled: bool,
    qty: float,
    commission: float,
    slippage: float,
    strict_end: bool,
    exec_delay: int,
):
    results = []
    orb_lookback = get_orb_lookback(start_time, end_time, interval)
    
    from range import normalize_period_for_interval
    safe_period = normalize_period_for_interval(interval, period)
    
    import yfinance as yf
    try:
        bulk_raw = yf.download(
            tickers=tickers,
            period=safe_period,
            interval=interval,
            group_by='ticker',
            progress=False
        )
    except Exception as e:
        st.error(f"Veri indirme hatası: {e}")
        bulk_raw = pd.DataFrame()

    if bulk_raw.empty:
        return pd.DataFrame()
        
    for ticker in tickers:
        try:
            raw_df = extract_ticker_data(bulk_raw, ticker)
            if raw_df.empty:
                continue
                
            bt = run_backtest(
                ticker=ticker,
                interval=interval,
                period=period,
                range_lookback=orb_lookback,
                allow_short=allow_short_enabled,
                strategy_mode="matriks",
                orb_start=start_time,
                orb_end=end_time,
                strict_end_bar=strict_end,
                execution_delay_bars=exec_delay,
                raw_df=raw_df,
            )
            if bt.empty:
                continue

            last_day = bt.index.max().date()
            df_today = bt[bt.index.date == last_day]
            if df_today.empty:
                continue

            kesin_high = float(df_today["Range_High"].iloc[-1])
            kesin_low = float(df_today["Range_Low"].iloc[-1])
            current_close = float(df_today["Close"].iloc[-1])
            current_time = df_today.index[-1].strftime('%H:%M')
            islem_saati = df_today.index[-1].time() >= datetime.strptime(end_time, "%H:%M").time()
            
            status = "⏳ Kanal İçi / Beklemede"
            
            if islem_saati:
                if current_close > kesin_high:
                    status = "🚀 AL (Kanalı Yukarı Kırdı)"
                elif current_close < kesin_low:
                    if allow_short_enabled:
                        status = "📉 AÇIĞA SAT (Kanalı Aşağı Kırdı)"
                    else:
                        status = "📤 POZ KAPAT / SAT"
            else:
                status = f"⏱️ {end_time} Öncesi - Kanal Oluşuyor"
                
            dist_to_high = ((current_close - kesin_high) / kesin_high) * 100
            dist_to_low = ((current_close - kesin_low) / kesin_low) * 100
            bt_info = backtest_summary(bt)
            trades = generate_trade_log(
                bt,
                quantity=qty,
                commission_bps=commission,
                slippage_bps=slippage,
            )
            t_stats = trade_statistics(trades)
            
            results.append({
                "Hisse": ticker.replace(".IS", ""),
                "Son Fiyat": round(current_close, 2),
                f"Range High ({end_time})": round(kesin_high, 2),
                f"Range Low ({end_time})": round(kesin_low, 2),
                "Kanal Üstüne Uzaklık (%)": round(dist_to_high, 2),
                "Kanal Altına Uzaklık (%)": round(dist_to_low, 2),
                "Durum": status,
                "5G ORB Getiri (%)": round(bt_info["strategy_pct"], 2),
                "5G Al-Tut (%)": round(bt_info["market_pct"], 2),
                "İşlem Sayısı": int(bt_info["total_trades"]),
                "Kazanma Oranı (%)": round(bt_info["win_rate_pct"], 2),
                "Net PnL (TL)": round(t_stats["net_realized_pnl_tl"], 2),
                "Max DD (%)": round(bt_info["max_drawdown_pct"], 2),
                "Veri Gunu": str(last_day),
                "Son Güncelleme": current_time,
            })
        except Exception:
            continue
            
    return pd.DataFrame(results)


@st.cache_data(ttl=60)
def generate_viop_scanner_data(
    tickers: list[str],
    start_time: str,
    end_time: str,
    interval: str,
    period: str,
    allow_short_enabled: bool,
    starting_balance: float,
    margin_pct: float,
    commission_bps: float,
    slippage_bps: float,
    strict_end: bool,
    exec_delay: int,
):
    results = []
    orb_lookback = get_orb_lookback(start_time, end_time, interval)
    
    from range import normalize_period_for_interval
    safe_period = normalize_period_for_interval(interval, period)
    
    import yfinance as yf
    try:
        bulk_raw = yf.download(
            tickers=tickers,
            period=safe_period,
            interval=interval,
            group_by='ticker',
            progress=False
        )
    except Exception:
        bulk_raw = pd.DataFrame()

    if bulk_raw.empty:
        return pd.DataFrame()
        
    for ticker in tickers:
        try:
            raw_df = extract_ticker_data(bulk_raw, ticker)
            if raw_df.empty:
                continue
                
            bt = run_backtest(
                ticker=ticker,
                interval=interval,
                period=period,
                range_lookback=orb_lookback,
                allow_short=allow_short_enabled,
                strategy_mode="matriks",
                orb_start=start_time,
                orb_end=end_time,
                strict_end_bar=strict_end,
                execution_delay_bars=exec_delay,
                raw_df=raw_df,
            )
            if bt.empty:
                continue
                
            _, _, viop_summary = simulate_viop_portfolio(
                df=bt,
                starting_balance=starting_balance,
                margin_pct=margin_pct,
                commission_bps=commission_bps,
                slippage_bps=slippage_bps
            )
            
            if not viop_summary:
                continue
                
            results.append({
                "Hisse": ticker.replace(".IS", ""),
                "Başlangıç Bakiyesi": round(viop_summary["starting_balance"], 2),
                "Son Bakiye": round(viop_summary["final_balance"], 2),
                "Net P&L (TL)": round(viop_summary["total_pnl_tl"], 2),
                "Net P&L (%)": round(viop_summary["total_pnl_pct"], 2),
                "İşlem Sayısı": int(viop_summary["total_trades"]),
                "Kazanma Oranı (%)": round(viop_summary["win_rate_pct"], 2),
                "Sharpe Oranı": round(viop_summary["sharpe_ratio"], 2),
                "Toplam Maliyet (TL)": round(viop_summary["total_costs_tl"], 2),
                "Max Drawdown (%)": round(viop_summary.get("max_drawdown_pct", 0.0), 2)
            })
        except Exception:
            continue
            
    return pd.DataFrame(results)

# İnteraktif Plotly Çizim Fonksiyonu
def create_interactive_plot(df: pd.DataFrame, ticker: str, start_time: str, end_time: str, trades: pd.DataFrame = None):
    fig = make_subplots(
        rows=2, cols=1, 
        shared_xaxes=True, 
        vertical_spacing=0.1,
        subplot_titles=(f"📈 {ticker} Fiyat & ORB Kanal Seviyeleri", "📊 Kümülatif Getiri Karşılaştırması (%)"),
        row_heights=[0.6, 0.4]
    )

    # 1. Kapanış Fiyatı Çizgisi
    fig.add_trace(
        go.Scatter(
            x=df.index, 
            y=df["Close"], 
            name="Kapanış Fiyatı",
            line=dict(color="#3b82f6", width=2),
            hovertemplate="Tarih: %{x}<br>Fiyat: %{y:.2f} TL<extra></extra>"
        ),
        row=1, col=1
    )

    # 2. Kanal Üst Sınırı (Range High)
    fig.add_trace(
        go.Scatter(
            x=df.index, 
            y=df["Range_High"], 
            name="Kanal Üst Sınırı (High)",
            line=dict(color="#10b981", width=1.5, dash="dash"),
            hovertemplate="Kanal Üstü: %{y:.2f} TL<extra></extra>"
        ),
        row=1, col=1
    )
    
    # 3. Kanal Alt Sınırı (Range Low)
    fig.add_trace(
        go.Scatter(
            x=df.index, 
            y=df["Range_Low"], 
            name="Kanal Alt Sınırı (Low)",
            line=dict(color="#ef4444", width=1.5, dash="dash"),
            hovertemplate="Kanal Altı: %{y:.2f} TL<extra></extra>"
        ),
        row=1, col=1
    )

    # Sinyal Noktaları (Markers)
    if trades is not None and not trades.empty:
        # Long Girişler
        longs = trades[trades["Yon"] == "LONG"]
        if not longs.empty:
            fig.add_trace(
                go.Scatter(
                    x=longs["Giris Zamani"],
                    y=longs["Giris Fiyat"],
                    mode="markers",
                    marker=dict(symbol="triangle-up", size=14, color="#10b981", line=dict(color="#064e3b", width=1.5)),
                    name="AL Giriş",
                    hovertemplate="AL Giriş: %{y:.2f} TL<br>Zaman: %{x}<extra></extra>"
                ),
                row=1, col=1
            )
            
            # Long Çıkışlar (Kapanan Pozlar)
            long_exits = longs.dropna(subset=["Cikis Zamani"])
            if not long_exits.empty:
                fig.add_trace(
                    go.Scatter(
                        x=long_exits["Cikis Zamani"],
                        y=long_exits["Cikis Fiyat"],
                        mode="markers",
                        marker=dict(symbol="x", size=11, color="#10b981", line=dict(color="#064e3b", width=1.5)),
                        name="AL Pozisyon Kapat",
                        hovertemplate="AL Çıkış: %{y:.2f} TL<br>Zaman: %{x}<br>Net PnL: %{text}%<extra></extra>",
                        text=long_exits["Net PnL (%)"]
                    ),
                    row=1, col=1
                )
                
        # Short Girişler (Açığa Satış)
        shorts = trades[trades["Yon"] == "SHORT"]
        if not shorts.empty:
            fig.add_trace(
                go.Scatter(
                    x=shorts["Giris Zamani"],
                    y=shorts["Giris Fiyat"],
                    mode="markers",
                    marker=dict(symbol="triangle-down", size=14, color="#ef4444", line=dict(color="#7f1d1d", width=1.5)),
                    name="AÇIĞA SAT Giriş",
                    hovertemplate="Açığa Satış: %{y:.2f} TL<br>Zaman: %{x}<extra></extra>"
                ),
                row=1, col=1
            )
            
            short_exits = shorts.dropna(subset=["Cikis Zamani"])
            if not short_exits.empty:
                fig.add_trace(
                    go.Scatter(
                        x=short_exits["Cikis Zamani"],
                        y=short_exits["Cikis Fiyat"],
                        mode="markers",
                        marker=dict(symbol="x", size=11, color="#ef4444", line=dict(color="#7f1d1d", width=1.5)),
                        name="AÇIĞA SAT Kapat",
                        hovertemplate="Açığa Kapat: %{y:.2f} TL<br>Zaman: %{x}<br>Net PnL: %{text}%<extra></extra>",
                        text=short_exits["Net PnL (%)"]
                    ),
                    row=1, col=1
                )

    # 2. Grafik: Kümülatif Getiri
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["Cum_Market_Return"] * 100,
            name="Al-Tut (Market)",
            line=dict(color="#64748b", width=1.5),
            hovertemplate="Market Getirisi: %{y:.2f}%<extra></extra>"
        ),
        row=2, col=1
    )
    
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["Cum_Strategy_Return"] * 100,
            name="ORB Stratejisi",
            line=dict(color="#8b5cf6", width=2.5),
            hovertemplate="ORB Strateji Getirisi: %{y:.2f}%<extra></extra>"
        ),
        row=2, col=1
    )

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=680,
        hovermode="x unified",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        margin=dict(l=10, r=10, t=60, b=10)
    )

    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor="#334155", row=1, col=1)
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor="#334155", row=1, col=1)
    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor="#334155", row=2, col=1)
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor="#334155", row=2, col=1)
    
    fig.update_yaxes(title_text="Fiyat (TL)", row=1, col=1)
    fig.update_yaxes(title_text="Kümülatif Getiri (%)", row=2, col=1)
    
    return fig

# ANA AKIŞ BAŞLANGICI
tickers = parse_tickers(custom_list)
if not tickers:
    st.error("Lütfen en az bir geçerli hisse kodu giriniz.")
    st.stop()

selected_interval, selected_period = get_interval_and_period(interval_label)

# Veriyi arka planda paralel çek ve analiz et
data_df = fetch_and_analyze_parallel(
    tickers=tickers,
    start_time=range_start.strftime("%H:%M"),
    end_time=range_end.strftime("%H:%M"),
    interval=selected_interval,
    period=selected_period,
    allow_short_enabled=allow_short,
    qty=quantity,
    commission=commission_bps,
    slippage=slippage_bps,
    strict_end=strict_end_bar,
    exec_delay=0 if execution_mode.startswith("Aynı") else 1,
)

# SEKMELERİ TANIMLA
tab_scanner, tab_analysis, tab_viop, tab_guide = st.tabs([
    "📋 Sinyal Tarayıcı (Scanner)", 
    "📈 Tek Hisse Analiz & Grafik", 
    "📈 VIOP Portföy Backtest",
    "📖 Strateji Açıklaması & Rehber"
])

# TAB 1: SİNYAL TARAYICI
with tab_scanner:
    if not data_df.empty:
        # Filtreleme
        if show_only_signals:
            data_df = data_df[data_df["Durum"].str.contains("AL|SAT|AÇIĞA", regex=True)]
            
        if data_df.empty:
            st.info("Filtreleme kriterlerine uyan aktif bir sinyal bulunmamaktadır.")
        else:
            # Sinyal Sayaçları
            al_sayisi = len(data_df[data_df['Durum'].str.contains("AL")])
            sat_sayisi = len(data_df[data_df['Durum'].str.contains("SAT|AÇIĞA", regex=True)])
            bekle_sayisi = len(data_df[data_df['Durum'].str.contains("Beklemede|Öncesi", regex=True)])
            
            # Premium Metrik Kartları
            st.markdown(f"""
            <div class="kpi-container">
                <div class="kpi-card border-blue">
                    <div class="kpi-title">Taranan Hisse Sayısı</div>
                    <div class="kpi-value">{len(data_df)}</div>
                </div>
                <div class="kpi-card border-green">
                    <div class="kpi-title">🟢 Aktif AL Sinyali</div>
                    <div class="kpi-value">{al_sayisi}</div>
                </div>
                <div class="kpi-card border-red">
                    <div class="kpi-title">🔴 Aktif SAT/AÇIĞA SAT</div>
                    <div class="kpi-value">{sat_sayisi}</div>
                </div>
                <div class="kpi-card border-amber">
                    <div class="kpi-title">⏳ Bekleme / Oluşumda</div>
                    <div class="kpi-value">{bekle_sayisi}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            st.subheader("Hisse Sinyal Matrisi")
            
            # DataFrame Görsel İyileştirmesi ve Pandas Styling
            display_df = data_df.sort_values(
                by=["Durum", "Kanal Üstüne Uzaklık (%)"], 
                ascending=[True, False]
            )
            
            def style_status_column(val):
                if "AL" in str(val):
                    return 'background-color: rgba(16, 185, 129, 0.18); color: #00ffb7; font-weight: bold; border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 6px; text-shadow: 0 0 10px rgba(0,255,183,0.35);'
                elif "SAT" in str(val) or "AÇIĞA" in str(val):
                    return 'background-color: rgba(239, 68, 68, 0.18); color: #ff5252; font-weight: bold; border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 6px; text-shadow: 0 0 10px rgba(255,82,82,0.35);'
                elif "Beklemede" in str(val):
                    return 'background-color: rgba(245, 158, 11, 0.12); color: #ffd166; font-weight: 500; border: 1px solid rgba(245, 158, 11, 0.2); border-radius: 6px;'
                return 'color: #94a3b8;'

            styled_table = safe_applymap(display_df.style, style_status_column, subset=["Durum"])
            st.dataframe(styled_table, use_container_width=True, height=480)
            
            # Yenileme butonu
            col_ref_1, col_ref_2 = st.columns([10, 2])
            with col_ref_2:
                if st.button("🔄 Paneli Yenile", use_container_width=True):
                    st.rerun()
    else:
        st.warning("Henüz taranan verilere erişilemiyor. Lütfen piyasanın açık olduğundan veya Yahoo Finance'in veri döndürdüğünden emin olun.")

# TAB 2: DETAYLI HİSSE ANALİZİ
with tab_analysis:
    if not data_df.empty:
        st.subheader("Tek Hisse Derinlemesine Backtest & Detayları")
        selected_symbol = st.selectbox("Analiz edilecek hisseyi seçin", data_df["Hisse"].tolist())
        selected_ticker = f"{selected_symbol}.IS"
        
        # Seçili hissenin backtestini tekrar hızlıca al
        selected_bt = run_backtest(
            ticker=selected_ticker,
            interval=selected_interval,
            period=selected_period,
            range_lookback=get_orb_lookback(range_start.strftime("%H:%M"), range_end.strftime("%H:%M"), selected_interval),
            allow_short=allow_short,
            strategy_mode="matriks",
            orb_start=range_start.strftime("%H:%M"),
            orb_end=range_end.strftime("%H:%M"),
            strict_end_bar=strict_end_bar,
            execution_delay_bars=0 if execution_mode.startswith("Aynı") else 1,
        )
        
        if not selected_bt.empty:
            # Gerekli günlük ve istatistikleri çek
            trade_df = generate_trade_log(
                selected_bt,
                quantity=quantity,
                commission_bps=commission_bps,
                slippage_bps=slippage_bps,
            )
            stats = trade_statistics(trade_df)
            daily_df, weekly_df, max_dd = performance_breakdown(selected_bt)
            
            # Gelişmiş Risk Metriklerini Kartlarla Yazdır
            st.markdown(f"""
            <div class="kpi-container">
                <div class="kpi-card border-blue">
                    <div class="kpi-title">Toplam İşlem sayısı</div>
                    <div class="kpi-value">{int(stats["total_trades"])} <span style="font-size: 0.85rem; color:#94a3b8;">({int(stats["closed_trades"])} Kapanan)</span></div>
                </div>
                <div class="kpi-card border-green">
                    <div class="kpi-title">🏆 Kazanma Oranı</div>
                    <div class="kpi-value">%{stats["win_rate_pct"]:.2f}</div>
                </div>
                <div class="kpi-card border-purple">
                    <div class="kpi-title">📈 Toplam Net Kar (TL)</div>
                    <div class="kpi-value">{stats["net_realized_pnl_tl"]:,.2f} TL <span style="font-size: 0.85rem; color:#94a3b8;">(%{stats["net_realized_pnl_pct"]:.2f})</span></div>
                </div>
                <div class="kpi-card border-amber">
                    <div class="kpi-title">📊 Profit Factor</div>
                    <div class="kpi-value">{stats.get("profit_factor", 0.0)}</div>
                </div>
                <div class="kpi-card border-red">
                    <div class="kpi-title">📉 Max Drawdown</div>
                    <div class="kpi-value">%{max_dd:.2f}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            # İnteraktif Plotly Grafiği Ekle
            plotly_fig = create_interactive_plot(
                selected_bt, 
                selected_symbol, 
                range_start.strftime("%H:%M"), 
                range_end.strftime("%H:%M"), 
                trade_df
            )
            st.plotly_chart(plotly_fig, use_container_width=True)
            
            # İşlem Listesi ve İstatistik Detay Tabloları
            col_l, col_r = st.columns([7, 3])
            
            with col_l:
                st.subheader("📋 İşlem Günlüğü (Trade Log)")
                if not trade_df.empty:
                    # İşlem bazında PnL renklendirmesi
                    def style_pnl_rows(val):
                        try:
                            val_float = float(val)
                            if val_float > 0:
                                return 'color: #10b981; font-weight: 500;'
                            elif val_float < 0:
                                return 'color: #ef4444; font-weight: 500;'
                        except ValueError:
                            pass
                        return ''

                    styled_trades = safe_applymap(trade_df.style, style_pnl_rows, subset=["Brut PnL (%)", "Net PnL (%)", "Brut PnL (TL)", "Net PnL (TL)"])
                    st.dataframe(styled_trades, use_container_width=True, height=350)
                    
                    # CSV İndirme Butonu
                    csv_data = trade_df.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📥 İşlem Günlüğünü Excel/CSV Olarak İndir",
                        data=csv_data,
                        file_name=f"{selected_symbol}_orb_islemleri.csv",
                        mime="text/csv",
                        use_container_width=False
                    )
                else:
                    st.info("Bu tarih aralığında henüz oluşmuş işlem bulunmamaktadır.")
            
            with col_r:
                st.subheader("⚡ Detaylı İstatistikler")
                stat_data = {
                    "Risk Metrikleri": [
                        "Ort. Net İşlem Getirisi (%)",
                        "En İyi İşlem Getirisi (%)",
                        "En Kötü İşlem Getirisi (%)",
                        "Toplam Katlanılan Maliyet (TL)",
                        "Aktif Açık Pozisyonlar"
                    ],
                    "Değer": [
                        f"%{stats['avg_net_pnl_pct']:.2f}",
                        f"%{stats.get('max_win_pct', 0.0):.2f}",
                        f"%{stats.get('max_loss_pct', 0.0):.2f}",
                        f"{stats.get('total_costs_tl', 0.0):,.2f} TL",
                        str(stats["open_positions"])
                    ]
                }
                st.table(pd.DataFrame(stat_data))
                
            # Performans Periyodik Kırılımları
            st.markdown("---")
            col_day, col_week = st.columns(2)
            with col_day:
                st.subheader("📅 Günlük Performans Özeti (Son 15 Gün)")
                st.dataframe(daily_df.tail(15).rename(columns={"Gunluk Getiri (%)": "Günlük Getiri (%)"}), use_container_width=True, height=250)
            with col_week:
                st.subheader("📆 Haftalık Performans Özeti (Son 10 Hafta)")
                st.dataframe(weekly_df.tail(10).rename(columns={"Haftalik Getiri (%)": "Haftalık Getiri (%)"}), use_container_width=True, height=250)
        else:
            st.warning("Seçilen hisse için backtest verisi çekilemedi.")
    else:
        st.warning("Hisse verileri yüklenemedi.")
def create_viop_balance_plot(portfolio_df: pd.DataFrame, ticker: str, start_balance: float):
    fig = go.Figure()
    
    # Portföy Bakiye Eğrisi
    fig.add_trace(
        go.Scatter(
            x=portfolio_df.index,
            y=portfolio_df["Bakiye"],
            name="Portföy Bakiyesi",
            line=dict(color="#10b981", width=2.5),
            fill='tozeroy',
            fillcolor='rgba(16, 185, 129, 0.05)',
            hovertemplate="Tarih: %{x}<br>Bakiye: %{y:,.2f} TL<extra></extra>"
        )
    )
    
    # Başlangıç bakiyesi referans çizgisi
    fig.add_shape(
        type="line",
        x0=portfolio_df.index[0],
        y0=start_balance,
        x1=portfolio_df.index[-1],
        y1=start_balance,
        line=dict(color="#64748b", width=1.5, dash="dash"),
    )
    
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=450,
        title=dict(text=f"📈 {ticker} Kaldıraçlı VIOP Portföy Bakiye Eğrisi", font=dict(size=16)),
        hovermode="x unified",
        margin=dict(l=10, r=10, t=50, b=10)
    )
    
    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor="#334155")
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor="#334155")
    fig.update_yaxes(title_text="Bakiye (TL)")
    
    return fig

# TAB 3: VIOP PORTFÖY BACKTEST
with tab_viop:
    if not data_df.empty:
        st.subheader("📊 Tüm Hisselerin VIOP Performans Matrisi")
        
        # Tüm hisselerin kaldıraçlı portföy özetlerini hesapla
        viop_scanner_df = generate_viop_scanner_data(
            tickers=tickers,
            start_time=range_start.strftime("%H:%M"),
            end_time=range_end.strftime("%H:%M"),
            interval=selected_interval,
            period=selected_period,
            allow_short_enabled=allow_short,
            starting_balance=viop_starting_balance,
            margin_pct=viop_margin_pct / 100.0,
            commission_bps=viop_commission_bps,
            slippage_bps=viop_slippage_bps,
            strict_end=strict_end_bar,
            exec_delay=0 if execution_mode.startswith("Aynı") else 1,
        )
        
        if not viop_scanner_df.empty:
            # PnL kolonlarını renklendir
            def style_viop_scanner_pnl(val):
                try:
                    val_float = float(val)
                    if val_float > 0:
                        return 'background-color: rgba(16, 185, 129, 0.18); color: #00ffb7; font-weight: bold; border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 6px; text-shadow: 0 0 10px rgba(0,255,183,0.35);'
                    elif val_float < 0:
                        return 'background-color: rgba(239, 68, 68, 0.18); color: #ff5252; font-weight: bold; border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 6px; text-shadow: 0 0 10px rgba(255,82,82,0.35);'
                except ValueError:
                    pass
                return ''
                
            styled_viop_scanner = safe_applymap(
                viop_scanner_df.style, 
                style_viop_scanner_pnl, 
                subset=["Net P&L (TL)", "Net P&L (%)"]
            )
            st.dataframe(styled_viop_scanner, use_container_width=True, height=320)
        else:
            st.info("VIOP tarayıcı verileri yüklenemedi.")
            
        st.markdown("---")
        st.subheader("🔍 Tek Hisse VIOP Detay Analizi")
        selected_viop_symbol = st.selectbox("VIOP Analizi için Hisse Seçin", data_df["Hisse"].tolist(), key="viop_symbol_select")
        selected_viop_ticker = f"{selected_viop_symbol}.IS"
        
        # Seçili hissenin backtest verilerini çek
        viop_bt = run_backtest(
            ticker=selected_viop_ticker,
            interval=selected_interval,
            period=selected_period,
            range_lookback=get_orb_lookback(range_start.strftime("%H:%M"), range_end.strftime("%H:%M"), selected_interval),
            allow_short=allow_short,
            strategy_mode="matriks",
            orb_start=range_start.strftime("%H:%M"),
            orb_end=range_end.strftime("%H:%M"),
            strict_end_bar=strict_end_bar,
            execution_delay_bars=0 if execution_mode.startswith("Aynı") else 1,
        )
        
        if not viop_bt.empty:
            # VIOP Portföy simülasyonunu çalıştır
            viop_portfolio, viop_trades, viop_summary = simulate_viop_portfolio(
                df=viop_bt,
                starting_balance=viop_starting_balance,
                margin_pct=viop_margin_pct / 100.0,
                commission_bps=viop_commission_bps,
                slippage_bps=viop_slippage_bps
            )
            
            if not viop_portfolio.empty:
                # Portföy Özet Metrikleri
                pnl_color = "#10b981" if viop_summary["total_pnl_tl"] >= 0 else "#ef4444"
                
                st.markdown(f"""
                <div class="kpi-container">
                    <div class="kpi-card border-blue">
                        <div class="kpi-title">Başlangıç Bakiyesi</div>
                        <div class="kpi-value">{viop_summary["starting_balance"]:,.2f} TL</div>
                    </div>
                    <div class="kpi-card border-purple">
                        <div class="kpi-title">Son Bakiye</div>
                        <div class="kpi-value">{viop_summary["final_balance"]:,.2f} TL</div>
                    </div>
                    <div class="kpi-card" style="border-left: 5px solid {pnl_color};">
                        <div class="kpi-title">Toplam Net P&L</div>
                        <div class="kpi-value" style="color: {pnl_color};">{viop_summary["total_pnl_tl"]:,.2f} TL <span style="font-size: 0.85rem; color:#94a3b8;">(%{viop_summary["total_pnl_pct"]:.2f})</span></div>
                    </div>
                    <div class="kpi-card border-green">
                        <div class="kpi-title">🏆 Kazanma Oranı</div>
                        <div class="kpi-value">%{viop_summary["win_rate_pct"]:.2f}</div>
                    </div>
                    <div class="kpi-card border-amber">
                        <div class="kpi-title">📊 Sharpe Oranı</div>
                        <div class="kpi-value">{viop_summary["sharpe_ratio"]:.2f}</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                # Bakiye Eğrisi Grafiği
                balance_fig = create_viop_balance_plot(viop_portfolio, selected_viop_symbol, viop_starting_balance)
                st.plotly_chart(balance_fig, use_container_width=True)
                
                # Detaylı Tablolar
                col_viop_l, col_viop_r = st.columns([7, 3])
                
                with col_viop_l:
                    st.subheader("📋 VIOP İşlem Günlüğü")
                    if not viop_trades.empty:
                        def style_viop_pnl(val):
                            try:
                                val_float = float(val)
                                if val_float > 0:
                                    return 'color: #10b981; font-weight: 500;'
                                elif val_float < 0:
                                    return 'color: #ef4444; font-weight: 500;'
                            except ValueError:
                                pass
                            return ''
                            
                        styled_viop_trades = safe_applymap(viop_trades.style, style_viop_pnl, subset=["Brut PnL (TL)", "Net PnL (TL)", "Net PnL (%)"])
                        st.dataframe(styled_viop_trades, use_container_width=True, height=350)
                        
                        # CSV İndirme Butonu
                        viop_csv = viop_trades.to_csv(index=False).encode('utf-8')
                        st.download_button(
                            label="📥 VIOP İşlemlerini Excel/CSV Olarak İndir",
                            data=viop_csv,
                            file_name=f"{selected_viop_symbol}_viop_islemleri.csv",
                            mime="text/csv",
                            key="download_viop_csv"
                        )
                    else:
                        st.info("Bu hisse için oluşmuş VIOP işlemi bulunmamaktadır.")
                        
                with col_viop_r:
                    st.subheader("⚡ Portföy Risk Analizi")
                    viop_stats = {
                        "VIOP Metriği": [
                            "Toplam İşlem Sayısı",
                            "Toplam Ödenen Komisyon + Kayma (TL)",
                            "Aktif Açık Pozisyonlar",
                            "Kontrat Başı Lot Sayısı",
                            "Simüle Edilen Kaldıraç Oranı"
                        ],
                        "Değer": [
                            str(viop_summary["total_trades"]),
                            f"{viop_summary['total_costs_tl']:,.2f} TL",
                            "Evet (1)" if viop_summary["open_positions"] > 0 else "Hayır (0)",
                            "100 Lot",
                            f"{round(100.0 / viop_margin_pct, 1)}x Kaldıraç"
                        ]
                    }
                    st.table(pd.DataFrame(viop_stats))
            else:
                st.warning("Portföy simülasyonu çalıştırılamadı.")
        else:
            st.warning("Seçilen hissenin fiyat verileri çekilemedi.")
    else:
        st.warning("Hisse verileri yüklenemedi.")

# TAB 4: STRATEJİ REHBERİ
with tab_guide:
    st.subheader("📖 Opening Range Breakout (ORB) Nedir ve Nasıl Çalışır?")
    st.markdown("""
    ORB stratejisi, piyasa açılışından sonra belirli bir süre boyunca (genellikle ilk 15 veya 30 dakika) oluşan en yüksek ve en düşük fiyat seviyelerinin (kanal sınırları) kırılmasına dayanan klasik bir trend takip stratejisidir.
    
    ### Strateji İşleyiş Kuralları:
    1. **Kanalın Belirlenmesi**: Pazar açılış saatinden (örneğin 10:00) kanal bitiş saatine (örneğin 10:15) kadar hisse senedinin ulaştığı **en yüksek fiyat (Range High)** ve **en düşük fiyat (Range Low)** kaydedilir.
    2. **Breakout (Kırılım) İzleme**: Kanal belirlendikten sonra fiyat kanalın dışına çıkarsa işlem tetiklenir.
       * **Kapanış > Range High**: **AL** sinyali tetiklenir (Trend yukarı yönlü).
       * **Kapanış < Range Low**: 
         * Eğer **Açığa Satış (Short)** aktifse: **AÇIĞA SAT** sinyali tetiklenir.
         * Eğer short aktif değilse: Mevcut AL pozisyonu kapatılarak **NAKİT** durumuna geçilir.
    
    ### Parametrelerin Anlamı:
    * **10:15 Barı Zorunlu (Matriks Birebir)**: Eğer bu seçenek aktifse, Matriks formulasyonuyla uyumlu çalışarak tam kanal bitiş saatindeki (10:15) barın oluşması beklenir. Bar oluşmadan kanal hesaplanmaz.
    * **Sinyal Uygulama Modu**:
      * *Aynı Bar*: Sinyalin oluştuğu barın kapanışında hemen işlem gerçekleştirilir.
      * *Sonraki Bar*: Sinyal oluştuktan sonraki ilk barın açılışında işlem gerçekleştirilir. Backtestlerin daha gerçekçi olması için genelde 1 bar gecikme (Sonraki Bar) tercih edilir.
      
    ### Risk Yönetimi İpuçları:
    * **Bps (Basis Points - Onbinde Bir)**: Komisyon ve Slippage ayarları için kullanılır. Örneğin, aracı kurum komisyonunuz onbinde 2 ise bunu 2.0 bps olarak girmeniz gerekir. 
    * Fiyat Kayması (**Slippage**), yüksek volatilitede emrinizin istediğiniz fiyattan eşleşmeme payını temsil eder. Backtestlerinizi daha gerçekçi kılmak için mutlaka onbinde 1 veya 2 (1-2 bps) kayma payı eklemeniz tavsiye edilir.
    """)