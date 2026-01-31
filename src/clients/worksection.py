import hashlib
import httpx
from typing import List, Dict, Any, Optional
from src.config import settings
from tenacity import retry, stop_after_attempt, wait_exponential
import logging

logger = logging.getLogger(__name__)


class WorksectionClient:
    """Client for Worksection Admin API"""
    
    def __init__(self):
        self.api_key = settings.WORKSECTION_API_KEY
        self.base_url = settings.worksection_base_url
        self.timeout = 30.0
    
    def _generate_hash(self, query_params: str) -> str:
        """Generate MD5 hash for API authentication"""
        data = query_params + self.api_key
        return hashlib.md5(data.encode()).hexdigest()
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _request(self, action: str, params: Dict[str, Any] = None) -> Dict:
        """Make authenticated request to Worksection API"""
        params = params or {}
        
        # Build query string for hash in exact order expected by API
        # Format: action=X&param1=Y&param2=Z (alphabetical after action)
        hash_parts = [f"action={action}"]
        for key in sorted(params.keys()):
            value = params[key]
            if value is not None:
                hash_parts.append(f"{key}={value}")
        
        hash_query = "&".join(hash_parts)
        hash_value = self._generate_hash(hash_query)
        
        # Build URL params - put action and hash at the end to match working curl
        url_params = dict(params)
        url_params['action'] = action
        url_params['hash'] = hash_value
        
        # Build URL with exact parameter order (action first, then sorted params, then hash)
        url = f"{self.base_url}?{hash_query}&hash={hash_value}"
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('status') != 'ok':
                logger.error(f"Worksection API error: {data}")
                raise Exception(f"Worksection API error: {data.get('message', 'Unknown error')}")
            
            return data
    
    async def get_projects(self, filter_status: str = None) -> List[Dict]:
        """Get all projects"""
        params = {}
        if filter_status:
            params['filter'] = filter_status
        
        data = await self._request('get_projects', params)
        return data.get('data', [])
    
    async def get_tasks(self, project_id: str, extra: str = "text") -> List[Dict]:
        """Get tasks for a specific project"""
        params = {
            'id_project': project_id,
            'extra': extra
        }
        data = await self._request('get_tasks', params)
        return data.get('data', [])
    
    async def get_all_tasks(self, filter_status: str = None, extra: str = "text") -> List[Dict]:
        """Get all tasks across all projects"""
        params = {'extra': extra}
        if filter_status:
            params['filter'] = filter_status
        
        data = await self._request('get_all_tasks', params)
        return data.get('data', [])
    
    async def get_task(self, task_id: str) -> Optional[Dict]:
        """Get a specific task by ID"""
        params = {'id_task': task_id}
        try:
            data = await self._request('get_task', params)
            return data.get('data')
        except Exception as e:
            logger.error(f"Error getting task {task_id}: {e}")
            return None
    
    async def search_tasks(self, text: str) -> List[Dict]:
        """Search tasks by text"""
        params = {'text': text}
        data = await self._request('search_tasks', params)
        return data.get('data', [])
    
    async def test_connection(self) -> bool:
        """Test API connection"""
        try:
            projects = await self.get_projects()
            logger.info(f"Worksection connection OK: {len(projects)} projects found")
            return True
        except Exception as e:
            logger.error(f"Worksection connection failed: {e}")
            return False
