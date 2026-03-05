import asyncio
import os
import re
from functools import lru_cache

import yfinance as yf
from fastapi import FastAPI, HTTPException, Security, Depends
from fastapi.security.api_key import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# ─────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────
MAX_TICKERS = 15
TICKER_REGEX = re.compile(r"^[A-Z0-9.\-]{1,10}$")
API_KEY_ENV = os.environ.get("API_KEY", "")
ALLOWED_ORIGINS = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",")]

# Warn loudly at startup if no key is set
if not API_KEY_ENV:
    import warnings
    warnings.warn(
        "API_KEY env variable is not set — API is running with NO authentication.",
        stacklevel=2,
    )

# ─────────────────────────────────────────────────────────────
# App + CORS
# ─────────────────────────────────────────────────────────────
app = FastAPI(
    title="Market Dashboard API",
    description="Financial data API — ticker info & financial statements",
    version="2.0.0",
    docs_url="/docs",       # Swagger UI at /docs
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["X-API-Key", "Content-Type"],
)

# ─────────────────────────────────────────────────────────────
# API Key auth
# ─────────────────────────────────────────────────────────────
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_api_key(api_key: str = Security(api_key_header)):
    """Dependency: validate API key. Always enforced."""
    if not api_key or api_key != API_KEY_ENV:
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")


# ─────────────────────────────────────────────────────────────
# Input validation
# ─────────────────────────────────────────────────────────────
def parse_and_validate_tickers(ticker_param: str) -> list[str]:
    tickers = [t.strip().upper() for t in ticker_param.split(",") if t.strip()]
    if not tickers:
        raise HTTPException(status_code=400, detail="No ticker symbols provided.")
    if len(tickers) > MAX_TICKERS:
        raise HTTPException(
            status_code=400,
            detail=f"Too many tickers. Maximum allowed is {MAX_TICKERS}, got {len(tickers)}."
        )
    for t in tickers:
        if not TICKER_REGEX.match(t):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid ticker symbol: '{t}'. Only A-Z, 0-9, '.', '-' are allowed (max 10 chars)."
            )
    return tickers


# ─────────────────────────────────────────────────────────────
# Formatting utils
# ─────────────────────────────────────────────────────────────
def fmt(value, decimals=2):
    if value is None: return None
    try: return round(float(value), decimals)
    except (ValueError, TypeError): return None

def fmt_B(value):  # billions
    if value is None: return None
    try: return f"{round(float(value) / 1_000_000_000, 2)} B$"
    except (ValueError, TypeError): return None

def fmt_M(value):  # millions
    if value is None: return None
    try: return f"{round(float(value) / 1_000_000, 2)} M$"
    except (ValueError, TypeError): return None

def fmt_pct(value):
    if value is None: return None
    try: return f"{round(float(value) * 100, 2)} %"
    except (ValueError, TypeError): return None

def calc_change(current, previous):
    if current is None or previous is None: return None
    try:
        c, p = float(current), float(previous)
        return round(((c - p) / p) * 100, 2) if p != 0 else None
    except (ValueError, TypeError): return None


