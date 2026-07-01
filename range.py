import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt
from datetime import datetime
from zoneinfo import ZoneInfo


IST_TZ = ZoneInfo("Europe/Istanbul")


def normalize_period_for_interval(interval: str, period: str) -> str:
    interval = interval.lower().strip()
    period = period.lower().strip()

    if interval == "1m":
        allowed = {"1d", "5d", "7d"}
        return period if period in allowed else "5d"

    return period


def fetch_intraday_data(ticker: str, interval: str = "1m", period: str = "5d") -> pd.DataFrame:
    safe_period = normalize_period_for_interval(interval, period)
    df = yf.download(tickers=ticker, period=safe_period, interval=interval, progress=False)

    if df.empty:
        return df

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)

    return df.dropna().copy()


def ensure_istanbul_time(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    # Yinelenen zaman etiketlerini temizle (resample çökmelerini önlemek için)
    work = df.sort_index().copy()
    work = work[~work.index.duplicated(keep="last")]
    
    idx = work.index
    if getattr(idx, "tz", None) is None:
        # Yerel CSV verileri zaten İstanbul saatinde olduğu için doğrudan lokalize edilir (saat kaydırılmaz)
        # Yaz saati geçişlerindeki tutarsızlıkları önlemek için ambiguous ve nonexistent 'NaT' yapılır
        localized_idx = idx.tz_localize(IST_TZ, ambiguous='NaT', nonexistent='NaT')
        work.index = localized_idx
        work = work[work.index.notna()]
    else:
        work.index = idx.tz_convert(IST_TZ)
    return work


def apply_orb_logic(df: pd.DataFrame, range_lookback: int = 15, allow_short: bool = False) -> pd.DataFrame:
    work = df.copy()

    work["Range_High"] = work["High"].shift(1).rolling(window=range_lookback).max()
    work["Range_Low"] = work["Low"].shift(1).rolling(window=range_lookback).min()
    work = work.dropna().copy()

    work["Signal"] = pd.Series(index=work.index, dtype="float64")
    work.loc[work["Close"] > work["Range_High"], "Signal"] = 1
    if allow_short:
        work.loc[work["Close"] < work["Range_Low"], "Signal"] = -1
    else:
        work.loc[work["Close"] < work["Range_Low"], "Signal"] = 0

    # Breakout olmayan barlarda son sinyali koru, bir sonraki barda uygula.
    work["Signal"] = work["Signal"].ffill().fillna(0).astype(int)
    work["Position"] = work["Signal"].shift(1).ffill().fillna(0).astype(int)
    work["Market_Return"] = work["Close"].pct_change()
    work["Strategy_Return"] = work["Market_Return"] * work["Position"]
    work["Cum_Market_Return"] = (1 + work["Market_Return"].fillna(0)).cumprod() - 1
    work["Cum_Strategy_Return"] = (1 + work["Strategy_Return"].fillna(0)).cumprod() - 1
    return work


def apply_matriks_orb_logic(
    df: pd.DataFrame,
    orb_start: str = "10:00",
    orb_end: str = "10:15",
    allow_short: bool = False,
    strict_end_bar: bool = True,
    execution_delay_bars: int = 1,
) -> pd.DataFrame:
    if df.empty:
        return df

    work = ensure_istanbul_time(df)
    start_t = datetime.strptime(orb_start, "%H:%M").time()
    end_t = datetime.strptime(orb_end, "%H:%M").time()

    work["Range_High"] = pd.Series(index=work.index, dtype="float64")
    work["Range_Low"] = pd.Series(index=work.index, dtype="float64")
    work["KesinHigh"] = pd.Series(index=work.index, dtype="float64")
    work["KesinLow"] = pd.Series(index=work.index, dtype="float64")
    work["SignalRaw"] = pd.Series(index=work.index, dtype="float64")

    unique_days = pd.Index(work.index.date).unique()

    for day in unique_days:
        day_mask = pd.Index(work.index.date) == day
        day_df = work.loc[day_mask]

        day_range = day_df.between_time(orb_start, orb_end)
        if day_range.empty:
            continue

        if strict_end_bar:
            # En azından orb_end saatine kadar günün verisi olduğundan emin ol (10:15 barı zorunluluğu)
            # Tam dakika bazında sayısal kontrol kullanarak barın kendisinin eksik olduğu durumları da destekle
            day_times_minutes = day_df.index.hour * 60 + day_df.index.minute
            end_minutes = end_t.hour * 60 + end_t.minute
            if not any(day_times_minutes >= end_minutes):
                continue

        # Matriks formuluyle uyumlu: 10:00'dan 10:15 barina kadar olusan seviyeyi sabitle.
        kesin_high = float(day_range["High"].max())
        kesin_low = float(day_range["Low"].min())

        # Dakika bazında sayısal karşılaştırma (timezone ve pandas obje karşılaştırma hatalarını önler)
        work_minutes = work.index.hour * 60 + work.index.minute
        end_minutes = end_t.hour * 60 + end_t.minute
        active_mask = day_mask & (work_minutes >= end_minutes)
        
        work.loc[active_mask, "Range_High"] = kesin_high
        work.loc[active_mask, "Range_Low"] = kesin_low
        work.loc[active_mask, "KesinHigh"] = kesin_high
        work.loc[active_mask, "KesinLow"] = kesin_low

        long_cond = active_mask & (work["Close"] > kesin_high)
        low_break_cond = active_mask & (work["Close"] < kesin_low)

        work.loc[long_cond, "SignalRaw"] = 1
        if allow_short:
            work.loc[low_break_cond, "SignalRaw"] = -1
        else:
            work.loc[low_break_cond, "SignalRaw"] = 0

    work = work.dropna(subset=["Range_High", "Range_Low"]).copy()
    if work.empty:
        return work

    work["Signal"] = work["SignalRaw"].ffill().fillna(0).astype(int)

    shift_n = max(int(execution_delay_bars), 0)
    if shift_n > 0:
        work["Position"] = work["Signal"].shift(shift_n).ffill().fillna(0).astype(int)
    else:
        work["Position"] = work["Signal"].astype(int)

    work["Market_Return"] = work["Close"].pct_change()
    work["Strategy_Return"] = work["Market_Return"] * work["Position"]
    work["Cum_Market_Return"] = (1 + work["Market_Return"].fillna(0)).cumprod() - 1
    work["Cum_Strategy_Return"] = (1 + work["Strategy_Return"].fillna(0)).cumprod() - 1
    return work


def _position_transition_label(prev_pos: int, new_pos: int) -> str:
    transitions = {
        (0, 1): "AL",
        (1, 0): "POZ KAPAT",
        (0, -1): "AÇIĞA SAT",
        (-1, 0): "AÇIĞI KAPAT",
        (1, -1): "AL KAPAT + AÇIĞA SAT",
        (-1, 1): "AÇIĞI KAPAT + AL",
    }
    return transitions.get((prev_pos, new_pos), "POZISYON DEGISIMI")


def _cost_rates(commission_bps: float, slippage_bps: float) -> tuple[float, float]:
    commission_rate = max(float(commission_bps), 0.0) / 10000.0
    slippage_rate = max(float(slippage_bps), 0.0) / 10000.0
    return commission_rate, slippage_rate


def generate_trade_log(
    df: pd.DataFrame,
    quantity: float = 1.0,
    commission_bps: float = 0.0,
    slippage_bps: float = 0.0,
) -> pd.DataFrame:
    if df.empty or "Position" not in df.columns:
        return pd.DataFrame()

    qty = max(float(quantity), 0.0)
    commission_rate, slippage_rate = _cost_rates(commission_bps, slippage_bps)
    cost_rate_side = commission_rate + slippage_rate

    rows = []
    open_trade = None
    prev_pos = 0

    for ts, row in df.iterrows():
        price = float(row["Close"])
        new_pos = int(row["Position"])

        if new_pos == prev_pos:
            continue

        transition = _position_transition_label(prev_pos, new_pos)

        if open_trade is not None and prev_pos != 0:
            entry_price = open_trade["Giris Fiyat"]
            direction = open_trade["Yon"]

            if direction == "LONG":
                gross_pct = ((price - entry_price) / entry_price) * 100
                gross_tl = (price - entry_price) * qty
            else:
                gross_pct = ((entry_price - price) / entry_price) * 100
                gross_tl = (entry_price - price) * qty

            cost_tl = (entry_price + price) * qty * cost_rate_side
            cost_pct = ((cost_tl / (entry_price * qty)) * 100) if entry_price > 0 and qty > 0 else 0.0
            net_pct = gross_pct - cost_pct
            net_tl = gross_tl - cost_tl

            open_trade["Cikis Zamani"] = ts
            open_trade["Cikis Fiyat"] = round(price, 4)
            open_trade["Brut PnL (%)"] = round(gross_pct, 2)
            open_trade["Maliyet (%)"] = round(cost_pct, 2)
            open_trade["Net PnL (%)"] = round(net_pct, 2)
            open_trade["Brut PnL (TL)"] = round(gross_tl, 2)
            open_trade["Maliyet (TL)"] = round(cost_tl, 2)
            open_trade["Net PnL (TL)"] = round(net_tl, 2)
            open_trade["Durum"] = "KAPALI"
            open_trade["Kapanis Nedeni"] = transition
            rows.append(open_trade)
            open_trade = None

        if new_pos != 0:
            open_trade = {
                "Giris Zamani": ts,
                "Cikis Zamani": pd.NaT,
                "Yon": "LONG" if new_pos == 1 else "SHORT",
                "Giris Fiyat": round(price, 4),
                "Cikis Fiyat": None,
                "Adet/Lot": qty,
                "Brut PnL (%)": None,
                "Maliyet (%)": None,
                "Net PnL (%)": None,
                "Brut PnL (TL)": None,
                "Maliyet (TL)": None,
                "Net PnL (TL)": None,
                "Durum": "ACIK",
                "Kapanis Nedeni": "",
            }

        prev_pos = new_pos

    if open_trade is not None:
        last_price = float(df["Close"].iloc[-1])
        entry_price = float(open_trade["Giris Fiyat"])
        if open_trade["Yon"] == "LONG":
            gross_pct = ((last_price - entry_price) / entry_price) * 100
            gross_tl = (last_price - entry_price) * qty
        else:
            gross_pct = ((entry_price - last_price) / entry_price) * 100
            gross_tl = (entry_price - last_price) * qty

        est_cost_tl = (entry_price + last_price) * qty * cost_rate_side
        est_cost_pct = ((est_cost_tl / (entry_price * qty)) * 100) if entry_price > 0 and qty > 0 else 0.0
        net_pct = gross_pct - est_cost_pct
        net_tl = gross_tl - est_cost_tl

        open_trade["Cikis Fiyat"] = round(last_price, 4)
        open_trade["Brut PnL (%)"] = round(gross_pct, 2)
        open_trade["Maliyet (%)"] = round(est_cost_pct, 2)
        open_trade["Net PnL (%)"] = round(net_pct, 2)
        open_trade["Brut PnL (TL)"] = round(gross_tl, 2)
        open_trade["Maliyet (TL)"] = round(est_cost_tl, 2)
        open_trade["Net PnL (TL)"] = round(net_tl, 2)
        open_trade["Durum"] = "ACIK"
        open_trade["Kapanis Nedeni"] = "Acik Pozisyon"
        rows.append(open_trade)

    if not rows:
        return pd.DataFrame()

    trade_df = pd.DataFrame(rows)
    trade_df.insert(0, "Islem No", range(1, len(trade_df) + 1))
    return trade_df


def trade_statistics(trade_df: pd.DataFrame) -> dict:
    if trade_df.empty:
        return {
            "total_trades": 0,
            "closed_trades": 0,
            "win_rate_pct": 0.0,
            "avg_net_pnl_pct": 0.0,
            "net_realized_pnl_pct": 0.0,
            "net_realized_pnl_tl": 0.0,
            "open_positions": 0,
            "profit_factor": 0.0,
            "max_win_pct": 0.0,
            "max_loss_pct": 0.0,
            "total_costs_tl": 0.0,
        }

    closed = trade_df[trade_df["Durum"] == "KAPALI"].copy()
    open_positions = int((trade_df["Durum"] == "ACIK").sum())

    if closed.empty:
        return {
            "total_trades": int(len(trade_df)),
            "closed_trades": 0,
            "win_rate_pct": 0.0,
            "avg_net_pnl_pct": 0.0,
            "net_realized_pnl_pct": 0.0,
            "net_realized_pnl_tl": 0.0,
            "open_positions": open_positions,
            "profit_factor": 0.0,
            "max_win_pct": 0.0,
            "max_loss_pct": 0.0,
            "total_costs_tl": 0.0,
        }

    wins = int((closed["Net PnL (%)"] > 0).sum())
    closed_count = int(len(closed))
    win_rate = (wins / closed_count) * 100 if closed_count else 0.0

    profits = float(closed[closed["Net PnL (%)"] > 0]["Net PnL (%)"].sum())
    losses = abs(float(closed[closed["Net PnL (%)"] < 0]["Net PnL (%)"].sum()))
    
    if losses > 0:
        profit_factor = round(profits / losses, 2)
    else:
        profit_factor = round(profits, 2) if profits > 0 else 1.0

    max_win = float(closed["Net PnL (%)"].max()) if not closed.empty else 0.0
    max_loss = float(closed["Net PnL (%)"].min()) if not closed.empty else 0.0
    total_costs = float(closed["Maliyet (TL)"].sum()) if not closed.empty else 0.0

    return {
        "total_trades": int(len(trade_df)),
        "closed_trades": closed_count,
        "win_rate_pct": round(win_rate, 2),
        "avg_net_pnl_pct": round(float(closed["Net PnL (%)"].mean()), 2),
        "net_realized_pnl_pct": round(float(closed["Net PnL (%)"].sum()), 2),
        "net_realized_pnl_tl": round(float(closed["Net PnL (TL)"].sum()), 2),
        "open_positions": open_positions,
        "profit_factor": profit_factor,
        "max_win_pct": round(max_win, 2),
        "max_loss_pct": round(max_loss, 2),
        "total_costs_tl": round(total_costs, 2),
    }


def performance_breakdown(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, float]:
    if df.empty or "Strategy_Return" not in df.columns:
        return pd.DataFrame(), pd.DataFrame(), 0.0

    work = df.copy()
    strategy = work["Strategy_Return"].fillna(0.0)

    daily = ((1 + strategy).resample("D").prod() - 1) * 100
    weekly = ((1 + strategy).resample("W-FRI").prod() - 1) * 100

    equity = (1 + strategy).cumprod()
    running_peak = equity.cummax()
    drawdown = (equity / running_peak) - 1
    max_drawdown_pct = float(drawdown.min() * 100)

    daily_df = daily.reset_index()
    daily_df.columns = ["Tarih", "Gunluk Getiri (%)"]

    weekly_df = weekly.reset_index()
    weekly_df.columns = ["Hafta", "Haftalik Getiri (%)"]

    return daily_df, weekly_df, round(max_drawdown_pct, 2)


def run_backtest(
    ticker: str = "THYAO.IS",
    interval: str = "1m",
    period: str = "5d",
    range_lookback: int = 15,
    allow_short: bool = False,
    strategy_mode: str = "matriks",
    orb_start: str = "10:00",
    orb_end: str = "10:15",
    strict_end_bar: bool = True,
    execution_delay_bars: int = 1,
    raw_df: pd.DataFrame = None,
) -> pd.DataFrame:
    if raw_df is not None:
        raw = raw_df
    else:
        raw = fetch_intraday_data(ticker=ticker, interval=interval, period=period)
    if raw.empty:
        return raw

    mode = strategy_mode.lower().strip()
    if mode == "rolling":
        return apply_orb_logic(raw, range_lookback=range_lookback, allow_short=allow_short)

    return apply_matriks_orb_logic(
        raw,
        orb_start=orb_start,
        orb_end=orb_end,
        allow_short=allow_short,
        strict_end_bar=strict_end_bar,
        execution_delay_bars=execution_delay_bars,
    )


def backtest_summary(df: pd.DataFrame) -> dict:
    if df.empty:
        return {
            "market_pct": 0.0,
            "strategy_pct": 0.0,
            "signal": "Veri Yok",
            "total_trades": 0,
            "win_rate_pct": 0.0,
            "open_positions": 0,
        }

    final_market = float(df["Cum_Market_Return"].iloc[-1] * 100)
    final_strategy = float(df["Cum_Strategy_Return"].iloc[-1] * 100)
    last_signal = int(df["Signal"].iloc[-1])
    if last_signal == 1:
        signal = "AL"
    elif last_signal == -1:
        signal = "AÇIĞA SAT"
    else:
        signal = "NAKIT"

    trades = generate_trade_log(df)
    stats = trade_statistics(trades)
    _, _, max_dd = performance_breakdown(df)

    return {
        "market_pct": final_market,
        "strategy_pct": final_strategy,
        "signal": signal,
        "total_trades": stats["total_trades"],
        "win_rate_pct": stats["win_rate_pct"],
        "open_positions": stats["open_positions"],
        "max_drawdown_pct": max_dd,
    }

def simulate_viop_portfolio(
    df: pd.DataFrame,
    starting_balance: float = 100000.0,
    margin_pct: float = 0.20,
    commission_bps: float = 1.0,
    slippage_bps: float = 5.0,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    if df.empty or "Position" not in df.columns:
        return pd.DataFrame(), pd.DataFrame(), {}

    current_balance = starting_balance
    position_col = df["Position"].values
    close_col = df["Close"].values
    index_col = df.index
    
    cost_rate = (commission_bps + slippage_bps) / 10000.0
    
    trade_logs = []
    active_trade = None
    balances = []
    
    for i in range(len(df)):
        ts = index_col[i]
        price = close_col[i]
        pos = position_col[i]
        
        floating_pnl = 0.0
        if active_trade is not None:
            if active_trade["Yon"] == "LONG":
                floating_pnl = (price - active_trade["Giris Fiyat"]) * active_trade["Kontrat"] * 100
            else:
                floating_pnl = (active_trade["Giris Fiyat"] - price) * active_trade["Kontrat"] * 100
            
            est_cost = (active_trade["Giris Fiyat"] + price) * active_trade["Kontrat"] * 100 * cost_rate
            floating_pnl -= est_cost
            
            if pos != active_trade["PosValue"]:
                exit_price = price
                direction = active_trade["Yon"]
                cnt = active_trade["Kontrat"]
                
                if direction == "LONG":
                    gross_pnl = (exit_price - active_trade["Giris Fiyat"]) * cnt * 100
                else:
                    gross_pnl = (active_trade["Giris Fiyat"] - exit_price) * cnt * 100
                
                cost = (active_trade["Giris Fiyat"] + exit_price) * cnt * 100 * cost_rate
                net_pnl = gross_pnl - cost
                current_balance += net_pnl
                
                active_trade["Cikis Zamani"] = ts
                active_trade["Cikis Fiyat"] = round(exit_price, 4)
                active_trade["Brut PnL (TL)"] = round(gross_pnl, 2)
                active_trade["Maliyet (TL)"] = round(cost, 2)
                active_trade["Net PnL (TL)"] = round(net_pnl, 2)
                active_trade["Net PnL (%)"] = round((net_pnl / (active_trade["Giris Fiyat"] * cnt * 100)) * 100, 2) if cnt > 0 else 0.0
                active_trade["Bakiye"] = round(current_balance, 2)
                active_trade["Durum"] = "KAPALI"
                
                trade_logs.append(active_trade)
                active_trade = None
                floating_pnl = 0.0
                
        if active_trade is None and pos != 0:
            margin_per_contract = price * 100 * margin_pct
            if margin_per_contract > 0:
                contracts = int(current_balance // margin_per_contract)
            else:
                contracts = 0
                
            if contracts > 0:
                active_trade = {
                    "Islem No": len(trade_logs) + 1,
                    "Giris Zamani": ts,
                    "Cikis Zamani": pd.NaT,
                    "Yon": "LONG" if pos == 1 else "SHORT",
                    "Giris Fiyat": round(price, 4),
                    "Cikis Fiyat": None,
                    "Kontrat": contracts,
                    "Teminat (TL)": round(contracts * margin_per_contract, 2),
                    "Pozisyon Büyüklüğü (TL)": round(contracts * price * 100, 2),
                    "Brut PnL (TL)": 0.0,
                    "Maliyet (TL)": 0.0,
                    "Net PnL (TL)": 0.0,
                    "Net PnL (%)": 0.0,
                    "Bakiye": round(current_balance, 2),
                    "Durum": "ACIK",
                    "PosValue": pos
                }
                
        balances.append(current_balance + floating_pnl)
        
    # Son bar kapanışında açık pozisyon varsa logla
    if active_trade is not None:
        last_price = close_col[-1]
        ts = index_col[-1]
        cnt = active_trade["Kontrat"]
        direction = active_trade["Yon"]
        
        if direction == "LONG":
            gross_pnl = (last_price - active_trade["Giris Fiyat"]) * cnt * 100
        else:
            gross_pnl = (active_trade["Giris Fiyat"] - last_price) * cnt * 100
            
        cost = (active_trade["Giris Fiyat"] + last_price) * cnt * 100 * cost_rate
        net_pnl = gross_pnl - cost
        
        active_trade["Cikis Zamani"] = ts
        active_trade["Cikis Fiyat"] = round(last_price, 4)
        active_trade["Brut PnL (TL)"] = round(gross_pnl, 2)
        active_trade["Maliyet (TL)"] = round(cost, 2)
        active_trade["Net PnL (TL)"] = round(net_pnl, 2)
        active_trade["Net PnL (%)"] = round((net_pnl / (active_trade["Giris Fiyat"] * cnt * 100)) * 100, 2) if cnt > 0 else 0.0
        active_trade["Bakiye"] = round(current_balance + net_pnl, 2)
        active_trade["Durum"] = "ACIK"
        
        trade_logs.append(active_trade)

    portfolio_df = pd.DataFrame(index=df.index)
    portfolio_df["Bakiye"] = balances

    # Yıllıklandırılmış Sharpe Oranı
    daily_balances = portfolio_df["Bakiye"].resample("D").last().ffill()
    daily_returns = daily_balances.pct_change().dropna()
    if len(daily_returns) > 1 and daily_returns.std() > 0:
        sharpe = float((daily_returns.mean() / daily_returns.std()) * (252 ** 0.5))
    else:
        sharpe = 0.0
        
    closed_trades = [t for t in trade_logs if t["Durum"] == "KAPALI"]
    wins = [t for t in closed_trades if t["Net PnL (TL)"] > 0]
    win_rate = (len(wins) / len(closed_trades) * 100) if len(closed_trades) > 0 else 0.0
    
    # Max drawdown of equity curve
    equity_series = pd.Series(balances)
    running_peak = equity_series.cummax()
    drawdown = (equity_series / running_peak) - 1.0
    max_dd_pct = float(drawdown.min() * 100.0) if not drawdown.empty else 0.0

    summary = {
        "starting_balance": starting_balance,
        "final_balance": round(balances[-1], 2),
        "total_pnl_tl": round(balances[-1] - starting_balance, 2),
        "total_pnl_pct": round(((balances[-1] - starting_balance) / starting_balance) * 100, 2),
        "total_trades": len(trade_logs),
        "closed_trades": len(closed_trades),
        "win_rate_pct": round(win_rate, 2),
        "sharpe_ratio": round(sharpe, 2),
        "total_costs_tl": round(sum([t["Maliyet (TL)"] for t in trade_logs]), 2),
        "open_positions": 1 if active_trade is not None else 0,
        "max_drawdown_pct": round(max_dd_pct, 2)
    }
    
    trade_df = pd.DataFrame(trade_logs)
    return portfolio_df, trade_df, summary


def plot_backtest(df: pd.DataFrame, ticker: str) -> None:
    if df.empty:
        print("Veri bulunamadi, grafik cizilemedi.")
        return

    plt.figure(figsize=(14, 7))
    plt.plot(df.index, df["Cum_Market_Return"] * 100, label="Hisse (Al-Tut)", color="gray", alpha=0.6)
    plt.plot(df.index, df["Cum_Strategy_Return"] * 100, label="ORB Stratejisi", color="blue", linewidth=1.5)
    plt.title(f"{ticker} - 1 Dakikalik ORB Strateji Kiyaslamasi")
    plt.xlabel("Tarih")
    plt.ylabel("Kumulatif Getiri (%)")
    plt.legend()
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.show()


if __name__ == "__main__":
    TICKER = "THYAO.IS"
    TIMEFRAME = "1m"
    PERIOD = "5d"
    RANGE_LOOKBACK = 15

    print(f"{TICKER} icin veri indiriliyor...")
    bt_df = run_backtest(
        ticker=TICKER,
        interval=TIMEFRAME,
        period=PERIOD,
        range_lookback=RANGE_LOOKBACK,
    )

    info = backtest_summary(bt_df)
    print("=" * 40)
    print(f"BACKTEST SONUCU ({TICKER})")
    print(f"Kanal Periyodu: {RANGE_LOOKBACK} dakika")
    print(f"Al-Tut Getirisi: %{info['market_pct']:.2f}")
    print(f"ORB Getirisi: %{info['strategy_pct']:.2f}")
    print(f"Son Sinyal: {info['signal']}")
    print("=" * 40)

    plot_backtest(bt_df, TICKER)