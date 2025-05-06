"""API Router for Google OAuth 2.0 flow."""

import logging
import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request as GoogleAuthRequest

from transcript_engine.core.config import Settings, get_settings
from transcript_engine.core.dependencies import get_templates # For showing messages

logger = logging.getLogger(__name__)
router = APIRouter()

# Helper functions for token storage (simple JSON file for local app)
# In a multi-user or production app, use a proper database or secure store.

def _get_token_path(settings: Settings) -> Path:
    # Ensure the path is relative to the project root if not absolute
    token_p = Path(settings.GOOGLE_OAUTH_TOKENS_PATH)
    if not token_p.is_absolute():
        # Assuming project root is where the main script/Dockerfile context is
        # This might need adjustment based on actual execution context
        return Path.cwd() / token_p 
    return token_p

def _save_tokens(credentials: Credentials, settings: Settings):
    token_path = _get_token_path(settings)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_data = {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }
    try:
        with open(token_path, 'w') as f:
            json.dump(token_data, f)
        logger.info(f"Saved Google OAuth tokens to {token_path}")
    except IOError as e:
        logger.error(f"Error saving Google OAuth tokens to {token_path}: {e}", exc_info=True)

def _load_tokens(settings: Settings) -> Optional[Credentials]:
    token_path = _get_token_path(settings)
    if token_path.exists():
        try:
            with open(token_path, 'r') as f:
                token_data = json.load(f)
            # Ensure all necessary fields are present for Credentials object
            if not all(k in token_data for k in ['token', 'token_uri', 'client_id', 'client_secret', 'scopes']):
                logger.warning(f"Token file {token_path} is missing required fields. Ignoring.")
                return None
            creds = Credentials(**token_data)
            # Check if token is expired and try to refresh if refresh_token exists
            if creds.expired and creds.refresh_token:
                try:
                    logger.info("Google OAuth token expired, attempting refresh.")
                    creds.refresh(GoogleAuthRequest()) # google.auth.transport.requests.Request
                    _save_tokens(creds, settings) # Save refreshed tokens
                    logger.info("Successfully refreshed and saved Google OAuth token.")
                except RefreshError as e:
                    logger.error(f"Error refreshing Google OAuth token: {e}. User may need to re-authenticate.", exc_info=True)
                    # Optionally, delete the invalid token file here so user is forced to re-auth
                    # token_path.unlink(missing_ok=True)
                    return None # Indicate refresh failed
            logger.info(f"Loaded Google OAuth tokens from {token_path}")
            return creds
        except (IOError, json.JSONDecodeError, ValueError) as e:
            logger.error(f"Error loading or parsing Google OAuth tokens from {token_path}: {e}", exc_info=True)
    return None

@router.get("/auth/google/login", name="google_login")
async def google_oauth_login(request: Request, settings: Settings = Depends(get_settings)):
    """Initiates the Google OAuth 2.0 authorization flow."""
    client_secret_path = Path(settings.GOOGLE_CLIENT_SECRET_JSON_PATH)
    if not client_secret_path.is_absolute():
        client_secret_path = Path.cwd() / client_secret_path

    if not client_secret_path.exists():
        logger.error(f"Google client_secret.json not found at {client_secret_path}")
        raise HTTPException(status_code=500, detail="Google OAuth client secret file not configured correctly.")

    # Scopes can be combined if needed for multiple services in one go
    # For now, let's assume we want both Calendar and Tasks scopes.
    all_scopes = list(set(settings.GOOGLE_CALENDAR_API_SCOPES + settings.GOOGLE_TASKS_API_SCOPES))

    flow = Flow.from_client_secrets_file(
        str(client_secret_path),
        scopes=all_scopes,
        redirect_uri=settings.GOOGLE_OAUTH_REDIRECT_URI
    )

    # Store the flow in the session or a temporary server-side store if state verification is critical
    # For a simple local app, storing state might be less critical but good practice.
    # request.session['oauth_flow_state'] = flow.authorization_url()[1] # Storing state
    authorization_url, state = flow.authorization_url(
        access_type='offline', # Request refresh token for offline access
        prompt='consent'      # Force consent screen to ensure refresh token is granted
    )
    # Store state in session to verify it in callback, FastAPI session middleware needed for this.
    # As a simpler alternative for local app, we can skip strict state check for now if session middleware is not set up.
    # logger.debug(f"Generated OAuth state: {state}") # Requires session middleware
    
    logger.info(f"Redirecting user to Google OAuth consent screen: {authorization_url}")
    return RedirectResponse(authorization_url)

@router.get("/auth/google/callback", name="google_callback", response_class=HTMLResponse)
async def google_oauth_callback(
    request: Request, 
    code: str = Query(...), 
    # state: Optional[str] = Query(None), # If using state verification
    settings: Settings = Depends(get_settings),
    templates: Jinja2Templates = Depends(get_templates)
):
    """Handles the callback from Google after user authorization."""
    logger.info(f"Received callback from Google OAuth with authorization code.")
    # State verification would happen here if implemented
    # stored_state = request.session.pop('oauth_flow_state', None)
    # if not state or state != stored_state:
    #     raise HTTPException(status_code=400, detail="OAuth state mismatch.")

    client_secret_path = Path(settings.GOOGLE_CLIENT_SECRET_JSON_PATH)
    if not client_secret_path.is_absolute():
        client_secret_path = Path.cwd() / client_secret_path

    if not client_secret_path.exists(): # Should have been caught in login, but double check
        logger.error(f"Google client_secret.json not found at {client_secret_path} during callback.")
        return templates.TemplateResponse("message_display.html", {"request": request, "title": "OAuth Error", "message": "Critical OAuth configuration error."}, status_code=500)

    all_scopes = list(set(settings.GOOGLE_CALENDAR_API_SCOPES + settings.GOOGLE_TASKS_API_SCOPES))
    flow = Flow.from_client_secrets_file(
        str(client_secret_path),
        scopes=all_scopes,
        redirect_uri=settings.GOOGLE_OAUTH_REDIRECT_URI
    )

    try:
        flow.fetch_token(code=code)
        credentials = flow.credentials
        _save_tokens(credentials, settings)
        logger.info("Successfully fetched and saved Google OAuth tokens.")
        # Redirect to a success page or back to the actionables UI
        # For now, just a simple success message page.
        # Ensure you have a 'message_display.html' template or similar.
        return templates.TemplateResponse("message_display.html", {"request": request, "title": "Google Authentication Successful", "message": "Successfully authenticated with Google. You can now export items."})
    except Exception as e:
        logger.error(f"Error fetching or saving Google OAuth token: {e}", exc_info=True)
        return templates.TemplateResponse("message_display.html", {"request": request, "title": "Google Authentication Failed", "message": f"Could not obtain token from Google: {str(e)}"}, status_code=400)

# Helper function to get credentials (used by service endpoints)
# This could also be a dependency
def get_google_credentials(settings: Settings = Depends(get_settings)) -> Optional[Credentials]:
    """Loads stored Google OAuth credentials. If not found or invalid, user needs to login."""
    return _load_tokens(settings) 