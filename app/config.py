"""Configuration management using Infisical for secrets."""
import os
from typing import Optional
from pydantic_settings import BaseSettings
from infisical_sdk import InfisicalSDKClient


class Settings(BaseSettings):
    """Application settings loaded from Infisical and environment variables."""
    
    # Infisical configuration (from environment)
    infisical_url: str = "https://infisical.example.com"
    infisical_token: str  # Service Token (st.xxx.yyy.zzz)
    infisical_project_id: str = "4627ccea-f94c-4f19-9605-6892dfd37ee0"
    infisical_environment: str = "dev"
    
    # Application configuration (defaults, can be overridden)
    app_port: int = 8080
    ai_model: str = "gpt-4o"
    
    # Secrets from Infisical (loaded dynamically)
    linkedin_email: Optional[str] = None
    linkedin_password: Optional[str] = None
    github_token: Optional[str] = None
    postal_api_key: Optional[str] = None
    postal_server_url: Optional[str] = None
    approval_email: Optional[str] = None
    linkedin_handles: Optional[str] = None
    app_base_url: Optional[str] = None
    timezone: str = "America/Denver"
    
    # Scraping configuration
    scraping_lookback_days: int = 7
    scraping_max_posts_per_handle: int = 50
    
    # Posting intelligence configuration
    daily_post_limit: int = 3
    min_post_spacing_minutes: int = 90
    posting_hour_start: int = 6  # 6am MST
    posting_hour_end: int = 21  # 9pm MST
    posting_weekdays_only: bool = True
    enable_posting_jitter: bool = True
    posting_jitter_minutes: int = 15
    
    # Rate limiting safety
    max_posts_per_hour: int = 5
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "allow"


def load_config() -> Settings:
    """Load configuration from environment and Infisical."""
    
    # Load base settings from environment
    settings = Settings()
    
    print(f"🔐 Connecting to Infisical...")
    print(f"   URL: {settings.infisical_url}")
    print(f"   Project: {settings.infisical_project_id}")
    print(f"   Environment: {settings.infisical_environment}")
    
    try:
        # Initialize Infisical SDK client with host and token
        client = InfisicalSDKClient(
            host=settings.infisical_url,
            token=settings.infisical_token
        )
        
        # Fetch all secrets from Infisical using project_id (not project_slug)
        secrets_response = client.secrets.list_secrets(
            project_id=settings.infisical_project_id,
            environment_slug=settings.infisical_environment,
            secret_path="/"
        )
        
        print(f"✅ Connected to Infisical successfully")
        print(f"📦 Loading {len(secrets_response.secrets)} secrets from Infisical...")
        
        # Map secrets to settings
        secret_mapping = {
            "LINKEDIN_EMAIL": "linkedin_email",
            "LINKEDIN_PASSWORD": "linkedin_password",
            "GITHUB_TOKEN": "github_token",
            "POSTAL_API_KEY": "postal_api_key",
            "POSTAL_SERVER_URL": "postal_server_url",
            "APPROVAL_EMAIL": "approval_email",
            "LINKEDIN_HANDLES": "linkedin_handles",
            "APP_BASE_URL": "app_base_url",
            "TIMEZONE": "timezone",
            "AI_MODEL": "ai_model",  # Can be overridden in Infisical
        }
        
        loaded_count = 0
        for secret in secrets_response.secrets:
            key = secret.secretKey
            value = secret.secretValue
            
            if key in secret_mapping:
                attr_name = secret_mapping[key]
                setattr(settings, attr_name, value)
                loaded_count += 1
                # Mask sensitive values in logs
                if "password" in key.lower() or "token" in key.lower() or "key" in key.lower():
                    display_value = f"{value[:8]}..." if len(value) > 8 else "***"
                else:
                    display_value = value
                print(f"   ✓ {key}: {display_value}")
        
        print(f"✅ Loaded {loaded_count} secrets from Infisical")
        
        # Validate required secrets
        required = [
            ("linkedin_email", "LINKEDIN_EMAIL"),
            ("linkedin_password", "LINKEDIN_PASSWORD"),
            ("github_token", "GITHUB_TOKEN"),
            ("postal_api_key", "POSTAL_API_KEY"),
            ("postal_server_url", "POSTAL_SERVER_URL"),
            ("approval_email", "APPROVAL_EMAIL"),
            ("linkedin_handles", "LINKEDIN_HANDLES"),
            ("app_base_url", "APP_BASE_URL"),
        ]
        
        missing = []
        for attr, key in required:
            if not getattr(settings, attr):
                missing.append(key)
        
        if missing:
            raise ValueError(f"❌ Missing required secrets in Infisical: {', '.join(missing)}")
        
        print(f"✅ All required secrets validated")
        
        return settings
        
    except Exception as e:
        print(f"❌ Failed to load configuration from Infisical: {e}")
        print(f"   Make sure INFISICAL_TOKEN is set correctly")
        print(f"   Token should be in format: st.xxx.yyy.zzz")
        raise


# Global settings instance (loaded once on startup)
settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get the global settings instance."""
    global settings
    if settings is None:
        settings = load_config()
    return settings
