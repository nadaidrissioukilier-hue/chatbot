"""Client HTTP vers llama.cpp (VM1) - Pure requests, pas de package openai"""
from typing import Dict, Any, List
import requests
import json
from src.config import LLAMACPP_URL, LLAMACPP_MODEL, LLAMACPP_TIMEOUT

class LlamaCppClient:
    """Client HTTP natif pour llama.cpp (compatible avec /v1/chat/completions)"""

    def __init__(self, base_url: str = LLAMACPP_URL):
        self.base_url = base_url.rstrip("/")
        self.model = LLAMACPP_MODEL
        self.timeout = LLAMACPP_TIMEOUT
    
    def health_check(self) -> bool:
        """Vérifie la disponibilité du serveur"""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=5)
            return response.status_code == 200
        except requests.RequestException:
            return False
    
    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
        stream: bool = False,
        **kwargs
    ) -> Dict[str, Any] | str:
        """
        Chat completion via /v1/chat/completions
        Compatible avec format OpenAI mais sur localhost llama.cpp
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "stream": stream,
            **kwargs
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/v1/chat/completions",
                json=payload,
                timeout=self.timeout,
                stream=stream
            )
            response.raise_for_status()
            
            if stream:
                return response
            
            result = response.json()
            return result.get("choices", [{}])[0].get("message", {}).get("content", "")
        
        except requests.RequestException as e:
            raise RuntimeError(f"Erreur llama.cpp chat: {str(e)}")
    
    def generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
        **kwargs
    ) -> str:
        """Génère du texte (format legacy /completion)"""
        
        payload = {
            "prompt": prompt,
            "n_predict": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "stop": ["<|end_of_text|>", "\n\n"],
            **kwargs
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/completion",
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            result = response.json()
            return result.get("content", "").strip()
        except requests.RequestException as e:
            raise RuntimeError(f"Erreur llama.cpp: {str(e)}")
    
    def stream_chat_completion(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 512,
        **kwargs
    ):
        """Streaming chat completion (SSE)"""
        
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "stream": True,
            **kwargs
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/v1/chat/completions",
                json=payload,
                stream=True,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            for line in response.iter_lines():
                if not line:
                    continue
                
                line_str = line.decode() if isinstance(line, bytes) else line
                
                if line_str.startswith("data: "):
                    data_str = line_str[6:].strip()
                    if data_str == "[DONE]":
                        break
                    
                    try:
                        data = json.loads(data_str)
                        delta = data.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        pass
        
        except requests.RequestException as e:
            raise RuntimeError(f"Erreur streaming: {str(e)}")
    
    def get_model_info(self) -> Dict[str, Any]:
        """Récupère les infos du modèle"""
        try:
            response = requests.get(f"{self.base_url}/v1/models", timeout=5)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise RuntimeError(f"Erreur model info: {str(e)}")
