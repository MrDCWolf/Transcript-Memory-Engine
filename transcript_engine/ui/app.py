"""Streamlit UI for interacting with the Transcript Memory Engine RAG API."""

import streamlit as st
import httpx
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Configuration ---
BACKEND_API_URL = "http://localhost:8000/api/v1/chat/query" # URL of your FastAPI backend
REQUEST_TIMEOUT = 30.0 # seconds

# --- Streamlit App Layout ---
st.set_page_config(page_title="Transcript Memory Engine", layout="wide")
st.title("🧠 Transcript Memory Engine")
st.caption("Ask questions about your ingested transcripts.")

# --- User Input ---
query_text = st.text_input("Enter your query:", key="query_input")

# Add input for k
k_value = st.number_input(
    "Number of chunks (k):", 
    min_value=1, 
    max_value=50, # Allow up to 50 chunks
    value=5, # Default to 5
    step=1,
    help="How many relevant transcript chunks should be retrieved to answer the query?"
)

submit_button = st.button("Ask", key="ask_button")

# --- API Call and Response Handling ---
if submit_button and query_text:
    st.markdown("--- *Thinking...* ---")
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            payload = {"query_text": query_text, "k": k_value}
            logger.info(f"Sending query to backend: {payload}")
            response = client.post(BACKEND_API_URL, json=payload)
            response.raise_for_status() # Raise exception for 4xx/5xx errors
            
            response_data = response.json()
            answer = response_data.get("answer", "Error: No answer found in response.")
            
            logger.info(f"Received answer from backend: {answer[:100]}...")
            st.markdown("### Answer:")
            st.markdown(answer)
            
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error calling backend: {e.response.status_code} - {e.response.text}", exc_info=True)
        st.error(f"Error communicating with backend: {e.response.status_code}")
        st.error(f"Details: {e.response.text}")
    except httpx.RequestError as e:
        logger.error(f"Request error calling backend: {e}", exc_info=True)
        st.error("Error: Could not connect to the backend API. Is it running?")
        st.error(f"Details: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)
        st.error("An unexpected error occurred.")
        st.exception(e)
elif submit_button and not query_text:
    st.warning("Please enter a query.") 