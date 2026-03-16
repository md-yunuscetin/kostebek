from typing import Dict, Any, List
import asyncio
from pydantic import BaseModel
from datetime import datetime
from src.state import AgentState
from src.models import IdeaDraft, InvestmentMemo
from src.agents.base import get_llm
from src.tools.ops_tools import save_obsidian_note
from src.utils.logger import get_logger
from src.utils.vector_store import vector_store
from src.telegram_gate import send_telegram_report_document


logger = get_logger("writer")

class WriterOutput(BaseModel):
    markdown_content: str

def run_writer_agent(state: AgentState) -> Dict[str, Any]:
    """Onaylanmış fikirleri (approved_ideas) ve değerlendirmeleri Obsidian formatına çevirir ve kaydeder."""
    logger.info("[AGENT] Writer: Obsidian Markdown Raporu Yazılıyor...")
    
    approved_ideas: List[IdeaDraft] = state.get("approved_ideas", [])
    evaluations: List[InvestmentMemo] = state.get("evaluations", [])
    
    if not approved_ideas:
        logger.warning("[AGENT] Writer: Onaylanmış fikir yok. Rapor oluşturulmadı.")
        return {"final_output": "Onaylanmış fikir bulunamadı."}
        
    llm = get_llm(temperature=0.3)
    structured_llm = llm.with_structured_output(WriterOutput)
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    system_prompt = f"""Sen titiz bir teknik yazarsın. Görevin onaylanmış fikirleri kusursuz bir Markdown formatına dönüştürmek.
KURAL 1: En başa aşağıdaki YAML Frontmatter bloğunu BİREBİR ekle:
---
date: {today_str}
tags: [iş-fikirleri, saas, ai-pipeline, acil-oku]
puan: (En yüksek puan / 40)
---
KURAL 2: Her fikrin başlığını (H3), detayını, eleştirmen skorlarını okunaklı listeler halinde yaz.
KURAL 3: Orijinal Reddit Bağlantısını da 'Kaynak' olarak [Kaynak Linki](...) formatında ekle.
KURAL 4: Hiçbir giriş-çıkış cümlesi kurma. SADECE MARKDOWN metnini ver."""

    user_content = "ONAYLANMIŞ FİKİRLER VE PUANLAR:\n\n"
    for idea in approved_ideas:
        # İlgili evaluation'ı bul
        ev_text = "Değerlendirme bulunamadı."
        for ev in evaluations:
            if ev.idea_id == idea.idea_id:
                ev_text = f"Pazar: {ev.market_need_score}/10 | Yapılabilirlik: {ev.feasibility_score}/10 | Rekabet: {ev.competition_score}/10 | Hedef Kitle: {ev.audience_clarity_score}/10 | Risk: {ev.risk_score}/10\nAnaliz: {ev.analysis}"
                break
                
        sources = ", ".join(idea.source_urls)
        user_content += f"- Başlık: {idea.title}\n- Problem: {idea.problem}\n- Çözüm: {idea.solution}\n- Wedge: {idea.wedge}\n- Hedef Kitle: {idea.target_audience}\n- Değerlendirme: {ev_text}\n- Kaynaklar: {sources}\n\n"
        
    try:
        result = structured_llm.invoke(system_prompt + "\n\n" + user_content)
        
        # Tool çağrısı: Dosyayı kaydet
        save_msg = save_obsidian_note.invoke({
            "idea_title": "Toplu İş Fikirleri Raporu V7",
            "markdown_content": result.markdown_content
        })
        logger.info(f"[AGENT] Writer Sonucu: {save_msg}")
        
           # V7: ONAYLANMIŞ FİKİRLERİ VEKTÖR HAFIZAYA GÖM
        for idea in approved_ideas:
            final_score = 0
            for ev in evaluations:
                if ev.idea_id == idea.idea_id:
                    final_score = ev.total_score
                    break
            vector_store.save_idea(idea, final_score)
            logger.info(f"[AGENT] Writer: {idea.title[:30]}... vektör veritabanına eklendi.")

        # ✅ Tam raporu Telegram'a .md dosyası olarak gönder
        try:
            today_str = datetime.now().strftime("%Y-%m-%d")
            filename = f"kostebek-rapor-{today_str}.md"
            asyncio.run(send_telegram_report_document(filename, result.markdown_content))
        except Exception as e:
            logger.error(f"[AGENT] Writer: Telegram'a rapor gönderilemedi: {e}")
        
        return {"final_output": result.markdown_content}

        
    except Exception as e:
        logger.error(f"[AGENT] Writer Hatası: {e}")
        return {"final_output": f"Hata oluştu: {e}"}
