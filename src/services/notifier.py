from typing import Dict, Any, Optional, List
from aiogram import Bot
from src.config import settings
from src.storage import AsyncSessionLocal, NotificationRepository
from src.services.threat_analyzer import get_threat_emoji, get_role_description
from src.utils import generate_case_key
import hashlib
import json
import logging

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Send court case notifications to Telegram"""
    
    def __init__(self, bot: Bot = None):
        self.bot = bot or Bot(token=settings.TELEGRAM_BOT_TOKEN)
        self.chat_id = None  # Will be set from admin IDs or specific chat
    
    async def send_case_notification(
        self,
        case_data: Dict[str, Any],
        threat_analysis: Dict[str, Any],
        chat_id: str = None,
        edrpou_matches: List[str] = None,
        is_new_case: bool = True,  # True if NOT in Worksection (RED ALERT)
        is_case_subscription: bool = False  # True if from case subscription
    ) -> Optional[str]:
        """
        Send notification about new court case.
        
        Returns:
            Message ID if sent successfully, None otherwise
        """
        target_chat = chat_id or self._get_default_chat()
        
        if not target_chat:
            logger.error("No chat ID configured for notifications")
            return None
        
        # Generate case key for deduplication (per user)
        base_case_key = generate_case_key(
            case_id=case_data.get('case_id'),
            case_number=case_data.get('normalized_case_number') or case_data.get('case_number'),
            court_code=case_data.get('court_code')
        )
        case_key = f"{base_case_key}:{target_chat}"  # Per-user deduplication
        
        # Check if already notified to this user
        async with AsyncSessionLocal() as session:
            repo = NotificationRepository(session)
            
            if await repo.notification_sent(case_key):
                logger.debug(f"Notification already sent for {case_key}")
                return None
            
            # Format message
            message = self._format_case_message(
                case_data, threat_analysis, edrpou_matches, 
                is_new_case, is_case_subscription
            )
            
            # Send message
            try:
                sent = await self.bot.send_message(
                    chat_id=target_chat,
                    text=message,
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
                
                # Record notification
                payload_hash = hashlib.md5(json.dumps(case_data, sort_keys=True, default=str).encode()).hexdigest()
                
                await repo.add_notification(
                    case_key=case_key,
                    normalized_case_number=case_data.get('normalized_case_number'),
                    threat_level=threat_analysis.get('threat_level'),
                    telegram_message_id=str(sent.message_id),
                    telegram_chat_id=target_chat,
                    payload_hash=payload_hash
                )
                
                logger.info(f"Notification sent for case {case_key}")
                return str(sent.message_id)
                
            except Exception as e:
                logger.error(f"Failed to send notification: {e}")
                return None
    
    def _format_case_message(
        self,
        case_data: Dict[str, Any],
        threat_analysis: Dict[str, Any],
        edrpou_matches: List[str] = None,
        is_new_case: bool = True,
        is_case_subscription: bool = False
    ) -> str:
        """Format case data into Telegram message - industrial quality"""
        from datetime import datetime
        
        threat_level = threat_analysis.get('threat_level', 'MEDIUM')
        is_criminal = threat_analysis.get('is_criminal', False)
        case_category = threat_analysis.get('case_category', 'civil')
        
        # RED ALERT prefix for new cases not in Worksection
        red_alert = ""
        if is_new_case:
            red_alert = "🔴🔴🔴 <b>НОВА СПРАВА!</b> 🔴🔴🔴\n<i>⚡ Справи НЕМАЄ в Worksection!</i>\n\n"
        
        # Case subscription prefix
        case_sub_prefix = ""
        if is_case_subscription:
            case_sub_prefix = "📌 <b>МОНІТОРИНГ СПРАВИ</b>\n\n"
        
        # Header based on threat level
        if threat_level == "CRITICAL":
            header = "🚨 <b>КРИТИЧНО: Кримінальна справа</b>"
        elif threat_level == "HIGH":
            header = "⚠️ <b>УВАГА: Держорган-позивач</b>"
        elif threat_level == "LOW":
            header = "ℹ️ <b>Інформаційно: Компанія-позивач</b>"
        else:
            # Different header for cases already in Worksection
            if is_new_case:
                header = "📋 <b>Нова судова справа</b>"
            else:
                header = "📄 <b>Оновлення по справі</b>"
        
        # Combine prefixes
        header = red_alert + case_sub_prefix + header
        
        # Case info
        case_number = case_data.get('normalized_case_number') or case_data.get('case_number', 'N/A')
        court = case_data.get('court_name', '')
        case_type = case_data.get('case_type_name') or case_data.get('form', '')
        doc_type = case_data.get('document_type', '')
        company_name = case_data.get('company_name', '')
        
        # Shorten court name
        if court:
            court = court.replace('районний суд', 'р-н суд').replace('області', 'обл.')
        
        # Build compact message
        msg = f"""{header}

<b>№ {case_number}</b>
{court}

├ Тип: {case_type}"""
        
        if doc_type:
            msg += f"\n├ Документ: {doc_type}"
        
        if company_name:
            msg += f"\n├ Компанія: {company_name}"
        
        if edrpou_matches:
            msg += f"\n└ ЄДРПОУ: <code>{edrpou_matches[0]}</code>"
        
        # Source link
        source_link = case_data.get('source_link')
        if source_link:
            msg += f"\n\n🔗 <a href=\"{source_link}\">Переглянути документ</a>"
        
        # Timestamp
        msg += f"\n\n<i>{datetime.now().strftime('%d.%m.%Y %H:%M')}</i>"
        
        return msg
    
    def _truncate(self, text: str, max_len: int) -> str:
        """Truncate text to max length"""
        if len(text) <= max_len:
            return text
        return text[:max_len-3] + "..."
    
    def _get_default_chat(self) -> Optional[str]:
        """Get default chat ID for notifications"""
        admin_ids = settings.admin_ids
        if admin_ids:
            return str(admin_ids[0])
        return None
    
    async def send_test_message(self, chat_id: str = None) -> bool:
        """Send test message to verify connection"""
        target = chat_id or self._get_default_chat()
        
        if not target:
            logger.error("No chat ID for test message")
            return False
        
        try:
            await self.bot.send_message(
                chat_id=target,
                text="🔧 Тестове повідомлення. Бот працює!",
                parse_mode="HTML"
            )
            return True
        except Exception as e:
            logger.error(f"Test message failed: {e}")
            return False
