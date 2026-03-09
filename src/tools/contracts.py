from pydantic import BaseModel, Field
from typing import Literal, List, Dict, Any, Optional

class ToolResult(BaseModel):
    """Her arama/kazıma aracının (Scraper vb.) döndürmesi gereken standart sözleşme (Contract)"""
    success: bool = Field(description="İşlemin başarı durumu")
    source: str = Field(description="Verinin geldiği kaynak, örn: 'Reddit/r/SaaS', 'HackerNews'")
    items: List[Dict[str, Any]] = Field(default_factory=list, description="Çekilen veri listesi")
    error_type: Literal["none", "rate_limit", "auth", "network", "parse", "timeout", "dependency"] = Field(default="none")
    error_msg: str = Field(default="", description="Detaylı hata mesajı")
    had_errors: bool = Field(default=False, description="Ufak bile olsa exception yakalanıp yakalanmadığı")
    retry_after: int = Field(default=0, description="Rate limit (429) durumunda kaç saniye bekleneceği (Saniye)")
    provenance: Dict[str, Any] = Field(default_factory=dict, description="İzlenebilirlik metadata'sı (query, token vb.)")
