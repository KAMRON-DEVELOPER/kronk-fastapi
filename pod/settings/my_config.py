from functools import lru_cache
from pathlib import Path
from typing import Optional

import spacy
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DEBUG: bool = True

    BASE_DIR: Path = Path(__file__).parent.parent.resolve()
    TEMP_IMAGES_FOLDER_PATH: Path = BASE_DIR / "static/images"
    TEMP_VIDEOS_FOLDER_PATH: Path = BASE_DIR / "static/videos"

    # SSL/TLS PROD
    CA: Optional[str] = None
    CLIENT_CERT: Optional[str] = None
    CLIENT_KEY: Optional[str] = None

    # SSL/TLS DEV
    CA_PATH: Path = BASE_DIR / "certs/ca/ca.pem"
    FASTAPI_CLIENT_CERT_PATH: Path = BASE_DIR / "certs/client/client-cert.pem"
    FASTAPI_CLIENT_KEY_PATH: Path = BASE_DIR / "certs/client/client-key.pem"

    # DATABASE
    DATABASE_URL: str = ""

    # REDIS
    REDIS_HOST: str = ""

    # FIREBASE ADMIN SDK
    FIREBASE_ADMINSDK: Optional[str] = None
    FIREBASE_ADMINSDK_PATH: Path = BASE_DIR / "certs/kronk-production-firebase-adminsdk.json"

    # FIREBASE ADMIN SDK
    GCP_PROJECT_ID: str = "1081239849482"
    GCS_BUCKET_NAME: str = "kronk-gcs-bucket"
    GCP_CREDENTIALS: Optional[str] = None
    GCP_CREDENTIALS_PATH: Path = BASE_DIR / "certs/kronk-production-gcp-credentials.json"

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

    # LINGVANEX
    LINGVANEX_API_KEY: str = ""

    @model_validator(mode="after")
    def inject_secret_file_paths(self):
        secret_base = Path("/run/secrets")

        if self.FIREBASE_ADMINSDK:
            self.FIREBASE_ADMINSDK_PATH = secret_base / "FIREBASE_ADMINSDK"

        if self.GCP_CREDENTIALS:
            self.GCP_CREDENTIALS_PATH = secret_base / "GCP_CREDENTIALS"

        if self.CA:
            self.CA_PATH = secret_base / "ca.pem"

        if self.CLIENT_CERT:
            self.FASTAPI_CLIENT_CERT_PATH = secret_base / "client_cert.pem"

        if self.CLIENT_KEY:
            self.FASTAPI_CLIENT_KEY_PATH = secret_base / "client_key.pem"

        return self

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", secrets_dir="/run/secrets")


@lru_cache
def get_settings():
    return Settings()


@lru_cache(maxsize=1)
def get_nlp():
    return spacy.load("en_core_web_sm")
