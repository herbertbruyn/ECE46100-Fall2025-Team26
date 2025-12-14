import os
import logging
import requests
from typing import Dict, Optional
from dataclasses import dataclass


@dataclass
class LLMResponse:
    content: str
    usage_stats: Optional[Dict] = None
    model_used: Optional[str] = None
    finish_reason: Optional[str] = None


class LLMManager:
    def __init__(self):
        """Initialize the LLM Manager with Purdue GenAI Studio API."""
        
        self.api_key = os.getenv("GEN_AI_STUDIO_API_KEY")
        if not self.api_key:
            raise ValueError(
                "GEN_AI_STUDIO_API_KEY not configured. Cannot make API calls."
            )

    def call_genai_api(self, prompt: str, model: Optional[str] = None
                       ) -> LLMResponse:
        """
        Call Purdue GenAI Studio API with the given prompt.
        
        Args:
            prompt: The user prompt to send to the LLM
            model: Optional model name (defaults to "llama3.1:latest")
        
        Returns:
            LLMResponse: Structured response with content and metadata
        """
        model_name = model or "llama3.1:latest"
        url = "https://genai.rcac.purdue.edu/api/chat/completions"
        
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        body = {
            "model": model_name,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a precise JSON generator. You ALWAYS "
                               "respond with valid JSON and nothing else. No "
                               "explanations, no markdown, no code blocks."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.1,
            "max_tokens": 512,
            "stream": False
        }
        
        try:
            response = requests.post(url, headers=headers, json=body, timeout=30)
            
            
            if response.status_code == 200:
                
                # Parse the JSON response
                try:
                    response_data = response.json()
                except Exception as json_err:
                    raise RuntimeError(f"Failed to parse LLM response as JSON: {json_err}")
                
                # Extract the content from the response
                choices = response_data.get("choices", [])
                
                if choices and len(choices) > 0:
                    message = choices[0].get("message", {})
                    content = message.get("content", "")
                else:
                    content = ""
                
                # Extract usage stats if available
                usage = response_data.get("usage", {})
                
                # Get finish reason
                finish_reason = "STOP"
                if choices:
                    finish_reason = choices[0].get("finish_reason", "STOP")
                    logging.debug(f"[LLM] Finish reason: {finish_reason}")
                
                logging.info(f"[LLM] Successfully completed API call")
                return LLMResponse(
                    content=content,
                    usage_stats=usage if usage else None,
                    model_used=model_name,
                    finish_reason=finish_reason
                )
            else:
                # Non-200 status code
                error_msg = f"HTTP {response.status_code}"
                try:
                    error_body = response.json()
                    logging.error(f"[LLM] API error response: {error_body}")
                    error_msg += f" - {error_body}"
                except:
                    error_text = response.text[:500]
                    logging.error(f"[LLM] API error text: {error_text}")
                    error_msg += f" - {error_text}"
                
                raise Exception(f"Purdue LLM API returned error: {error_msg}")
                
        except requests.exceptions.Timeout as e:
            logging.error(f"[LLM] Request timed out after 30 seconds: {e}")
            raise RuntimeError(f"Purdue LLM API request timed out: {e}")
        except requests.exceptions.ConnectionError as e:
            logging.error(f"[LLM] Connection error to Purdue LLM API: {e}")
            raise RuntimeError(f"Failed to connect to Purdue LLM API: {e}")
        except requests.exceptions.RequestException as e:
            logging.error(f"[LLM] Request exception: {e}")
            raise RuntimeError(f"Purdue LLM API request failed: {e}")
        except Exception as e:
            logging.error(f"[LLM] Unexpected error during API call: {e}")
            logging.error(f"[LLM] Error type: {type(e).__name__}")
            raise RuntimeError(f"Failed to call Purdue LLM API: {e}")
