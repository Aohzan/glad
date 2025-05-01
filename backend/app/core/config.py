import secrets
import sys
from typing import Annotated, Any, Self
import warnings
from pydantic import AnyUrl, BeforeValidator, model_validator, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


def parse_cors(v: Any) -> list[str] | str:
    if isinstance(v, str) and not v.startswith("["):
        return [i.strip() for i in v.split(",")]
    elif isinstance(v, list | str):
        return v
    raise ValueError(v)


class Settings(BaseSettings):
    """
    Application settings.
    """

    model_config = SettingsConfigDict(
        # Use top level .env file (one level above ./backend/)
        env_file="../.env",
        env_ignore_empty=True,
        extra="ignore",
    )

    PROJECT_NAME: str = "Glad"
    API_V1_STR: str = "/api/v1"

    ENVIRONMENT: str = "dev"  # local, dev, staging, production
    LOG_LEVEL: str = "info"  # debug, info, warning, error, critical
    DATA_DIR: str = "../data"

    # CORS
    FRONTEND_URL: str = "http://localhost:5173"
    BACKEND_CORS_ORIGINS: Annotated[
        list[AnyUrl] | str, BeforeValidator(parse_cors)
    ] = []

    @computed_field  # type: ignore[prop-decorator]
    @property
    def all_cors_origins(self) -> list[str]:
        return list(
            set(
                [str(origin).rstrip("/")
                 for origin in self.BACKEND_CORS_ORIGINS]
                + [self.FRONTEND_URL]
            )
        )

    # Database
    DATABASE_URL: str = f"sqlite:///./{DATA_DIR}/glad.db"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        # Use in-memory database for tests
        if "pytest" in sys.modules:
            return "sqlite:///:memory:"
        return self.DATABASE_URL
    # POSTGRES_SERVER: str
    # POSTGRES_PORT: int = 5432
    # POSTGRES_USER: str
    # POSTGRES_PASSWORD: str = ""
    # POSTGRES_DB: str = ""

    # Security
    SECRET_KEY: str = secrets.token_urlsafe(32)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    EMAIL_RESET_TOKEN_EXPIRE_HOURS: int = 48
    FIRST_SUPERUSER: str = "admin@me.com"
    FIRST_SUPERUSER_PASSWORD: str = "changethis"

    def _check_default_secret(self, var_name: str, value: str | None) -> None:
        if value == "changethis":
            message = (
                f'The value of {var_name} is "changethis", '
                "for security, please change it, at least for deployments."
            )
            if self.ENVIRONMENT in ["local", "dev"] or "pytest" in sys.modules:
                warnings.warn(message, stacklevel=1)
            else:
                raise ValueError(message)

    @model_validator(mode="after")
    def _enforce_non_default_secrets(self) -> Self:
        self._check_default_secret("SECRET_KEY", self.SECRET_KEY)
        # self._check_default_secret("POSTGRES_PASSWORD", self.POSTGRES_PASSWORD)
        self._check_default_secret(
            "FIRST_SUPERUSER_PASSWORD", self.FIRST_SUPERUSER_PASSWORD
        )

        return self


# Create settings instance
settings = Settings()
