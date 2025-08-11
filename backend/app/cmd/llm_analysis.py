import g4f
from fastapi import HTTPException
# TODO: ollama, openrouter , yandexgpt support
# Настройка g4f
g4f.debug.logging = True


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

        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Ошибка при запросе к LLM: {str(e)}"
            ) from e


# Инициализация сервиса
llm_service = LLMService()
