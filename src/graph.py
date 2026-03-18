from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
try:
    import redis
except ImportError:
    redis = None
import uuid
import os

from src.state import AgentState
from src.agents.collector import run_collector_agent
from src.agents.extractor import run_extractor_agent
from src.agents.ideagen import run_ideagen_agent
from src.agents.critic import run_critic_agent
from src.agents.guard import run_guard_agent
from src.agents.writer import run_writer_agent
from src.agents.supervisor import run_supervisor_agent
from src.approval_gates import obsidian_approval_gate, prompt_registry_approval_gate
from src.self_healer import healer_orchestrator
from src.self_improver import improver_agent
from src.utils.logger import get_logger
from src.agents.domain_filter import run_domain_filter_agent, check_domain_filter_route

logger = get_logger("supervisor")

# ==========================================
# SUPERVISOR: ROUTING FONKSİYONLARI
# ==========================================

def check_guard_route(state: AgentState):
    """
    Kopya taklit dedektöründen dönen durumu değerlendirir.
    - Geçerli fikir varsa → Writer
    - Retry şansı varsa → IdeaGen
    - Limit dolmuşsa → END (Self-Healer tetiklenebilir)
    """
    approved = state.get("approved_ideas", [])
    retry_count = state.get("retry_count", 0)
    error = state.get("error")
    max_retries = 2

    # Bir hata varsa - Self Healer'a git
    if error:
        logger.warning(f"[SUPERVISOR] Hata tespit edildi: {error} -> Healer")
        return "Healer"

    if approved:
        logger.info("[SUPERVISOR] Guard onayı alındı -> ObsidianGate")
        return "ObsidianGate"

    if retry_count < max_retries:
        logger.warning(f"[SUPERVISOR] Fikirler reddedildi! Döngü başlatılıyor (Retry: {retry_count}/{max_retries}) -> IdeaGen")
        return "IdeaGen"

    logger.error("[SUPERVISOR] Maksimum döngüye ulaşıldı, geçerli fikir bulunamadı -> ObsidianGate (Son çare)")
    return "ObsidianGate"


def check_healer_route(state: AgentState):
    """
    Self-Healer sonucunda hatanın giderilip giderilmediğini kontrol eder.
    """
    error = state.get("error")
    healing_attempts = state.get("healing_attempts", 0)
    max_heal_attempts = 3

    if not error:
        # Hata giderildi - kaldığı yerden devam et (Collector'e gönder, tekrar dene)
        logger.info("[SUPERVISOR] Self-Healer hatayı düzeltti -> Collector (Yeniden başlıyor)")
        return "Collector"

    if healing_attempts >= max_heal_attempts:
        logger.error("[SUPERVISOR] Self-Healer başarısız! Maksimum deneme aşıldı -> END")
        return END

    # Hata hâlâ var, bir daha dene
    logger.warning(f"[SUPERVISOR] Hata giderilemedi (deneme {healing_attempts}) -> Healer tekrarlanıyor")
    return "Healer"


def check_collector_route(state: AgentState):
    """Collector hiç veri bulamazsa, doğrudan END'e git."""
    raw_data = state.get("raw_data", [])
    if not raw_data:
        logger.warning("[SUPERVISOR] Collector hiç veri bulamadı -> Sistem erken sonlanıyor (END)")
        return END
    return "Extractor"


def check_extractor_route(state: AgentState):
    """Extractor hiç problem çıkaramazsa, IdeaGen'e gidip boş dönmesini engelle ve END'e git."""
    pain_points = state.get("pain_points", [])
    if not pain_points:
        logger.warning("[SUPERVISOR] Extractor geçerli problem (PainPoint) bulamadı -> Sistem erken sonlanıyor (END)")
        return END
    return "DomainFilter"   # 👈 DEĞİŞTİ


def check_supervisor_route(state: AgentState):
    """Supervisor ayarlanan pipeline moduna göre rotayı çizer."""
    goal = state.get("user_goal", "full_pipeline")
    if goal == "only_ideate":
        return "Extractor"
    if goal == "only_report":
        return "ObsidianGate"
    return "Collector"


# ==========================================
# WRAPPER FONKSİYONLARI (Node Sarmalayıcı)
# ==========================================

def run_healer_node(state: AgentState):
    """Self-Healing Orchestrator'ı LangGraph node'u olarak çalıştırır."""
    error = state.get("error")
    if not error:
        return {}
    
    outcome = healer_orchestrator.diagnose(error, state)
    attempts = state.get("healing_attempts", 0)
    
    if outcome.healed:
        # Geçici onarım: Şimdilik hatayı temzileyip dönüyor (Faz 2'de Supervisor tam ele alacak)
        logger.info(f"[HEALER_NODE] Outcome: {outcome.action} - {outcome.details}")
        return {"error": None, "healing_attempts": attempts + 1}
    else:
        logger.error(f"[HEALER_NODE] Onarım Şansı Yok: {outcome.details}")
        return {"healing_attempts": attempts + 1}


