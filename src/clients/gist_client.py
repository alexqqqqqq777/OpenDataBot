"""
Client for reading case numbers from GitHub Gist.
This replaces direct Worksection API access for security.
"""

import httpx
import logging
from typing import List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class GistClient:
    """Client for reading Worksection case numbers from GitHub Gist."""
    
    def __init__(self, gist_id: str):
        self.gist_id = gist_id
        self.raw_url = f"https://gist.githubusercontent.com/raw/{gist_id}/worksection_cases.json"
        self.api_url = f"https://api.github.com/gists/{gist_id}"
        self.timeout = 30.0
        self._cache: Optional[dict] = None
        self._cache_time: Optional[datetime] = None
        self._cache_ttl = 300  # 5 minutes
    
    async def get_case_numbers(self, use_cache: bool = True) -> List[str]:
        """
        Get case numbers from Gist.
        
        Args:
            use_cache: If True, use cached data if available and not expired
            
        Returns:
            List of normalized case numbers
        """
        # Check cache
        if use_cache and self._cache and self._cache_time:
            age = (datetime.utcnow() - self._cache_time).total_seconds()
            if age < self._cache_ttl:
                logger.debug(f"Using cached Gist data ({age:.0f}s old)")
                return self._cache.get('case_numbers', [])
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # Try raw URL first (faster, no rate limit)
                response = await client.get(self.raw_url)
                response.raise_for_status()
                
                data = response.json()
                
                # Update cache
                self._cache = data
                self._cache_time = datetime.utcnow()
                
                case_numbers = data.get('case_numbers', [])
                updated_at = data.get('updated_at', 'unknown')
                
                logger.info(f"Loaded {len(case_numbers)} case numbers from Gist (updated: {updated_at})")
                return case_numbers
                
        except Exception as e:
            logger.error(f"Failed to fetch Gist: {e}")
            
            # Return cached data if available
            if self._cache:
                logger.warning("Using stale cached data")
                return self._cache.get('case_numbers', [])
            
            return []
    
    async def get_metadata(self) -> dict:
        """Get metadata about the Gist (updated_at, count)."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(self.raw_url)
                response.raise_for_status()
                data = response.json()
                
                return {
                    'count': data.get('count', 0),
                    'updated_at': data.get('updated_at'),
                }
        except Exception as e:
            logger.error(f"Failed to fetch Gist metadata: {e}")
            return {'count': 0, 'updated_at': None}
    
    async def test_connection(self) -> bool:
        """Test if Gist is accessible."""
        try:
            case_numbers = await self.get_case_numbers(use_cache=False)
            return len(case_numbers) > 0
        except Exception as e:
            logger.error(f"Gist connection test failed: {e}")
            return False
