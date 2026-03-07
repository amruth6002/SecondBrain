"""Configuration management — loads from environment variables, never hardcodes secrets."""

import os
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))


class Settings:
    # Azure Phi-4 (primary model)
    AZURE_PHI4_ENDPOINT: str = os.getenv("AZURE_PHI4_ENDPOINT", "")
    AZURE_PHI4_API_KEY: str = os.getenv("AZURE_PHI4_API_KEY", "")

    # Azure OpenAI (fallback if GPT models become available)
    AZURE_OPENAI_ENDPOINT: str = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    AZURE_OPENAI_API_KEY: str = os.getenv("AZURE_OPENAI_API_KEY", "")

    # App settings
    MAX_UPLOAD_SIZE_MB: int = 20
    MAX_CONTENT_LENGTH: int = 50000  # max chars to send to LLM
    MODEL_NAME: str = "Phi-4"

    @property
    def phi4_base_url(self) -> str:
        """Extract base URL from the full endpoint for OpenAI client."""
        # Endpoint: https://xxx.services.ai.azure.com/models/chat/completions?api-version=...
        # We need: https://xxx.services.ai.azure.com/models
        endpoint = self.AZURE_PHI4_ENDPOINT
        if "/chat/completions" in endpoint:
            endpoint = endpoint.split("/chat/completions")[0]
        if "?" in endpoint:
            endpoint = endpoint.split("?")[0]
        return endpoint


settings = Settings()
