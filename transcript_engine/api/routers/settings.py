"""API Router for managing application settings via UI."""

import logging
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from transcript_engine.core.config import Settings, get_settings, set_ui_ollama_url, set_ui_default_model
from transcript_engine.core.dependencies import get_templates, reset_singletons # Need to create reset_singletons

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/settings/", response_class=HTMLResponse)
def get_settings_page(
    request: Request,
    settings: Settings = Depends(get_settings),
    templates: Jinja2Templates = Depends(get_templates)
):
    """Serves the settings page."""
    logger.info("Serving settings page.")
    return templates.TemplateResponse(
        request=request, name="settings.html", context={"settings": settings}
    )

@router.post("/settings/", response_class=HTMLResponse)
def update_settings(
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
    ollama_url: str = Form(...),
    default_model: str = Form(...)
):
    """Updates settings based on form submission."""
    logger.info(f"Received settings update: URL='{ollama_url}', Model='{default_model}'")
    message = ""
    success = False
    try:
        # Update settings in memory
        set_ui_ollama_url(ollama_url)
        set_ui_default_model(default_model)

        # Reset dependent services to pick up changes
        reset_singletons() 
        
        message = "Settings updated successfully. Changes will apply to new requests."
        success = True
        logger.info(message)
        
    except Exception as e:
        message = f"Error updating settings: {e}"
        success = False
        logger.error(message, exc_info=True)

    # Re-render the form part with the new settings and a message
    # Need to get potentially updated settings *after* reset could clear cache
    updated_settings = get_settings() 
    return templates.TemplateResponse(
        request=request, 
        name="_settings_form.html", 
        context={
            "settings": updated_settings,
            "message": message, 
            "success": success
        }
    ) 