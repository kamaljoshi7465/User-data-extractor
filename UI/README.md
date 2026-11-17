# UI (React + Vite)

## Overview
A lightweight React front‑end built with Vite that consumes the FastAPI backend to display ARRT user records.

## Quick Start
```bash
# From the project root
cd UI

# Install dependencies (npm or yarn)
npm install   # or `yarn`

# Run the development server
npm run dev   # Vite will start at http://localhost:5173
```

The UI expects the backend API to be reachable at `http://127.0.0.1:8000`. If your backend runs on a different host or port, update the `API_BASE_URL` constant in `.env`.

## Features
- **User List Table** showing Name, City, State, Credential String.
- **Pagination** (Prev/Next) with configurable page size (default 20).
- **Search** box that filters by first/last name (case‑insensitive) via the backend `search` query param.
- **Loading spinner** and error handling.
- **Responsive layout** suitable for desktop and mobile.

## Project Structure
```
UI/
├─ public/               # static assets (favicon, etc.)
├─ src/                  # React source
│   ├─ App.jsx           # main component – fetches data, renders table
│   ├─ App.css           # styling for the table and controls
│   └─ index.jsx        # entry point
├─ vite.config.js        # Vite configuration (React plugin enabled)
├─ package.json          # scripts, dependencies
└─ README.md            # (this file)
```

## Development Tips
- **Hot Module Replacement** works out of the box – any change to `src/*` triggers a browser refresh.
- To adjust the number of rows per page, edit the `PAGE_SIZE` constant in `src/App.jsx`.
- The UI uses the native `fetch` API; no additional HTTP client libraries are required.
- CORS is already enabled on the backend (`allow_origins=["*"]`). In production you should restrict this to the UI origin.

## Build for Production
```bash
npm run build   # creates `dist/` with optimized assets
```

