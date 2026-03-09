import asyncio
from typing import Dict, Any
from langgraph.types import Command
from src.state import AgentState
from src.utils.logger import get_logger
from src.utils.prompt_registry import get_registry
from src.utils.telegram_gate import ask_via_telegram, send_telegram_notification

logger = get_logger("approval_gates")

def obsidian_approval_gate(state: AgentState) -> Command:
    approved_ideas = state.get("approved_ideas", [])
    if not approved_ideas:
        logger.info("[GATE] ObsidianGate: Onaylanmış fikir yok, sonlanıyor.")
        return Command(goto="__end__")
        
    evaluations = state.get("evaluations", [])
    
    # Eşleştir ve puanlara göre (IdeaDraft, score) tuple'ları oluştur
    idea_scores = []
    for idea in approved_ideas:
        eval_memo = next((e for e in evaluations if e.idea_id == idea.idea_id), None)
        score = eval_memo.total_score if eval_memo else 0
        idea_scores.append((idea, score))
        
    if not idea_scores:
        return Command(goto="__end__")
        
    # En yüksek puanlı fikri bul
    idea_scores.sort(key=lambda x: x[1], reverse=True)
    best_idea, best_score = idea_scores[0]

    # V9.1: BİLDİRİM MODU - Onay bekleme, direkt devam et
    notify_msg = f"🚀 *OTOMATİK ONAY*: En iyi fikir Obsidian'a kaydediliyor.\n\n📋 *Fikir*: {best_idea.title} ({best_score}/50)\n"
    
    try:
        asyncio.run(send_telegram_notification(notify_msg))
    except Exception as e:
        logger.error(f"[GATE] Bildirim hatası: {e}")
    
    # Otomatik olarak Writer'a git
    return Command(goto="Writer")


def prompt_registry_approval_gate(state: AgentState) -> Command: # Keep original type hints for consistency
    registry = get_registry()
    if not registry:
        logger.info("[GATE] PromptGate: Redis yok, bu gate atlanıyor.")
        return Command(goto="__end__")
        
    # Herhangi bir agent ("ideagen" vs) için candidate var mı bak
    candidates = []
    # Şuan sadece ideagen candidate üretiyor ama genişletilebilir
    for agent in ["ideagen", "critic", "extractor", "guard"]:
        key = registry._get_key(agent)
        all_prompts = registry.redis.hgetall(key)
        for _, p_json in all_prompts.items():
            from src.utils.prompt_registry import PromptVersion
            import json
            p_obj = PromptVersion(**json.loads(p_json))
            if p_obj.status == "candidate":
                candidates.append((agent, p_obj))
                
    if not candidates:
        return Command(goto="__end__")
        
    # İlk candidate için onay iste (basitlik adına)
    target_agent, candidate_prompt = candidates[0]

    message = f"\n[PROMPT GATE] *Self-Improver* yeni bir Prompt kuralı öneriyor (Agent: {target_agent}).\n\nBu kuralı aktif edelim mi?\n{candidate_prompt.content[-150:]}..."
    
    try:
        decision = asyncio.run(ask_via_telegram(message, ["approve", "reject"]))
    except Exception as e:
        logger.error(f"[GATE] PromptGate telegram hatası, otomatik red edildi: {e}")
        decision = "reject"
    
    # Eğer approve gelirse, yeni prompt aktive edilir
    if decision == "approve":
        registry.activate_prompt(target_agent, candidate_prompt.id)
        # The original edit had `from src.utils.logger import get_logger` here, but it's already imported globally.
        # Also, `get_logger("approval")` is called, but the global `logger` is `get_logger("approval_gates")`.
        # Assuming the intent is to use the existing `logger` or a new one for "approval" specifically.
        # For faithfulness, I'll keep the `get_logger("approval")` call as it was in the user's provided block.
        _approval_logger = get_logger("approval")
        _approval_logger.info(f"[PROMPT GATE] {target_agent} için yeni prompt ({candidate_prompt.id}) aktive edildi!")
    else:
        # Rejected durumuna da çekilebilir ama basitçe bekletiyoruz
        pass

    return Command(goto="__end__")
