import os
import uuid
import typer
import logging
from src.utils.logger import setup_logger, run_id
from src.utils.config_loader import config
from src.graph import build_supervisor_graph
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz
from dotenv import load_dotenv

app = typer.Typer(help="Reddit Miner V4 - AI Mimarisiyle Denetimli İş Fikri Üreticisi")

# Ortam değişkenlerini (API Keys) Yükle
load_dotenv()

# LangSmith Görünürlüğü (Observability) Aktifleştir
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_PROJECT"] = os.getenv("LANGCHAIN_PROJECT", "reddit-miner-v4")

# Global Logger Kurulumu
logger = setup_logger()

def execute_pipeline(dry_run: bool = False, min_score: int = None):
    """Core execution logic (Supervisor workflow)"""
    # Her Run için UUID (Correlation ID)
    current_run_id = str(uuid.uuid4())[:8]
    run_id.set(current_run_id)
    
    logger.info("🚀 Pipeline başlatılıyor...")
    
    if min_score is not None:
        config.setdefault("reddit", {}).setdefault("filters", {})["min_score"] = min_score

    supervisor_app = build_supervisor_graph()
    
    # LangGraph Thread Belleği bağlamı
    thread_config = {"configurable": {"thread_id": current_run_id}}
    
    initial_state = {
        "raw_data": [],
        "pain_points": [],
        "ideas": [],
        "evaluations": [],
        "approved_ideas": [],
        "final_output": "",
        "guard_feedback": "",
        "retry_count": 0
    }
    
    try:
        final_state = supervisor_app.invoke(initial_state, config=thread_config)
        logger.info(f"✅ Pipeline başarıyla tamamlandı. Thread: {current_run_id}")
    except Exception as e:
        logger.error(f"❌ PIPELINE ÇÖKÜŞÜ: {e}")


@app.command()
def run(
    dry_run: bool = typer.Option(False, "--dry-run", help="Obsidian'a kaydetmeden (OpsTool) sadece test et"),
    min_score: int = typer.Option(None, help="Config dosyasındaki upvote eşiğini ezer"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Debug loglarını aktif eder")
):
    """Madenciyi tek seferlik manuel olarak tetikler."""
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    execute_pipeline(dry_run=dry_run, min_score=min_score)


@app.command()
def schedule(
    hour: int = typer.Option(7, help="Çalışma saati (0-23)"),
    minute: int = typer.Option(0, help="Çalışma dakikası (0-59)")
):
    """Zamanlayıcıyı (Cron) başlatarak arka planda her gün çalışmasını sağlar."""
    scheduler = BlockingScheduler(timezone=pytz.timezone("Europe/Istanbul"))
    
    scheduler.add_job(
        execute_pipeline,
        CronTrigger(hour=hour, minute=minute),
        id="reddit_miner_daily",
        max_instances=1,
        misfire_grace_time=600  # 10 dakika gecikmeye tolerans
    )
    
    logger.info(f"📅 Scheduler başlatıldı. Her gün {hour:02d}:{minute:02d}'da otonom çalışacak.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler durduruldu.")

if __name__ == "__main__":
    app()
