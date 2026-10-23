"""
Synthetic data for `python screener.py --demo`.

Produces CompanyData objects with the same shape the yfinance fetcher
returns, so the scoring and report can be tested without any downloads.
The numbers are random and mean nothing.
"""

import numpy as np
import pandas as pd

import config
from screener import CompanyData

# Rough sector profiles: (P/E, P/B, EV/EBITDA, op margin, dividend yield, is_financial)
PROFILES = {
    "banks":         (8,  0.8, None, 0.30, 0.055, True),
    "insurance":     (11, 1.5, None, 0.12, 0.060, True),
    "oil_gas":       (8,  1.2, 4,    0.18, 0.050, False),
    "mining":        (10, 1.6, 5,    0.25, 0.045, False),
    "utilities":     (15, 1.8, 10,   0.22, 0.055, False),
    "retail":        (13, 2.0, 7,    0.06, 0.035, False),
    "housebuilders": (12, 1.1, 8,    0.12, 0.050, False),
    "staples":       (17, 3.5, 12,   0.20, 0.040, False),
    "healthcare":    (20, 4.0, 14,   0.22, 0.025, False),
    "industrials":   (19, 3.0, 12,   0.13, 0.020, False),
    "reits":         (14, 0.8, 18,   0.60, 0.050, False),
    "telecom_media": (14, 1.8, 7,    0.15, 0.045, False),
}


def make_demo_companies(sector_keys):
    rng = np.random.default_rng(42)
    today = pd.Timestamp.today().normalize()
    days = pd.bdate_range(today - pd.DateOffset(years=16), today)
    companies, failures = {}, []

    for key in sector_keys:
        pe0, pb0, ev0, margin0, dy0, financial = PROFILES[key]
        for i, (ticker, name) in enumerate(config.SECTORS[key]["tickers"].items()):
            # Leave one company out to show how failures are reported
            if key == "mining" and i == len(config.SECTORS[key]["tickers"]) - 1:
                failures.append({"ticker": ticker, "name": name, "sector": key,
                                 "reason": "HTTPError: 404 (demo failure)"})
                continue

            # Price: geometric random walk with a company-specific drift
            drift = rng.normal(0.04, 0.05) / 252
            vol = rng.uniform(0.18, 0.35) / np.sqrt(252)
            shocks = rng.normal(drift, vol, len(days))
            covid = (days >= "2020-02-20") & (days <= "2020-03-23")
            shocks[covid] -= 0.012
            prices = pd.Series(rng.uniform(1, 30) * np.exp(np.cumsum(shocks)), index=days)

            # Dividends: interim (1/3) and final (2/3), cut during 2020
            company_dy = dy0 * rng.uniform(0.6, 1.4)
            div_dates = []
            for year in range(days[0].year, today.year + 1):
                for month, share in ((4, 2 / 3), (9, 1 / 3)):
                    d = pd.Timestamp(year, month, 15)
                    if days[0] < d < today:
                        div_dates.append((d, share))
            divs = {}
            for d, share in div_dates:
                amount = prices.asof(d) * company_dy * share
                if d.year == 2020:
                    amount *= 0.3
                divs[d] = amount
            if i == 1:  # one special dividend per sector
                special = pd.Timestamp(today.year - 2, 6, 15)
                divs[special] = prices.asof(special) * 0.10
            dividends = pd.Series(divs).sort_index()

            # Annual fundamentals for the last four fiscal years, set
            # relative to market cap at the time with company-level noise
            shares = rng.uniform(5e8, 6e9)
            ends = [pd.Timestamp(today.year - k, 12, 31) for k in range(4, 0, -1)]
            pe = pe0 * rng.uniform(0.6, 1.5)
            pb = pb0 * rng.uniform(0.6, 1.5)
            margin = margin0 * rng.uniform(0.6, 1.4)
            margin_drift = rng.normal(0, 0.01)
            rows = {}
            for k, end in enumerate(ends):
                mcap = prices.asof(end) * shares
                net_income = mcap / (pe * rng.uniform(0.85, 1.15))
                if key == "retail" and i == 2 and k == len(ends) - 1:
                    net_income = -abs(net_income) * 0.4  # one loss-maker
                equity = mcap / (pb * rng.uniform(0.9, 1.1))
                m = max(margin + margin_drift * k, 0.01)
                ebit = net_income / 0.75 * rng.uniform(0.95, 1.1)
                revenue = abs(ebit) / m
                if financial:
                    ebitda = total_debt = np.nan
                    cash = np.nan
                else:
                    ev_mult = ev0 * rng.uniform(0.7, 1.3)
                    ebitda = abs(ebit) * rng.uniform(1.2, 1.6)
                    total_debt = max(ev_mult * ebitda - mcap, 0) + mcap * 0.1
                    cash = mcap * rng.uniform(0.03, 0.12)
                total_assets = equity * (rng.uniform(12, 20) if financial else rng.uniform(1.8, 3.0))
                ocf = abs(net_income) * rng.uniform(1.0, 1.6)
                capex = -ocf * rng.uniform(0.2, 0.5)
                interest = (total_debt * rng.uniform(0.03, 0.06)) if not financial else np.nan
                pretax = ebit - (interest if not financial else 0.0)
                rows[end] = {
                    "revenue": revenue,
                    "gross_profit": np.nan if financial else revenue * min(m * rng.uniform(2.0, 3.5), 0.9),
                    "ebitda": ebitda, "ebit": ebit,
                    "interest_expense": interest,
                    "pretax_income": pretax, "tax_provision": pretax * rng.uniform(0.18, 0.27),
                    "net_income": net_income,
                    "total_assets": total_assets,
                    "current_assets": np.nan if financial else total_assets * rng.uniform(0.2, 0.4),
                    "current_liabilities": np.nan if financial else total_assets * rng.uniform(0.15, 0.35),
                    "equity": equity,
                    "tangible_book": equity * rng.uniform(0.6, 0.95),
                    "total_debt": total_debt,
                    "long_term_debt": total_debt * 0.8 if pd.notna(total_debt) else np.nan,
                    "cash": cash, "shares": shares * (1 + rng.normal(0, 0.01)) ** k,
                    "fcf": ocf + capex, "ocf": ocf, "capex": capex,
                    "dividends_paid": -mcap * company_dy,
                    "buybacks": -mcap * rng.choice([0.0, rng.uniform(0.01, 0.05)]),
                }
            annual = pd.DataFrame.from_dict(rows, orient="index")

            companies[ticker] = CompanyData(
                ticker=ticker, name=name, sector=key,
                prices=prices, dividends=dividends, annual=annual,
                current_shares=shares,
                forward_pe=pe * rng.uniform(0.75, 1.05),
            )
    return companies, failures
