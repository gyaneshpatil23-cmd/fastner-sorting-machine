"""
Gemini Vision Client module for AI Fastener Inspection System.
Handles API authentication, structured JSON prompt generation, image payload encoding,
response validation, and connection testing.
"""

import json
import re
from typing import Dict, Any, Tuple
import cv2
import numpy as np
from PIL import Image
import io

from config import (
    ALLOWED_CATEGORIES,
    CATEGORY_UNKNOWN,
    DEFAULT_MODEL,
    get_gemini_api_key
)
from logger import app_logger

# System instructions and classification prompt
FASTENER_CLASSIFICATION_PROMPT = """You are an industrial fastener classification vision system.

Analyze the provided image and identify the primary fastener object.
Classify it into EXACTLY ONE of these categories:
- NUT
- BOLT
- SCREW
- WASHER
- UNKNOWN

Focus on visible physical geometry:
- NUT: A threaded internally-holed fastener, commonly hexagonal, square, or flanged.
- BOLT: A fastener with a head and a threaded cylindrical shaft (usually flat blunt end, designed for mating with a nut).
- SCREW: A threaded fastener characterized by a head with a driver slot/recess and often a tapered or pointed shank.
- WASHER: A flat or spring annular ring-shaped component with a central hole for load distribution.
- UNKNOWN: If the image is unclear, blurry, or does not contain a recognizable fastener.

Return ONLY a valid, raw JSON object in the exact format:
{
  "category": "NUT | BOLT | SCREW | WASHER | UNKNOWN",
  "confidence": 0.95,
  "reason": "Short engineering explanation based on visible physical geometry."
}

Do NOT wrap in markdown or backticks if possible, and do not invent any other categories."""


