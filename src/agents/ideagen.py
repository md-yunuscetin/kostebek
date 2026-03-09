from typing import Dict, Any, List
from pydantic import BaseModel
from src.state import AgentState
from src.models import IdeaDraft
from src.agents.base import get_llm
from src.utils.logger import get_logger
from src.memory import store
from src.utils.prompt_registry import get_registry

logger = get_logger("ideagen")

class IdeagenOutput(BaseModel):
    ideas: List[IdeaDraft]

def run_ideagen_agent(state: AgentState) -> Dict[str, Any]:
    """Çıkarılan PainPoint'lerden iş fikirleri (IdeaDraft) üretir.
    
    V5 upgrade: Store'daki prosedürel bellekten (öğrenilmiş kurallar) okuyarak
    Brainstormer prompt'unu dinamik olarak zenginleştirir.
    """
    logger.info("[AGENT] IdeaGen: Problemlerden (Pain Points) iş fikirleri üretiliyor...")
    pain_points = state.get("pain_points", [])

    if not pain_points:
        logger.warning("[AGENT] IdeaGen: Fikir üretilecek problem bulunamadı.")
        return {"ideas": []}

    # V5: Store'dan öğrenilmiş prompt kurallarını oku (Prosedürel Bellek)
    learned_rules = ""
    try:
        prompt_ns = ("prompts", "brainstormer")
        active_item = store.get(prompt_ns, "v_active")
        if active_item and active_item.value.get("rules"):
            learned_rules = active_item.value["rules"]
            logger.info(f"[AGENT] IdeaGen - Store'dan {len(learned_rules.splitlines())} öğrenilmiş kural yüklendi.")
    except Exception as e:
        logger.debug(f"[AGENT] IdeaGen - Store'dan kural okuma hatası (normal): {e}")

    # Yaratıcılık için ısı biraz daha yüksek olabilir (0.7)
    llm = get_llm(temperature=0.7)
    structured_llm = llm.with_structured_output(IdeagenOutput)

    fallback_prompt = """Sen vizyoner bir Ürün Geliştirici (Idea Generator)'sin.
Görevlerin:
1. Sana verilen İnsan Şikayetleri ve Problemleri (Pain Points) listesinden yola çık.
2. Bu problemler için kârlı, inovatif ve doğrudan 'acı çeken' kitleyi hedefleyen SaaS veya B2B/B2C ürün fikirleri üret.
3. Her çözüm için benzersiz bir 'idea_id' (örn: uuid) belirle.
4. 'wedge' (pazara giriş taktiği) ve 'pricing_hypothesis' (fiyatlandırma/gelir modeli varsayımı) önerilerini gerçekçi yap."""

    registry = get_registry()
    active_prompt_obj = registry.get_active_prompt("ideagen") if registry else None
    
    if active_prompt_obj:
        system_prompt = active_prompt_obj.content
    else:
        system_prompt = fallback_prompt
        if registry:
            registry.register_prompt("ideagen", fallback_prompt, status="active", notes="Initial Default")

    # Prosedürel bellek: öğrenilmiş kurallar
    if learned_rules:
        system_prompt += f"\n\n[SİSTEM HAFIZASINDAN ÖĞRENME - Bu Kurallara Kesinlikle Uy!]\n{learned_rules}"

    # Guard geri bildirimi varsa ekle (retry döngüsü)
    if state.get("guard_feedback"):
        system_prompt += f"\n\n[DİKKAT! ÖNCEKİ DENETİM (GUARD) REDDETTİ, BU SEFER DAHA FARKLI VE NİŞ OL!]\nReddedilme Nedeni:\n{state.get('guard_feedback')}"

    user_content = "ÇÖZÜLECEK PROBLEMLER:\n"
    for p in pain_points:
        user_content += f"\n- Problem ID: {p.pain_id}\n  Tema: {p.theme}\n  Kitle: {p.user_segment}\n  Aciliyet: {p.urgency_score}/10\n  Linkler/Kaynaklar: {p.evidence_posts}\n"

    attempts = 0
    max_llm_retries = 3
    
    while attempts < max_llm_retries:
        try:
            result = structured_llm.invoke(system_prompt + "\n\n" + user_content)

            if hasattr(result, 'usage_metadata') and result.usage_metadata:
                 logger.debug(f"[IdeaGen] Token -> Input: {result.usage_metadata.input_tokens}, Output: {result.usage_metadata.output_tokens}")

            logger.info(f"[AGENT] IdeaGen: {len(result.ideas)} inovatif iş fikri üretildi.")
            return {"ideas": result.ideas}

        except Exception as e:
            attempts += 1
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                wait_time = attempts * 15
                logger.warning(f"[AGENT] IdeaGen: Rate limit (429) tespiti. {wait_time} saniye bekleniyor... (Deneme {attempts}/{max_llm_retries})")
                import time
                time.sleep(wait_time)
            else:
                logger.error(f"[AGENT] IdeaGen Hatası: {e}")
                break
                
    return {"ideas": [], "error": "Maximum retries exceeded due to LLM errors."}
