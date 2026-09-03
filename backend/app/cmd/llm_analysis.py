"""Module for unified interface to LLM services"""

import os
from typing import Any

import g4f
import httpx
from dotenv import load_dotenv
from fastapi import HTTPException
from g4f.client import AsyncClient
from ollama import AsyncClient as OllamaAsyncClient

from app.core.llm_templ import LLMTemplates

g4f.debug.logging = False

load_dotenv()
IS_LOCAL_LLM: int = int(os.getenv("LLMSERVICE__LOCAL", "0") or "0")
if IS_LOCAL_LLM == 1:
    client_ollama = OllamaAsyncClient(
        host=os.getenv("LLMSERVICE__API_URL", "http://localhost:11434"),
        timeout=httpx.Timeout(connect=5, read=120, write=10, pool=5),
    )
else:
    client_ollama = None

client_g4f = AsyncClient()


class LLMService:
    def __init__(self):
        self.providers = {
            "perplexity": g4f.Provider.Perplexity,
            "yqcloud": g4f.Provider.Yqcloud,
            "huggingspace": g4f.Provider.HuggingSpace,
            "kilocode": g4f.Provider.KiloCode,
        }

    async def query_llm(self, prompt: str, provider_name: str | None = None) -> str:
        """
        Отправляет запрос к бесплатным LLM через g4f
        """
        try:
            if IS_LOCAL_LLM == 1:
                return await self._local_llm(prompt)
            return await self._g4f_llm(prompt, provider_name)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"LLM request failed: {str(e)}"
            ) from e

    async def query_llm_chat(
        self, messages: list[dict[str, Any]], provider_name: str | None = None
    ) -> str:
        """Multi-turn chat query supporting both local and g4f backends."""
        try:
            if IS_LOCAL_LLM == 1:
                return await self._local_llm_chat(messages)
            return await self._g4f_llm_chat(messages, provider_name)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"LLM chat request failed: {str(e)}"
            ) from e

    @staticmethod
    async def _local_llm(prompt: str) -> str:
        """Query local Ollama with a single prompt."""
        res = await client_ollama.generate(
            model=os.getenv("LLMSERVICE__DEFAULT_MODEL", "mistral"),
            prompt=prompt,
            system=LLMTemplates.SYSTEM_PROMT,
        )
        # remove think text for deepseek-r1, qwen, qwq models
        parts_th = res.response.rsplit("</think>", 1)
        return parts_th[-1] if len(parts_th) > 1 else res.response

    @staticmethod
    async def _local_llm_chat(messages: list[dict[str, Any]]) -> str:
        """Query local Ollama with multi-turn message history."""
        res = await client_ollama.chat(
            model=os.getenv("LLMSERVICE__DEFAULT_MODEL", "mistral"),
            messages=messages,
        )
        text = res.message.content or ""
        parts_th = text.rsplit("</think>", 1)
        return parts_th[-1] if len(parts_th) > 1 else text

    async def _g4f_llm(self, prompt: str, provider_name: str | None) -> str:
        """Query g4f — auto-routes via AnyProvider if no provider specified."""
        if provider_name and provider_name in self.providers:
            provider = self.providers[provider_name]
            try:
                response = await client_g4f.chat.completions.create(
                    model=g4f.models.default,
                    messages=[{"role": "user", "content": prompt}],
                    provider=provider,
                )
                return response.choices[0].message.content or ""
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"Provider {provider_name} failed: {str(e)}",
                ) from e

        for name, provider in self.providers.items():
            try:
                response = await client_g4f.chat.completions.create(
                    model=g4f.models.default,
                    messages=[{"role": "user", "content": prompt}],
                    provider=provider,
                )
                content = response.choices[0].message.content or ""
                if content:
                    return content
            except Exception:
                continue

        return "No response from any LLM provider"

    async def _g4f_llm_chat(
        self, messages: list[dict[str, Any]], provider_name: str | None
    ) -> str:
        """Query g4f with message history."""
        if provider_name and provider_name in self.providers:
            provider = self.providers[provider_name]
            try:
                response = await client_g4f.chat.completions.create(
                    model=g4f.models.default,
                    messages=messages,
                    provider=provider,
                )
                return response.choices[0].message.content or ""
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"Provider {provider_name} failed: {str(e)}",
                ) from e

        for name, provider in self.providers.items():
            try:
                response = await client_g4f.chat.completions.create(
                    model=g4f.models.default,
                    messages=messages,
                    provider=provider,
                )
                content = response.choices[0].message.content or ""
                if content:
                    return content
            except Exception:
                continue

        return "No response from any LLM provider"


llm_service = LLMService()
