"""
Travel Chatbot API Routes

Simple API endpoints for the travel chatbot functionality.
"""

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse
import logging
from datetime import datetime

# Import our schemas
from .travel_chat_schema import ChatRequest, ChatResponse, HealthCheck
# Import our service (we'll create this next)
from .travel_chat import TravelChatService

# Set up logging
logger = logging.getLogger(__name__)

# Create router instance
router = APIRouter(
    prefix="/api/v1",
    tags=["Travel Chat"],
    responses={
        404: {"description": "Not found"},
        500: {"description": "Internal server error"}
    }
)

# Initialize the travel chat service
travel_service = TravelChatService()


# ===========================================
# MAIN CHAT ENDPOINT
# ===========================================

@router.post("/chat", response_model=ChatResponse)
async def chat_with_bot(request: ChatRequest):
    """
    Main chat endpoint for travel assistance.
    
    Handles:
    - Hotel searches with budget filtering
    - Destination recommendations for trips
    - General travel questions and follow-ups
    - Greetings and conversational responses
    """
    try:
        logger.info(f"Received chat message: {request.message[:100]}...")
        
        # Process the user message through our service
        response = await travel_service.process_message(request.message)
        
        logger.info(f"Generated response with hotels: {len(response.hotels or [])}, destinations: {len(response.destinations or [])}")
        
        return response
        
    except ValueError as e:
        # Handle business logic errors (invalid city, budget, etc.)
        logger.warning(f"Validation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid request: {str(e)}"
        )
        
    except ConnectionError as e:
        # Handle API connection issues (Amadeus, Groq down)
        logger.error(f"API connection error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Travel services are temporarily unavailable. Please try again later."
        )
        
    except Exception as e:
        # Handle unexpected errors
        logger.error(f"Unexpected error processing chat: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="I'm having trouble processing your request. Please try again."
        )


# ===========================================
# HEALTH CHECK ENDPOINT
# ===========================================

@router.get("/health", response_model=HealthCheck)
async def health_check():
    """
    Health check endpoint to verify service status.
    """
    try:
        # Test if our travel service is working
        is_healthy = await travel_service.health_check()
        
        if is_healthy:
            return HealthCheck(
                status="healthy",
                timestamp=datetime.now()
            )
        else:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "status": "unhealthy",
                    "timestamp": datetime.now().isoformat()
                }
            )
            
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unhealthy", 
                "timestamp": datetime.now().isoformat(),
                "error": str(e)
            }
        )