# ─────────────────────────────────────────────────────────────
# Core data builders  (run in thread pool — yfinance is sync)
# ─────────────────────────────────────────────────────────────
def _build_ticker_data(symbol: str) -> dict:
    ticker = yf.Ticker(symbol)
    info = ticker.info

    recent_news = []
    for item in (ticker.news or [])[:11]:
        content = item.get("content", {})
        click_url = content.get("clickThroughUrl") or {}
        recent_news.append({
            "title": content.get("title"),
            "summary": content.get("summary") or content.get("description") or "",
            "pubDate": content.get("pubDate"),
            "provider": content.get("provider", {}).get("displayName"),
            "source_url": click_url.get("url"),
        })

    cur = info.get("currentPrice") or info.get("regularMarketPrice")
    prev = info.get("previousClose") or info.get("regularMarketPreviousClose")
    one_day_chg = calc_change(cur, prev)
    wk52_chg = fmt_pct(info.get("52WeekChange"))

    return {
        "ticker": symbol,
        "shortName": info.get("shortName"),
        "timestamp": info.get("regularMarketTime"),
        "main_info": {
            "symbol": info.get("symbol"),
            "shortName": info.get("shortName"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "currency": info.get("currency"),
            "currentPrice": fmt(cur),
            "oneDayChange": f"{one_day_chg} %" if one_day_chg is not None else None,
            "fiftyTwoWeekChange": wk52_chg,
            "marketCap": fmt_B(info.get("marketCap")),
            "PS": fmt(info.get("priceToSalesTrailing12Months")),
            "PE": fmt(info.get("trailingPE")),
            "forwardPE": fmt(info.get("forwardPE")),
            "recommendation": info.get("recommendationKey"),
            "PT_Low": fmt(info.get("targetLowPrice")),
            "PT_High": fmt(info.get("targetHighPrice")),
        },
        "company_info": {
            "website": info.get("website"),
            "address1": info.get("address1"),
            "city": info.get("city"),
            "state": info.get("state"),
            "zip": info.get("zip"),
            "country": info.get("country"),
            "phone": info.get("phone"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "fullTimeEmployees": info.get("fullTimeEmployees"),
            "longBusinessSummary": info.get("longBusinessSummary"),
        },
        "valuation": {
            "marketCap": fmt_B(info.get("marketCap")),
            "enterpriseValue": fmt_B(info.get("enterpriseValue")),
            "priceToBook": fmt(info.get("priceToBook")),
            "priceToSalesTrailing12Months": fmt(info.get("priceToSalesTrailing12Months")),
            "enterpriseToRevenue": fmt(info.get("enterpriseToRevenue")),
            "enterpriseToEbitda": fmt(info.get("enterpriseToEbitda")),
            "bookValue": fmt(info.get("bookValue")),
            "sharesOutstanding": fmt_M(info.get("sharesOutstanding")),
            "floatShares": fmt_M(info.get("floatShares")),
        },
        "ratios": {
            "trailingPE": fmt(info.get("trailingPE")),
            "forwardPE": fmt(info.get("forwardPE")),
            "pegRatio": fmt(info.get("pegRatio")),
            "priceToBook": fmt(info.get("priceToBook")),
            "profitMargins": fmt_pct(info.get("profitMargins")),
            "operatingMargins": fmt_pct(info.get("operatingMargins")),
            "returnOnAssets": fmt_pct(info.get("returnOnAssets")),
            "returnOnEquity": fmt_pct(info.get("returnOnEquity")),
            "currentRatio": fmt(info.get("currentRatio")),
            "quickRatio": fmt(info.get("quickRatio")),
            "debtToEquity": fmt(info.get("debtToEquity")),
        },
        "returns": {
            "returnOnAssets": fmt_pct(info.get("returnOnAssets")),
            "returnOnEquity": fmt_pct(info.get("returnOnEquity")),
            "profitMargins": fmt_pct(info.get("profitMargins")),
            "operatingMargins": fmt_pct(info.get("operatingMargins")),
            "grossMargins": fmt_pct(info.get("grossMargins")),
            "ebitdaMargins": fmt_pct(info.get("ebitdaMargins")),
        },
        "growth": {
            "revenueGrowth": fmt_pct(info.get("revenueGrowth")),
            "earningsGrowth": fmt_pct(info.get("earningsGrowth")),
            "earningsQuarterlyGrowth": fmt_pct(info.get("earningsQuarterlyGrowth")),
            "revenuePerShare": fmt(info.get("revenuePerShare")),
            "totalRevenue": fmt_B(info.get("totalRevenue")),
            "earningsPerShare": fmt(info.get("trailingEps")),
            "forwardEps": fmt(info.get("forwardEps")),
            "pegRatio": fmt(info.get("pegRatio")),
        },
        "price_performance": {
            "currentPrice": fmt(cur),
            "previousClose": fmt(prev),
            "open": fmt(info.get("open")),
            "dayLow": fmt(info.get("dayLow")),
            "dayHigh": fmt(info.get("dayHigh")),
            "fiftyTwoWeekLow": fmt(info.get("fiftyTwoWeekLow")),
            "fiftyTwoWeekHigh": fmt(info.get("fiftyTwoWeekHigh")),
            "fiftyDayAverage": fmt(info.get("fiftyDayAverage")),
            "twoHundredDayAverage": fmt(info.get("twoHundredDayAverage")),
            "52WeekChange": wk52_chg,
            "SandP52WeekChange": fmt_pct(info.get("SandP52WeekChange")),
        },
        "risk": {
            "beta": fmt(info.get("beta")),
            "overallRisk": info.get("overallRisk"),
            "auditRisk": info.get("auditRisk"),
            "boardRisk": info.get("boardRisk"),
            "compensationRisk": info.get("compensationRisk"),
            "shareHolderRightsRisk": info.get("shareHolderRightsRisk"),
        },
        "debt": {
            "totalDebt": fmt_B(info.get("totalDebt")),
            "totalCash": fmt_B(info.get("totalCash")),
            "totalCashPerShare": fmt(info.get("totalCashPerShare")),
            "debtToEquity": fmt(info.get("debtToEquity")),
            "currentRatio": fmt(info.get("currentRatio")),
            "quickRatio": fmt(info.get("quickRatio")),
            "freeCashflow": fmt_B(info.get("freeCashflow")),
            "operatingCashflow": fmt_B(info.get("operatingCashflow")),
        },
        "trading_info": {
            "volume": info.get("volume"),
            "averageVolume": info.get("averageVolume"),
            "averageVolume10days": info.get("averageVolume10days"),
            "bid": fmt(info.get("bid")),
            "ask": fmt(info.get("ask")),
            "fiftyDayAverage": fmt(info.get("fiftyDayAverage")),
            "twoHundredDayAverage": fmt(info.get("twoHundredDayAverage")),
            "change_from_50DMA": f"{calc_change(cur, info.get('fiftyDayAverage'))}%" if calc_change(cur, info.get("fiftyDayAverage")) else None,
            "change_from_200DMA": f"{calc_change(cur, info.get('twoHundredDayAverage'))}%" if calc_change(cur, info.get("twoHundredDayAverage")) else None,
            "oneDayChange": f"{one_day_chg}%" if one_day_chg is not None else None,
        },
        "price_targets": {
            "targetHighPrice": fmt(info.get("targetHighPrice")),
            "targetLowPrice": fmt(info.get("targetLowPrice")),
            "targetMeanPrice": fmt(info.get("targetMeanPrice")),
            "targetMedianPrice": fmt(info.get("targetMedianPrice")),
            "recommendationMean": fmt(info.get("recommendationMean")),
            "recommendationKey": info.get("recommendationKey"),
            "numberOfAnalystOpinions": info.get("numberOfAnalystOpinions"),
        },
        "dividends": {
            "dividendRate": fmt(info.get("dividendRate")),
            "dividendYield": fmt_pct(info.get("dividendYield")),
            "exDividendDate": info.get("exDividendDate"),
            "payoutRatio": fmt_pct(info.get("payoutRatio")),
            "fiveYearAvgDividendYield": fmt_pct(info.get("fiveYearAvgDividendYield")),
            "trailingAnnualDividendRate": fmt(info.get("trailingAnnualDividendRate")),
            "trailingAnnualDividendYield": fmt_pct(info.get("trailingAnnualDividendYield")),
        },
        "earnings": {
            "trailingEps": fmt(info.get("trailingEps")),
            "forwardEps": fmt(info.get("forwardEps")),
            "mostRecentQuarter": info.get("mostRecentQuarter"),
            "netIncomeToCommon": fmt_B(info.get("netIncomeToCommon")),
            "trailingPegRatio": fmt(info.get("trailingPegRatio")),
        },
        "recent_news": recent_news,
    }


def _build_fin_statement(symbol: str) -> dict:
    """
    Returns income statement, balance sheet, and cash flow —
    both annual (last 4Y) and quarterly (last 4Q).
    """
    ticker = yf.Ticker(symbol)

    def df_to_dict(df):
        """Convert a yfinance DataFrame to a JSON-serialisable dict."""
        if df is None or df.empty:
            return {}
        # Columns are dates — convert to ISO strings
        df.columns = [str(c)[:10] for c in df.columns]
        # Replace NaN / inf with None
        df = df.where(df.notna(), other=None)
        return df.to_dict()

    return {
        "ticker": symbol,
        "income_statement": {
            "annual":    df_to_dict(ticker.financials),
            "quarterly": df_to_dict(ticker.quarterly_financials),
        },
        "balance_sheet": {
            "annual":    df_to_dict(ticker.balance_sheet),
            "quarterly": df_to_dict(ticker.quarterly_balance_sheet),
        },
        "cash_flow": {
            "annual":    df_to_dict(ticker.cashflow),
            "quarterly": df_to_dict(ticker.quarterly_cashflow),
        },
    }


# ─────────────────────────────────────────────────────────────
# Async wrappers  (offload sync yfinance calls to thread pool)
# ─────────────────────────────────────────────────────────────
async def fetch_ticker(symbol: str) -> dict:
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(None, _build_ticker_data, symbol)
    except Exception as e:
        return {"ticker": symbol, "error": str(e)}


async def fetch_fin_statement(symbol: str) -> dict:
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(None, _build_fin_statement, symbol)
    except Exception as e:
        return {"ticker": symbol, "error": str(e)}


# ─────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────

@app.get("/health", tags=["Utils"])
async def health():
    return {"status": "ok"}


@app.get(
    "/ticker/{symbols}",
    tags=["Ticker"],
    summary="Market data — single or multiple tickers",
    description=(
        "Comma-separated ticker symbols in the path, up to 15.\n\n"
        "**Single:** `/ticker/AAPL`\n\n"
        "**Multiple:** `/ticker/AAPL,MSFT,NVDA`"
    ),
)
async def get_tickers(
    symbols: str,
    _: None = Depends(verify_api_key),
):
    tickers = parse_and_validate_tickers(symbols)
    results = await asyncio.gather(*[fetch_ticker(s) for s in tickers])
    return results[0] if len(results) == 1 else list(results)


@app.get(
    "/fin_statement/{symbols}",
    tags=["Financial Statements"],
    summary="Financial statements — single or multiple tickers",
    description=(
        "Returns annual & quarterly **income statement**, **balance sheet**, "
        "and **cash flow**.\n\n"
        "Comma-separated ticker symbols in the path, up to 15.\n\n"
        "**Single:** `/fin_statement/AAPL`\n\n"
        "**Multiple:** `/fin_statement/AAPL,MSFT`"
    ),
)
async def get_fin_statements(
    symbols: str,
    _: None = Depends(verify_api_key),
):
    tickers = parse_and_validate_tickers(symbols)
    results = await asyncio.gather(*[fetch_fin_statement(s) for s in tickers])
    return results[0] if len(results) == 1 else list(results)
