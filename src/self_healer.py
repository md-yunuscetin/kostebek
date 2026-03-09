from pydantic import BaseModel
from typing import Literal
from src.state import AgentState
from src.utils.logger import get_logger

logger = get_logger("self_healer")

class HealerOutcome(BaseModel):
    healed: bool = False
    action: Literal["lower_temperature", "switch_model", "relax_filters", "skip_source", "abort"]
    scope: Literal["run_only", "session", "permanent"]
    details: str

class SelfHealingOrchestrator:
    """Pipeline hatalarını tespit edip sadece onarım 'kararı' veren (mutasyon yapmayan) diagnostik meta-ajan."""
    
    def diagnose(self, error: Exception, state: AgentState) -> HealerOutcome:
        """Config'e kesinlikle dokunmaz. Hata log'una göre aksiyon kararı verir."""
        if not error:
            return HealerOutcome(healed=False, action="abort", scope="run_only", details="Hata yok.")
            
        error_str = str(error).lower()
        
        # 1. API Kotası / Rate Limit Hatası
        if "429" in error_str or "quota" in error_str or "rate limit" in error_str:
            return HealerOutcome(
                healed=True, 
                action="switch_model",
                scope="run_only",
                details="Rate limit / Quota aşıldı: gemini-2.5-flash modeline geçerek devam et."
            )
            
        # 2. Kaynaktan veri çekilememe (Boş dönüş)
        if "empty_scraper" in error_str or len(state.get("raw_data", [])) == 0:
            return HealerOutcome(
                healed=True, 
                action="relax_filters",
                scope="run_only",
                details="Scraper veri bulamadı: min_score eşiğini 10 puan düşür."
            )
            
        # 3. Beklenmeyen Parse Formatı Hatası
        if "json" in error_str or "validation" in error_str or "parse" in error_str:
            return HealerOutcome(
                healed=True,
                action="lower_temperature",
                scope="run_only",
                details="LLM JSON üretemedi: Temperature'ı düşür."
            )
            
        # Bilinmeyen: İptal
        return HealerOutcome(
            healed=False,
            action="abort",
            scope="run_only",
            details=f"Tanımlanamayan hata: {error_str}"
        )

healer_orchestrator = SelfHealingOrchestrator()
