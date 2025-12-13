import os
import logging
from typing import Dict, Optional
from dataclasses import dataclass

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


@dataclass
class LLMResponse:
    content: str
    usage_stats: Optional[Dict] = None
    model_used: Optional[str] = None
    finish_reason: Optional[str] = None


class LLMManager:
    """
    Manages interactions with OpenAI's ChatGPT API.
    
    This class provides a unified interface for making LLM API calls,
    specifically for generating JSON responses based on prompts.
    
    Environment Variables:
        OPENAI_API_KEY: Your OpenAI API key (required)
    
    Example:
        >>> llm = LLMManager()
        >>> response = llm.call_genai_api("Analyze this model...")
        >>> print(response.content)
    """
    
    def __init__(self):
        """
        Initialize the LLM Manager with OpenAI client.
        
        Raises:
            ValueError: If OPENAI_API_KEY is not set in environment variables
            ImportError: If openai package is not installed
        """
        if OpenAI is None:
            raise ImportError(
                "OpenAI package not installed. Run: pip install openai"
            )
        
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OPENAI_API_KEY not configured. Cannot make API calls. "
                "Please set your OpenAI API key in the environment variables."
            )
        
        # Initialize OpenAI client
        self.client = OpenAI(api_key=self.api_key)

    def call_genai_api(self, prompt: str, model: Optional[str] = None
                       ) -> LLMResponse:
        """
        Call OpenAI's Chat Completions API with the given prompt.
        
        This method sends a prompt to OpenAI's API and returns a structured
        response. The system is configured to return valid JSON only.
        
        Args:
            prompt: The user prompt to send to the LLM
            model: Optional model name (defaults to "gpt-4o-mini" for cost-efficiency)
        
        Returns:
            LLMResponse: A structured response containing:
                - content: The LLM's response text
                - usage_stats: Token usage statistics
                - model_used: The model that was used
                - finish_reason: Why the completion finished
        
        Raises:
            RuntimeError: If the API call fails
        
        Example:
            >>> llm = LLMManager()
            >>> response = llm.call_genai_api("Generate JSON for model metrics")
            >>> print(response.content)  # JSON string
            >>> print(response.usage_stats)  # {'prompt_tokens': 50, ...}
        """
        # Use gpt-4o-mini by default for cost-efficiency
        # Can also use "gpt-4o" for more complex tasks
        model_name = model or "gpt-4o-mini"
        
        try:
            # Make the API call using OpenAI's chat completions
            response = self.client.chat.completions.create(
                model=model_name,
                messages=[
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
                temperature=0.1,  # Low temperature for more deterministic outputs
                max_tokens=512,   # Sufficient for most JSON responses
                stream=False
            )
            
            # Extract the response content
            content = response.choices[0].message.content or ""
            
            # Build usage statistics dictionary
            usage_stats = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            }
            
            # Get finish reason
            finish_reason = response.choices[0].finish_reason or "stop"
            
            return LLMResponse(
                content=content,
                usage_stats=usage_stats,
                model_used=model_name,
                finish_reason=finish_reason
            )
            
        except Exception as e:
            logging.error(f"OpenAI API call failed: {e}")
            raise RuntimeError(f"Failed to call OpenAI API: {e}")
