"""Configuration settings for VPS1."""

from urllib.parse import quote_plus
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    
    # Telegram Bot
    bot_token: str
    channel_id: int = 0  # Channel to join
    group_id: int = 0    # Group to join
    admin_password: str = "admin123"  # Password for /admin command
    
    # Database
    db_host: str = "localhost"
    db_port: int = 3306
    db_name: str = "github_student_bot"
    db_user: str = "bot_user"
    db_password: str = ""
    
    # API Server (local)
    api_server_url: str = "http://localhost:5000"
    
    # VPS2 Submit Service
    vps2_url: str = "http://localhost:5001"
    
    # SePay Payment
    sepay_account_number: str = ""
    sepay_bank_code: str = "TPBank"
    sepay_webhook_secret: str = ""
    
    # Webhook Server
    webhook_host: str = "0.0.0.0"
    webhook_port: int = 8080
    
    # Pricing
    verification_price: int = 30000  # VND
    referral_bonus_credits: int = 1
    
    @property
    def database_url(self) -> str:
        """Get async database URL."""
        encoded_password = quote_plus(self.db_password)
        return (
            f"mysql+aiomysql://{self.db_user}:{encoded_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )
    
    @property
    def sync_database_url(self) -> str:
        """Get sync database URL for migrations."""
        encoded_password = quote_plus(self.db_password)
        return (
            f"mysql+pymysql://{self.db_user}:{encoded_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


# Global settings instance
settings = Settings()
