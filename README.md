# CURRENT_HISTORICAL_STOCKS  
Production-Style Full Stack Stock Analytics App

A real-world full stack web application for portfolio tracking, stock analytics, billing, quotas, caching, and automated market data updates.

Built to demonstrate production architecture without unnecessary complexity.

---

## Tech Stack

**Backend**
- FastAPI (Python)
- PostgreSQL
- JWT Authentication
- Google OAuth
- Stripe Billing
- OpenAI API (newsletter generation)

**Frontend**
- React
- Vite
- Bootstrap styling

**Infrastructure**
- Docker Compose (backend + frontend + db)
- Designed for AWS EC2 deployment
- Nginx reverse proxy (production)
- Let’s Encrypt SSL (production)

---

## Core Features

### Portfolio Management
- Portfolio CRUD
- Buy / Sell transactions
- Cash + holdings valuation
- Performance tracking

### Market Benchmark Comparison
- Portfolio performance vs S&P 500
- Index normalized to 100 baseline
- CSV export for:
  - Transactions
  - Performance data

### Performance Optimization
- In-memory portfolio performance cache
- TTL-based expiration
- Version-based invalidation when transactions change

### Auth & Billing
- JWT authentication
- Google OAuth login
- Stripe subscription integration
- Dev billing bypass (for local testing)
- Free vs Pro usage limits
- Newsletter quota enforcement

### AI Newsletter
- OpenAI-powered newsletter generation
- Preview mode
- Send mode
- Usage window tracking to control API cost

### Automated Market Data
- SP500 historical table
- Daily update job script
- Designed to run via:
  - Docker exec locally
  - Systemd timer on EC2 (recommended production approach)

---

## Project Structure

/
  backend/
    app/
      main.py
      jobs/
      ...
  frontend/
    src/
    ...
  docker-compose.yml
  README.md
  .env.example
  .env.docker.example

---

## Requirements

- Docker Desktop (Windows / Mac) or Docker Engine (Linux)
- Git (recommended)
- OpenAI API key (for newsletter feature)
- Google OAuth credentials (for login)
- Stripe keys (for billing tests)

---

## Environment Setup

This project uses a local Docker environment file.

### 1. Create your Docker env file

From the project root:

cp .env.docker.example .env.docker

Then open `.env.docker` and fill in:

- OPENAI_API_KEY
- VITE_GOOGLE_CLIENT_ID
- GOOGLE_CLIENT_ID
- STRIPE_SECRET_KEY (optional for dev bypass)
- STRIPE_PRICE_ID
- STRIPE_WEBHOOK_SECRET

Do NOT commit `.env.docker`.

---

## Run Locally

From the project root:

### Build + start all services

docker compose up --build

Services:

- Frontend → http://localhost:5173
- Backend → http://localhost:8000

### Stop services

Press CTRL + C

Or in another terminal:

docker compose down

---

## Health Check

After running:

GET http://localhost:8000/health

---

## Run Backend Tests

docker compose exec backend pytest

---

## Manual Daily SP500 Update

If the job file exists at:

backend/app/jobs/update_sp500_daily.py

Run:

docker compose exec backend python -m app.jobs.update_sp500_daily --days-back 10

This pulls recent historical data and upserts into the database.

---

## Production Deployment Outline (AWS EC2)

Target architecture:

- EC2 instance
- Docker + Docker Compose
- Nginx reverse proxy
- Let’s Encrypt SSL
- Systemd timer for daily data update

Update workflow:

git pull  
docker compose up -d --build

---

## Security Notes

Do NOT commit:
- .env.docker
- API keys
- Secrets

Commit:
- .env.example
- .env.docker.example

---

## Design Philosophy

- Production realism over unnecessary complexity
- Clean Docker-based workflow
- Minimal but meaningful architecture
- Clear separation of backend / frontend / database
- Cost-controlled OpenAI usage

---

## Status

Fully working locally inside Docker:

- Portfolio CRUD
- Transactions
- Performance vs SP500
- CSV export
- Newsletter quota enforcement
- Stripe dev upgrade flow
- Google login
- Performance caching
- Database-backed usage windows
- Daily SP500 update script

Next phase:
- GitHub push
- EC2 deployment
- Nginx + SSL
- Automated daily update timer
