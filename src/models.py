from pydantic import BaseModel, Field
from typing import List, Optional, Dict

class PainPoint(BaseModel):
    pain_id: str = Field(description="Benzersiz problem ID'si (UUID veya hash)")
    theme: str = Field(description="Problemin ana teması veya kategorisi")
    user_segment: str = Field(description="Bu problemi yaşayan kullanıcı segmenti")
    evidence_posts: List[str] = Field(description="Problemi doğrulayan Reddit post linkleri")
    urgency_score: int = Field(ge=1, le=10, description="Problemin aciliyet skoru (1-10)")
    monetizability_score: int = Field(ge=1, le=10, description="İnsanların bu problemi çözmek için para ödeme ihtimali (1-10)")

class IdeaDraft(BaseModel):
    idea_id: str = Field(description="Benzersiz fikir ID'si (UUID veya hash)")
    title: str = Field(description="Fikrin çarpıcı başlığı")
    problem: str = Field(description="Çözdüğü problem alanı")
    solution: str = Field(description="Önerilen çözüm veya uygulama fikri")
    wedge: str = Field(description="Pazara giriş stratejisi (wedge) veya niş odak")
    target_audience: str = Field(description="Kimin bu ürünü satın alacağı")
    pricing_hypothesis: str = Field(description="Önerilen fiyatlandırma veya gelir modeli")
    source_urls: List[str] = Field(description="İlham alınan orijinal reddit post linkleri")
    trend_score: Optional[int] = Field(default=None, description="0-100 arası Google Trends ilgi skoru")
class InvestmentMemo(BaseModel):
    idea_id: str
    market_need_score: int = Field(ge=1, le=10, description="İnsanlar para öder mi? (1-10)")
    feasibility_score: int = Field(ge=1, le=10, description="Tek başına veya küçük bir ekiple yapılabilir mi? (1-10)")
    competition_score: int = Field(ge=1, le=10, description="Piyasada rekabet ne durumda? Niş mi? (1-10)")
    audience_clarity_score: int = Field(ge=1, le=10, description="Kim satın alacak belli mi? (1-10)")
    risk_score: int = Field(ge=1, le=10, description="Regülasyon, dağıtım veya teknik risk (1-10)")
    analysis: str = Field(description="Yatırım tezi ve eleştirel analiz.")

    @property
    def total_score(self) -> int:
        return self.market_need_score + self.feasibility_score + self.competition_score + self.audience_clarity_score + self.risk_score

class NoveltyCheck(BaseModel):
    idea_id: str = Field(description="Orijinal filtrelenen fikrin eşsiz string ID'si")
    is_novel: bool = Field(description="Mevcut büyük pazar liderlerinin (Notion, Trello vb.) birebir kopyası değilse True")
    duplicate_type: str = Field(description="Kopya türü: none, title, semantic, market_clone")
    feedback: str = Field(description="Eğer False ise neden reddedildiğinin açıklaması")

class GuardOutput(BaseModel):
    results: Dict[str, NoveltyCheck] = Field(description="Idea ID string key, NoveltyCheck objesi ise value olacak.")
