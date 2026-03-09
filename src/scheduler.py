import os
import glob
import asyncio
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import yaml

from src.agents.base import get_llm
from src.utils.logger import get_logger
from src.utils.telegram_gate import ask_via_telegram

logger = get_logger("scheduler")

# Config yolunu dinamik al
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
config_path = os.path.join(base_dir, "config.yaml")

with open(config_path, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

obsidian_path = config["obsidian"]["vault_path"]
project_folder = config["obsidian"]["project_folder"]
full_vault_path = os.path.join(obsidian_path, project_folder)

async def weekly_digest():
    """O haftanın Obsidian klasöründeki tüm raporları okuyup özetler."""
    logger.info("[SCHEDULER] Haftalık Özet Raporu oluşturuluyor...")
    
    week_ago = datetime.now() - timedelta(days=7)
    reports = []

    # Markdown dosyalarını tara
    search_path = os.path.join(full_vault_path, "*.md")
    for md_file in glob.glob(search_path):
        # Dosya son 7 güne aitse al
        if os.path.getmtime(md_file) > week_ago.timestamp():
            with open(md_file, "r", encoding="utf-8") as f:
                # Token sınırını aşmamak için her raporun ilk 2000 karakterini çekelim (genelde en iyi fikirler ve özet buradadır)
                reports.append(f.read()[:2000])

    if not reports:
        logger.warning("[SCHEDULER] Bu hafta için oluşturulmuş hiçbir rapor bulunamadı.")
        return

    logger.info(f"[SCHEDULER] {len(reports)} adet rapor bulundu. LLM özetine gönderiliyor...")

    summary_prompt = f"""Sen yatırımcı ve ürün yöneticisi şapkası taşıyan tecrübeli bir analistsin.
Bu haftaki toplam {len(reports)} güncel iş fikri raporunu incele.
Görevlerin:
1. Bu hafta üretilen tüm fikirler arasından GÖZE EN ÇARPAN (en yüksek puan potansiyeli veya market boşluğu) 1 fikri seç.
2. Neden bu haftanın "Şampiyonu" olduğunu 3 kısa madde ile açıkla.
3. Çok net, heyecan verici ve kısa bir Türkçe özet çıkar. Asla giriş / gelişme / sonuç şeklinde uzatma.

REPORTS:
{"=".join(reports)}
"""

    llm = get_llm(temperature=0.4)
    try:
        summary_response = llm.invoke(summary_prompt)
        text_content = summary_response.content
        
        message = f"📊 *Haftalık İş Fikri Özeti*\n\n{text_content}\n\n_Bu hafta toplam {len(reports)} rapor/fikir tarandı._"
        
        # Sadece "Tamam" botunu koyup mesaj atalım
        await ask_via_telegram(message, ["ok"])
        logger.info("[SCHEDULER] Haftalık özet Telegram üzerinden gönderildi!")
        
    except Exception as e:
        logger.error(f"[SCHEDULER] LLM veya Telegram hatası: {e}")

def start_scheduler():
    scheduler = AsyncIOScheduler()
    # Her Pazar sabahı saat 09:00 (Türkiye saatiyle çalışması için Europe/Istanbul verilebilir fakat Timezone default sunucudan alınacak)
    scheduler.add_job(
        weekly_digest,
        CronTrigger(day_of_week="sun", hour=9, minute=0),
        id="weekly_digest_job",
        replace_existing=True
    )
    scheduler.start()
    logger.info("[SCHEDULER] APScheduler başlatıldı! Haftalık Özet Her Pazar 09:00'da çalışacak.")

if __name__ == "__main__":
    # Test etmek istersen direk çağır:
    asyncio.run(weekly_digest())
