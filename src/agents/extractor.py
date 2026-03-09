from typing import Dict, Any
from pydantic import BaseModel
from src.state import AgentState
from src.models import PainPoint
from src.agents.base import get_llm
from src.utils.logger import get_logger
from src.utils.prompt_registry import get_registry
import uuid

logger = get_logger("extractor")

class ExtractorOutput(BaseModel):
    pain_points: list[PainPoint]

def run_extractor_agent(state: AgentState) -> Dict[str, Any]:
    """Toplanan ham verilerden yapılandırılmış PainPoint'ler çıkarır (Subagent)"""
    logger.info("[AGENT] Extractor: Yorumlar ve postlardan sancılı problemler (Pain Points) çıkarılıyor...")
    raw_data = state.get("raw_data", [])
    
    if not raw_data:
        logger.warning("[AGENT] Extractor: İncelenecek veri yok.")
        return {"pain_points": []}
        
    # Daha deterministik (kesin) veri çekimi için düşük sıcaklık
    llm = get_llm(temperature=0.3)
    structured_llm = llm.with_structured_output(ExtractorOutput)
    
    fallback_prompt = """Sen analitik bir Pazar Araştırmacısısın (Insight Extractor).
Görevlerin:
1. Aşağıdaki toplanan Reddit postlarını ve yorumlarını derince analiz et.
2. İnsanların yakındığı, eksikliğini hissettiği problemleri (Pain Points) tespit et.
3. Aynı konu etrafındaki şikayetleri tek bir PainPoint başlığında kümele (Clusterla).
4. Her bir PainPoint için 'pain_id' (örn: uuid, P-001 vb.) üret.
SADECE ŞEMAYA UYGUN JSON VERİSİ DÖNDÜR."""

    registry = get_registry()
    active_prompt_obj = registry.get_active_prompt("extractor") if registry else None
    
    if active_prompt_obj:
        system_prompt = active_prompt_obj.content
    else:
        system_prompt = fallback_prompt
        if registry:
            registry.register_prompt("extractor", fallback_prompt, status="active", notes="Initial Default")

    user_content = "TOPLANAN VERİLER:\n"
    # Tüm veriyi gönderirsek Context Window limiti aşılabilir, en iyi 20 tanesini alalım.
    for item in raw_data[:20]:
        user_content += f"\n- Kaynak: {item.get('source', 'Bilinmeyen')}\n  Başlık: {item['title']}\n  Post: {item['text'][:300]}...\n  Yorumlar: {item.get('top_comments', [])}\n  Link: {item['url']}\n"
    
    attempts = 0
    max_llm_retries = 3
    
    while attempts < max_llm_retries:
        try:
            result = structured_llm.invoke(system_prompt + "\n\n" + user_content)
            
            if hasattr(result, 'usage_metadata') and result.usage_metadata is not None:
                 logger.debug(f"[Extractor] Token Kullanımı -> Input: {result.usage_metadata.input_tokens}, Output: {result.usage_metadata.output_tokens}")
                 
            logger.info(f"[AGENT] Extractor: {len(result.pain_points)} benzersiz problem kümesi bulundu.")
            return {"pain_points": result.pain_points}
            
        except Exception as e:
            attempts += 1
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                wait_time = attempts * 15 # Hata durumunda bekleme süresini artır
                logger.warning(f"[AGENT] Extractor: Rate limit (429) tespiti. {wait_time} saniye bekleniyor... (Deneme {attempts}/{max_llm_retries})")
                import time
                time.sleep(wait_time)
            else:
                logger.error(f"[AGENT] Extractor Hatası: {e}")
                break
                
    return {"pain_points": []}
