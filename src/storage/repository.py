from typing import List, Optional
from datetime import datetime
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from src.storage.models import (
    MonitoredCompany, OpenDataBotSubscription, WorksectionCase,
    CourtCase, NotificationSent, SyncState, UserSubscription,
    UserSettings, CaseSubscription, BotUser
)
import logging

logger = logging.getLogger(__name__)


class CompanyRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def add_company(self, edrpou: str, company_name: str = None, user_id: int = None) -> MonitoredCompany:
        company = MonitoredCompany(
            edrpou=edrpou,
            company_name=company_name,
            added_by_user_id=user_id,
            is_active=True
        )
        self.session.add(company)
        await self.session.commit()
        await self.session.refresh(company)
        return company
    
    async def get_company(self, edrpou: str) -> Optional[MonitoredCompany]:
        result = await self.session.execute(
            select(MonitoredCompany).where(MonitoredCompany.edrpou == edrpou)
        )
        return result.scalar_one_or_none()
    
    async def get_active_companies(self) -> List[MonitoredCompany]:
        result = await self.session.execute(
            select(MonitoredCompany).where(MonitoredCompany.is_active == True)
        )
        return list(result.scalars().all())
    
    async def get_all_companies(self) -> List[MonitoredCompany]:
        result = await self.session.execute(select(MonitoredCompany))
        return list(result.scalars().all())
    
    async def deactivate_company(self, edrpou: str) -> bool:
        result = await self.session.execute(
            update(MonitoredCompany)
            .where(MonitoredCompany.edrpou == edrpou)
            .values(is_active=False, updated_at=datetime.utcnow())
        )
        await self.session.commit()
        return result.rowcount > 0
    
    async def activate_company(self, edrpou: str) -> bool:
        result = await self.session.execute(
            update(MonitoredCompany)
            .where(MonitoredCompany.edrpou == edrpou)
            .values(is_active=True, updated_at=datetime.utcnow())
        )
        await self.session.commit()
        return result.rowcount > 0
    
    async def delete_company(self, edrpou: str) -> bool:
        result = await self.session.execute(
            delete(MonitoredCompany).where(MonitoredCompany.edrpou == edrpou)
        )
        await self.session.commit()
        return result.rowcount > 0


class SubscriptionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def add_subscription(
        self, subscription_id: str, edrpou: str, 
        subscription_type: str, subscription_key: str = None
    ) -> OpenDataBotSubscription:
        sub = OpenDataBotSubscription(
            subscription_id=subscription_id,
            edrpou=edrpou,
            subscription_type=subscription_type,
            subscription_key=subscription_key or edrpou
        )
        self.session.add(sub)
        await self.session.commit()
        return sub
    
    async def get_subscriptions_by_edrpou(self, edrpou: str) -> List[OpenDataBotSubscription]:
        result = await self.session.execute(
            select(OpenDataBotSubscription)
            .where(OpenDataBotSubscription.edrpou == edrpou)
            .where(OpenDataBotSubscription.is_active == True)
        )
        return list(result.scalars().all())
    
    async def get_all_active_subscriptions(self) -> List[OpenDataBotSubscription]:
        result = await self.session.execute(
            select(OpenDataBotSubscription).where(OpenDataBotSubscription.is_active == True)
        )
        return list(result.scalars().all())
    
    async def deactivate_subscription(self, subscription_id: str) -> bool:
        result = await self.session.execute(
            update(OpenDataBotSubscription)
            .where(OpenDataBotSubscription.subscription_id == subscription_id)
            .values(is_active=False)
        )
        await self.session.commit()
        return result.rowcount > 0


class WorksectionCaseRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def upsert_case(
        self, normalized_case_number: str, task_id: str,
        raw_name: str = None, project_id: str = None, project_name: str = None
    ) -> WorksectionCase:
        existing = await self.session.execute(
            select(WorksectionCase)
            .where(WorksectionCase.normalized_case_number == normalized_case_number)
            .where(WorksectionCase.task_id == task_id)
        )
        case = existing.scalar_one_or_none()
        
        if case:
            case.raw_name = raw_name
            case.project_id = project_id
            case.project_name = project_name
            case.synced_at = datetime.utcnow()
        else:
            case = WorksectionCase(
                normalized_case_number=normalized_case_number,
                task_id=task_id,
                raw_name=raw_name,
                project_id=project_id,
                project_name=project_name
            )
            self.session.add(case)
        
        await self.session.commit()
        return case
    
    async def case_exists(self, normalized_case_number: str) -> bool:
        result = await self.session.execute(
            select(WorksectionCase.id)
            .where(WorksectionCase.normalized_case_number == normalized_case_number)
            .limit(1)
        )
        return result.scalar_one_or_none() is not None
    
    async def get_all_case_numbers(self) -> List[str]:
        result = await self.session.execute(
            select(WorksectionCase.normalized_case_number).distinct()
        )
        return [r[0] for r in result.all()]


class CourtCaseRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def upsert_case(self, case_data: dict) -> CourtCase:
        case_id = case_data.get('case_id')
        
        if case_id:
            existing = await self.session.execute(
                select(CourtCase).where(CourtCase.case_id == case_id)
            )
            case = existing.scalar_one_or_none()
        else:
            case = None
        
        if case:
            for key, value in case_data.items():
                if hasattr(case, key):
                    setattr(case, key, value)
            case.fetched_at = datetime.utcnow()
        else:
            case = CourtCase(**case_data)
            self.session.add(case)
        
        await self.session.commit()
        return case
    
    async def get_case(self, case_id: str = None, case_number: str = None) -> Optional[CourtCase]:
        if case_id:
            result = await self.session.execute(
                select(CourtCase).where(CourtCase.case_id == case_id)
            )
        elif case_number:
            result = await self.session.execute(
                select(CourtCase).where(CourtCase.normalized_case_number == case_number)
            )
        else:
            return None
        return result.scalar_one_or_none()
    
    async def get_cases_by_threat_level(self, threat_level: str, limit: int = 10) -> List[CourtCase]:
        result = await self.session.execute(
            select(CourtCase)
            .where(CourtCase.threat_level == threat_level)
            .order_by(CourtCase.fetched_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def get_cases_by_status(self, status: str, limit: int = 10) -> List[CourtCase]:
        result = await self.session.execute(
            select(CourtCase)
            .where(CourtCase.status == status)
            .order_by(CourtCase.fetched_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def get_recent_cases(self, limit: int = 15) -> List[CourtCase]:
        result = await self.session.execute(
            select(CourtCase)
            .order_by(CourtCase.fetched_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def get_cases_by_edrpou(self, edrpou: str, limit: int = 20) -> List[CourtCase]:
        result = await self.session.execute(
            select(CourtCase)
            .where(CourtCase.edrpou_matches.contains(edrpou))
            .order_by(CourtCase.fetched_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def update_case_status(self, case_id: str, status: str) -> bool:
        result = await self.session.execute(
            update(CourtCase)
            .where(CourtCase.case_id == case_id)
            .values(status=status, updated_at=datetime.utcnow())
        )
        await self.session.commit()
        return result.rowcount > 0
    
    async def mark_in_worksection(self, case_number: str, task_id: str = None) -> bool:
        result = await self.session.execute(
            update(CourtCase)
            .where(CourtCase.normalized_case_number == case_number)
            .values(
                is_in_worksection=True,
                worksection_task_id=task_id,
                status="in_worksection",
                updated_at=datetime.utcnow()
            )
        )
        await self.session.commit()
        return result.rowcount > 0


class NotificationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def notification_sent(self, case_key: str) -> bool:
        result = await self.session.execute(
            select(NotificationSent.id)
            .where(NotificationSent.case_key == case_key)
            .limit(1)
        )
        return result.scalar_one_or_none() is not None
    
    async def add_notification(
        self, case_key: str, normalized_case_number: str = None,
        threat_level: str = None, telegram_message_id: str = None,
        telegram_chat_id: str = None, payload_hash: str = None
    ) -> NotificationSent:
        notification = NotificationSent(
            case_key=case_key,
            normalized_case_number=normalized_case_number,
            threat_level=threat_level,
            telegram_message_id=telegram_message_id,
            telegram_chat_id=telegram_chat_id,
            payload_hash=payload_hash
        )
        self.session.add(notification)
        await self.session.commit()
        return notification
    
    async def get_recent_notifications(self, limit: int = 10) -> List[NotificationSent]:
        result = await self.session.execute(
            select(NotificationSent)
            .order_by(NotificationSent.sent_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


class SyncStateRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_state(self, key: str) -> Optional[str]:
        result = await self.session.execute(
            select(SyncState.value).where(SyncState.key_name == key)
        )
        row = result.scalar_one_or_none()
        return row
    
    async def set_state(self, key: str, value: str):
        existing = await self.session.execute(
            select(SyncState).where(SyncState.key_name == key)
        )
        state = existing.scalar_one_or_none()
        
        if state:
            state.value = value
            state.updated_at = datetime.utcnow()
        else:
            state = SyncState(key_name=key, value=value)
            self.session.add(state)
        
        await self.session.commit()


class UserSubscriptionRepository:
    """Repository for user-company subscriptions (multi-tenant)"""
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def subscribe(self, user_id: int, edrpou: str) -> UserSubscription:
        """Subscribe user to company notifications"""
        existing = await self.session.execute(
            select(UserSubscription)
            .where(UserSubscription.user_id == user_id)
            .where(UserSubscription.edrpou == edrpou)
        )
        sub = existing.scalar_one_or_none()
        
        if sub:
            sub.is_active = True
        else:
            sub = UserSubscription(user_id=user_id, edrpou=edrpou, is_active=True)
            self.session.add(sub)
        
        await self.session.commit()
        return sub
    
    async def unsubscribe(self, user_id: int, edrpou: str) -> bool:
        """Unsubscribe user from company"""
        result = await self.session.execute(
            update(UserSubscription)
            .where(UserSubscription.user_id == user_id)
            .where(UserSubscription.edrpou == edrpou)
            .values(is_active=False)
        )
        await self.session.commit()
        return result.rowcount > 0
    
    async def get_user_subscriptions(self, user_id: int) -> List[UserSubscription]:
        """Get all active subscriptions for a user"""
        result = await self.session.execute(
            select(UserSubscription)
            .where(UserSubscription.user_id == user_id)
            .where(UserSubscription.is_active == True)
        )
        return list(result.scalars().all())
    
    async def get_users_for_edrpou(self, edrpou: str) -> List[int]:
        """Get all user IDs subscribed to this EDRPOU"""
        result = await self.session.execute(
            select(UserSubscription.user_id)
            .where(UserSubscription.edrpou == edrpou)
            .where(UserSubscription.is_active == True)
        )
        return [r[0] for r in result.all()]
    
    async def get_subscription(self, user_id: int, edrpou: str) -> Optional[UserSubscription]:
        """Get specific subscription"""
        result = await self.session.execute(
            select(UserSubscription)
            .where(UserSubscription.user_id == user_id)
            .where(UserSubscription.edrpou == edrpou)
        )
        return result.scalar_one_or_none()
    
    async def is_subscribed(self, user_id: int, edrpou: str) -> bool:
        """Check if user is subscribed to company"""
        result = await self.session.execute(
            select(UserSubscription.id)
            .where(UserSubscription.user_id == user_id)
            .where(UserSubscription.edrpou == edrpou)
            .where(UserSubscription.is_active == True)
            .limit(1)
        )
        return result.scalar_one_or_none() is not None


class UserSettingsRepository:
    """Repository for user settings"""
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_settings(self, user_id: int) -> Optional[UserSettings]:
        """Get user settings"""
        result = await self.session.execute(
            select(UserSettings).where(UserSettings.user_id == user_id)
        )
        return result.scalar_one_or_none()
    
    async def get_or_create(self, user_id: int) -> UserSettings:
        """Get or create user settings"""
        settings = await self.get_settings(user_id)
        if not settings:
            settings = UserSettings(user_id=user_id)
            self.session.add(settings)
            await self.session.commit()
            await self.session.refresh(settings)
        return settings
    
    async def set_receive_all(self, user_id: int, value: bool) -> UserSettings:
        """Set receive_all_notifications preference"""
        settings = await self.get_or_create(user_id)
        settings.receive_all_notifications = value
        await self.session.commit()
        return settings
    
    async def get_receive_all(self, user_id: int) -> bool:
        """Check if user wants to receive all notifications"""
        settings = await self.get_settings(user_id)
        return settings.receive_all_notifications if settings else False


class CaseSubscriptionRepository:
    """Repository for case subscriptions"""
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def subscribe(self, user_id: int, case_number: str, case_name: str = None) -> CaseSubscription:
        """Subscribe user to a specific court case"""
        existing = await self.session.execute(
            select(CaseSubscription)
            .where(CaseSubscription.user_id == user_id)
            .where(CaseSubscription.case_number == case_number)
        )
        sub = existing.scalar_one_or_none()
        
        if sub:
            sub.is_active = True
            if case_name:
                sub.case_name = case_name
        else:
            sub = CaseSubscription(
                user_id=user_id, 
                case_number=case_number, 
                case_name=case_name,
                is_active=True
            )
            self.session.add(sub)
        
        await self.session.commit()
        return sub
    
    async def unsubscribe(self, user_id: int, case_number: str) -> bool:
        """Unsubscribe user from a case"""
        result = await self.session.execute(
            update(CaseSubscription)
            .where(CaseSubscription.user_id == user_id)
            .where(CaseSubscription.case_number == case_number)
            .values(is_active=False)
        )
        await self.session.commit()
        return result.rowcount > 0
    
    async def get_user_cases(self, user_id: int) -> List[CaseSubscription]:
        """Get all active case subscriptions for a user"""
        result = await self.session.execute(
            select(CaseSubscription)
            .where(CaseSubscription.user_id == user_id)
            .where(CaseSubscription.is_active == True)
        )
        return list(result.scalars().all())
    
    async def get_users_for_case(self, case_number: str) -> List[int]:
        """Get all user IDs subscribed to this case number"""
        result = await self.session.execute(
            select(CaseSubscription.user_id)
            .where(CaseSubscription.case_number == case_number)
            .where(CaseSubscription.is_active == True)
        )
        return [r[0] for r in result.all()]
    
    async def is_subscribed(self, user_id: int, case_number: str) -> bool:
        """Check if user is subscribed to a case"""
        result = await self.session.execute(
            select(CaseSubscription.id)
            .where(CaseSubscription.user_id == user_id)
            .where(CaseSubscription.case_number == case_number)
            .where(CaseSubscription.is_active == True)
            .limit(1)
        )
        return result.scalar_one_or_none() is not None


class BotUserRepository:
    """Repository for bot user access control"""
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_or_create(self, telegram_user_id: int, username: str = None, full_name: str = None) -> BotUser:
        """Get or create bot user on /start"""
        result = await self.session.execute(
            select(BotUser).where(BotUser.telegram_user_id == telegram_user_id)
        )
        user = result.scalar_one_or_none()
        
        if user:
            # Update profile info if changed
            changed = False
            if username and user.username != username:
                user.username = username
                changed = True
            if full_name and user.full_name != full_name:
                user.full_name = full_name
                changed = True
            if changed:
                await self.session.commit()
            return user
        
        user = BotUser(
            telegram_user_id=telegram_user_id,
            username=username,
            full_name=full_name,
            contractor_access=False,
            contractor_access_requested=False,
            is_active=True
        )
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user
    
    async def get_user(self, telegram_user_id: int) -> Optional[BotUser]:
        """Get bot user by telegram ID"""
        result = await self.session.execute(
            select(BotUser).where(BotUser.telegram_user_id == telegram_user_id)
        )
        return result.scalar_one_or_none()
    
    async def has_contractor_access(self, telegram_user_id: int) -> bool:
        """Check if user has contractor check access"""
        result = await self.session.execute(
            select(BotUser.contractor_access)
            .where(BotUser.telegram_user_id == telegram_user_id)
        )
        row = result.scalar_one_or_none()
        return row is True
    
    async def set_contractor_access(self, telegram_user_id: int, granted: bool) -> bool:
        """Grant or revoke contractor access"""
        result = await self.session.execute(
            update(BotUser)
            .where(BotUser.telegram_user_id == telegram_user_id)
            .values(contractor_access=granted, contractor_access_requested=False)
        )
        await self.session.commit()
        return result.rowcount > 0
    
    async def set_access_requested(self, telegram_user_id: int) -> bool:
        """Mark that user has requested contractor access"""
        result = await self.session.execute(
            update(BotUser)
            .where(BotUser.telegram_user_id == telegram_user_id)
            .values(contractor_access_requested=True)
        )
        await self.session.commit()
        return result.rowcount > 0
    
    async def get_all_users(self) -> List[BotUser]:
        """Get all bot users"""
        result = await self.session.execute(
            select(BotUser).order_by(BotUser.created_at)
        )
        return list(result.scalars().all())
