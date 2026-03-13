from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.auth import get_current_user
from app.routers import leads, campaigns, sequences, emails, analytics, settings as settings_router, signals, contacts, queue, webhooks, replies

app = FastAPI(title="505 Leads API")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "https://*.vercel.app"],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(leads.router, prefix="/api/v1")
app.include_router(campaigns.router, prefix="/api/v1")
app.include_router(sequences.router, prefix="/api/v1")
app.include_router(emails.router, prefix="/api/v1")
app.include_router(analytics.router, prefix="/api/v1")
app.include_router(settings_router.router, prefix="/api/v1")
app.include_router(signals.router, prefix="/api/v1")
app.include_router(contacts.router, prefix="/api/v1")
app.include_router(queue.router, prefix="/api/v1")
app.include_router(webhooks.router, prefix="/api/v1")
app.include_router(replies.router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/api/v1/auth/me")
async def auth_me(user: dict = Depends(get_current_user)):
    return {"id": user["sub"], "email": user.get("email"), "user_metadata": user.get("user_metadata", {})}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
