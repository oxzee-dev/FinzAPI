# finz-api

Financial data REST API built with **FastAPI**, powered by **yfinance**.

---

## Architecture

```
Client (dashboard)
      │
      │  GET /ticker/AAPL,MSFT
      │  X-API-Key: <secret>
      ▼
FastAPI app  (api/main.py)
  ├── Auth              X-API-Key header — always enforced
  ├── CORS              ALLOWED_ORIGINS env var
  ├── Validation        max 15 tickers, regex [A-Z0-9.\-]{1,10}
  └── asyncio.gather()  all tickers fetched in parallel via thread pool
            │
            ▼
      yfinance (Yahoo Finance)
```

**Key design choices:**
- All tickers fetched **concurrently** — 15 tickers ≈ same latency as 1
- Single path-param pattern — no query strings
- One shared `_gather()` helper keeps every route to 2 lines

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `API_KEY` | ✅ | Secret sent in `X-API-Key` header |
| `ALLOWED_ORIGINS` | optional | Comma-separated CORS origins, defaults to `*` |

Generate a secure key:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## Endpoints

All protected routes require: `X-API-Key: YOUR_KEY`

URL pattern: `/{route}/{SYMBOL}` or `/{route}/{SYMBOL1},{SYMBOL2},...`

Single ticker returns an **object**, multiple tickers return an **array**.

---

### `GET /health`
No auth. Returns `{"status": "ok"}`.

---

### `GET /ticker/{symbols}`
Full market snapshot — price, valuation, ratios, margins, risk, dividends, news, price targets.
```bash
curl -H "X-API-Key: KEY" https://your-api/ticker/AAPL
curl -H "X-API-Key: KEY" https://your-api/ticker/AAPL,PLTR,NVDA
```

---

### `GET /earnings/{symbols}`
Earnings calendar dates and forward EPS estimates.
```bash
curl -H "X-API-Key: KEY" https://your-api/earnings/AAPL,MSFT
```
Returns: `earnings_dates`, `earnings_estimate`

---

### `GET /growth_estimate/{symbols}`
Analyst revenue and earnings growth estimates.
```bash
curl -H "X-API-Key: KEY" https://your-api/growth_estimate/AAPL,MSFT
```
Returns: `revenue_estimates`, `earnings_estimate`

---

### `GET /income_stmt/{symbols}`
Full income statement (annual).
```bash
curl -H "X-API-Key: KEY" https://your-api/income_stmt/AAPL,MSFT
```
Returns: `income_stmt`

---

### `GET /balance_sheet/{symbols}`
Full balance sheet (annual).
```bash
curl -H "X-API-Key: KEY" https://your-api/balance_sheet/AAPL,MSFT
```
Returns: `balance_sheet`

---

### `GET /inside_tx/{symbols}`
Insider buy/sell transactions.
```bash
curl -H "X-API-Key: KEY" https://your-api/inside_tx/AAPL,MSFT
```
Returns: `insider_transactions`

---

### `GET /sec_filings/{symbols}`
SEC filings list (type, date, URL).
```bash
curl -H "X-API-Key: KEY" https://your-api/sec_filings/AAPL,MSFT
```
Returns: `sec_filings`

---

## Local Development

```bash
pip install fastapi uvicorn yfinance mangum pandas

export API_KEY=your_secret_key

uvicorn api.main:app --reload --port 8000
```

Swagger UI → `http://localhost:8000/docs`

---

## Route Summary

| Route | Tag | yfinance source |
|---|---|---|
| `/ticker/{s}` | Ticker | `ticker.info` + `ticker.news` |
| `/earnings/{s}` | Fundamentals | `earnings_dates`, `earnings_estimate` |
| `/growth_estimate/{s}` | Fundamentals | `get_revenue_estimates()`, `get_earnings_estimate()` |
| `/income_stmt/{s}` | Financial Statements | `get_income_stmt()` |
| `/balance_sheet/{s}` | Financial Statements | `get_balance_sheet()` |
| `/inside_tx/{s}` | Ownership | `get_insider_transactions()` |
| `/sec_filings/{s}` | Ownership | `sec_filings` |
