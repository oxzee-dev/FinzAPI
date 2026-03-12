# finz-api

Financial data REST API built with **FastAPI**, deployed on serverless, powered by **yfinance**.

---

## Architecture

```
Client (dashboard)
      │
      │  GET /ticker/AAPL,MSFT
      │  X-API-Key: <secret>
      ▼
  ├── api/index.py        ← Mangum (ASGI → Lambda bridge)
  └── api/main.py         ← FastAPI app
        ├── Auth middleware     (X-API-Key header)
        ├── CORS middleware     (ALLOWED_ORIGINS env var)
        ├── Input validation    (max 15 tickers, regex check)
        └── asyncio.gather()   ← parallel yfinance calls
                │
                ▼
          yfinance (Yahoo Finance)
```

**Key design choices:**
- All tickers fetched **concurrently** via `asyncio.gather()` + thread pool — 15 tickers ≈ same latency as 1
- Auth is **always enforced** — no dev bypass, 401 if key missing or wrong
- Single path-param pattern for both single and multi-ticker calls

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `API_KEY` | ✅ | Secret key clients must send in `X-API-Key` header |
| `ALLOWED_ORIGINS` | optional | Comma-separated CORS origins. Defaults to `*` |

Generate a secure key:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## Endpoints

### `GET /health`
No auth required. Returns `{"status": "ok"}`.

---

### `GET /ticker/{symbols}`
Market data — price, valuation, ratios, dividends, news, price targets.

```bash
# Single
curl -H "X-API-Key: YOUR_KEY" https://finz-api.vercel.app/ticker/AAPL

# Multiple (up to 15)
curl -H "X-API-Key: YOUR_KEY" https://finz-api.vercel.app/ticker/AAPL,MSFT,NVDA
```

Returns a single object for 1 ticker, array for multiple.

---

### `GET /fin_statement/{symbols}`
Annual + quarterly **income statement**, **balance sheet**, **cash flow**.

```bash
# Single
curl -H "X-API-Key: YOUR_KEY" https://finz-api.vercel.app/fin_statement/AAPL

# Multiple
curl -H "X-API-Key: YOUR_KEY" https://finz-api.vercel.app/fin_statement/AAPL,MSFT
```

---

## Response structure — `/ticker`

```json
{
  "ticker": "AAPL",
  "main_info":        { "currentPrice", "marketCap", "PE", "recommendation", ... },
  "valuation":        { "enterpriseValue", "priceToBook", ... },
  "ratios":           { "trailingPE", "profitMargins", "debtToEquity", ... },
  "returns":          { "returnOnEquity", "grossMargins", ... },
  "growth":           { "revenueGrowth", "earningsGrowth", ... },
  "price_performance":{ "fiftyTwoWeekHigh", "fiftyDayAverage", ... },
  "risk":             { "beta", "overallRisk", ... },
  "debt":             { "totalDebt", "freeCashflow", ... },
  "trading_info":     { "volume", "change_from_50DMA", ... },
  "price_targets":    { "targetMeanPrice", "recommendationKey", ... },
  "dividends":        { "dividendYield", "payoutRatio", ... },
  "earnings":         { "trailingEps", "forwardEps", ... },
  "recent_news":      [ { "title", "summary", "pubDate", "source_url" } ]
}
```

---

## Local Development

```bash
pip install fastapi uvicorn yfinance mangum pandas

# Set your key locally
export API_KEY=your_secret_key

uvicorn api.main:app --reload --port 8000

# Swagger UI
open http://localhost:8000/docs
```

---


> ⚠️ Always redeploy after adding/changing env vars
