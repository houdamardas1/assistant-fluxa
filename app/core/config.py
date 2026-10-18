"""
Configuration management
"""

from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings"""

    # `extra="ignore"` : le fichier .env contient aussi les variables du moteur
    # RAG (GROQ_API_KEY, GROQ_VERIFY_MODEL...) que cette classe ne declare pas.
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Application
    APP_NAME: str = "Fluxa"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    ENVIRONMENT: str = "development"

    # Security
    # A definir dans .env (32 caracteres minimum). Hors "development", le
    # serveur REFUSE de demarrer avec la valeur par defaut.
    SECRET_KEY: str = "your-secret-key-here-change-in-production"
    ALGORITHM: str = "HS256"
    JWT_TTL_MINUTES: int = 60
    RATE_LIMIT_PER_MINUTE: int = 20
    # Origines autorisees pour le navigateur. Dans .env : format JSON,
    # ex. CORS_ORIGINS=["http://localhost:3000","http://localhost:5173"]
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]

    # Audit (SQLite pour le POC, meme schema que PostgreSQL)
    AUDIT_DB_PATH: str = "data/audit.db"
    USERS_DB_PATH: str = "data/users.db"
    PG_DSN: str = ""  # DSN PostgreSQL (psycopg) ; vide = SQLite

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/morocco_ai"

    # Azure (à configurer plus tard)
    AZURE_OPENAI_ENDPOINT: Optional[str] = None
    AZURE_OPENAI_KEY: Optional[str] = None
    AZURE_OPENAI_DEPLOYMENT: str = "gpt-4"
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT: str = "text-embedding-ada-002"

    AZURE_SEARCH_ENDPOINT: Optional[str] = None
    AZURE_SEARCH_KEY: Optional[str] = None
    AZURE_SEARCH_INDEX: str = "morocco-data-index"

    # RAG Settings
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    TOP_K_RESULTS: int = 10

    # LLM Settings
    MAX_TOKENS: int = 4096
    TEMPERATURE: float = 0.3
    TOP_P: float = 0.95


settings = Settings()
