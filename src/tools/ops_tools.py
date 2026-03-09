import os
from datetime import datetime
from langchain_core.tools import tool
from src.utils.logger import get_logger
from src.utils.config_loader import config

logger = get_logger("ops_tools")

@tool
def save_obsidian_note(
    idea_title: str,
    markdown_content: str,
) -> str:
    """
    Raporlanan veya onaylanan nihai iş fikrini Obsidian klasörüne kaydeder.
    Klasör konumu YAML ayarlarından otomatik çekilir.
    """
    try:
        obsidian_config = config.get("obsidian", {})
        vault_path = obsidian_config.get("vault_path", r"C:\Users\Yunus\Desktop\İş Fikirleri")
        
        os.makedirs(vault_path, exist_ok=True)
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        # Dosya adı için güvenli karakterler
        safe_title = "".join([c if c.isalnum() else " " for c in idea_title]).strip()[:30]
        filename = f"{today_str} - {safe_title}.md"
        filepath = os.path.join(vault_path, filename)
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(markdown_content)
            
        logger.info(f"[TOOL] Dosya başarıyla kaydedildi: {filepath}")
        return f"Başarılı: Dosya {filepath} konumuna kaydedildi."
    except Exception as e:
        logger.error(f"[TOOL] Obsidian'a kaydedilirken hata: {e}")
        return f"Hata: {e}"
