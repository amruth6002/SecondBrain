"""Configuration management — loads from environment variables, never hardcodes secrets."""

import os
from dotenv import load_dotenv

# Load .env — search up from backend/ to find it
_config_dir = os.path.dirname(__file__)
for _levels in ["../../.env", "../../../.env", "../../../../.env"]:
    _candidate = os.path.join(_config_dir, _levels)
    if os.path.exists(_candidate):
        load_dotenv(_candidate)
        break
else:
    load_dotenv()  # Fallback: try default .env or system env vars


class Settings:
    # Azure OpenAI — GPT-4.1-mini (Primary)
    AZURE_OPENAI_ENDPOINT: str = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    AZURE_OPENAI_API_KEY: str = os.getenv("AZURE_OPENAI_API_KEY", "")
    AZURE_OPENAI_DEPLOYMENT: str = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1")
    AZURE_OPENAI_API_VERSION: str = os.getenv("AZURE_OPENAI_API_VERSION", "2025-01-01-preview")
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT: str = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small")

    MONGODB_URI: str = os.getenv("MONGODB_URI", "")

    # App settings
    MAX_UPLOAD_SIZE_MB: int = 20
    MAX_CONTENT_LENGTH: int = 50000  # max chars to send to LLM
    MODEL_NAME: str = "GPT-4.1"

    @property
    def chat_completions_url(self) -> str:
        """Build the Azure OpenAI chat completions URL from the base endpoint."""
        endpoint = self.AZURE_OPENAI_ENDPOINT.rstrip("/")

        # If the endpoint already contains the full path (deployment URL), extract base
        if "/openai/deployments/" in endpoint:
            # e.g. https://resource.openai.azure.com/openai/deployments/gpt-4.1/chat/completions?...
            endpoint = endpoint.split("/openai/deployments/")[0].rstrip("/")
        elif "?" in endpoint:
            endpoint = endpoint.split("?")[0].rstrip("/")

        # Build standard Azure OpenAI chat completions URL
        return (
            f"{endpoint}/openai/deployments/{self.AZURE_OPENAI_DEPLOYMENT}"
            f"/chat/completions?api-version={self.AZURE_OPENAI_API_VERSION}"
        )


settings = Settings()
