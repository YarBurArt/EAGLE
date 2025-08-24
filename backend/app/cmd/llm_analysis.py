""" Module for unified interface to LLM services """
import os
from dotenv import load_dotenv

import g4f
from ollama import Client
from fastapi import HTTPException

from app.core.llm_templ import LLMTemplates

# Настройка g4f
g4f.debug.logging = True

load_dotenv()
IS_LOCAL_LLM: bool = os.getenv('LLMSERVICE__LOCAL')
if IS_LOCAL_LLM:
    client_ollama = Client(host=os.getenv('LLMSERVICE__API_URL'))
else:
    client_ollama = None


class LLMService:
    def __init__(self):
        self.providers = {
            "aichat": g4f.Provider.Chatai,
            "bing": g4f.Provider.bing,
            "you": g4f.Provider.You,
        }

    async def query_llm(self, prompt: str, provider_name: str = None) -> str:
        """
        Отправляет запрос к бесплатным LLM через g4f
        """
        # TODO: support custom system prompt
        try:
            if IS_LOCAL_LLM:
                res: str = self._local_llm(prompt)
            else:
                res: str = await self._g4f_llm(prompt, provider_name)
            return res
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Ошибка при запросе к LLM: {str(e)}"
            ) from e

    def _local_llm(self, prompt: str) -> str:
        """ query with local llm ollama """
        res: dict = client_ollama.generate(
            model=os.getenv('LLMSERVICE__DEFAULT_MODEL'),
            prompt=prompt, system=LLMTemplates.SYSTEM_PROMT
        )
        # remove think text for deepseek-r1, qwen , qwq models
        parts_th = res.response.rsplit('</think>', 1)
        return parts_th[-1] if len(parts_th) > 1 else res.response

    async def _g4f_llm(self, prompt: str, provider_name: str) -> str:
        """ query with g4f proxy providers like DDG """
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
                raise HTTPException(
                    status_code=500,
                    detail=f"Provider {provider_name} failed: {str(e)}"
                ) from e

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


# Инициализация сервиса
llm_service = LLMService()
