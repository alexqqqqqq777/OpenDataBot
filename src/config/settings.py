import os
from pathlib import Path
from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = Field(default="sqlite:///./court_monitor.db")
    
    # OpenDataBot
    OPENDATABOT_API_KEY: str = Field(default="")
    OPENDATABOT_BASE_URL: str = Field(default="https://opendatabot.com/api/v3")
    
    # Worksection
    WORKSECTION_API_KEY: str = Field(default="")
    WORKSECTION_ACCOUNT: str = Field(default="")
    WORKSECTION_CASE_PATTERN: str = Field(default=r"(\d{3,4}/\d+/\d{2}(?:-[А-Яа-яІіЇїЄєҐґЦц]+)?)")
    
    # Gist-based Worksection sync (secure mode - no WS API key on server)
    WORKSECTION_GIST_ID: str = Field(default="")  # If set, use Gist instead of direct API
    
    # Telegram
    TELEGRAM_BOT_TOKEN: str = Field(default="")
    TELEGRAM_ADMIN_IDS: str = Field(default="")  # comma-separated user IDs
    
    # Monitoring Schedule (24h format)
    OPENDATABOT_CHECK_HOURS: str = Field(default="8,20")  # Morning 8:00, Evening 20:00
    WORKSECTION_SYNC_HOURS: str = Field(default="7,19")   # Before ODB checks
    INITIAL_RUN_MODE: str = Field(default="index_only")   # index_only | notify_all
    
    @property
    def opendatabot_hours(self) -> list:
        return [int(h.strip()) for h in self.OPENDATABOT_CHECK_HOURS.split(",")]
    
    @property
    def worksection_hours(self) -> list:
        return [int(h.strip()) for h in self.WORKSECTION_SYNC_HOURS.split(",")]
    
    # Threat detection
    DANGEROUS_PLAINTIFFS: str = Field(
        default="прокуратура,податкова,поліція,дбр,набу,сбу,держгеокадастр,виконавча служба"
    )
    HIGH_PRIORITY_CASE_TYPES: str = Field(default="2,5")  # 2=criminal, 5=admin violations
    
    @property
    def worksection_base_url(self) -> str:
        return f"https://{self.WORKSECTION_ACCOUNT}.worksection.com/api/admin/v2/"
    
    @property
    def admin_ids(self) -> List[int]:
        if not self.TELEGRAM_ADMIN_IDS:
            return []
        return [int(x.strip()) for x in self.TELEGRAM_ADMIN_IDS.split(",") if x.strip()]
    
    @property
    def dangerous_plaintiffs_list(self) -> List[str]:
        return [x.strip().lower() for x in self.DANGEROUS_PLAINTIFFS.split(",")]
    
    @property
    def high_priority_types(self) -> List[int]:
        return [int(x.strip()) for x in self.HIGH_PRIORITY_CASE_TYPES.split(",")]
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
