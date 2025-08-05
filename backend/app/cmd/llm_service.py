import logging
from typing import Dict, Any, Optional
import httpx
from ..core.config import Settings
from llm_connector import LLMConnector

logger = logging.getLogger(__name__)


class LLMService:
    def __init__(self):
        self.connector = LLMConnector(
            base_url=Settings.LLM_API_URL,
            api_key=Settings.LLM_API_KEY,
            timeout=Settings.LLM_TIMEOUT
        )

    async def generate(
            self,
            prompt: str,
            model: str = "mistral",
            temperature: float = 0.7,
            max_tokens: int = 1000,
            context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generate text completion using LLM
        """
        payload = {
            "prompt": prompt,
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "context": context or {}
        }

        return await self.connector.generate_completion(payload)

    async def get_available_models(self) -> list:
        """
        Get list of available models
        """
        return await self.connector.get_models()