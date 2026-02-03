from typing import List, Dict, Any
from datetime import datetime
from src.clients import OpenDataBotClient
from src.storage import (
    AsyncSessionLocal, CompanyRepository, SubscriptionRepository,
    WorksectionCaseRepository, NotificationRepository, SyncStateRepository,
    CourtCaseRepository, UserSubscriptionRepository, UserSettingsRepository,
    CaseSubscriptionRepository
)
from src.services.threat_analyzer import analyze_threat
from src.services.notifier import TelegramNotifier
from src.utils import normalize_case_number, generate_case_key
from aiogram import Bot
import logging

logger = logging.getLogger(__name__)


class CourtMonitoringService:
    """Main service for court case monitoring"""
    
    def __init__(self, bot: Bot = None):
        self.odb_client = OpenDataBotClient()
        self.notifier = TelegramNotifier(bot)
    
    async def setup_subscriptions(self) -> int:
        """
        Create OpenDataBot subscriptions for all active companies.
        Uses subscription type 'company' per OpenDataBot documentation.
        
        Returns:
            Number of new subscriptions created
        """
        created = 0
        
        async with AsyncSessionLocal() as session:
            company_repo = CompanyRepository(session)
            sub_repo = SubscriptionRepository(session)
            
            companies = await company_repo.get_active_companies()
            logger.info(f"Setting up subscriptions for {len(companies)} companies")
            
            for company in companies:
                edrpou = company.edrpou
                
                # Check existing subscriptions
                existing = await sub_repo.get_subscriptions_by_edrpou(edrpou)
                existing_types = {s.subscription_type for s in existing}
                
                # Create company subscription (monitors all court cases by EDRPOU)
                # Per OpenDataBot docs: type=company for monitoring legal entities
                if 'company' not in existing_types:
                    try:
                        result = await self.odb_client.create_subscription(
                            subscription_type='company',
                            subscription_key=edrpou
                        )
                        sub_id = result.get('data', {}).get('id')
                        if sub_id:
                            await sub_repo.add_subscription(
                                subscription_id=str(sub_id),
                                edrpou=edrpou,
                                subscription_type='company'
                            )
                            created += 1
                            logger.info(f"Created company subscription for {edrpou}")
                    except Exception as e:
                        logger.error(f"Failed to create subscription for {edrpou}: {e}")
        
        return created
    
    async def check_new_cases(self) -> int:
        """
        Check for new court cases via OpenDataBot history.
        
        History format from OpenDataBot:
        {
            "notificationId": "123",
            "date": "2026-01-16",
            "type": "court",
            "code": "34328899",  # EDRPOU
            "text": "...",
            "items": [
                {"caseNumber": "370/4268/25", "courtName": "...", "form": "Цивільне", ...}
            ]
        }
        
        Returns:
            Number of new notifications sent
        """
        notifications_sent = 0
        
        async with AsyncSessionLocal() as session:
            sync_repo = SyncStateRepository(session)
            ws_repo = WorksectionCaseRepository(session)
            notification_repo = NotificationRepository(session)
            company_repo = CompanyRepository(session)
            case_repo = CourtCaseRepository(session)
            
            # Get last processed notification ID
            last_id = await sync_repo.get_state('opendatabot_last_notification_id')
            
            # Get active EDRPOUs (normalize by stripping leading zeros)
            companies = await company_repo.get_active_companies()
            edrpou_set = {c.edrpou.lstrip('0') for c in companies}
            edrpou_names = {c.edrpou.lstrip('0'): c.company_name for c in companies}
            # Also keep original for lookup
            edrpou_original = {c.edrpou.lstrip('0'): c.edrpou for c in companies}
            
            if not edrpou_set:
                logger.info("No active companies to monitor")
                return 0
            
            # Get Worksection case numbers for deduplication
            ws_case_numbers = set(await ws_repo.get_all_case_numbers())
            
            logger.info(f"Checking history from_id={last_id}, tracking {len(edrpou_set)} companies")
            
            # Fetch history (type=court for court cases)
            history = await self.odb_client.get_history(limit=100)
            
            items = history.get('items', [])
            logger.info(f"Received {len(items)} history items")
            
            max_id = last_id
            
            for event in items:
                notification_id = str(event.get('notificationId', ''))
                event_edrpou_raw = str(event.get('code', ''))
                event_edrpou = event_edrpou_raw.lstrip('0')  # Normalize EDRPOU
                event_type = event.get('type', '')
                
                # Skip if not court event
                if event_type != 'court':
                    continue
                
                # Skip if not our company
                if event_edrpou not in edrpou_set:
                    logger.debug(f"Event for {event_edrpou_raw} (normalized: {event_edrpou}) - not in monitoring list, skipping")
                    continue
                
                # Track max ID
                if notification_id and (not max_id or notification_id > max_id):
                    max_id = notification_id
                
                # Skip if already processed
                if last_id and notification_id <= last_id:
                    continue
                
                # Process court items from this event
                court_items = event.get('items', [])
                logger.info(f"Processing event {notification_id} for {event_edrpou}: {len(court_items)} court items")
                
                for ci in court_items:
                    case_number = ci.get('caseNumber', '')
                    normalized = normalize_case_number(case_number)
                    
                    if not normalized:
                        continue
                    
                    # Check if in Worksection (already known)
                    is_in_worksection = normalized in ws_case_numbers
                    
                    # Get original EDRPOU for DB lookups
                    original_edrpou = edrpou_original.get(event_edrpou, event_edrpou)
                    
                    # Build case data
                    case_data = {
                        'case_id': ci.get('number'),
                        'normalized_case_number': normalized,
                        'court_name': ci.get('courtName', ''),
                        'case_type_name': ci.get('form', ''),
                        'document_type': ci.get('type', ''),
                        'date_opened': ci.get('date'),
                        'source_link': ci.get('documentLink', ''),
                        'edrpou_matches': [original_edrpou],
                        'company_name': edrpou_names.get(event_edrpou, ''),
                    }
                    
                    # Determine threat level
                    is_criminal = 'Кримінальне' in ci.get('form', '')
                    threat_analysis = analyze_threat(case_data, 'defendant')
                    if is_criminal:
                        threat_analysis['threat_level'] = 'CRITICAL'
                        threat_analysis['emoji'] = '🚨'
                    
                    # Save to local DB
                    await case_repo.upsert_case({
                        'case_id': ci.get('number'),
                        'normalized_case_number': normalized,
                        'court_name': ci.get('courtName'),
                        'case_type_name': ci.get('form'),
                        'source_link': ci.get('documentLink'),
                        'edrpou_matches': [original_edrpou],
                        'status': 'new',
                        'threat_level': threat_analysis.get('threat_level', 'MEDIUM'),
                        'is_in_worksection': is_in_worksection,
                    })
                    
                    # Get subscribed users and their settings
                    user_sub_repo = UserSubscriptionRepository(session)
                    settings_repo = UserSettingsRepository(session)
                    case_sub_repo = CaseSubscriptionRepository(session)
                    
                    subscribed_users = await user_sub_repo.get_users_for_edrpou(original_edrpou)
                    
                    # Also get users subscribed to this specific case number
                    case_subscribed_users = await case_sub_repo.get_users_for_case(normalized)
                    
                    # Combine and deduplicate users
                    all_users = set(subscribed_users) | set(case_subscribed_users)
                    
                    if all_users:
                        for user_id in all_users:
                            # Check user settings
                            receive_all = await settings_repo.get_receive_all(user_id)
                            is_case_sub = user_id in case_subscribed_users
                            
                            # Skip if in Worksection AND user doesn't want all notifications AND not case subscription
                            if is_in_worksection and not receive_all and not is_case_sub:
                                logger.debug(f"Skipping {normalized} for user {user_id} - in WS, filter enabled")
                                continue
                            
                            msg_id = await self.notifier.send_case_notification(
                                case_data=case_data,
                                threat_analysis=threat_analysis,
                                edrpou_matches=[original_edrpou],
                                chat_id=str(user_id),
                                is_new_case=not is_in_worksection,
                                is_case_subscription=is_case_sub
                            )
                            if msg_id:
                                notifications_sent += 1
                        logger.info(f"Processed case {normalized} for {len(all_users)} users (in_ws={is_in_worksection})")
                    else:
                        # Fallback to admin if no user subscriptions (only if not in Worksection)
                        if not is_in_worksection:
                            msg_id = await self.notifier.send_case_notification(
                                case_data=case_data,
                                threat_analysis=threat_analysis,
                                edrpou_matches=[original_edrpou],
                                is_new_case=True
                            )
                            if msg_id:
                                notifications_sent += 1
                                logger.info(f"Sent admin notification for case {normalized}")
            
            # Update last processed ID
            if max_id and max_id != last_id:
                await sync_repo.set_state('opendatabot_last_notification_id', max_id)
        
        logger.info(f"Check completed: {notifications_sent} notifications sent")
        return notifications_sent
    
    def _extract_case_data(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Extract case data from history item"""
        data = item.get('data', {})
        
        case_number = data.get('case_number') or data.get('number')
        
        if not case_number:
            return {}
        
        return {
            'case_id': data.get('id'),
            'case_number': case_number,
            'normalized_case_number': normalize_case_number(case_number),
            'court_code': data.get('court_code'),
            'court_name': data.get('court_name') or data.get('court'),
            'case_type': data.get('judgment') or data.get('case_type'),
            'plaintiff': data.get('plaintiff') or data.get('sides', {}).get('plaintiff'),
            'defendant': data.get('defendant') or data.get('sides', {}).get('defendant'),
            'subject': data.get('subject') or data.get('description'),
            'claim_amount': data.get('claim_amount'),
            'date_opened': data.get('date_opened') or data.get('date'),
            'stage': data.get('stage') or data.get('status'),
            'judge': data.get('judge'),
            'source_link': data.get('link') or data.get('url'),
            'raw_data': item
        }
    
    def _find_edrpou_matches(self, item: Dict[str, Any], edrpou_set: set) -> List[str]:
        """Find which tracked EDRPOUs match this case"""
        matches = []
        
        subscription_key = item.get('subscription_key', '')
        if subscription_key in edrpou_set:
            matches.append(subscription_key)
        
        # Also check in case data
        data = item.get('data', {})
        text_to_check = str(data.get('plaintiff', '')) + str(data.get('defendant', ''))
        
        for edrpou in edrpou_set:
            if edrpou in text_to_check and edrpou not in matches:
                matches.append(edrpou)
        
        return matches


async def run_monitoring_cycle(bot: Bot = None):
    """Run one monitoring cycle"""
    service = CourtMonitoringService(bot)
    
    try:
        # Setup any new subscriptions
        new_subs = await service.setup_subscriptions()
        if new_subs:
            logger.info(f"Created {new_subs} new subscriptions")
        
        # Check for new cases
        notifications = await service.check_new_cases()
        logger.info(f"Monitoring cycle complete: {notifications} notifications")
        
        return notifications
        
    except Exception as e:
        logger.error(f"Monitoring cycle error: {e}")
        raise
