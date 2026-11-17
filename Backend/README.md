# ARRT User Data Extractor

## Quick Start
```bash
# Clone the repo (if not already)
cd ~/Desktop/user-data-extractor

# Set up Python environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create .env from the template and fill in your ARRT credentials (see below)
cp .env.example .env
nano .env   # add ARRT_COOKIE, ARRT_ANTIFORGERY_TOKEN, ARRT_CAPTCHA_TOKEN, etc.

# Run the server
python run.py
```
The API will be available at `http://127.0.0.1:8000`.

## Running the Server
- **Development**: `uvicorn app.main:app --reload`
- **Production** (example): `uvicorn app.main:app --host 0.0.0.0 --port 8000`

## API Endpoints (FastAPI)
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/users/export-csv` | Trigger ARRT extraction and generate a CSV file. |
| `POST` | `/api/users/bulk-insert` | Upload a CSV produced by the extractor and store rows in the database. |
| `GET`  | `/api/users/all` | Fetch users with pagination (`skip`, `limit`) and optional case‑insensitive name search (`search`). |

The **search** query parameter now correctly supports `null`/empty values and uses `ILIKE` for case‑insensitive matching.

## Environment Variables (`.env`)
```ini
ARRT_API_URL=https://www.arrt.org/VerifyCredentials/SearchByName
ARRT_COOKIE=your_session_cookie
ARRT_ANTIFORGERY_TOKEN=your_token
ARRT_CAPTCHA_TOKEN=your_captcha_success_code
MAX_CONCURRENCY=1   # keep low to avoid overloading the external server
REQUEST_TIMEOUT=60
MAX_RETRIES=3
BACKOFF_FACTOR=1.5
EXPORTS_DIR=exports
POSTGRES_URL=postgresql+asyncpg://[USER]:[PASSWORD]@localhost:[PORT]/[DB_NAME]
```
> **Note**: CAPTCHA tokens expire after once used. For large extractions you will need to refresh the token manually; the app will stop with a clear error message if the token is invalid.

## CORS & UI Integration
CORS middleware is enabled with `allow_origins=["*"]` for development. Adjust the list in `app/main.py` before deploying to production.

## Captcha & Rate‑Limit Handling
- The external ARRT service requires a valid reCAPTCHA token for each request batch.
- If the token expires, the server returns a **403** with a helpful message; the UI should prompt the user to solve the CAPTCHA again.
- The extractor respects a **max concurrency** of 1 by default to avoid hitting the server's rate limits.

## Development Notes
- Tests are located in `tests/`. Run them with `pytest`.
- The project uses **Python 3.11+** (tested on 3.14).
- Database models are defined in `app/models/`. Migration scripts are not required; tables are auto‑created on startup.
- For detailed architecture, see the original sections below (kept unchanged for reference).

---

## 1. Project Objective

The external ARRT directory search endpoint (`/VerifyCredentials/SearchByName`) requires two search parameters:
- `firstName`
- `lastName`

Querying with open wildcards (`firstName=%%` and `lastName=%%`) crashes the external server because the result set exceeds memory and connection limits.

This backend application solves that problem by:
1. **Partitioning the Search Space**: Generating targeted alphabetical first‑name prefix queries (e.g., `Aa%` through `Az%` paired with `lastName=%%`).
2. **Controlled Asynchronous Requests**: Dispatching HTTP POST requests using `httpx.AsyncClient` with concurrency bounds (default concurrency = 1) to protect the external server.
3. **Resilient Error Containment**: Catching transient connection issues and retrying with exponential backoff while fast‑failing on invalid CAPTCHA or server overload (HTTP 429/503).
4. **Automated Deduplication**: Removing duplicate user records using unique external IDs (`id`, `userId`, `arrtId`, etc.) or composite content hashes.
5. **Excel‑Compatible CSV Export**: Saving records into UTF‑8 BOM‑encoded CSV files with dynamically discovered columns and consistent field ordering.

> **Important Scope Note:** The default 26 two‑letter patterns (`Aa%` .. `Az%`) only retrieve a subset of users whose first names begin with "A". It does **not** claim complete extraction of the ARRT database. The pattern generator is modular and configurable so it can easily be expanded to other prefixes (`B`..`Z`) and deeper combinations.

---

## 2. Project Architecture

The application is structured into decoupled, single‑responsibility layers:
```
┌────────────────────────────────────────────────────────┐
│                   FastAPI Router                       │
│             POST /api/users/export-csv                 │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│                   ExtractionService                    │
│   - Pattern coordination                               │
│   - Bounded concurrency (asyncio.Semaphore)            │
│   - Memory deduplication (external ID tracking)        │
└──────────────┬──────────────────────────┬──────────────┘
                │                          │
                ▼                          ▼
┌──────────────────────────────┐ ┌───────────────────────┐
│        ArrtApiService        │ │      CsvService       │
│ - httpx.AsyncClient          │ │ - Dynamic column map  │
│ - Exponential backoff retry  │ │ - asyncio.Lock safety │
│ - Token & Header injection   │ │ - UTF-8 BOM encoding  │
│ - Adaptive JSON/HTML parsing │ │ - Collision avoidance │
└──────────────────────────────┘ └───────────────────────┘
```
