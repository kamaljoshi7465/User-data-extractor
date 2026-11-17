# ARRT User Data Extractor

A full-stack application to extract user records from the ARRT credential verification directory, export them into CSV files, store them in PostgreSQL, and display them through a React frontend.

## Tech Stack

| Component | Technology |
|---|---|
| Frontend | React.js, Vite |
| Backend | Python, FastAPI |
| Database | PostgreSQL |
| HTTP Client | HTTPX |
| ORM | SQLAlchemy |

## Features

**Backend**
- Asynchronous ARRT API integration.
- Alphabetical search pattern generation.
- CAPTCHA and session handling.
- CSV export with duplicate detection.
- Bulk CSV import into PostgreSQL.
- Paginated API with case-insensitive name search.

**Frontend**
- User records displayed in a table.
- Search by name.
- Previous/Next pagination.
- Configurable page size.
- Loading and error handling.

## Project Structure

```text
user-data-extractor/
├── Backend/
│   ├── app/
│   │   ├── routes/
│   │   ├── services/
│   │   ├── models/
│   │   ├── schemas/
│   │   └── utils/
│   ├── exports/
│   ├── tests/
│   ├── .env.example
│   ├── requirements.txt
│   └── run.py
│
├── UI/
│   ├── src/
│   ├── public/
│   ├── package.json
│   └── vite.config.js
│
├── .gitignore
└── README.md
```

## Installation & Setup

### 1. Clone Repository

```bash
git clone https://github.com/kamaljoshi7465/User-data-extractor.git
cd user-data-extractor
```

### 2. Backend Setup

```bash
cd Backend

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
```

Configure ARRT session details and PostgreSQL connection in `.env`.

### 3. Frontend Setup

```bash
cd UI
npm install
```

Create `.env`:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

## Environment Variables

Backend `.env`:

```env
ARRT_API_URL=https://www.arrt.org/VerifyCredentials/SearchByName

ARRT_COOKIE=your_session_cookie
ARRT_ANTIFORGERY_TOKEN=your_token
ARRT_CAPTCHA_TOKEN=your_captcha_token

MAX_CONCURRENCY=1
REQUEST_TIMEOUT=60
MAX_RETRIES=3
BACKOFF_FACTOR=1.5

EXPORTS_DIR=exports

POSTGRES_URL=postgresql+asyncpg://arrt_admin:YOUR_PASSWORD@localhost:5432/arrt_users
```

**Note:** CAPTCHA tokens may expire or be single-use. Refresh them through the legitimate browser flow when required.

## Database Setup

Install PostgreSQL:

```bash
sudo apt update
sudo apt install postgresql postgresql-contrib -y
```

Create database and user:

```bash
sudo -u postgres psql
```

```sql
CREATE DATABASE arrt_users;
CREATE USER arrt_admin WITH PASSWORD 'YOUR_PASSWORD';

GRANT ALL PRIVILEGES ON DATABASE arrt_users TO arrt_admin;

\c arrt_users

GRANT ALL ON SCHEMA public TO arrt_admin;
ALTER SCHEMA public OWNER TO arrt_admin;

\q
```

Database tables are created automatically by the application according to its SQLAlchemy models.

## Running the Application

**Terminal 1 – Backend**

```bash
cd Backend
source venv/bin/activate
python run.py
```

Backend: http://127.0.0.1:8000


**Terminal 2 – Frontend**

```bash
cd UI
npm run dev
```

Frontend: http://localhost:5173

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/users/export-csv` | Extract ARRT users and generate CSV |
| POST | `/api/users/bulk-insert` | Import CSV records into PostgreSQL |
| GET | `/api/users/all` | Fetch paginated users with optional name search |

Example:

```http
GET /api/users/all?skip=0&limit=20&search=Amaris
```

## Application Workflow

```text
ARRT API
   ↓
Alphabetical Search Patterns
   ↓
Data Extraction & Deduplication
   ↓
CSV Export
   ↓
Bulk CSV Import
   ↓
PostgreSQL Database
   ↓
FastAPI REST APIs
   ↓
React Frontend
```

## Testing

Run backend tests:

```bash
cd Backend
source venv/bin/activate
pytest -v
```

Build frontend:

```bash
cd UI
npm run build
```

## Important Notes

- Default extraction patterns (`Aa%` to `Az%`) cover only a subset of ARRT records, not the complete directory.
- CAPTCHA and session credentials must remain valid.
- Keep database credentials, cookies, CAPTCHA tokens, and sensitive record tokens out of Git.
- Configure restricted CORS origins and proper access controls before production deployment.

## Future Improvements

- Expand alphabetical search coverage.
- Add extraction progress tracking and resume support.
- Implement advanced filters and sorting.
- Add authentication and authorization.
- Deploy backend and database to AWS or another cloud provider.

---

**Project:** ARRT User Data Extractor  
**Backend:** FastAPI | **Frontend:** React | **Database:** PostgreSQL
