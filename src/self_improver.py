import json
from datetime import datetime
from typing import Dict, Any
from src.state import AgentState
from src.utils.logger import get_logger
from src.utils.config_loader import config, load_config
from src.memory import store
from src.agents.base import get_llm
from langchain_core.messages import HumanMessage, SystemMessage
from src.utils.prompt_registry import get_registry

logger = get_logger("self_improver")

class SelfImprovementAgent:
    """Her çalışma sonrası sistem performansını analiz eden ve Prompt'u optimize eden Ajan."""
    
    def evaluate_run(self, state: AgentState) -> Dict[str, Any]:
        """Çalışmayı analiz eder ve belleğe (store) yazar."""
        logger.info("[IMPROVER] Otonom İyileştirme Döngüsü Başlatılıyor...")
        
        evals = state.get("evaluations", [])
        def compute_total(e):
            return e.market_need_score + e.feasibility_score + e.competition_score + e.audience_clarity_score + e.risk_score
        best_score = max([compute_total(e) for e in evals]) if evals else 0
        idea_count = len(state.get("ideas", []))
        raw_count = len(state.get("raw_data", []))
        retries = state.get("retry_count", 0)
        
        metrics = {
            "date": datetime.now().isoformat(),
            "best_score": best_score,
            "ideas_generated": idea_count,
            "raw_posts_collected": raw_count,
            "guard_retries": retries,
            "conversion_rate": idea_count / max(raw_count, 1)
        }
        
        # Redis/Memory Store'a Çalışma Geçmişini Ekle (Epizodik Bellek)
        namespace = ("performance", "runs")
        key = "history"
        
        history_item = store.get(namespace, key)
        history_data = history_item.value if history_item else {"runs": []}
        history_data["runs"].append(metrics)
        
        store.put(namespace, key, history_data)
        
        # Son 5 çalışma üzerinden kendi kararını ver
        self._auto_adjust_config_and_prompts(metrics, history_data["runs"])
        
        return {"final_output": state.get("final_output", "") + "\n\n> [!NOTE] Otonom İyileştirme tetiklendi. Sistem bir sonraki çalışma için optimize edildi."}
    
    def _auto_adjust_config_and_prompts(self, current_metrics, history):
        """Kötü performansta config'i otomatik ayarlar ve Prompt optimize eder."""
        recent = history[-5:]
        avg_score = sum(r["best_score"] for r in recent) / max(1, len(recent))
        
        logger.info(f"[IMPROVER] Son {len(recent)} çalışmanın Ortalama En Yüksek Skoru: {avg_score:.1f}")
        
        if avg_score < 25 and len(history) >= 2:
             logger.warning("[IMPROVER] Genel Kalite Düşük! Parametreler analiz ediliyor...")
             if current_metrics["raw_posts_collected"] < 5:
                  filters = config.setdefault("reddit", {}).setdefault("filters", {})
                  filters["min_score"] = max(2, filters.get("min_score", 10) - 5)
                  logger.warning(f"🔧 [İyileştirme] Veri az - min_score düşürüldü: {filters['min_score']}")

        # Çok fazla ret yendiyse Brainstormer Prompt'unu yeniden eğit!
        if current_metrics["guard_retries"] >= 2:
             logger.warning("[IMPROVER] Guard Retries çok yüksek. Brainstormer Prompt A/B Testi için yeniden yazılacak...")
             self._refine_brainstormer_prompt()

    def _refine_brainstormer_prompt(self):
        """Reddedilen fikirlerden öğrenerek Prompt'a dinamik kurallar ekler."""
        ns = ("history", "rejected_ideas")
        # Store'dan son reddedilen kopyaları al
        items = store.search(ns, limit=10)
        rejection_reasons = [it.value.get("reason", "Kopya") for it in items]
        
        if not rejection_reasons:
             return
             
        llm = get_llm(temperature=0.2)
        system_msg = SystemMessage(content="Sen kendi performansını iyileştiren bir Meta-Mühendissin.")
        user_msg = HumanMessage(content=f"""
Mevcut ürün fikirleri jeneratörümüz (Brainstormer) şu anki istemlerle sürekli reddedilen (klişe veya kopya) fikirler üretiyor.
Yakın zamanda reddedilme nedenlerimiz şunlar:
{json.dumps(rejection_reasons, ensure_ascii=False)}

Görevin: Ortaya çıkan bu hataları engellemek için SADECE 2 adet kısa ve öz "KURAL" yazmak. Hiçbir bağlaç, başlık kullanma. Doğrudan listele.""")
        
        try:
             improvement = llm.invoke([system_msg, user_msg])
             learned_rules = improvement.content.strip()
             
             learned_rules = improvement.content.strip()
             
             # Aktif Prompt'u al veya oluştur
             registry = get_registry()
             if not registry: return
             
             active_prompt = registry.get_active_prompt("ideagen")
             if not active_prompt: return
             
             # Mevcut prompt içeriğine yeni kuralları dahil edip Candidate yap
             new_content = active_prompt.content + f"\n\n[SİSTEM HAFIZASINDAN ÖĞRENME/KURAL]\n{learned_rules}"
             
             candidate = registry.register_prompt(
                 agent_name="ideagen", 
                 content=new_content, 
                 status="candidate", 
                 notes="Auto-generated Brainstormer optimization from rejection reasons"
             )
             
             logger.info(f"🧠 [ÖĞRENME GERÇEKLEŞTİ] IdeaGen (Brainstormer) için yeni bir Candidate Prompt eklendi: ID {candidate.id}")
             
        except Exception as e:
             logger.error(f"[IMPROVER] Prompt refinement hatası: {e}")

improver_agent = SelfImprovementAgent()
