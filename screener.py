"""
UK relative-value screener.

Pulls prices, dividends and annual statements from yfinance, computes
sector-specific valuation and quality metrics, scores each company against
its peers today and against its own peer-relative history, and writes an
HTML report.

Usage:
    python screener.py                    # full run, all sectors in config.py
    python screener.py --sectors banks reits
    python screener.py --demo             # synthetic data, no downloads

Reports are saved as output/uk_value_screen_YYYY-MM-DD.html inside the
folder that holds this code, whatever folder you run it from. Nothing else is
stored between runs: every run fetches fresh data.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd

import config


# ---------------------------------------------------------------------------
# Data container
# ---------------------------------------------------------------------------

@dataclass
class CompanyData:
    """Everything fetched for one company, already converted to GBP."""
    ticker: str
    name: str
    sector: str
    quote_currency: str = "GBp"
    financial_currency: str = "GBP"
    yahoo_sector: str = ""
    yahoo_industry: str = ""
    prices: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))     # GBP, daily
    dividends: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))  # GBP per share, ex-date
    annual: pd.DataFrame = field(default_factory=pd.DataFrame)  # index: period end, GBP
    current_shares: float = np.nan
    forward_pe: float = np.nan     # snapshot from Yahoo, no history
    warnings: list = field(default_factory=list)

    # Filled in by prepare_dividends()
    ttm_dividend: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    specials_excluded: int = 0


# Standard field name -> Yahoo statement row labels to try, in order.
STATEMENT_ROWS = {
    "revenue":       ("income", ["Total Revenue", "Operating Revenue"]),
    "gross_profit":  ("income", ["Gross Profit"]),
    "ebitda":        ("income", ["EBITDA", "Normalized EBITDA"]),
    "ebit":          ("income", ["EBIT", "Operating Income"]),
    "interest_expense": ("income", ["Interest Expense", "Interest Expense Non Operating"]),
    "pretax_income": ("income", ["Pretax Income"]),
    "tax_provision": ("income", ["Tax Provision"]),
    "net_income":    ("income", ["Net Income Common Stockholders", "Net Income",
                                 "Net Income From Continuing Operation Net Minority Interest"]),
    "total_assets":  ("balance", ["Total Assets"]),
    "current_assets": ("balance", ["Current Assets"]),
    "current_liabilities": ("balance", ["Current Liabilities"]),
    "equity":        ("balance", ["Common Stock Equity", "Stockholders Equity"]),
    "tangible_book": ("balance", ["Tangible Book Value"]),
    "total_debt":    ("balance", ["Total Debt"]),
    "long_term_debt": ("balance", ["Long Term Debt"]),
    "cash":          ("balance", ["Cash And Cash Equivalents",
                                  "Cash Cash Equivalents And Short Term Investments"]),
    "shares":        ("balance", ["Ordinary Shares Number", "Share Issued"]),
    "fcf":           ("cashflow", ["Free Cash Flow"]),
    "ocf":           ("cashflow", ["Operating Cash Flow"]),
    "capex":         ("cashflow", ["Capital Expenditure"]),
    "dividends_paid": ("cashflow", ["Cash Dividends Paid", "Common Stock Dividend Paid"]),
    "buybacks":      ("cashflow", ["Repurchase Of Capital Stock", "Common Stock Payments"]),
}
MONEY_FIELDS = [f for f in STATEMENT_ROWS if f != "shares"]


# ---------------------------------------------------------------------------
# Fetching (yfinance)
# ---------------------------------------------------------------------------

def _naive_index(obj):
    """Drop timezone information so all date arithmetic is consistent."""
    if obj is None or len(obj) == 0:
        return obj
    idx = pd.DatetimeIndex(obj.index)
    if idx.tz is not None:
        idx = idx.tz_convert("Europe/London").tz_localize(None)
    obj = obj.copy()
    obj.index = idx.normalize()
    return obj


def _pick_row(df: pd.DataFrame, labels: list[str]) -> pd.Series | None:
    if df is None or df.empty:
        return None
    for label in labels:
        if label in df.index:
            row = pd.to_numeric(df.loc[label], errors="coerce")
            if isinstance(row, pd.DataFrame):  # duplicated label
                row = row.iloc[0]
            if row.notna().any():
                return row
    return None


def _fx_series(currency: str, fx_cache: dict) -> pd.Series | None:
    """Daily units of `currency` per 1 GBP. None for GBP itself."""
    if currency in ("GBP", "GBp", "GBX"):
        return None
    if currency not in fx_cache:
        import yfinance as yf
        hist = yf.Ticker(f"GBP{currency}=X").history(period="max", auto_adjust=False)
        fx_cache[currency] = _naive_index(hist["Close"]).dropna()
    return fx_cache[currency]


def _to_gbp(values: pd.Series, currency: str, fx_cache: dict) -> pd.Series:
    """Convert a date-indexed series from `currency` to GBP at each date."""
    if currency in ("GBp", "GBX"):
        return values / 100.0
    fx = _fx_series(currency, fx_cache)
    if fx is None:
        return values
    rates = fx.reindex(fx.index.union(values.index)).ffill().reindex(values.index)
    return values / rates


def fetch_company(ticker: str, name: str, sector: str, fx_cache: dict) -> CompanyData:
    import yfinance as yf

    cd = CompanyData(ticker=ticker, name=name, sector=sector)
    tk = yf.Ticker(ticker)

    try:
        info = tk.info or {}
    except Exception as exc:  # yfinance raises a variety of errors here
        info = {}
        cd.warnings.append(f"info unavailable ({type(exc).__name__})")

    cd.quote_currency = info.get("currency") or "GBp"
    fin_ccy = info.get("financialCurrency") or "GBP"
    cd.financial_currency = "GBP" if fin_ccy in ("GBp", "GBX") else fin_ccy
    cd.yahoo_sector = info.get("sector", "")
    cd.yahoo_industry = info.get("industry", "")

    # Prices, dividends, splits
    years = config.SETTINGS["dividend_history_years"] + 1
    hist = tk.history(period=f"{years}y", auto_adjust=False, actions=True)
    if hist is None or hist.empty:
        raise RuntimeError("no price history returned")
    hist = _naive_index(hist)
    cd.prices = _to_gbp(hist["Close"].dropna(), cd.quote_currency, fx_cache)

    divs = hist.get("Dividends", pd.Series(dtype=float))
    divs = divs[divs > 0]
    cd.dividends = _to_gbp(divs, cd.quote_currency, fx_cache)

    splits = hist.get("Stock Splits", pd.Series(dtype=float))
    splits = splits[(splits > 0) & (splits != 1)]

    # Annual statements
    statements = {
        "income": tk.income_stmt,
        "balance": tk.balance_sheet,
        "cashflow": tk.cashflow,
    }
    rows = {}
    for fld, (stmt, labels) in STATEMENT_ROWS.items():
        row = _pick_row(statements[stmt], labels)
        if row is not None:
            rows[fld] = row
    if not rows:
        cd.warnings.append("no annual statements")
        cd.annual = pd.DataFrame(columns=list(STATEMENT_ROWS))
    else:
        annual = pd.DataFrame(rows)
        annual.index = pd.DatetimeIndex(annual.index).tz_localize(None).normalize()
        annual = annual.sort_index().reindex(columns=list(STATEMENT_ROWS))

        # Free cash flow fallback: operating cash flow + capex (capex is negative)
        missing_fcf = annual["fcf"].isna() & annual["ocf"].notna() & annual["capex"].notna()
        annual.loc[missing_fcf, "fcf"] = annual.loc[missing_fcf, "ocf"] + annual.loc[missing_fcf, "capex"]

        for fld in MONEY_FIELDS:
            annual[fld] = _to_gbp(annual[fld], cd.financial_currency, fx_cache)

        # Put historical share counts on today's split basis, matching the
        # split-adjusted price series.
        for period_end in annual.index:
            later = splits[splits.index > period_end]
            if len(later):
                annual.loc[period_end, "shares"] *= float(np.prod(later.values))
        cd.annual = annual

    cd.forward_pe = info.get("forwardPE") or np.nan
    cd.current_shares = info.get("sharesOutstanding") or np.nan
    if pd.isna(cd.current_shares) and not cd.annual.empty:
        cd.current_shares = cd.annual["shares"].dropna().iloc[-1] if cd.annual["shares"].notna().any() else np.nan

    return cd


def fetch_all(sector_keys: list[str]) -> tuple[dict, list]:
    companies, failures = {}, []
    fx_cache: dict = {}
    pause = config.SETTINGS["request_pause_seconds"]
    total = sum(len(config.SECTORS[k]["tickers"]) for k in sector_keys)
    done = 0
    for key in sector_keys:
        for ticker, name in config.SECTORS[key]["tickers"].items():
            done += 1
            print(f"[{done}/{total}] {ticker:<8} {name}")
            try:
                companies[ticker] = fetch_company(ticker, name, key, fx_cache)
            except Exception as exc:
                failures.append({"ticker": ticker, "name": name, "sector": key,
                                 "reason": f"{type(exc).__name__}: {exc}"})
                print(f"    failed: {exc}")
            time.sleep(pause)
    return companies, failures


# ---------------------------------------------------------------------------
# Dividends
# ---------------------------------------------------------------------------

def prepare_dividends(cd: CompanyData) -> None:
    """Exclude special dividends and build a daily trailing-12-month series."""
    settings = config.SETTINGS
    divs = cd.dividends.sort_index()
    keep = []
    for i, (date, amount) in enumerate(divs.items()):
        # Compare with the largest of the previous six payments, so a
        # recovery after a dividend cut is not mistaken for a special.
        prior = divs.iloc[max(0, i - 6):i]
        if len(prior) >= 3 and amount > settings["special_dividend_multiple"] * prior.max():
            cd.specials_excluded += 1
            continue
        keep.append((date, amount))
    regular = pd.Series(dict(keep), dtype=float)

    if cd.prices.empty:
        return
    daily = pd.Series(0.0, index=cd.prices.index)
    if len(regular):
        aligned = regular.groupby(regular.index).sum()
        # Snap ex-dates onto trading days
        aligned.index = cd.prices.index[cd.prices.index.searchsorted(aligned.index).clip(max=len(cd.prices) - 1)]
        daily = daily.add(aligned.groupby(level=0).sum(), fill_value=0.0)
    cd.ttm_dividend = daily.rolling("365D").sum()

    # Unit sanity check: a trailing yield over 50% almost always means
    # dividends and prices are in different units (pence versus pounds).
    yld = (cd.ttm_dividend / cd.prices).replace([np.inf, -np.inf], np.nan)
    positive = yld[yld > 0]
    if len(positive) and positive.median() > 0.5:
        cd.ttm_dividend = cd.ttm_dividend / 100.0
        cd.warnings.append("dividends rescaled from pence (unit mismatch detected)")


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def _div(a, b):
    if a is None or b is None or pd.isna(a) or pd.isna(b) or b == 0:
        return np.nan
    return a / b


def _price_asof(prices: pd.Series, date: pd.Timestamp, max_stale_days: int = 10) -> float:
    window = prices.loc[:date]
    if window.empty or (date - window.index[-1]).days > max_stale_days:
        return np.nan
    return float(window.iloc[-1])


def _pos(x) -> bool:
    return x is not None and pd.notna(x) and x > 0


def _tax_rate(f) -> float:
    """Effective tax rate, clipped to a sensible range; UK main rate if unknown."""
    rate = _div(f["tax_provision"], f["pretax_income"])
    if pd.isna(rate) or not _pos(f["pretax_income"]):
        return 0.25
    return float(min(max(rate, 0.0), 0.5))


def _piotroski(f, p) -> float:
    """Piotroski F-score from the latest (f) and prior (p) annual accounts.

    Tests whose inputs are missing are skipped; the score is rescaled to a
    0-9 range from the tests available, and needs at least seven of them.
    """
    tests = []

    def add(condition):
        if condition is not None:
            tests.append(bool(condition))

    roa, roa_p = _div(f["net_income"], f["total_assets"]), _div(p["net_income"], p["total_assets"])
    add(roa > 0 if pd.notna(roa) else None)
    add(f["ocf"] > 0 if pd.notna(f["ocf"]) else None)
    add(roa > roa_p if pd.notna(roa) and pd.notna(roa_p) else None)
    add(f["ocf"] > f["net_income"] if pd.notna(f["ocf"]) and pd.notna(f["net_income"]) else None)
    debt_f = f["long_term_debt"] if pd.notna(f["long_term_debt"]) else f["total_debt"]
    debt_p = p["long_term_debt"] if pd.notna(p["long_term_debt"]) else p["total_debt"]
    lev, lev_p = _div(debt_f, f["total_assets"]), _div(debt_p, p["total_assets"])
    add(lev <= lev_p if pd.notna(lev) and pd.notna(lev_p) else None)
    cr, cr_p = _div(f["current_assets"], f["current_liabilities"]), _div(p["current_assets"], p["current_liabilities"])
    add(cr > cr_p if pd.notna(cr) and pd.notna(cr_p) else None)
    add(f["shares"] <= p["shares"] * 1.001 if pd.notna(f["shares"]) and pd.notna(p["shares"]) else None)
    gm, gm_p = _div(f["gross_profit"], f["revenue"]), _div(p["gross_profit"], p["revenue"])
    add(gm > gm_p if pd.notna(gm) and pd.notna(gm_p) else None)
    at, at_p = _div(f["revenue"], f["total_assets"]), _div(p["revenue"], p["total_assets"])
    add(at > at_p if pd.notna(at) and pd.notna(at_p) else None)

    if len(tests) < 7:
        return np.nan
    return sum(tests) * 9.0 / len(tests)


def compute_metrics(cd: CompanyData, date: pd.Timestamp, use_current_shares: bool) -> dict:
    """All metrics for one company as of `date`, using only fundamentals
    assumed public by then (period end + reporting lag).

    use_current_shares=True marks the live calculation: it uses Yahoo's
    current share count and includes snapshot-only metrics such as forward P/E.
    """
    lag = pd.Timedelta(days=config.SETTINGS["reporting_lag_days"])
    out = {m: np.nan for m in config.METRICS}
    out.update(period_end=pd.NaT, price=np.nan, market_cap=np.nan)

    if cd.annual.empty:
        return out
    available = cd.annual[cd.annual.index + lag <= date]
    if available.empty:
        return out
    f = available.iloc[-1]
    p = available.iloc[-2] if len(available) >= 2 else None
    out["period_end"] = available.index[-1]

    price = _price_asof(cd.prices, date)
    shares = cd.current_shares if use_current_shares and pd.notna(cd.current_shares) else f["shares"]
    mcap = price * shares if pd.notna(price) and pd.notna(shares) else np.nan
    cash = f["cash"] if pd.notna(f["cash"]) else 0.0
    ev = mcap + f["total_debt"] - cash if pd.notna(mcap) and pd.notna(f["total_debt"]) else np.nan
    net_debt = f["total_debt"] - cash if pd.notna(f["total_debt"]) else np.nan
    tax = _tax_rate(f)
    interest = abs(f["interest_expense"]) if pd.notna(f["interest_expense"]) else np.nan
    dividends = abs(f["dividends_paid"]) if pd.notna(f["dividends_paid"]) else np.nan
    buybacks = abs(f["buybacks"]) if pd.notna(f["buybacks"]) else np.nan

    # --- Valuation multiples ---
    out["pe"] = _div(mcap, f["net_income"])
    ni_hist = available["net_income"].dropna()
    if len(ni_hist) >= 2:
        out["pe_avg"] = _div(mcap, ni_hist.mean())
    if use_current_shares and _pos(cd.forward_pe):
        out["fwd_pe"] = cd.forward_pe
    out["pb"] = _div(mcap, f["equity"])
    out["ptbv"] = _div(mcap, f["tangible_book"])
    out["p_ocf"] = _div(mcap, f["ocf"])
    out["ev_ebitda"] = _div(ev, f["ebitda"]) if _pos(f["ebitda"]) else np.nan
    out["ev_ebit"] = _div(ev, f["ebit"])
    out["ev_sales"] = _div(ev, f["revenue"])
    out["ev_gp"] = _div(ev, f["gross_profit"]) if _pos(f["gross_profit"]) else np.nan

    # --- Yields ---
    out["fcf_yield"] = _div(f["fcf"], mcap)
    if pd.notna(f["fcf"]) and _pos(ev):
        out["ufcf_yield"] = (f["fcf"] + (interest if pd.notna(interest) else 0.0) * (1 - tax)) / ev
    if not cd.ttm_dividend.empty and pd.notna(price):
        ttm = cd.ttm_dividend.loc[:date]
        out["div_yield"] = _div(float(ttm.iloc[-1]), price) if len(ttm) else np.nan
    if pd.notna(dividends) or pd.notna(buybacks):
        returned = (dividends if pd.notna(dividends) else 0.0) + (buybacks if pd.notna(buybacks) else 0.0)
        out["shareholder_yield"] = _div(returned, mcap)

    # --- Quality: returns ---
    out["roe"] = _div(f["net_income"], f["equity"]) if _pos(f["equity"]) else np.nan
    out["rote"] = _div(f["net_income"], f["tangible_book"]) if _pos(f["tangible_book"]) else np.nan
    out["roa"] = _div(f["net_income"], f["total_assets"]) if _pos(f["total_assets"]) else np.nan
    invested = f["equity"] + net_debt if pd.notna(f["equity"]) and pd.notna(net_debt) else np.nan
    if _pos(invested) and pd.notna(f["ebit"]):
        out["roic"] = f["ebit"] * (1 - tax) / invested

    # --- Quality: margins and growth ---
    out["gross_margin"] = _div(f["gross_profit"], f["revenue"])
    margins = available["ebit"] / available["revenue"]
    out["op_margin"] = margins.iloc[-1]
    if margins.notna().sum() >= 2:
        out["margin_trend"] = margins.iloc[-1] - margins.iloc[:-1].mean()
    rev = available["revenue"].dropna()
    if len(rev) >= 2 and rev.iloc[0] > 0 and rev.iloc[-1] > 0:
        years = (rev.index[-1] - rev.index[0]).days / 365.25
        if years > 0.5:
            out["revenue_growth"] = (rev.iloc[-1] / rev.iloc[0]) ** (1 / years) - 1

    # --- Quality: cash and balance sheet ---
    out["cash_conversion"] = _div(f["fcf"], f["net_income"]) if _pos(f["net_income"]) else np.nan
    out["net_debt_ebitda"] = _div(net_debt, f["ebitda"]) if _pos(f["ebitda"]) else np.nan
    out["interest_cover"] = _div(f["ebit"], interest) if _pos(interest) else np.nan
    out["dividend_cover"] = _div(f["net_income"], dividends) if _pos(dividends) else np.nan
    sh = available["shares"].dropna()
    if len(sh) >= 2 and sh.iloc[0] > 0:
        years = (sh.index[-1] - sh.index[0]).days / 365.25
        if years > 0.5:
            out["share_change"] = (sh.iloc[-1] / sh.iloc[0]) ** (1 / years) - 1
    if p is not None:
        out["piotroski"] = _piotroski(f, p)

    out["price"] = price
    out["market_cap"] = mcap
    return out


def cheapness(metric: str, value: float) -> float:
    """Transform a metric so that higher always means cheaper.

    Multiples are inverted into yields. This keeps loss-makers in the
    ranking (a negative P/E becomes a negative earnings yield, correctly
    ranking as expensive) rather than producing nonsense rankings.
    """
    if pd.isna(value):
        return np.nan
    if config.METRICS[metric]["kind"] == "valuation":
        return 1.0 / value if value != 0 else np.nan
    return value


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def pct_rank(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    """Percentile rank 0-100 among non-missing values."""
    s = series.astype(float)
    valid = s.notna()
    out = pd.Series(np.nan, index=s.index)
    n = valid.sum()
    if n == 0:
        return out
    if n == 1:
        out[valid] = 50.0
        return out
    ranks = s[valid].rank(ascending=higher_is_better, method="average")
    out[valid] = (ranks - 1) / (n - 1) * 100.0
    return out


def weighted_mean(frame: pd.DataFrame, weights: dict) -> pd.Series:
    """Row-wise weighted mean, renormalising over non-missing columns."""
    cols = [c for c in weights if c in frame.columns]
    if not cols:
        return pd.Series(np.nan, index=frame.index)
    w = pd.Series({c: weights[c] for c in cols})
    values = frame[cols]
    mask = values.notna()
    num = (values.fillna(0.0) * w).sum(axis=1)
    den = (mask * w).sum(axis=1)
    return (num / den).where(den > 0)


def history_dates() -> list[pd.Timestamp]:
    s = config.SETTINGS
    end = pd.Timestamp.today().normalize()
    start = end - pd.DateOffset(years=s["history_years"])
    return list(pd.date_range(start, end, freq=s["history_frequency"]))


def score_sector(key: str, companies: dict) -> dict:
    """Score every company in one sector. Returns tables and chart data."""
    sector = config.SECTORS[key]
    s = config.SETTINGS
    members = [cd for cd in companies.values() if cd.sector == key]
    today = pd.Timestamp.today().normalize()

    # ----- Current snapshot -------------------------------------------------
    rows = {}
    for cd in members:
        m = compute_metrics(cd, today, use_current_shares=True)
        m.update(name=cd.name, ticker=cd.ticker)
        rows[cd.ticker] = m
    now = pd.DataFrame.from_dict(rows, orient="index")
    if now.empty:
        return {"key": key, "table": now, "history": {}, "div_bands": {}, "regression": None}

    val_metrics = list(sector["valuation"])
    qual_metrics = list(sector["quality"])

    # Peer value: percentile of cheapness within the sector today
    for metric in val_metrics:
        cheap = now[metric].map(lambda v, m=metric: cheapness(m, v))
        now[f"pct_{metric}"] = pct_rank(cheap, higher_is_better=True)
    now["peer_value"] = weighted_mean(
        pd.DataFrame({m: now[f"pct_{m}"] for m in val_metrics}), sector["valuation"])

    # Quality
    for metric in qual_metrics:
        hib = config.METRICS[metric]["higher_is_better"]
        now[f"pct_{metric}"] = pct_rank(now[metric], higher_is_better=hib)
    now["quality"] = weighted_mean(
        pd.DataFrame({m: now[f"pct_{m}"] for m in qual_metrics}), sector["quality"])

    # ----- History: spread of cheapness versus the sector median -------------
    # At each evaluation date, each company's cheapness minus the sector
    # median. Today's spread is then placed within the company's own
    # distribution of past spreads. This strips out market-wide re-rating.
    dates = history_dates()
    hist_rows = []
    for date in dates:
        for cd in members:
            m = compute_metrics(cd, date, use_current_shares=False)
            for metric in val_metrics:
                hist_rows.append({"date": date, "ticker": cd.ticker, "metric": metric,
                                  "cheap": cheapness(metric, m[metric])})
    hist = pd.DataFrame(hist_rows)
    now_long = pd.DataFrame([
        {"date": today, "ticker": t, "metric": metric, "cheap": cheapness(metric, now.at[t, metric])}
        for t in now.index for metric in val_metrics])
    panel = pd.concat([hist, now_long], ignore_index=True)

    counts = panel.groupby(["date", "metric"])["cheap"].transform("count")
    medians = panel.groupby(["date", "metric"])["cheap"].transform("median")
    panel["spread"] = (panel["cheap"] - medians).where(counts >= 3)
    panel["sector_median"] = medians.where(counts >= 3)

    history_charts = {}
    hist_scores = {}
    hist_points = {}
    for ticker in now.index:
        per_metric = {}
        chart = {}
        n_points = 0
        for metric in val_metrics:
            sub = panel[(panel["ticker"] == ticker) & (panel["metric"] == metric)].sort_values("date")
            past = sub[sub["date"] < today]["spread"].dropna()
            n_points = max(n_points, len(past))
            current = sub[sub["date"] == today]["spread"]
            current = current.iloc[0] if len(current) else np.nan
            if len(past) >= s["min_history_points"] and pd.notna(current):
                per_metric[metric] = ((past < current).sum() + 0.5 * (past == current).sum()) / len(past) * 100
            chart[metric] = {
                "dates": [d.strftime("%Y-%m-%d") for d in sub["date"]],
                "company": sub["cheap"].tolist(),
                "median": sub["sector_median"].tolist(),
            }
        hist_scores[ticker] = per_metric
        hist_points[ticker] = n_points
        history_charts[ticker] = chart
    hist_df = pd.DataFrame.from_dict(hist_scores, orient="index").reindex(index=now.index, columns=val_metrics)
    now["history_value"] = weighted_mean(hist_df, sector["valuation"])
    now["history_points"] = pd.Series(hist_points).reindex(now.index)

    # ----- Dividend yield versus its own long history ------------------------
    div_bands = {}
    div_scores = {}
    for cd in members:
        if cd.ttm_dividend.empty or cd.prices.empty:
            continue
        yld = (cd.ttm_dividend / cd.prices).replace([np.inf, -np.inf], np.nan).dropna()
        cutoff = today - pd.DateOffset(years=s["dividend_history_years"])
        yld = yld[yld.index >= cutoff]
        if len(yld) < 252 * 3 or yld.iloc[-1] <= 0:
            continue
        current = yld.iloc[-1]
        div_scores[cd.ticker] = (yld < current).mean() * 100
        monthly = yld.resample("ME").last().dropna()
        div_bands[cd.ticker] = {
            "dates": [d.strftime("%Y-%m-%d") for d in monthly.index],
            "yield": monthly.round(5).tolist(),
            "p25": float(yld.quantile(0.25)),
            "p50": float(yld.quantile(0.50)),
            "p75": float(yld.quantile(0.75)),
            "years": round((yld.index[-1] - yld.index[0]).days / 365.25, 1),
        }
    now["dividend_value"] = pd.Series(div_scores).reindex(now.index)

    # ----- Composite --------------------------------------------------------
    weights = s["composite_weights"]
    now["composite"] = weighted_mean(now, weights).where(now["peer_value"].notna())

    # ----- Regression: multiple versus the fundamental that justifies it -----
    regression = None
    if sector.get("regression"):
        x_m, y_m = sector["regression"]
        pts = now[[x_m, y_m, "name"]].dropna()
        pts = pts[pts[y_m] > 0]
        now["reg_resid"] = np.nan
        if len(pts) >= 4 and pts[x_m].std() > 0:
            slope, intercept = np.polyfit(pts[x_m], pts[y_m], 1)
            fitted = intercept + slope * pts[x_m]
            resid = (pts[y_m] / fitted - 1).where(fitted > 0)
            now.loc[resid.index, "reg_resid"] = resid
            regression = {
                "x": x_m, "y": y_m,
                "points": [{"ticker": t, "name": r["name"], "x": float(r[x_m]), "y": float(r[y_m]),
                            "resid": None if pd.isna(resid.get(t)) else float(resid[t])}
                           for t, r in pts.iterrows()],
                "slope": float(slope), "intercept": float(intercept),
            }

    # ----- Flags ------------------------------------------------------------
    flags = {}
    for cd in members:
        t = cd.ticker
        f = []
        row = now.loc[t]
        if (pd.notna(row["peer_value"]) and pd.notna(row["quality"])
                and row["peer_value"] >= s["value_trap_value_min"]
                and row["quality"] <= s["value_trap_quality_max"]):
            f.append("Possible value trap")
        if pd.notna(row["pe"]) and row["pe"] < 0:
            f.append("Loss-making")
        missing = [config.METRICS[m]["label"] for m in val_metrics if pd.isna(row[m])]
        if missing:
            f.append("Missing " + ", ".join(missing))
        if pd.notna(row["period_end"]) and (today - row["period_end"]).days > 550:
            f.append("Stale accounts")
        if cd.specials_excluded:
            f.append(f"{cd.specials_excluded} special dividend(s) excluded")
        f.extend(w.capitalize() for w in cd.warnings)
        flags[t] = f
    now["flags"] = pd.Series(flags)
    now["sector"] = key

    return {"key": key, "table": now, "history": history_charts,
            "div_bands": div_bands, "regression": regression}


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run(sector_keys: list[str], demo: bool = False, output: str | None = None) -> str:
    config.validate_config()
    if demo:
        from demo_data import make_demo_companies
        companies, failures = make_demo_companies(sector_keys)
    else:
        companies, failures = fetch_all(sector_keys)

    for cd in companies.values():
        prepare_dividends(cd)

    results = []
    for key in sector_keys:
        print(f"Scoring {config.SECTORS[key]['name']}")
        results.append(score_sector(key, companies))

    from report import build_report
    generated = datetime.now()
    html = build_report(results, failures, generated=generated, demo=demo)
    path = Path(output) if output else default_output_path(generated, demo)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    print(f"Report written to {path}")
    return str(path)


def default_output_path(generated: datetime, demo: bool = False) -> Path:
    """<folder containing this code>/output/uk_value_screen_YYYY-MM-DD.html"""
    s = config.SETTINGS
    name = s["output_filename"].format(date=generated.strftime("%Y-%m-%d"))
    if demo:
        stem, dot, ext = name.rpartition(".")
        name = f"{stem}_demo.{ext}" if dot else f"{name}_demo"
    return Path(__file__).resolve().parent / s["output_dir"] / name


def main():
    parser = argparse.ArgumentParser(description="UK relative-value screener")
    parser.add_argument("--sectors", nargs="*", help="sector keys from config.py (default: all)")
    parser.add_argument("--demo", action="store_true", help="use synthetic data, no downloads")
    parser.add_argument("--output", help="write the report to this path instead of the dated file in output/")
    args = parser.parse_args()

    keys = args.sectors or list(config.SECTORS)
    unknown = [k for k in keys if k not in config.SECTORS]
    if unknown:
        parser.error(f"unknown sector(s): {', '.join(unknown)}. Options: {', '.join(config.SECTORS)}")
    run(keys, demo=args.demo, output=args.output)


if __name__ == "__main__":
    main()