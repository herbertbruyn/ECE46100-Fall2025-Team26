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
        # logging.info("Initializing LLM Manager...")
        
        self.api_key = os.getenv("GEN_AI_STUDIO_API_KEY")
        if not self.api_key:
            logging.error("GEN_AI_STUDIO_API_KEY environment variable not found")
            raise ValueError(
                "GEN_AI_STUDIO_API_KEY not configured. Cannot make API calls."
            )
        
        # Log successful initialization (mask most of the key for security)
        # masked_key = f"{self.api_key[:8]}...{self.api_key[-4:]}" if len(self.api_key) > 12 else "***"
        # logging.info(f"LLM Manager initialized successfully with API key: {masked_key}")

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
        
        # Log the API call details
        # prompt_preview = prompt[:200] + "..." if len(prompt) > 200 else prompt
        # logging.info(f"[LLM] Making API call to Purdue GenAI Studio")
        # logging.info(f"[LLM] Model: {model_name}")
        # logging.info(f"[LLM] Prompt length: {len(prompt)} characters")
        # logging.debug(f"[LLM] Prompt preview: {prompt_preview}")
        
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
            # logging.info(f"[LLM] Sending POST request to {url}")
            # Increased timeout for free-tier EC2 with potentially slower API responses
            response = requests.post(url, headers=headers, json=body, timeout=60)
            
            # logging.info(f"[LLM] Response status code: {response.status_code}")
            
            if response.status_code == 200:
                # logging.info(f"[LLM] API call successful - parsing response")
                
                # Parse the JSON response
                try:
                    response_data = response.json()
                    # logging.debug(f"[LLM] Response data structure: {list(response_data.keys())}")
                except Exception as json_err:
                    logging.error(f"[LLM] Failed to parse JSON response: {json_err}")
                    logging.error(f"[LLM] Raw response text: {response.text[:500]}")
                    raise RuntimeError(f"Failed to parse LLM response as JSON: {json_err}")
                
                # Extract the content from the response
                choices = response_data.get("choices", [])
                # logging.debug(f"[LLM] Number of choices in response: {len(choices)}")
                
                if choices and len(choices) > 0:
                    message = choices[0].get("message", {})
                    content = message.get("content", "")
                    # logging.info(f"[LLM] Extracted content length: {len(content)} characters")
                    # logging.debug(f"[LLM] Content preview: {content[:200]}")
                else:
                    content = ""
                    logging.warning("[LLM] No choices found in response, using empty content")
                
                # Extract usage stats if available
                usage = response_data.get("usage", {})
                # if usage:
                #     logging.info(f"[LLM] Token usage: {usage}")
                # else:
                #     logging.debug("[LLM] No usage stats in response")
                
                # Get finish reason
                finish_reason = "STOP"
                if choices:
                    finish_reason = choices[0].get("finish_reason", "STOP")
                    # logging.debug(f"[LLM] Finish reason: {finish_reason}")
                
                # logging.info(f"[LLM] Successfully completed API call")
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
