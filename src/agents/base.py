import os
from langchain_google_genai import ChatGoogleGenerativeAI
from src.utils.config_loader import config

def get_llm(temperature: float = None) -> ChatGoogleGenerativeAI:
    """Merkezi LLM nesnesini yaratır ve konfigüre eder."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY bulunamadı! Lütfen .env dosyanızı kontrol edin.")
        
    pipeline_conf = config.get("pipeline", {})
    # Fallback model for testing without quota issues
    model_name = pipeline_conf.get("llm_model", "gemini-2.5-flash")
    
    if temperature is None:
        temperature = pipeline_conf.get("llm_temperature", 0.7)
        
    return ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=api_key,
        temperature=temperature,
        max_retries=3
    )
