"""
Travel Chatbot FastAPI Application

Simple FastAPI app that serves the travel chatbot API.
"""

from fastapi import FastAPI
import logging

# Import our router
from app.services.travel_chat.travel_chat_route import router as chat_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Create FastAPI app
app = FastAPI(
    title="Travel Chatbot API",
    description="AI-powered travel assistant for hotel and destination recommendations",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Include our chat router
app.include_router(chat_router)

# Root endpoint
@app.get("/")
async def root():
    """Welcome message for the API."""
    return {
        "message": "🤖 Travel Chatbot API",
        "status": "running",
        "docs": "/docs",
        "endpoints": {
            "chat": "/api/v1/chat",
            "health": "/api/v1/health"
        }
    }