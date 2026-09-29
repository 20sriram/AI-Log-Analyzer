# AI-Powered Log Anomaly Detection and Root-Cause Analysis System

A college mini-project that sends simulated application logs to a FastAPI backend, stores them in PostgreSQL, and displays logs and an experimental incident analysis on a React dashboard.

## Architecture

```text
Log generator -> FastAPI -> SQLAlchemy -> PostgreSQL
                                  |
React/Vite dashboard <- log and analysis API endpoints
```

The analysis endpoint passes stored logs through an Isolation Forest detector, a time-window event correlator, and a service-priority root-cause heuristic.

## Requirements

- Python and Node.js with npm
- PostgreSQL running locally
- A PostgreSQL database named `log_analyzer`

Create the database if it does not already exist:

```sql
CREATE DATABASE log_analyzer;
```

Create a root-level `.env` file with a SQLAlchemy PostgreSQL connection URL. Replace the placeholders with your local PostgreSQL username and password; URL-encode special characters in the password.

```dotenv
DATABASE_URL=postgresql://<username>:<password>@localhost:5432/log_analyzer
```

The `.env` file contains local credentials and should not be committed.

## Install

From the project root in PowerShell, create a virtual environment and install the backend dependencies:

```powershell
py -m venv venv
.\venv\Scripts\python.exe -m pip install fastapi uvicorn sqlalchemy psycopg2-binary python-dotenv requests scikit-learn
```

Install the frontend dependencies:

```powershell
cd frontend
npm install
cd ..
```

## Run

Start the backend from the project root so it can load `.env` and import the project modules:

```powershell
.\venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload
```

Start the dashboard in a second terminal:

```powershell
cd frontend
npm run dev
```

Open the Vite URL printed in the terminal, normally `http://localhost:5173`.

To generate the sample events, run this from the project root in a third terminal after the backend is available:

```powershell
.\venv\Scripts\python.exe log_generator\generator.py
```

The generator sends a finite sequence of normal and failure events. Each run appends records to PostgreSQL and appends text to `data/logs/application.log`; it does not clear prior data.

## API

FastAPI's interactive API documentation is available at `http://127.0.0.1:8000/docs` while the backend is running.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/` | Backend status message |
| `POST` | `/logs` | Store one log entry |
| `GET` | `/logs` | Return stored log entries |
| `GET` | `/logs/analyze` | Analyze stored logs and return anomalies, related events, a probable root cause, severity, confidence, and explanation |

Example `POST /logs` request body:

```json
{
  "timestamp": "2026-09-28 12:00:00",
  "service": "database",
  "level": "ERROR",
  "message": "Database connection failed"
}
```

## Current Limitations

- The generator uses a fixed sample sequence and does not retry failed requests.
- The detector uses a small set of numeric features derived from log level, message length, and service-name length. The correlation and root-cause ranking are heuristics, not causal analysis.
- Analysis currently considers the stored log history rather than a selected incident, and the confidence value is not a calibrated probability.
- The API currently returns all stored logs without pagination. The dashboard uses local API URLs and polls for updates.
- The repository does not currently define a Python dependency lock/requirements file or an automated test suite.

Treat the analysis as a demonstration, not as a production incident diagnosis.