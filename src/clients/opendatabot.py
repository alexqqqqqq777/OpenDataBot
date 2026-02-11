import httpx
import json
from typing import List, Dict, Any, Optional
from src.config import settings
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import logging
from datetime import datetime
from pathlib import Path
from sqlalchemy import select
from src.storage.database import get_db
from src.storage.models import ApiResponseCache

logger = logging.getLogger(__name__)

# Dedicated logger for OpenDataBot API responses
odb_history_logger = logging.getLogger('opendatabot.history')


class OpenDataBotError(Exception):
    """OpenDataBot API error"""
    pass


class RateLimitError(OpenDataBotError):
    """Rate limit exceeded"""
    pass


class OpenDataBotClient:
    """Client for OpenDataBot API v3"""
    
    def __init__(self):
        self.api_key = settings.OPENDATABOT_API_KEY
        self.full_api_key = getattr(settings, 'OPENDATABOT_FULL_API_KEY', self.api_key)
        self.base_url = settings.OPENDATABOT_BASE_URL
        self.timeout = 30.0
    
    @retry(
        stop=stop_after_attempt(3), 
        wait=wait_exponential(multiplier=2, min=4, max=30),
        retry=retry_if_exception_type(RateLimitError)
    )
    async def _request(
        self, method: str, endpoint: str, 
        params: Dict[str, Any] = None, 
        data: Dict[str, Any] = None
    ) -> Dict:
        """Make authenticated request to OpenDataBot API"""
        params = params or {}
        params['apiKey'] = self.api_key
        
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            if method.upper() == 'GET':
                response = await client.get(url, params=params)
            elif method.upper() == 'POST':
                response = await client.post(url, params=params, data=data)
            elif method.upper() == 'DELETE':
                response = await client.delete(url, params=params)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            # Handle rate limiting
            if response.status_code == 429:
                logger.warning("OpenDataBot rate limit hit, retrying...")
                raise RateLimitError("Rate limit exceeded")
            
            if response.status_code == 503:
                raise OpenDataBotError("Service unavailable")
            
            response.raise_for_status()
            return response.json()
    
    # === Subscriptions ===
    
    async def create_subscription(
        self, subscription_type: str, subscription_key: str,
        second_side: str = None, court_id: str = None
    ) -> Dict:
        """
        Create a monitoring subscription.
        
        Types for court monitoring:
        - new-court-defendant: new cases where company is defendant
        - new-court-plaintiff: new cases where company is plaintiff
        - court-by-involved: changes in cases by party
        - court-by-number: changes in specific case by number
        """
        params = {
            'type': subscription_type,
            'subscriptionKey': subscription_key
        }
        
        if second_side:
            params['secondSide'] = second_side
        if court_id:
            params['courtId'] = court_id
        
        data = await self._request('POST', '/subscriptions', params=params)
        logger.info(f"Created subscription: {subscription_type} for {subscription_key}")
        return data
    
    async def get_subscriptions(
        self, subscription_type: str = None, 
        subscription_key: str = None,
        limit: int = 100
    ) -> List[Dict]:
        """Get list of subscriptions"""
        params = {'limit': limit}
        if subscription_type:
            params['type'] = subscription_type
        if subscription_key:
            params['subscriptionKey'] = subscription_key
        
        data = await self._request('GET', '/subscriptions', params=params)
        return data.get('data', {}).get('items', [])
    
    async def delete_subscription(self, subscription_id: int) -> bool:
        """Delete a subscription"""
        try:
            await self._request('DELETE', f'/subscriptions/{subscription_id}')
            logger.info(f"Deleted subscription: {subscription_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete subscription {subscription_id}: {e}")
            return False
    
    # === History (notifications) ===
    
    async def get_history(
        self, from_id: str = None, subscription_id: str = None,
        notification_type: str = None, date_start: str = None,
        date_end: str = None, limit: int = 100, offset: int = 0
    ) -> Dict:
        """
        Get notification history.
        
        Types for court cases:
        - new_court_defendant
        - new_court_plaintiff
        - court
        - court_status
        - involved
        """
        params = {
            'limit': limit,
            'offset': offset
        }
        
        if from_id:
            params['from_id'] = from_id
        if subscription_id:
            params['subscription_id'] = subscription_id
        if notification_type:
            params['type'] = notification_type
        if date_start:
            params['date_start'] = date_start
        if date_end:
            params['date_end'] = date_end
        
        data = await self._request('GET', '/history', params=params)
        
        # Full logging of history response
        history_data = data.get('data', {})
        items = history_data.get('items', [])
        
        odb_history_logger.info(f"=== OpenDataBot History Response ===")
        odb_history_logger.info(f"Timestamp: {datetime.now().isoformat()}")
        odb_history_logger.info(f"Params: from_id={from_id}, type={notification_type}, limit={limit}")
        odb_history_logger.info(f"Total items received: {len(items)}")
        
        for idx, item in enumerate(items):
            odb_history_logger.info(
                f"[{idx+1}/{len(items)}] notificationId={item.get('notificationId')} | "
                f"type={item.get('type')} | code={item.get('code')} | date={item.get('date')}"
            )
            # Log full item as JSON for detailed analysis
            odb_history_logger.debug(f"Full item: {json.dumps(item, ensure_ascii=False, default=str)}")
        
        odb_history_logger.info(f"=== End History Response ===")
        
        return history_data
    
    # === Court Status ===
    
    async def get_court_status(
        self, case_number: str = None, text_involved: str = None,
        date_from: str = None, date_to: str = None,
        limit: int = 100, offset: int = 0
    ) -> List[Dict]:
        """Get court case status information"""
        params = {
            'limit': limit,
            'offset': offset
        }
        
        if case_number:
            params['case_number'] = case_number
        if text_involved:
            params['text_involved'] = text_involved
        if date_from:
            params['date_from'] = date_from
        if date_to:
            params['date_to'] = date_to
        
        data = await self._request('GET', '/court-status', params=params)
        return data.get('data', {}).get('items', [])
    
    # === Company Info ===
    
    async def get_company(self, code: str) -> Optional[Dict]:
        """Get company info by EDRPOU"""
        try:
            data = await self._request('GET', f'/company/{code}')
            return data.get('data')
        except Exception as e:
            logger.error(f"Failed to get company {code}: {e}")
            return None
    
    async def test_connection(self) -> bool:
        """Test API connection"""
        if not self.api_key:
            logger.warning("OpenDataBot API key not configured")
            return False
        
        try:
            # Try to get subscriptions list
            await self.get_subscriptions()
            logger.info("OpenDataBot connection OK")
            return True
        except Exception as e:
            logger.error(f"OpenDataBot connection failed: {e}")
            return False
    
    # === Full Company/Person Check (uses separate API key) ===
    
    async def _get_from_cache(self, endpoint: str, query_key: str) -> Optional[tuple]:
        """Get cached API response from database. Returns (data, cached_at) or None"""
        async with get_db() as session:
            result = await session.execute(
                select(ApiResponseCache).where(
                    ApiResponseCache.endpoint == endpoint,
                    ApiResponseCache.query_key == query_key
                )
            )
            cached = result.scalar_one_or_none()
            
            if cached:
                # Increment hit count
                cached.hit_count += 1
                await session.commit()
                logger.info(f"Cache HIT for {endpoint}/{query_key} (hits: {cached.hit_count})")
                return (cached.response_data, cached.updated_at)
            
            return None
    
    async def _delete_from_cache(self, endpoint: str, query_key: str):
        """Delete cached entry to force refresh"""
        async with get_db() as session:
            result = await session.execute(
                select(ApiResponseCache).where(
                    ApiResponseCache.endpoint == endpoint,
                    ApiResponseCache.query_key == query_key
                )
            )
            cached = result.scalar_one_or_none()
            if cached:
                await session.delete(cached)
                await session.commit()
                logger.info(f"Cache DELETED for {endpoint}/{query_key}")
    
    async def _save_to_cache(self, endpoint: str, query_key: str, response_data: Dict):
        """Save API response to cache in database"""
        async with get_db() as session:
            # Check if exists (upsert)
            result = await session.execute(
                select(ApiResponseCache).where(
                    ApiResponseCache.endpoint == endpoint,
                    ApiResponseCache.query_key == query_key
                )
            )
            existing = result.scalar_one_or_none()
            
            if existing:
                existing.response_data = response_data
                existing.updated_at = datetime.utcnow()
            else:
                cache_entry = ApiResponseCache(
                    endpoint=endpoint,
                    query_key=query_key,
                    response_data=response_data
                )
                session.add(cache_entry)
            
            await session.commit()
            logger.info(f"Cache SAVED for {endpoint}/{query_key}")
    
    async def _request_full(self, endpoint: str, params: Dict[str, Any] = None) -> Dict:
        """Make request using FULL API key for company/person checks"""
        full_api_key = settings.OPENDATABOT_FULL_API_KEY
        if not full_api_key:
            raise OpenDataBotError("OPENDATABOT_FULL_API_KEY not configured")
        
        params = params or {}
        params['apiKey'] = full_api_key
        
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url, params=params)
            
            if response.status_code == 429:
                raise RateLimitError("Rate limit exceeded")
            if response.status_code == 404:
                return {"status": "error", "message": "Not found"}
            if response.status_code == 402:
                raise OpenDataBotError("Payment required - API limit reached")
            
            response.raise_for_status()
            return response.json()
    
    async def get_full_company(self, code: str, force_refresh: bool = False) -> Optional[Dict]:
        """
        Get full company information by EDRPOU code.
        Includes: registry data, factors (tax, court, sanctions), beneficiaries, etc.
        Uses cache to reduce API costs.
        Returns dict with 'data' and 'cached_at' (None if fresh from API).
        """
        endpoint = 'full-company'
        
        # Force refresh - delete cache first
        if force_refresh:
            await self._delete_from_cache(endpoint, code)
        else:
            # Check cache first
            cached = await self._get_from_cache(endpoint, code)
            if cached:
                data, cached_at = cached
                return {'data': data, 'cached_at': cached_at}
        
        try:
            data = await self._request_full(f'/full-company/{code}')
            if data.get('status') == 'ok':
                result = data.get('data')
                # Save to cache
                await self._save_to_cache(endpoint, code, result)
                return {'data': result, 'cached_at': None}
            return None
        except Exception as e:
            logger.error(f"Failed to get full company {code}: {e}")
            raise
    
    async def get_fop(self, code: str, force_refresh: bool = False) -> Optional[Dict]:
        """
        Get FOP (individual entrepreneur) info by IPN code.
        Uses cache to reduce API costs.
        """
        endpoint = 'fop'
        
        if force_refresh:
            await self._delete_from_cache(endpoint, code)
        else:
            cached = await self._get_from_cache(endpoint, code)
            if cached:
                data, cached_at = cached
                return {'data': data, 'cached_at': cached_at}
        
        try:
            data = await self._request_full(f'/fop/{code}')
            if data.get('status') == 'ok':
                result = data.get('data')
                await self._save_to_cache(endpoint, code, result)
                return {'data': result, 'cached_at': None}
            return None
        except Exception as e:
            logger.error(f"Failed to get FOP {code}: {e}")
            raise
    
    async def get_person(self, pib: str, force_refresh: bool = False) -> Optional[Dict]:
        """
        Get person information by full name (PIB).
        Uses cache to reduce API costs.
        """
        endpoint = 'person'
        query_key = pib.strip().upper()
        
        if force_refresh:
            await self._delete_from_cache(endpoint, query_key)
        else:
            cached = await self._get_from_cache(endpoint, query_key)
            if cached:
                data, cached_at = cached
                return {'data': data, 'cached_at': cached_at}
        
        try:
            data = await self._request_full('/person', params={'pib': pib})
            if data.get('status') == 'ok':
                result = data.get('data')
                await self._save_to_cache(endpoint, query_key, result)
                return {'data': result, 'cached_at': None}
            return None
        except Exception as e:
            logger.error(f"Failed to get person {pib}: {e}")
            raise
    
    async def get_person_by_inn(
        self, 
        code: str, 
        force_refresh: bool = False,
        user_name: str = None,
        user_code: str = None
    ) -> Optional[Dict]:
        """
        Get person information by INN (individual tax number).
        Uses cache to reduce API costs.
        
        If user_name and user_code are provided, includes realty (DRORM) data.
        """
        endpoint = 'person-by-ipn'
        # Include auth info in cache key if provided
        cache_key = f"{code}:{user_code}" if user_code else code
        
        if force_refresh:
            await self._delete_from_cache(endpoint, cache_key)
        else:
            cached = await self._get_from_cache(endpoint, cache_key)
            if cached:
                data, cached_at = cached
                return {'data': data, 'cached_at': cached_at}
        
        try:
            # Build params with optional authorization for realty
            # Full scope includes all available registries
            params = {}
            if user_name and user_code:
                params['scope'] = 'fop,realty,bankruptcy,penalty,sanction,rnboSanction,courtAssignments,wantedMvs,declarations,corruptors,lustrated,taxDebts,enforcementProceedings,asvp,erb'
                params['userName'] = user_name
                params['userCode'] = user_code
            
            data = await self._request_full(f'/person-by-ipn/{code}', params=params if params else None)
            if data.get('status') == 'ok':
                result = data.get('data')
                await self._save_to_cache(endpoint, cache_key, result)
                return {'data': result, 'cached_at': None}
            return None
        except Exception as e:
            logger.error(f"Failed to get person by INN {code}: {e}")
            raise
    
    async def get_passport(self, passport: str, force_refresh: bool = False) -> Optional[Dict]:
        """
        Check passport validity (if it's in the invalid passports database).
        Uses v2 API endpoint.
        """
        endpoint = 'passport'
        
        if force_refresh:
            await self._delete_from_cache(endpoint, passport)
        else:
            cached = await self._get_from_cache(endpoint, passport)
            if cached:
                data, cached_at = cached
                return {'data': data, 'cached_at': cached_at}
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url.replace('/v3', '/v2')}/passport",
                    params={'apiKey': self.full_api_key, 'passport': passport}
                )
                response.raise_for_status()
                result = response.json()
                await self._save_to_cache(endpoint, passport, result)
                return {'data': result, 'cached_at': None}
        except Exception as e:
            logger.error(f"Failed to check passport {passport}: {e}")
            raise

    async def get_api_statistics(self) -> Optional[Dict]:
        """
        Get API usage statistics and limits.
        Returns dict with limits info for contractor checks.
        """
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    f"{self.base_url}/statistics",
                    params={'apiKey': self.full_api_key}
                )
                response.raise_for_status()
                data = response.json()
                
                result = {
                    'company': data.get('companyName', ''),
                    'limits': []
                }
                
                for item in data.get('series', []):
                    result['limits'].append({
                        'name': item.get('name', ''),
                        'title': item.get('title', ''),
                        'used': item.get('used', 0),
                        'month_limit': item.get('monthLimit', 0),
                    })
                
                return result
        except Exception as e:
            logger.error(f"Failed to get API statistics: {e}")
            return None
