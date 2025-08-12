"""
Travel Chatbot Data Models - Simplified Version

Simple request/response models for the chat system.
"""

from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime


# ===========================================
# REQUEST MODEL
# ===========================================

class ChatRequest(BaseModel):
    """User chat message request."""
    message: str = Field(..., description="User's message")
    
    class Config:
        json_schema_extra = {
            "example": {
                "message": "I want hotels in Paris"
            }
        }


# ===========================================
# RESPONSE MODELS
# ===========================================

class HotelInfo(BaseModel):
    """Simple hotel information."""
    name: str
    price: Optional[str] = None
    rating: Optional[str] = None
    location: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "Hotel Paris Central",
                "price": "€150/night",
                "rating": "4⭐",
                "location": "Central Paris"
            }
        }


class DestinationInfo(BaseModel):
    """Simple destination information."""
    name: str
    country: Optional[str] = None
    highlights: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "Barcelona",
                "country": "Spain",
                "highlights": "Sagrada Familia, Park Güell, Gothic Quarter"
            }
        }


class ChatResponse(BaseModel):
    """Chatbot response."""
    response: str = Field(..., description="Chatbot's text response")
    hotels: Optional[List[HotelInfo]] = None
    destinations: Optional[List[DestinationInfo]] = None
    timestamp: datetime = Field(default_factory=datetime.now)
    
    class Config:
        json_schema_extra = {
            "example": {
                "response": "🏨 Here are great hotels in Paris under €200:\n\n1. Hotel Paris Central - €150/night - 4⭐",
                "hotels": [
                    {
                        "name": "Hotel Paris Central",
                        "price": "€150/night",
                        "rating": "4*",
                        "location": "Central Paris"
                    }
                ],
                "destinations": None,
                "timestamp": "2024-08-10T10:30:00"
            }
        }


# ===========================================
# UTILITY MODEL
# ===========================================

class HealthCheck(BaseModel):
    """Health check response."""
    status: str = "healthy"
    timestamp: datetime = Field(default_factory=datetime.now)