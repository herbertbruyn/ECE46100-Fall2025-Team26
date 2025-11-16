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
        self.genai_api_key = os.getenv("GEN_AI_STUDIO_API_KEY")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.provider = None

        if self.gemini_api_key:
            self.provider = "gemini"
        elif self.genai_api_key:
            self.provider = "genai"
        else:
            raise ValueError(
                "Neither GEN_AI_STUDIO_API_KEY nor GEMINI_API_KEY are configured. Cannot make API calls."
            )

    def call_llm_api(self, prompt: str, model: Optional[str] = None) -> LLMResponse:
        if self.provider == "genai":
            return self._call_genai_api(prompt, model)
        elif self.provider == "gemini":
            return self._call_gemini_api(prompt, model)
        else:
            # This should not be reached given the __init__ logic
            raise RuntimeError("No LLM provider configured.")

    def _call_genai_api(self, prompt: str, model: Optional[str] = None) -> LLMResponse:
        url = "https://genai.rcac.purdue.edu/api/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.genai_api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": model or "llama3.1:latest",
            "messages": [
                {
                    "role": "system",
                    "content": "You are a precise JSON generator. You ALWAYS "
                    "respond with valid JSON and nothing else. No "
                    "explanations, no markdown, no code blocks.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 512,
            "stream": False,
        }

        try:
            response = requests.post(url, headers=headers, json=body)
            if response.status_code == 200:
                response_data = response.json()
                choices = response_data.get("choices", [])
                content = ""
                if choices:
                    message = choices[0].get("message", {})
                    content = message.get("content", "")

                usage = response_data.get("usage", {})
                finish_reason = "STOP"
                if choices:
                    finish_reason = choices[0].get("finish_reason", "STOP")

                return LLMResponse(
                    content=content,
                    usage_stats=usage if usage else None,
                    model_used=model or "llama3.1:latest",
                    finish_reason=finish_reason,
                )
            else:
                raise Exception(f"Error: {response.status_code}, {response.text}")
        except Exception as e:
            logging.error(f"Purdue LLM API call failed: {e}")
            raise RuntimeError(f"Failed to call Purdue LLM API: {e}")

    def _call_gemini_api(self, prompt: str, model: Optional[str] = None) -> LLMResponse:
        # Use gemini-1.5-flash-latest by default if no model is specified
        model_name = model or "gemini-2.0-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"

        headers = {
            "Content-Type": "application/json",
            "X-goog-api-key": self.gemini_api_key
        }
        
        # Combine system and user prompts for Gemini
        full_prompt = (
            "You are a precise JSON generator. You ALWAYS respond with valid JSON and nothing else. "
            "No explanations, no markdown, no code blocks.\n\n"
            f"{prompt}"
        )

        body = {"contents": [{"parts": [{"text": full_prompt}]}]}

        try:
            response = requests.post(url, headers=headers, json=body)
            if response.status_code == 200:
                response_data = response.json()
                
                # Extract content from the Gemini response
                candidates = response_data.get("candidates", [])
                content = ""
                if candidates:
                    first_candidate = candidates[0]
                    if "content" in first_candidate and "parts" in first_candidate["content"]:
                        content_parts = first_candidate["content"]["parts"]
                        if content_parts:
                            content = content_parts[0].get("text", "")

                # Gemini API (v1beta) does not provide detailed usage stats or finish reason in the same way
                # We'll populate with reasonable defaults
                finish_reason = "STOP" # Default, can be refined if API provides it
                if candidates:
                    finish_reason = candidates[0].get("finishReason", "STOP")

                return LLMResponse(
                    content=content,
                    usage_stats=None,  # Not available in this response format
                    model_used=model_name,
                    finish_reason=finish_reason,
                )
            else:
                raise Exception(f"Error: {response.status_code}, {response.text}")
        except Exception as e:
            logging.error(f"Gemini API call failed: {e}")
            raise RuntimeError(f"Failed to call Gemini API: {e}")
