import asyncio
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.config import settings
from src.storage import init_db
from src.bot import router
from src.services import run_monitoring_cycle, sync_worksection_cases

# Configure logging
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT
)
logger = logging.getLogger(__name__)

# Setup dedicated file logger for OpenDataBot history
def setup_opendatabot_logging():
    """Setup file logging for OpenDataBot API responses"""
    log_dir = Path(__file__).parent.parent / 'logs'
    log_dir.mkdir(exist_ok=True)
    
    odb_logger = logging.getLogger('opendatabot.history')
    odb_logger.setLevel(logging.DEBUG)
    
    # File handler with rotation (10MB max, keep 5 backups)
    file_handler = RotatingFileHandler(
        log_dir / 'opendatabot_history.log',
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    
    # Also log to console at INFO level
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    
    odb_logger.addHandler(file_handler)
    odb_logger.addHandler(console_handler)
    
    logger.info(f"OpenDataBot history logging configured: {log_dir / 'opendatabot_history.log'}")

setup_opendatabot_logging()


async def scheduled_monitoring(bot: Bot):
    """Scheduled task for monitoring court cases"""
    logger.info("Running scheduled monitoring...")
    try:
        await run_monitoring_cycle(bot)
    except Exception as e:
        logger.error(f"Monitoring error: {e}")


async def scheduled_worksection_sync(bot: Bot = None):
    """Scheduled task for Worksection sync"""
    logger.info("Running scheduled Worksection sync...")
    try:
        count = await sync_worksection_cases()
        logger.info(f"Worksection sync: {count} cases")
    except Exception as e:
        logger.error(f"Worksection sync error: {e}")


async def main():
    """Main entry point"""
    logger.info("Starting Court Monitoring Bot...")
    
    # Initialize database
    await init_db()
    logger.info("Database initialized")
    
    # Initial Worksection sync
    logger.info("Running initial Worksection sync...")
    try:
        count = await sync_worksection_cases()
        logger.info(f"Initial sync completed: {count} cases")
    except Exception as e:
        logger.error(f"Initial sync failed: {e}")
    
    # Initialize bot
    bot = Bot(
        token=settings.TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()
    dp.include_router(router)
    
    # Setup scheduler
    scheduler = AsyncIOScheduler()
    
    # Schedule OpenDataBot checks (e.g., 8:00 and 20:00)
    for hour in settings.opendatabot_hours:
        scheduler.add_job(
            scheduled_monitoring,
            CronTrigger(hour=hour, minute=0),
            args=[bot],
            id=f'monitoring_{hour}',
            name=f'Court monitoring at {hour}:00',
            replace_existing=True
        )
    
    # Schedule Worksection sync (e.g., 7:00 and 19:00 - before ODB checks)
    for hour in settings.worksection_hours:
        scheduler.add_job(
            scheduled_worksection_sync,
            CronTrigger(hour=hour, minute=0),
            args=[bot],
            id=f'worksection_sync_{hour}',
            name=f'Worksection sync at {hour}:00',
            replace_existing=True
        )
    
    scheduler.start()
    logger.info(f"Scheduler started: ODB at {settings.opendatabot_hours}, WS at {settings.worksection_hours}")
    
    # Start bot polling
    logger.info("Starting bot polling...")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
