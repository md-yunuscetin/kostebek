from typing import Dict, Any, Literal
from src.state import AgentState
from src.utils.logger import get_logger

logger = get_logger("supervisor")

# Kullanıcının çalıştırabileceği geçerli iş modları (Pipeline Modları)
AVAILABLE_MODES = ["full_pipeline", "only_scrape", "only_ideate", "only_report", "validate_market"]

def run_supervisor_agent(state: AgentState) -> Dict[str, Any]:
    """
    Sistemin ana kontrolcüsü (Supervisor).
    Çalışma moduna (user_goal) göre bütçe, token ve graph rotası izler.
    """
    goal = state.get("user_goal", "full_pipeline")
    
    if goal not in AVAILABLE_MODES:
        logger.warning(f"[SUPERVISOR] Gelişmemiş / Yanlış mod girildi: {goal}. Varsayılan 'full_pipeline' atanıyor.")
        goal = "full_pipeline"
        
    logger.info(f"🚦 [SUPERVISOR] Sistem {goal.upper()} modunda başlatılıyor.")
    
    # Token veya bütçe kullanım metrikleri başlatılıyor
    metrics = state.get("metrics", {})
    if not metrics:
         metrics = {
             "total_tokens_used": 0,
             "estimated_cost_usd": 0.0,
             "budget_limit_usd": 1.0  # Varsayılan bütçe 1 dolar
         }
         
    return {
        "user_goal": goal,
        "metrics": metrics
    }
