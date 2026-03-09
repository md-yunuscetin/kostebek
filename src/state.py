from typing import TypedDict, Annotated, List, Dict, Any, Optional, Literal
from src.models import PainPoint, IdeaDraft, InvestmentMemo
from operator import add

class AgentState(TypedDict, total=False):
    """
    Kalıcı Kısa Dönem Hafıza (Short-Term Memory / Thread State)
    """
    # — Kimlik & İzleme —
    run_id: str                      # Her çalışmaya benzersiz ID
    thread_id: str                   # LangGraph checkpoint anahtarı
    user_goal: Literal["full_pipeline", "only_scrape", "only_ideate", "only_report", "validate_market"]
    
    # — Veri —
    raw_data: List[Dict[str, Any]]                # Toplanan Reddit Postları vb.
    normalized_data: List[Dict[str, Any]]         # Normalizer Çıktısı (Henüz kullanılmıyor)
    pain_points: List[PainPoint]                  # Çıkarılan Problemler
    ideas: List[IdeaDraft]                        # Üretilen Fikirler
    evaluations: List[InvestmentMemo]             # Değerlendirmeler (Puanlar)
    approved_ideas: List[IdeaDraft]               # Novelty testinden geçmiş son liste
    
    # — Kontrol —
    guard_feedback: str                           # Novelty/Critic Red Sebepleri
    retry_count: Annotated[int, add]              # Toplam dönülen döngü sayısı
    ideas_approved: bool                          # Onay bayrağı
    approval_required: bool                       # Human-in-the-loop bayrağı
    
    # — Artifact / Operasyonel —
    artifacts: List[str]                          # Kaydedilen dosya yolları
    final_output: str                             # Obsidian MD Raporu
    tool_errors: Annotated[List[str], add]        # Her node hatasını biriktirir
    warnings: Annotated[List[str], add]           # Uyarı mesajları
    metrics: Dict[str, Any]                       # Token, süre, kaynak sayısı
    
    # — Hata / Healer —
    error: Optional[str]                          # Hata tespiti (Self-Healer için)
    healing_attempts: Annotated[int, add]         # Kendi kendini düzeltme denemesi
    run_overrides: Dict[str, Any]                 # Self_healer'ın global configi ezmek için kullandığı geçici değişkenler