def run_improver_node(state: AgentState):
    """Self-Improvement Agent'ı LangGraph node'u olarak çalıştırır."""
    return improver_agent.evaluate_run(state)


# ==========================================
# SUPERVISOR GRAPH OLUŞTURUCU
# ==========================================

def build_supervisor_graph():
    """Tüm alt ajanları (Specialist Subagents) ve Self-Healing/Improving döngüsünü yöneten LangGraph çalışma planı."""
    logger.info("[SUPERVISOR] LangGraph Supervisor V5 (Otonom) İnşa Ediliyor...")

    builder = StateGraph(AgentState)

    # --- Specialist Subagents ---
    builder.add_node("Supervisor", run_supervisor_agent)
    builder.add_node("Collector", run_collector_agent)
    builder.add_node("Extractor", run_extractor_agent)
    builder.add_node("DomainFilter", run_domain_filter_agent)  # 👈 EKLE
    builder.add_node("IdeaGen", run_ideagen_agent)
    builder.add_node("Critic", run_critic_agent)
    builder.add_node("Guard", run_guard_agent)
    builder.add_node("Writer", run_writer_agent)
    
    # --- HITL Gates ---
    builder.add_node("ObsidianGate", obsidian_approval_gate)
    builder.add_node("PromptGate", prompt_registry_approval_gate)

    # --- V5: Autonomous Meta-Agents ---
    builder.add_node("Healer", run_healer_node)
    builder.add_node("Improver", run_improver_node)

    # --- Standart ve Koşullu Akışlar ---
    builder.set_entry_point("Supervisor")
    
    builder.add_conditional_edges(
        "Supervisor",
        check_supervisor_route,
        {
            "Collector": "Collector",
            "Extractor": "Extractor",
            "ObsidianGate": "ObsidianGate"
        }
    )
    
    # Collector erken çıkış kontrolü
    builder.add_conditional_edges(
        "Collector",
        check_collector_route,
        {
            "Extractor": "Extractor",
            END: END
        }
    )

    # Extractor erken çıkış kontrolü
    builder.add_conditional_edges(
        "Extractor",
        check_extractor_route,
        {
            "DomainFilter": "DomainFilter",   # 👈 DEĞİŞTİ
            END: END
        }
    )

    builder.add_conditional_edges(
        "DomainFilter",
        check_domain_filter_route,
        {
            "IdeaGen": "IdeaGen",
            "END": END
        }
    )
    
    builder.add_edge("IdeaGen", "Critic")
    builder.add_edge("Critic", "Guard")

    # --- Koşullu Akış: Guard Döngüsü + Healer Yönlendirmesi ---
    builder.add_conditional_edges(
        "Guard",
        check_guard_route,
        {
            "ObsidianGate": "ObsidianGate",
            "IdeaGen": "IdeaGen",
            "Healer": "Healer",
            END: END
        }
    )

    # --- Self-Healer Sonrası Yönlendirme ---
    builder.add_conditional_edges(
        "Healer",
        check_healer_route,
        {
            "Collector": "Collector",
            "Healer": "Healer",
            END: END
        }
    )

    # --- Writer'dan Improver'a (Her Çalışmada Performans Analizi) ---
    builder.add_edge("Writer", "Improver")
    builder.add_edge("Improver", "PromptGate")

    # --- Checkpointer ile Kalıcı Hafıza (ShallowRedisSaver / MemorySaver Fallback) ---
    def _get_checkpointer():
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        try:
            import redis as redis_lib
            # URL'den host/port/db bilgisini parse et (Opsiyonel manuel test için)
            # Basitçe Ping testi:
            test = redis_lib.from_url(redis_url, socket_connect_timeout=1, socket_timeout=1)
            test.ping()
            test.close()
            
            from langgraph.checkpoint.redis.shallow import ShallowRedisSaver
            saver = ShallowRedisSaver.from_conn_string(redis_url)
            saver.setup()
            logger.info(f"[SUPERVISOR] ✅ Supervisor Graph hazır (Redis Aktif: {redis_url})")
            return saver
        except Exception as e:
            logger.warning(
                f"[SUPERVISOR] ⚠️ Redis bağlantı hatası ({redis_url}): {type(e).__name__} → "
                "MemorySaver kullanılıyor (geçici, yeniden başlatmada state kaybolur)"
            )
            return MemorySaver()

    checkpointer = _get_checkpointer()
    app = builder.compile(checkpointer=checkpointer)

    return app
