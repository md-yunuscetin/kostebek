from typing import Dict, Any, List
from pydantic import BaseModel
from datetime import datetime
from src.state import AgentState
from src.models import IdeaDraft, InvestmentMemo
from src.agents.base import get_llm
from src.tools.ops_tools import save_obsidian_note
from src.utils.logger import get_logger
from src.utils.vector_store import vector_store
from src.utils.telegram_gate import send_telegram_report_document
import asyncio


logger = get_logger("writer")


class WriterOutput(BaseModel):
    markdown_content: str


def run_writer_agent(state: AgentState) -> Dict[str, Any]:
    ...
    try:
        result = structured_llm.invoke(system_prompt + "\n\n" + user_content)

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

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(
                send_telegram_report_document(filename, result.markdown_content)
            )
            loop.close()
        except Exception as e:
            logger.error(f"[AGENT] Writer: Telegram'a rapor gönderilemedi: {e}")

        return {"final_output": result.markdown_content}

    except Exception as e:
        logger.error(f"[AGENT] Writer Hatası: {e}")
        return {"final_output": f"Hata oluştu: {e}"}
