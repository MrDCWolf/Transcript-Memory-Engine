"""Service layer for the Actionable Items feature.

This service will contain the core logic for identifying candidates
from transcript segments using an LLM and parsing the results.
"""

import logging
from datetime import date
from typing import List, Optional
import re # For parsing LLM output

from transcript_engine.interfaces.llm_interface import LLMInterface
from transcript_engine.features.actionables_models import (
    CandidateActionableItem, 
    GoogleCalendarEventSchema, 
    GoogleTaskSchema, 
    GoogleReminderSchema
)
from transcript_engine.core.config import get_settings
from transcript_engine.features.actionables_models import CandidateActionableItem

logger = logging.getLogger(__name__)

def scan_transcript_for_actionables(
    transcript_segment: str,
    llm_service: LLMInterface,
    target_date: date,
    timeframe_key: str,
) -> List[CandidateActionableItem]:
    """Scans a transcript segment for actionable items using an LLM.

    Args:
        transcript_segment: The text content of the transcript for the timeframe.
        llm_service: An instance of an LLM service (conforming to LLMInterface).
        target_date: The date of the transcript segment.
        timeframe_key: The timeframe key (e.g., "morning", "afternoon").

    Returns:
        A list of CandidateActionableItem objects found in the segment.
    """
    if not transcript_segment or transcript_segment.isspace():
        logger.info("Transcript segment is empty. No actionables to scan.")
        return []

    # Construct the prompt for the LLM
    # Ensure date is formatted to string for the prompt
    formatted_date = target_date.strftime('%Y-%m-%d')
    system_prompt = f"""System: You are an AI assistant helping to extract actionable items from conversation transcripts. Analyze the following transcript segment from the {timeframe_key} of {formatted_date}. Identify any phrases or sentences that suggest a reminder, a calendar event/meeting, or a task.

For each item found, provide:
1. The exact text snippet.
2. Your suggested category (must be one of: REMINDER, EVENT, TASK).
3. Any people, specific times, or dates mentioned in the snippet, as heard.

Transcript Segment:
---
{transcript_segment}
---

Identified Items (provide as a list, each item starting with '- Snippet:', then '  Category:', then '  Entities:', each on a new line. If no items are found, respond with "No actionable items found."):
"""

    logger.debug(f"Sending prompt to LLM for actionable items scan:\n{system_prompt}")

    try:
        raw_llm_response = llm_service.generate(prompt=system_prompt)
        logger.debug(f"Raw LLM response:\n{raw_llm_response}")
    except Exception as e:
        logger.error(f"Error calling LLM service: {e}", exc_info=True)
        return []

    if not raw_llm_response or raw_llm_response.strip().lower() == "no actionable items found." or "no actionable items found" in raw_llm_response.lower():
        logger.info("LLM indicated no actionable items found.")
        return []

    # Parse the LLM output
    # This parsing logic assumes the LLM follows the specified format reasonably well.
    # It looks for items starting with "- Snippet:"
    # Each item is expected to have "Category:" and "Entities:" on subsequent lines.
    
    candidates: List[CandidateActionableItem] = []
    # Split the response into potential items. Each item starts with "- Snippet:"
    # Using a regex that captures content after markers and handles optional multiline snippets.
    # This regex is a bit more robust to variations in spacing and newlines.
    # It looks for "- Snippet:" then captures everything until "Category:", etc.
    
    # Regex to find blocks: starts with "- Snippet:", then "Category:", then "Entities:"
    # It allows for multiline content in snippet and entities.
    # (?s) is for DOTALL mode, making . match newlines.
    # item_pattern = re.compile(r"- Snippet:(.*?)(?:\n\s*Category:(.*?))?(?:\n\s*Entities:(.*?))?(?=\n- Snippet:|$)", re.DOTALL | re.IGNORECASE)

    # Simpler line-by-line parsing might be more robust initially if LLM output is clean item per item.
    # Let's try splitting by "- Snippet:" first, then processing each block.
    
    raw_items = raw_llm_response.split("- Snippet:")
    
    for raw_item_block in raw_items:
        if not raw_item_block.strip(): # Skip empty blocks (e.g., from the first split if response starts with "- Snippet:")
            continue

        snippet_text: Optional[str] = None
        category_text: Optional[str] = None
        entities_text: Optional[str] = None

        lines = raw_item_block.strip().split('\n')
        
        # The first line of the block (after "- Snippet:") is the snippet itself.
        # It might be multiline, so we need to reconstruct it carefully if parsing line by line.
        current_parsing_field = "snippet" # Default to snippet
        current_snippet_lines = []
        current_entities_lines = []

        # First line is snippet content (or start of it)
        if lines:
            first_line_content = lines.pop(0).strip()
            current_snippet_lines.append(first_line_content)

        for line in lines:
            line_stripped = line.strip()
            if line_stripped.lower().startswith("category:"):
                current_parsing_field = "category"
                category_text = line_stripped.lower().replace("category:", "", 1).strip().upper()
                # Validate category - simple check for now
                if category_text not in ["REMINDER", "EVENT", "TASK"]:
                    logger.warning(f"LLM returned invalid category '{category_text}'. Skipping this part of item.")
                    category_text = None # Or a default, or skip item
                continue
            elif line_stripped.lower().startswith("entities:"):
                current_parsing_field = "entities"
                entities_text = line_stripped.lower().replace("entities:", "", 1).strip()
                current_entities_lines.append(entities_text) # Start of entities
                continue
            
            # Continue accumulating multiline content based on current field
            if current_parsing_field == "snippet":
                current_snippet_lines.append(line.strip()) # Keep original spacing for snippet lines
            elif current_parsing_field == "entities":
                current_entities_lines.append(line.strip())
        
        snippet_text = "\n".join(current_snippet_lines).strip()
        if not snippet_text: # If snippet is empty after processing, skip
            logger.warning(f"Parsed an item block but snippet was empty. Block: {raw_item_block}")
            continue
            
        if current_entities_lines: # If entities parsing started
             entities_text = "\n".join(current_entities_lines).strip()
        elif entities_text: # If entities was single line and already captured
            pass # entities_text is already set
        else: # No entities found for this item
            entities_text = None

        if snippet_text and category_text: # Category is mandatory along with snippet
            try:
                candidate = CandidateActionableItem(
                    snippet=snippet_text,
                    suggested_category=category_text,
                    raw_entities=entities_text
                )
                candidates.append(candidate)
                logger.debug(f"Parsed actionable candidate: {candidate}")
            except Exception as e:
                logger.error(f"Error creating CandidateActionableItem for snippet '{snippet_text[:50]}...': {e}", exc_info=True)
        elif snippet_text and not category_text:
             logger.warning(f"Found snippet '{snippet_text[:50]}...' but no valid category. Skipping item.")

    if not candidates and raw_llm_response and raw_llm_response.strip():
        logger.warning(f"LLM response was not empty but no actionable items could be parsed. Response: {raw_llm_response}")

    return candidates

