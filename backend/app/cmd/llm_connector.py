import httpx
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class LLMConnector:
    def __init__(self, base_url: str, api_key: str = None, timeout: int = 60):
        self.base_url = base_url
        self.api_key = api_key
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)

    async def generate_completion(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send completion request to LLM API
        """
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            response = await self.client.post(
                f"{self.base_url}/v1/completions",
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"LLM API error: {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"LLM connection error: {str(e)}")
            raise

    async def get_models(self) -> list:
        """
        Get available models from LLM API
        """
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            response = await self.client.get(
                f"{self.base_url}/v1/models",
                headers=headers
            )
            response.raise_for_status()
            return response.json().get("data", [])
        except httpx.HTTPStatusError as e:
            logger.error(f"LLM models API error: {e.response.text}")
            return []
        except Exception as e:
            logger.error(f"LLM models connection error: {str(e)}")
            return []