# 505 Leads

AI-powered lead generation and campaign management tool.

## Architecture

- **Backend**: FastAPI (Python) — hosted on Oracle Cloud VM
- **Frontend**: React + Tailwind CSS — deployed on Vercel
- **Database**: Supabase (PostgreSQL)
- **Queue**: Celery + Upstash Redis
- **Email**: Brevo (Sendinblue) SMTP
- **Email Discovery**: Hunter.io API

## Project Structure

```
505-leads/
├── backend/          # FastAPI + Celery workers
├── frontend/         # React + Tailwind (Vite)
└── supabase/         # Database migrations
```

## Getting Started

### Backend

```bash
cd backend
cp .env.example .env
# Fill in your .env values

# With Docker
docker-compose up

# Without Docker
pip install -r requirements.txt
playwright install chromium
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Database

Run the SQL in `supabase/migrations/001_initial_schema.sql` in your Supabase SQL editor.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/api/v1/leads` | List leads |
| POST | `/api/v1/leads` | Create lead |
| GET | `/api/v1/campaigns` | List campaigns |
| POST | `/api/v1/campaigns` | Create campaign |
| GET | `/api/v1/sequences/campaign/:id` | List campaign sequences |
| GET | `/api/v1/emails` | List email queue |
| POST | `/api/v1/emails/:id/approve` | Approve queued email |
| GET | `/api/v1/analytics/overview` | Overview stats |
| GET | `/api/v1/settings/signal-definitions` | Signal definitions |

## Environment Variables

See `backend/.env.example` for all required variables.
