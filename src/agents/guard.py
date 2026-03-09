import uuid
from datetime import datetime
from typing import Dict, Any, List
from pydantic import BaseModel
from src.state import AgentState
from src.models import NoveltyCheck, IdeaDraft
from src.agents.base import get_llm
from src.utils.logger import get_logger
from src.utils.cache import is_duplicate, save_to_cache, load_cache
from src.utils.vector_store import vector_store
from src.memory import store
from src.utils.prompt_registry import get_registry

logger = get_logger("guard")

class GuardOutput(BaseModel):
    results: Dict[str, NoveltyCheck]

def run_guard_agent(state: AgentState) -> Dict[str, Any]:
    """Fikirlerin (IdeaDraft) orijinalliğini LLM ve Cache ile değerlendirir (Subagent)
    
    V5 upgrade: Reddedilen fikirler ve nedenler LangGraph Store'a (epizodik belleğe) yazılır.
    Bu sayede Self-Improver, reddedilme kalıplarını analiz edip Brainstormer Prompt'unu optimize eder.
    """
    logger.info("[AGENT] Guard: Orijinallik kontrolü ve Kopya tespiti yapılıyor...")
    ideas: List[IdeaDraft] = state.get("ideas", [])
    retry_count = state.get("retry_count", 0)
    update_dict = {"retry_count": retry_count}
    approved_ideas: List[IdeaDraft] = []

    if not ideas:
        return {"approved_ideas": [], "guard_feedback": "", "retry_count": retry_count}

    # Store'dan önceki reddedilen fikirleri okuyarak bağlam zenginleştirme (Semantik Bellek)
    rejected_ns = ("history", "rejected_ideas")
    past_rejected = []
    try:
        past_items = store.search(rejected_ns, limit=5)
        past_rejected = [item.value.get("title", "") for item in past_items if item.value.get("title")]
        if past_rejected:
            logger.info(f"[AGENT] Guard - Önceki reddedilen fikirler okundu: {len(past_rejected)} adet")
    except Exception as e:
        logger.debug(f"[AGENT] Guard - Store'dan geçmiş okuma hatası (normal): {e}")

    llm = get_llm(temperature=0.0) # Kesinlik için en düşük sıcaklık
    structured_llm = llm.with_structured_output(GuardOutput)

    # Geçmiş red listesini prompt'a ekle
    past_rejected_text = ""
    if past_rejected:
        past_rejected_text = f"\n\nDİKKAT - ÖNCEKİ RET LİSTESİ (Bunlar geçmişte zaten reddedildi, tekrar ret!):\n" + "\n".join(f"- {t}" for t in past_rejected)

    fallback_prompt_base = """Sen acımasız ve mantıklı bir "Kopya/Taklit Dedektörü"sün (Novelty Guard).
1. Sana verilen iş fikirlerini mevcut büyük pazar oyuncularıyla (Notion, Trello, Linear, Slack vb.) kıyasla.
2. Bu iş fikri BİREBİR AYNISI mi, yoksa spesifik bir kitleye (Wedge) odaklanan yeni bir yaklaşım mı?
3. Sadece gerçekten orijinal veya niş bir farklılığı (novelty) olanlara 'is_novel: True' ver. Geri kalanları reddet.
4. \"is_novel: False\" veriyorsan 'feedback' alanında sebebini net şekilde yaz."""

    registry = get_registry()
    active_prompt_obj = registry.get_active_prompt("guard") if registry else None
    
    if active_prompt_obj:
        system_prompt = str(active_prompt_obj.content) + past_rejected_text
    else:
        system_prompt = fallback_prompt_base + past_rejected_text
        if registry:
            registry.register_prompt("guard", fallback_prompt_base, status="active", notes="Initial Default")

    try:
        # V7: KOPYA TESPİTİ - Agentic RAG (Vector Store) ile LLM'den ÖNCE kontrol
        unique_ideas_for_llm = []
        failed_feedbacks = []
        
        for idea in ideas:
            # Fikrin tam metnini oluşturup ChromaDB benzerlik kontrolü yap
            idea_text = f"{idea.title}. {idea.problem}. {idea.solution}. {idea.wedge}"
            
            # threshold: 0.85 (Planda anlaşıldığı gibi default kalıyor)
            is_vector_duplicate = vector_store.find_similar_past_ideas(idea_text)
            
            if is_vector_duplicate:
                logger.warning(f"[AGENT] Guard - RAG KOPYA YAKALANDI (Milisaniyede engellendi): {idea.title}")
                reason = "VECTOR DB EŞLEŞMESİ: Bu fikre veya problemin çözümüne %85'ten fazla benzeyen bir iş fikri geçmişte üretilmiş/değerlendirilmiş."
                failed_feedbacks.append(reason)
                # Store'a kaydet ki Healer / Improver faydalansın
                _save_rejection_to_store(idea.title, reason)
            else:
                unique_ideas_for_llm.append(idea)
                
        # Eğer elde hiç özgün (unique) fikir kalmadıysa, LLM çağırmadan direkt Reddet
        if not unique_ideas_for_llm:
            retry_count = state.get("retry_count", 0)
            update_dict["guard_feedback"] = "Tüm fikirler Vektörel Hafıza (ChromaDB) tarafından geçmişteki projelere aşırı benzer bulunduğu için reddedildi.\n" + "\n".join(failed_feedbacks)
            update_dict["retry_count"] = retry_count + 1
            update_dict["approved_ideas"] = []
            logger.info("[AGENT] Guard: Tüm fikirler veritabanı benzerlik filtresine takıldı (Çıktı=0)")
            return update_dict
            
        # 1. LLM Novelty Judge (SADECE veritabanında olmayan orijinal fikirler için çalışır)
        user_content = "KONTROL EDİLECEK FİKİRLER:\n"
        for idea in unique_ideas_for_llm:
            user_content += f"\n- Fikir ID: {idea.idea_id}\n  Başlık: {idea.title}\n  Çözüm: {idea.solution}\n  Niş Odak: {idea.wedge}\n"

        result = structured_llm.invoke(system_prompt + "\n\n" + user_content)
        cache = load_cache()

        for idea in unique_ideas_for_llm:
            novelty = result.results.get(idea.idea_id)
            if novelty:
                if novelty.is_novel:
                    # Cache kontrolü
                    if not is_duplicate(idea.title, cache):
                        approved_ideas.append(idea)
                    else:
                        logger.info(f"[AGENT] Guard - Fikir reddedildi (Zaten cache'de var): {idea.title}")
                        _save_rejection_to_store(idea.title, "Önceden işlenmiş (cache'de var)")
                else:
                    logger.warning(f"[AGENT] Guard - Fikir kopyaydı (Reddedildi): {idea.title} - Nedeni: {novelty.feedback}")
                    failed_feedbacks.append(novelty.feedback)
                    # V5: Reddedilen fikri epizodik belleğe yaz
                    _save_rejection_to_store(idea.title, novelty.feedback)
            else:
                logger.warning(f"[AGENT] Guard - Fikir ID ({idea.idea_id}) için LLM yanıt döndürmedi: {idea.title}")
                failed_feedbacks.append("LLM yanıtı eksik.")
                _save_rejection_to_store(idea.title, "LLM failed to return novelty check for this ID")

        if not approved_ideas and failed_feedbacks and retry_count < 2:
            update_dict["guard_feedback"] = "Aşağıdaki fikirler klişe veya rakip kopyası olduğu için reddedildi:\n" + "\n".join(failed_feedbacks)
            update_dict["retry_count"] = retry_count + 1
            update_dict["approved_ideas"] = []
        else:
            # Başarılı olanları Cache'e ekle
            if approved_ideas:
                save_to_cache([idea.title for idea in approved_ideas])
            update_dict["approved_ideas"] = approved_ideas
            update_dict["guard_feedback"] = ""  # Clean feedback

        logger.info(f"[AGENT] Guard: {len(approved_ideas)} fikir onaydan geçti.")
        return update_dict

    except Exception as e:
        logger.error(f"[AGENT] Guard Hatası: {e}")
        return {"approved_ideas": [], "guard_feedback": "", "error": str(e), "retry_count": state.get("retry_count", 0)}


def _save_rejection_to_store(idea_title: str, reason: str):
    """Reddedilen fikri LangGraph Store'a (Epizodik Bellek) kaydeder."""
    try:
        rejected_ns = ("history", "rejected_ideas")
        key = str(uuid.uuid4()).replace("-", "")[:8]
        store.put(rejected_ns, key, {
            "title": idea_title,
            "reason": reason,
            "timestamp": datetime.now().isoformat()
        })
        logger.debug(f"[AGENT] Guard - Ret Store'a kaydedildi: {idea_title}")
    except Exception as e:
        logger.debug(f"[AGENT] Guard - Store yazma hatası (kritik değil): {e}")
