from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./data/app.db"
    LOCAL_TZ: str = "Asia/Kolkata"
    NIGHT_START: str = "22:00"
    NIGHT_END: str = "06:00"
    
    DEVIATION_THRESHOLD_M: int = 500
    DEVIATION_MIN_SECONDS: int = 120
    DEVIATION_MIN_METERS: int = 0
    MAX_GPS_GAP_SECONDS: int = 90
    
    DEFAULT_SPEED_LIMIT_KMPH: int = 60
    OVERSPEED_MIN_SECONDS: int = 30
    EXTREME_OVERSPEED_DELTA_KMPH: int = 40
    EXTREME_OVERSPEED_MIN_SECONDS: int = 10
    
    MAX_OTP_FAILURES: int = 3
    MAX_GPS_BATCH: int = 5000
    
    JWT_SECRET: str = "dev-secret-key-change-in-prod"
    OTP_SECRET: str = "dev-otp-secret-change-in-prod"
    JWT_TTL_MIN: int = 60
    
    CACHE_TTL_S: int = 300
    CACHE_MAX: int = 256
    
    ALERT_COORD_DECIMALS: int = 3
    SOS_COORD_DECIMALS: int = 5
    
    DEMO_MODE: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
