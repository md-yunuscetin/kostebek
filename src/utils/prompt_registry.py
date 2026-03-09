from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field
from datetime import datetime
import json
import uuid
import redis

from src.utils.logger import get_logger

logger = get_logger("prompt_registry")

class PromptVersion(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_name: str
    content: str
    status: Literal["candidate", "active", "retired"] = "candidate"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    performance_score: Optional[float] = None
    notes: Optional[str] = None

class PromptRegistry:
    def __init__(self, redis_client):
        """
        Redis tabanlı Prompt Versiyon Yönetim Sistemi.
        Redis'te her ajanın kendi Hash yapısı olur.
        """
        self.redis = redis_client
        self.prefix = "prompt_registry:"

    def _get_key(self, agent_name: str) -> str:
        return f"{self.prefix}{agent_name}"

    def register_prompt(self, agent_name: str, content: str, status: Literal["candidate", "active", "retired"] = "candidate", notes: str = None) -> PromptVersion:
        """Yeni bir prompt versiyonu kaydeder"""
        prompt = PromptVersion(
            agent_name=agent_name,
            content=content,
            status=status,
            notes=notes
        )
        key = self._get_key(agent_name)
        
        # Eğer statü active yapılmışsa eski active'leri retired yap
        if status == "active":
            self._retire_current_active(agent_name)
            
        self.redis.hset(key, prompt.id, prompt.model_dump_json())
        logger.info(f"[REGISTRY] Yeni prompt ({status}) kaydedildi: {agent_name} -> ID: {prompt.id}")
        return prompt

    def get_active_prompt(self, agent_name: str) -> Optional[PromptVersion]:
        """Bir ajanın güncel aktif (active) promptunu döndürür."""
        key = self._get_key(agent_name)
        all_prompts_raw = self.redis.hgetall(key)
        
        for p_id, p_json in all_prompts_raw.items():
            prompt_dict = json.loads(p_json.decode('utf-8'))
            if prompt_dict.get("status") == "active":
                return PromptVersion(**prompt_dict)
                
        return None

    def get_candidate_prompts(self, agent_name: str) -> List[PromptVersion]:
        """Ajan için onay bekleyen deneme yanılma promptlarını döndürür."""
        key = self._get_key(agent_name)
        all_prompts_raw = self.redis.hgetall(key)
        
        candidates = []
        for p_id, p_json in all_prompts_raw.items():
            prompt_dict = json.loads(p_json.decode('utf-8'))
            if prompt_dict.get("status") == "candidate":
                candidates.append(PromptVersion(**prompt_dict))
                
        return candidates

    def activate_prompt(self, agent_name: str, prompt_id: str):
        """Spesifik bir prompt_id'yi active konuma geçirir ve öncekini emekli eder."""
        key = self._get_key(agent_name)
        prompt_raw = self.redis.hget(key, prompt_id)
        if not prompt_raw:
            logger.error(f"[REGISTRY] Promp ID {prompt_id} bulunamadı!")
            return False
            
        prompt = PromptVersion(**json.loads(prompt_raw.decode('utf-8')))
        self._retire_current_active(agent_name)
        
        prompt.status = "active"
        self.redis.hset(key, prompt.id, prompt.model_dump_json())
        logger.info(f"[REGISTRY] Prompt {prompt.id} AKTİVE EDİLDİ.")
        return True

    def _retire_current_active(self, agent_name: str):
        """Sistemin önceki aktif promptunu retired konumuna alır."""
        active = self.get_active_prompt(agent_name)
        if active:
            active.status = "retired"
            key = self._get_key(agent_name)
            self.redis.hset(key, active.id, active.model_dump_json())
            logger.debug(f"[REGISTRY] Eski prompt ({active.id}) emekliye ayrıldı.")

# Global (Singleton) kullanım için:
_registry_instance = None
_registry_checked = False   # Bir kez kontrol et, hepsinde tekrar deneme

def get_registry() -> Optional[PromptRegistry]:
    global _registry_instance, _registry_checked

    if _registry_checked:
        return _registry_instance   # Zaten doğrulandı (veya Redis yok), tekrar ping atma

    _registry_checked = True
    try:
        client = redis.Redis(
            host="localhost",
            port=6379,
            socket_connect_timeout=2,
            socket_timeout=2,
            decode_responses=True
        )
        client.ping()   # ← GERÇEK bağlantı testi
        _registry_instance = PromptRegistry(client)
        logger.info("✅ PromptRegistry: Redis bağlantısı doğrulandı.")
    except (redis.ConnectionError, redis.TimeoutError, Exception) as e:
        logger.warning(
            f"⚠️ PromptRegistry: Redis yok ({type(e).__name__}). "
            "Prompt versiyonlama devre dışı — varsayılan promptlar kullanılacak."
        )
        _registry_instance = None
    return _registry_instance


