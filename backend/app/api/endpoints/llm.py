"""
Module only for llm endpoints
to simplify the creation of a chain relative to the user
"""
from typing import Dict, Any

from fastapi import (
    APIRouter, HTTPException
)
import g4f  # temp

from app.cmd.llm_analysis import llm_service
from app.schemas.requests import QueryRequest, CodeAnalysisRequest

router = APIRouter()


@router.post("/query", description="General questions to LLM")
async def llm_query(request: QueryRequest):
    """
    Основной эндпоинт для запросов к LLM
    """
    try:
        result = await llm_service.query_llm(request.prompt, request.provider)
        return {
            "success": True,
            "response": result,
            "prompt": request.prompt
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze/code", description="Analyze and explain code via LLM")
async def analyze_code(request: CodeAnalysisRequest):
    """
    Анализирует код с помощью LLM
    """
    try:
        prompt = f"analyze this code and explain it to me\n\n{request.code}"
        result = await llm_service.query_llm(prompt)
        return {
            "success": True,
            "analysis": result,
            "code": request.code
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"error code analysis {str(e)}"
        ) from e


@router.get("/providers", description="Return list of LLM providers")
async def get_providers():
    """
    Возвращает список доступных провайдеров
    """
    try:
        providers_list = []
        for name, provider in llm_service.providers.items():
            providers_list.append({
                "name": name,
                "class": provider.__name__
            })
        return {
            "success": True,
            "providers": providers_list
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"error retrieving provider: {str(e)}"
        ) from e


@router.post("/chat", description="Chat with llm in context of chain")
async def chat_conversation(messages: Dict[str, Any]):
    """
    Эндпоинт для ведения диалога
    """
    try:
        chat_messages = messages.get("messages", [])
        if not chat_messages:
            raise HTTPException(
                status_code=400, detail="message massive needed"
            )

        for name, provider in llm_service.providers.items():
            try:
                response = await g4f.ChatCompletion.create_async(
                    model=g4f.models.default,
                    messages=chat_messages,
                    provider=provider
                )
                if response and len(response) > 0:
                    return {
                        "success": True,
                        "response": response,
                        "provider": name
                    }
            except Exception as e:
                print(f"Provider {name} failed: {e}")
                continue

        raise HTTPException(
            status_code=500, detail="no response from providers"
        )

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"dialog error: {str(e)}"
        ) from e  # to track traceback
