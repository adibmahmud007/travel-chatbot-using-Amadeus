"""
Travel Chatbot Configuration Management

Simple configuration loader for environment variables.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # API Credentials
    amadeus_api_key: str = Field(..., description="Amadeus API Key")
    amadeus_api_secret: str = Field(..., description="Amadeus API Secret")
    groq_api_key: str = Field(..., description="Groq API Key for AI")
    
    # Application Configuration
    environment: str = Field("development", description="Environment mode")
    debug: bool = Field(True, description="Debug mode")
    log_level: str = Field("INFO", description="Logging level")
    
    # Server Configuration
    host: str = Field("0.0.0.0", description="Server host")
    port: int = Field(8000, description="Server port")
    
    # API Settings
    amadeus_base_url: str = Field("https://test.api.amadeus.com", description="Amadeus API base URL")
    groq_base_url: str = Field("https://api.groq.com/openai/v1", description="Groq API base URL")
    api_timeout: int = Field(30, description="API request timeout in seconds")
    
    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Create and cache application settings."""
    return Settings()


# Global settings instance
settings = get_settings()