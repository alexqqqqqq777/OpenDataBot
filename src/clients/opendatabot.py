import httpx
from typing import List, Dict, Any, Optional
from src.config import settings
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import logging

logger = logging.getLogger(__name__)


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
        return data.get('data', {})
    
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
