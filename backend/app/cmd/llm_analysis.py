import logging
from fastapi import APIRouter, HTTPException, Depends
from typing import Optional, Dict, Any
from pydantic import BaseModel
from llm_service import LLMService
from app.core.security import get_current_active_user # todo
from app.core.config import Settings

router = APIRouter()
logger = logging.getLogger(__name__)


class LLMAnalysisRequest(BaseModel):
    prompt: str
    model: Optional[str] = "mistral"
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 1000
    context: Optional[Dict[str, Any]] = None


class LLMAnalysisResponse(BaseModel):
    analysis_result: str
    model_used: str
    tokens_consumed: int
    status: str


@router.post("/analyze", response_model=LLMAnalysisResponse)
async def analyze_with_llm(
        request: LLMAnalysisRequest,
        current_user: dict = Depends(get_current_active_user),
        llm_service: LLMService = Depends()
):
    """
    use llm analysis using local model
    """
    try:
        logger.info(f"LLM analysis request from user {current_user['username']}")

        # Call LLM service
        response = await llm_service.generate(
            prompt=request.prompt,
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            context=request.context
        )

        return LLMAnalysisResponse(
            analysis_result=response["result"],
            model_used=response["model"],
            tokens_consumed=response["tokens_used"],
            status="success"
        )

    except Exception as e:
        logger.error(f"LLM analysis failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"LLM processing failed: {str(e)}"
        )


@router.get("/models")
async def get_available_models(
        current_user: dict = Depends(get_current_active_user),
        llm_service: LLMService = Depends()
):
    """
    get available llm models
    """
    try:
        models = await llm_service.get_available_models()
        return {"models": models, "status": "success"}
    except Exception as e:
        logger.error(f"Failed to fetch models: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch models: {str(e)}"
        )