# UK relative-value screener

Python tool that screens UK-listed stocks (FTSE 350 operating companies) for
relative value using yfinance data, and writes a single-file HTML report.
The user is a data analyst with an economics background: explain methods in
those terms (cross-sections, panels, regressions, look-ahead bias).

## Commands

- Install: `pip install -r requirements.txt`
- Demo run (synthetic data, no downloads): `python screener.py --demo`
- Full run: `python screener.py` (about 1,000 Yahoo requests, 10-20 minutes)
- Subset: `python screener.py --sectors banks software_tech`
- Validate tickers: `python check_tickers.py`
- Run `python screener.py --demo` after any change to check nothing breaks.

## Files

- `config.py`: everything about *what* to compare. SETTINGS, METRICS
  definitions, SECTORS (tickers, valuation and quality weights, regression
  pairs, notes), REGIME and SECTOR_OUTLOOK. Code never hard-codes a ticker
  or metric choice. `validate_config()` runs at start-up.
- `screener.py`: yfinance fetching, GBP conversion, point-in-time metric
  calculation (`compute_metrics`), scoring (`score_sector`), orchestration.
- `report.py`: builds the HTML report (Plotly from CDN, data embedded as JSON).
- `demo_data.py`: synthetic CompanyData for `--demo`.
- `check_tickers.py`: checks every ticker returns prices and a matching name.

## Design decisions (keep these unless asked to change them)

- No persistent data between runs: every run fetches fresh data. The user
  chose this deliberately. Ask before adding any log or database.
- Point-in-time: annual accounts count as public only `reporting_lag_days`
  (120) after period end, for current and historical scores alike.
- Valuation multiples are scored as yields (1 / multiple) so higher always
  means cheaper and loss-makers rank as expensive.
- Scores are within-sector percentiles (0-100). Peer score: today's
  cheapness. Own-history score: today's spread versus sector median, ranked
  against the company's past quarterly spreads. Dividend score: trailing
  yield versus up to 15 years of its own history. Quality: sector
  percentiles of quality metrics. Composite: weighted, missing components
  dropped and weights renormalised.
- SECTOR_OUTLOOK scores (-2 to +2) are the user's judgemental view of the
  assumed macro regime. They are displayed only and do not feed any score.
- Prices for .L tickers are usually in pence (GBp): divide by 100. Financial
  statements may be in GBP, USD or EUR: convert at the period-end FX rate.
- Investment trusts and funds are excluded from the universe.

## Report conventions

- Dark theme only. Colours are CSS variables on :root in report.py.
- Output goes to `output/uk_value_screen_YYYY-MM-DD.html` next to the code
  (demo runs add `_demo`). Location is based on `__file__`, not the cwd.
- Sidebar toggle switches valuation display between multiples and yields;
  scores never change with it.
- Create all chart boxes before drawing any Plotly chart, so each is sized
  to its final grid cell.

## Known gaps

- The yfinance fetch layer was written without live access. Statement row
  labels in `STATEMENT_ROWS` (screener.py) may need adjusting against real
  data; a metric blank across a whole sector usually means a wrong label.
- yfinance serves only about four years of annual statements, which limits
  the own-history score and any backtest of it.

## Planned next steps

1. `backtest.py`: rebuild scores point-in-time at month-ends, measure
   forward returns relative to sector median (total return), report IC,
   quintile spreads, event study (score crossing 80) and Fama-MacBeth
   regressions with Newey-West errors. Note survivorship bias: the universe
   is today's FTSE 350.
2. Weight estimation: IC-information-ratio weights shrunk toward the current
   config weights, non-negative, walk-forward validation with a gap; compare
   against current and equal weights out of sample.