class GeminiVisionClient:
    """Client for interacting with Google Gemini Vision models for fastener classification."""

    def __init__(self, model_name: str = DEFAULT_MODEL):
        self.model_name = model_name

    def set_model(self, model_name: str):
        self.model_name = model_name

    def classify_image(self, cv_img: np.ndarray, model_name: str = None) -> Dict[str, Any]:
        """
        Sends an OpenCV image to Gemini Vision model and returns structured classification dict.
        Returns:
            {
                "success": bool,
                "category": str,
                "confidence": float,
                "reason": str,
                "raw_response": str,
                "error": str (optional)
            }
        """
        api_key = get_gemini_api_key()
        if not api_key:
            return {
                "success": False,
                "category": CATEGORY_UNKNOWN,
                "confidence": 0.0,
                "reason": "Gemini API key is not configured. Please set GEMINI_API_KEY in Settings or .env file.",
                "error": "API_KEY_MISSING"
            }

        target_model = model_name or self.model_name

        try:
            # Convert OpenCV BGR image to PIL Image in RGB format
            rgb_img = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(rgb_img)

            # Call Gemini using google-generativeai SDK
            import google.generativeai as genai
            genai.configure(api_key=api_key)

            # Clean model name if needed
            model_id = target_model if not target_model.startswith("models/") else target_model.replace("models/", "")
            
            # Setup generation configuration
            generation_config = {
                "temperature": 0.1,
                "top_p": 0.95,
                "response_mime_type": "application/json"
            }

            try:
                model = genai.GenerativeModel(
                    model_name=model_id,
                    generation_config=generation_config
                )
                response = model.generate_content([FASTENER_CLASSIFICATION_PROMPT, pil_img])
            except Exception as model_err:
                # Fallback without response_mime_type if model variant lacks JSON mode parameter
                app_logger.warning(f"Standard JSON mode failed, retrying without response_mime_type: {model_err}")
                model = genai.GenerativeModel(model_name=model_id)
                response = model.generate_content([FASTENER_CLASSIFICATION_PROMPT, pil_img])

            raw_text = response.text if response and hasattr(response, 'text') else ""
            app_logger.debug(f"Gemini Raw Response: {raw_text}")

            parsed_result = self._parse_json_response(raw_text)
            parsed_result["success"] = True
            parsed_result["raw_response"] = raw_text
            return parsed_result

        except Exception as e:
            err_msg = str(e)
            app_logger.error(f"Gemini Classification Exception: {err_msg}")
            
            # Formulate user-friendly error message
            friendly_reason = "AI analysis failed."
            if "API_KEY_INVALID" in err_msg or "API key not valid" in err_msg or "400" in err_msg and "key" in err_msg.lower():
                friendly_reason = "Invalid Gemini API Key. Please verify your key in Settings."
            elif "Quota exceeded" in err_msg or "RESOURCE_EXHAUSTED" in err_msg or "429" in err_msg:
                friendly_reason = "Gemini API rate limit or quota exceeded. Please wait a moment."
            elif "getaddrinfo failed" in err_msg or "ConnectionError" in err_msg or "timeout" in err_msg.lower():
                friendly_reason = "Network error: Unable to connect to Gemini API. Please check internet connection."
            else:
                friendly_reason = f"Analysis Error: {err_msg}"

            return {
                "success": False,
                "category": CATEGORY_UNKNOWN,
                "confidence": 0.0,
                "reason": friendly_reason,
                "error": err_msg
            }

    def _parse_json_response(self, text: str) -> Dict[str, Any]:
        """
        Robustly extracts and validates JSON fields from Gemini response.
        Handles markdown blocks, partial quotes, or slight format deviations.
        """
        clean_text = text.strip()

        # Remove markdown code blocks if present
        if clean_text.startswith("```"):
            clean_text = re.sub(r"^```(?:json)?\s*", "", clean_text)
            clean_text = re.sub(r"\s*```$", "", clean_text)

        data = {}
        try:
            data = json.loads(clean_text)
        except Exception:
            # Fallback regex extraction of JSON object
            match = re.search(r"\{.*\}", clean_text, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(0))
                except Exception:
                    pass

        # Extract and normalize category
        raw_cat = str(data.get("category", "")).strip().upper()
        
        # Match against allowed categories
        category = CATEGORY_UNKNOWN
        for allowed in ALLOWED_CATEGORIES:
            if allowed in raw_cat:
                category = allowed
                break

        # Extract and normalize confidence
        raw_conf = data.get("confidence", 0.0)
        try:
            conf = float(raw_conf)
            if conf > 1.0 and conf <= 100.0:
                conf = conf / 100.0  # Convert percentage to 0.0 - 1.0
            conf = max(0.0, min(1.0, conf))
        except (ValueError, TypeError):
            conf = 0.50 if category != CATEGORY_UNKNOWN else 0.0

        # Extract reason
        reason = data.get("reason", "").strip()
        if not reason:
            if category != CATEGORY_UNKNOWN:
                reason = f"Detected physical geometry consistent with {category.lower()} characteristics."
            else:
                reason = "Object geometry could not be definitively classified into standard fastener categories."

        return {
            "category": category,
            "confidence": conf,
            "reason": reason
        }

    def test_connection(self, model_name: str = None) -> Tuple[bool, str]:
        """
        Tests API connectivity and authentication with Gemini.
        Returns (is_connected, status_message).
        """
        api_key = get_gemini_api_key()
        if not api_key:
            return False, "GEMINI_API_KEY is not set. Please configure your API key."

        target_model = model_name or self.model_name
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            
            model_id = target_model if not target_model.startswith("models/") else target_model.replace("models/", "")
            model = genai.GenerativeModel(model_name=model_id)
            
            # Simple minimal prompt to verify connection
            resp = model.generate_content("Respond with one word: 'CONNECTED'")
            if resp and resp.text:
                return True, f"Successfully connected to Gemini ({target_model})."
            return False, "Received empty response from Gemini API."
        except Exception as e:
            err_msg = str(e)
            if "API_KEY_INVALID" in err_msg or "API key not valid" in err_msg:
                return False, "Invalid API Key: Authentication failed."
            elif "404" in err_msg or "models/" in err_msg:
                return False, f"Model '{target_model}' not found or not supported for this API key."
            return False, f"Connection test failed: {err_msg}"
