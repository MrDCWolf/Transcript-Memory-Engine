"""API Router for managing application settings via UI."""

import logging
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from typing import Optional

from transcript_engine.core.config import (
    Settings, get_settings, 
    set_ui_ollama_url, set_ui_default_model,
    set_ui_model_context_window, set_ui_answer_buffer_tokens, 
    set_ui_context_target_tokens
)
from transcript_engine.core.dependencies import get_templates, reset_singletons, get_llm_service

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/settings/", response_class=HTMLResponse)
def get_settings_page(
    request: Request,
    settings: Settings = Depends(get_settings),
    templates: Jinja2Templates = Depends(get_templates),
    llm_service = Depends(get_llm_service),
):
    """Serves the settings page."""
    logger.info("Serving settings page.")
    ollama_models = llm_service.list_models() if llm_service else []
    return templates.TemplateResponse(
        request=request, 
        name="settings.html", 
        context={
            "settings": settings,
            "ollama_models": ollama_models
        }
    )

@router.post("/settings/", response_class=HTMLResponse)
def update_settings(
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
    llm_service = Depends(get_llm_service),
    ollama_url: str = Form(...),
    default_model: str = Form(...),
    model_context_window: int = Form(...),
    answer_buffer_tokens: int = Form(...),
    context_target_tokens: Optional[int] = Form(None),
):
    """Updates settings based on form submission and persists them."""
    logger.info(f"Received settings update: URL='{ollama_url}', Model='{default_model}', ContextWin='{model_context_window}', Buffer='{answer_buffer_tokens}', Target='{context_target_tokens}'")
    message = ""
    success = False
    try:
        # Update & persist settings using the config functions
        set_ui_ollama_url(ollama_url)
        set_ui_default_model(default_model)
        set_ui_model_context_window(model_context_window)
        set_ui_answer_buffer_tokens(answer_buffer_tokens)
        set_ui_context_target_tokens(context_target_tokens)

        # Reset dependent services to pick up changes 
        # (Important: Need to ensure services re-fetch settings on next use)
        reset_singletons() 
        message = "Settings updated successfully. Changes will apply to new requests."
        success = True
        logger.info(message)
    except Exception as e:
        message = f"Error updating settings: {e}"
        success = False
        logger.error(message, exc_info=True)

    # Re-render the form part with the new settings and a message
    # Fetch the latest settings *after* potential updates and reset
    updated_settings = get_settings() 
    ollama_models = llm_service.list_models() if llm_service else []
    return templates.TemplateResponse(
        request=request, 
        name="_settings_form.html", 
        context={
            "settings": updated_settings,
            "message": message, 
            "success": success,
            "ollama_models": ollama_models
        }
    ) 

@router.get("/settings/ollama-models", response_class=JSONResponse)
async def get_ollama_models(llm_service = Depends(get_llm_service)):
    """Returns a list of available Ollama models for populating the dropdown."""
    try:
        models = llm_service.list_models()
        return {"models": models}
    except Exception as e:
        logger.error(f"Error fetching Ollama models: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"models": [], "error": str(e)}) 