from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any
import g4f
import asyncio
import json

# Настройка g4f
g4f.debug.logging = True


class QueryRequest(BaseModel):
    prompt: str
    provider: Optional[str] = None


class CodeAnalysisRequest(BaseModel):
    code: str


class PayloadRequest(BaseModel):
    description: str
    language: Optional[str] = "python"


class LLMService:
    def __init__(self):
        self.providers = {
            "bing": g4f.Provider.bing,
            "you": g4f.Provider.You,
            "aichat": g4f.Provider.Chatai,
        }

    async def query_llm(self, prompt: str, provider_name: str = None) -> str:
        """
        Отправляет запрос к бесплатным LLM через g4f
        """
        # TODO: support custom system prompt
        try:
            # Если указан провайдер, используем его
            if provider_name and provider_name in self.providers:
                provider = self.providers[provider_name]
                try:
                    response = await g4f.ChatCompletion.create_async(
                        model=g4f.models.default,
                        messages=[{"role": "user", "content": prompt}],
                        provider=provider
                    )
                    return response
                except Exception as e:
                    raise HTTPException(status_code=500, detail=f"Provider {provider_name} failed: {str(e)}")

            # Если провайдер не указан или не найден, пробуем разные
            for name, provider in self.providers.items():
                try:
                    response = await g4f.ChatCompletion.create_async(
                        model=g4f.models.default,
                        messages=[{"role": "user", "content": prompt}],
                        provider=provider
                    )
                    if response and len(response) > 0:
                        return response
                except Exception as e:
                    print(f"Provider {name} failed: {e}")
                    continue

            return "Не удалось получить ответ от ни одного провайдера"

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Ошибка при запросе к LLM: {str(e)}")


# Инициализация сервиса
llm_service = LLMService()
