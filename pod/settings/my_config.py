from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import model_validator, FilePath
from pydantic_settings import BaseSettings, SettingsConfigDict

from utility.my_logger import my_logger


class Settings(BaseSettings):
    BASE_DIR: Path = Path(__file__).parent.parent.parent.resolve()
    TEMP_IMAGES_FOLDER_PATH: Path = Path(__file__).parent.parent.parent.resolve() / "static/images"
    TEMP_VIDEOS_FOLDER_PATH: Path = Path(__file__).parent.parent.resolve() / "static/videos"

    DEBUG: int = 1

    # DATABASE
    DATABASE_URL: str = ""

    # REDIS & TASKIQ
    CA: str = ""
    CA_PATH: Optional[FilePath] = None
    FASTAPI_CLIENT_CERT: str = ""
    FASTAPI_CLIENT_CERT_PATH: Optional[FilePath] = None
    FASTAPI_CLIENT_KEY: str = ""
    FASTAPI_CLIENT_KEY_PATH: Optional[FilePath] = None
    REDIS_HOST: str = ""
    REDIS_PASSWORD: str = ""

    # FIREBASE ADMIN SDK
    FIREBASE_ADMINSDK: str = ""
    FIREBASE_ADMINSDK_PATH: Optional[FilePath] = None

    # S3
    S3_ACCESS_KEY_ID: str = ""
    S3_SECRET_KEY: str = ""
    S3_ENDPOINT: str = ""
    S3_REGION: str = ""
    S3_BUCKET_NAME: str = ""

    # FASTAPI JWT
    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_TIME: int = 60
    REFRESH_TOKEN_EXPIRE_TIME: int = 7

    # EMAIL
    EMAIL_SERVICE_API_KEY: str = ""

    @model_validator(mode="after")
    def inject_secret_file_paths(self):
        # If the value is the content (Docker secret), infer the path
        secret_base = Path("/run/secrets")
        if not self.FIREBASE_ADMINSDK_PATH and (secret_base / "FIREBASE_ADMINSDK").exists():
            self.FIREBASE_ADMINSDK_PATH = secret_base / "FIREBASE_ADMINSDK"

        if not self.CA_PATH and (secret_base / "CA").exists():
            self.CA_PATH = secret_base / "CA"

        if not self.FASTAPI_CLIENT_CERT_PATH and (secret_base / "FASTAPI_CLIENT_CERT").exists():
            self.FASTAPI_CLIENT_CERT_PATH = secret_base / "FASTAPI_CLIENT_CERT"

        if not self.FASTAPI_CLIENT_KEY_PATH and (secret_base / "FASTAPI_CLIENT_KEY").exists():
            self.FASTAPI_CLIENT_KEY_PATH = secret_base / "FASTAPI_CLIENT_KEY"

        return self

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", secrets_dir="/run/secrets")


@lru_cache
def get_settings():
    s = Settings()

    my_logger.warning("🔧 get_settings(): Loaded configuration values...\n")

    # General
    my_logger.warning(f"BASE_DIR: {s.BASE_DIR}")
    my_logger.warning(f"TEMP_IMAGES_FOLDER_PATH: {s.TEMP_IMAGES_FOLDER_PATH}")
    my_logger.warning(f"TEMP_VIDEOS_FOLDER_PATH: {s.TEMP_VIDEOS_FOLDER_PATH}")
    my_logger.warning(f"DEBUG: {s.DEBUG}\n")

    # DATABASE
    my_logger.warning(f"DATABASE_URL: {s.DATABASE_URL}\n")

    # REDIS & TASKIQ
    my_logger.warning(f"CA_PATH: {s.CA_PATH}")
    my_logger.warning(f"FASTAPI_CLIENT_CERT_PATH: {s.FASTAPI_CLIENT_CERT_PATH}")
    my_logger.warning(f"FASTAPI_CLIENT_KEY_PATH: {s.FASTAPI_CLIENT_KEY_PATH}")
    my_logger.warning(f"REDIS_HOST: {s.REDIS_HOST}")
    my_logger.warning(f"REDIS_PASSWORD: {s.REDIS_PASSWORD[:3]}{'*' * (len(s.REDIS_PASSWORD) - 3) if s.REDIS_PASSWORD else ''}\n")

    # FIREBASE
    my_logger.warning(f"FIREBASE_ADMINSDK_PATH: {s.FIREBASE_ADMINSDK_PATH}\n")

    # S3
    my_logger.warning(f"S3_ACCESS_KEY_ID: {s.S3_ACCESS_KEY_ID}")
    my_logger.warning(f"S3_SECRET_KEY: {s.S3_SECRET_KEY[:4]}{'*' * (len(s.S3_SECRET_KEY) - 4) if s.S3_SECRET_KEY else ''}")
    my_logger.warning(f"S3_ENDPOINT: {s.S3_ENDPOINT}")
    my_logger.warning(f"S3_REGION: {s.S3_REGION}")
    my_logger.warning(f"S3_BUCKET_NAME: {s.S3_BUCKET_NAME}\n")

    # JWT
    my_logger.warning(f"SECRET_KEY: {s.SECRET_KEY[:4]}{'*' * (len(s.SECRET_KEY) - 4) if s.SECRET_KEY else ''}")
    my_logger.warning(f"ALGORITHM: {s.ALGORITHM}")
    my_logger.warning(f"ACCESS_TOKEN_EXPIRE_TIME: {s.ACCESS_TOKEN_EXPIRE_TIME}")
    my_logger.warning(f"REFRESH_TOKEN_EXPIRE_TIME: {s.REFRESH_TOKEN_EXPIRE_TIME}\n")

    # EMAIL
    my_logger.warning(f"EMAIL_SERVICE_API_KEY: {s.EMAIL_SERVICE_API_KEY[:4]}{'*' * (len(s.EMAIL_SERVICE_API_KEY) - 4) if s.EMAIL_SERVICE_API_KEY else ''}\n")

    return s
