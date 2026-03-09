from typing import Dict, Any, List
from pydantic import BaseModel
from src.state import AgentState
from src.models import InvestmentMemo
from src.agents.base import get_llm
from src.utils.logger import get_logger
from src.utils.prompt_registry import get_registry

logger = get_logger("critic")

class CriticOutput(BaseModel):
    evaluations: List[InvestmentMemo]

def run_critic_agent(state: AgentState) -> Dict[str, Any]:
    """İş fikirlerini (IdeaDraft) yatırımcı gözüyle eleştirir ve skorlar (Subagent)"""
    logger.info("[AGENT] Critic: Fikirler rasyonel bir yatırımcı gözüyle puanlanıyor...")
    ideas = state.get("ideas", [])
    
    if not ideas:
        logger.warning("[AGENT] Critic: Puanlanacak fikir bulunamadı.")
        return {"evaluations": []}
        
    llm = get_llm(temperature=0.2)
    structured_llm = llm.with_structured_output(CriticOutput)
    
    fallback_prompt = """Sen acımasız ve vizyoner bir Silikon Vadisi Melek Yatırımcısı'sın (Investment Committee).
Görevin: SANA VERİLEN İŞ FİKİRLERİNİ (IdeaDrafts) teker teker incele. SADECE EN İYİ OLANLARI DEĞERLENDİRME, HEPSİNE PUAN VER Ancak eleştirinde acımasız ol.
1. Market Need (Pazar İhtiyacı)
2. Feasibility (Teknik olarak yapılabilirlik)
3. Competition (Rekabet durumu)
4. Audience Clarity (Hedef kitlenin netliği)
5. Risk Score (Dağıtım, yasal veya teknik engel riski)
6. Zamanlama / Trend Mantığı (Gelen Google Trends Puanına göre zamanı doğru mu?)
(1-10 arası puanlar ver)
SADECE InvestmentMemo formatında şema döndür."""

    registry = get_registry()
    active_prompt_obj = registry.get_active_prompt("critic") if registry else None
    
    if active_prompt_obj:
        system_prompt = active_prompt_obj.content
    else:
        system_prompt = fallback_prompt
        if registry:
            registry.register_prompt("critic", fallback_prompt, status="active", notes="Initial Default")

    from src.tools.gtrends_tools import get_trend_score
    
    user_content = "FİKİRLER HAVUZU:\n"
    for idea in ideas:
        # Fikrin ana konusu olarak ilk birkaç kelimesini veya başlığını kullan (Basit bir heuristic)
        trend_kw = " ".join(idea.title.split()[:2])
        trend_val = get_trend_score(trend_kw)
        idea.trend_score = trend_val
        
        user_content += f"\n- Fikir ID: {idea.idea_id}\n  Başlık: {idea.title}\n  Problem: {idea.problem}\n  Çözüm: {idea.solution}\n  Wedge: {idea.wedge}\n  Hedef Kitle: {idea.target_audience}\n  Google Trends Puanı (Zamanlama): {trend_val}/100\n"

    try:
        result = structured_llm.invoke(system_prompt + "\n\n" + user_content)
        
        if hasattr(result, 'usage_metadata') and result.usage_metadata:
             logger.debug(f"[Critic] Token -> Input: {result.usage_metadata.input_tokens}, Output: {result.usage_metadata.output_tokens}")
             
        logger.info(f"[AGENT] Critic: {len(result.evaluations)} fikir detaylandırıldı.")
        
        # Sadece toplam skoru belli bir eşiğin üstünde olanları (deterministic olarak) filtrelemek isteyebiliriz.
        # Supervisor aşamasında da yapılabilir. Şimdilik hepsini döndürüyoruz.
        return {"evaluations": result.evaluations}
    except Exception as e:
        logger.error(f"[AGENT] Critic Hatası: {e}")
        return {"evaluations": []}
