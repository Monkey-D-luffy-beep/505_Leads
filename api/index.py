"""
Vercel serverless entry point for the FastAPI backend.
Vercel's Python runtime detects the ASGI `app` object automatically.
"""
import sys
import os

# Add backend directory to Python path so `app.*` imports resolve
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend'))

from app.main import app  # noqa: E402 — Vercel picks up this ASGI app
