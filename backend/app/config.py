from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    MONGODB_URL: str = "mongodb://localhost:27017/iot_care"
    MONGODB_DB_NAME: str = "iot_care"
    JWT_SECRET: str = "change-this-secret"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_MINUTES: int = 1440
    DEVICE_API_KEY: str = "dev-device-key"
    PATIENT_WEB_URL: str = "http://localhost:5173"
    DOCTOR_WEB_URL: str = "http://localhost:5174"
    SIM_API_BASE: str = "http://localhost:8000"
    ANOMALY_SERVICE_URL: str = "http://localhost:8010"
    ANOMALY_SERVICE_TIMEOUT_SECONDS: float = 4.0
    ANOMALY_SERVICE_API_KEY: str = ""
    ANOMALY_SERVICE_FALLBACK_TO_RULES: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
