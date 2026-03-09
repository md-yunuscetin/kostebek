from typing import Dict, Any

def update_metrics(state: Dict[str, Any], response: Any) -> Dict[str, Any]:
    """
    LLM'den dönen raw response objesinin içindeki usage_metadata'yı okur,
    state içindeki global metrics sözlüğüne token harcamalarını işler.
    
    Örnek kullanım (Ajan içinde):
    update_dict = {"approved_ideas": approved}
    update_dict.update(update_metrics(state, result))
    return update_dict
    """
    metrics = state.get("metrics", {})
    if not metrics:
        metrics = {
             "total_tokens_used": 0,
             "api_calls": 0,
             "estimated_cost_usd": 0.0,
             "budget_limit_usd": 1.0
         }
         
    if hasattr(response, "usage_metadata") and response.usage_metadata:
        # Langchain AIMessage metadata objesi varsa:
        try:
            tokens = response.usage_metadata.get("total_tokens", 0)
            metrics["total_tokens_used"] += tokens
            metrics["api_calls"] += 1
            # Örnek cost formülü: (Gemini 1.5 Flash üzerinden 1M token ~ 0.35$ gibi)
            metrics["estimated_cost_usd"] += (tokens / 1000000) * 0.35
        except Exception:
            pass
            
    return {"metrics": metrics}