# New function starts here
from openai import OpenAI # Added
import json # Added
from transcript_engine.core.config import get_settings # Added
from transcript_engine.features.actionables_models import (
    GoogleCalendarEventSchema, 
    GoogleTaskSchema, 
    GoogleReminderSchema
) # Specific models for this function

def extract_structured_data_for_item(
    item_snippet: str, 
    item_category: str, 
    target_date: date # Added to provide context for relative dates like "tomorrow"
) -> Optional[dict]:
    """Extracts structured data from a snippet using a cloud LLM (OpenAI) with function calling.

    Args:
        item_snippet: The text snippet of the confirmed actionable item.
        item_category: The final category ("EVENT", "TASK", "REMINDER") of the item.
        target_date: The date the original transcript segment was for, to help resolve relative dates.

    Returns:
        A dictionary representing the structured data (validated against the Pydantic schema),
        or None if extraction fails or API key is not configured.
    """
    settings = get_settings()
    if not settings.OPENAI_API_KEY:
        logger.warning("OpenAI API key is not configured. Skipping structured data extraction.")
        return None

    client = OpenAI(api_key=settings.OPENAI_API_KEY)

    schema_map = {
        "EVENT": GoogleCalendarEventSchema,
        "TASK": GoogleTaskSchema,
        "REMINDER": GoogleReminderSchema,
    }

    if item_category not in schema_map:
        logger.error(f"Invalid item_category: {item_category} for structured extraction.")
        return None

    TargetSchema = schema_map[item_category]
    function_name = f"create_google_{item_category.lower()}"
    
    tools = [
        {
            "type": "function",
            "function": {
                "name": function_name,
                "description": f"Extract details for a {item_category.lower()} from the text and populate the fields.",
                "parameters": TargetSchema.model_json_schema()
            }
        }
    ]

    current_date_for_context = target_date.strftime("%Y-%m-%d")
    
    prompt_messages = [
        {
            "role": "system", 
            "content": f"You are an expert assistant that extracts structured information from text. Today's date for context is {current_date_for_context}. When extracting datetimes, provide them in ISO 8601 format. For calendar events, if no end time is specified but a start time is, assume a 1-hour duration if reasonable for the context, otherwise leave end_datetime null. For tasks, if no due date is specified, leave due_date null."
        },
        {
            "role": "user", 
            "content": f"Based on the following text, extract the details to populate the {item_category.lower()} structure: '{item_snippet}'"
        }
    ]

    logger.debug(f"Sending request to OpenAI for structured extraction. Model: {settings.OPENAI_CHAT_MODEL_NAME}, Function: {function_name}")
    logger.debug(f"Prompt messages: {prompt_messages}")
    logger.debug(f"Tool definition (parameters schema): {tools[0]['function']['parameters']}")

    try:
        response = client.chat.completions.create(
            model=settings.OPENAI_CHAT_MODEL_NAME,
            messages=prompt_messages,
            tools=tools,
            tool_choice={"type": "function", "function": {"name": function_name}} # Force call this function
        )
        
        message = response.choices[0].message
        if message.tool_calls and message.tool_calls[0].function.name == function_name:
            function_args_json = message.tool_calls[0].function.arguments
            logger.debug(f"OpenAI returned function call with arguments: {function_args_json}")
            try:
                extracted_data_dict = json.loads(function_args_json)
                validated_data = TargetSchema(**extracted_data_dict)
                logger.info(f"Successfully extracted and validated structured data for {item_category}: {validated_data.model_dump()}")
                return validated_data.model_dump() # Return as dict
            except json.JSONDecodeError as json_err:
                logger.error(f"Failed to parse JSON arguments from OpenAI: {json_err}. Raw args: {function_args_json}", exc_info=True)
                return None
            except Exception as pydantic_err: # Catches Pydantic validation errors
                logger.error(f"Failed to validate extracted data against {TargetSchema.__name__}: {pydantic_err}. Raw data: {function_args_json}", exc_info=True)
                return None
        else:
            logger.warning(f"OpenAI did not return the expected function call. Response message: {message}")
            return None

    except Exception as e:
        logger.error(f"Error calling OpenAI API for structured extraction: {e}", exc_info=True)
        return None

# Removed the duplicate TODO comment line that was at the end of the file previously 