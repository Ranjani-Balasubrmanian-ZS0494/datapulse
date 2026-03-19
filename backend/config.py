from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import Optional
import os


class Settings(BaseSettings):
    OPENAI_API_KEY: str = ""
    AZURE_SQL_CONN: str = ""
    DASHBOARD_URL: str = "http://localhost:5173"
    FIX_MODE: str = "auto"

    # Azure Service Principal — optional, enables ADF run enrichment
    AZURE_CLIENT_ID: str = ""
    AZURE_CLIENT_SECRET: str = ""
    AZURE_TENANT_ID: str = ""
    AZURE_SUBSCRIPTION_ID: str = ""
    AZURE_RESOURCE_GROUP: str = ""
    AZURE_FACTORY_NAME: str = ""

    model_config = {"env_file": ".env", "extra": "ignore"}

    @property
    def is_degraded(self) -> bool:
        return not self.OPENAI_API_KEY or not self.AZURE_SQL_CONN

    @property
    def has_adf_credentials(self) -> bool:
        return all([
            self.AZURE_CLIENT_ID, self.AZURE_CLIENT_SECRET,
            self.AZURE_TENANT_ID, self.AZURE_SUBSCRIPTION_ID,
            self.AZURE_RESOURCE_GROUP, self.AZURE_FACTORY_NAME,
        ])


settings = Settings()
