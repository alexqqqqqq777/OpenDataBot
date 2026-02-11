import httpx
import json
from typing import Dict, Any, Optional, List
from src.config import settings
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import logging
from datetime import datetime
from sqlalchemy import select
from src.storage.database import get_db
from src.storage.models import ApiResponseCache

logger = logging.getLogger(__name__)


class ClarityError(Exception):
    """Clarity API error"""
    pass


class ClarityRateLimitError(ClarityError):
    """Rate limit / quota exceeded"""
    pass


class ClarityPaymentRequired(ClarityError):
    """Endpoint requires paid plan"""
    pass


class ClarityClient:
    """
    Client for Clarity Project API.
    All responses cached in DB (api_response_cache table) to minimize quota usage.
    Endpoints prefixed with 'clarity-' in cache to separate from OpenDataBot entries.

    Docs: https://github.com/the-clarity-project/api
    """

    # Clarity endpoint → cache key prefix
    _ENDPOINTS = {
        "edr.info": "clarity-edr-info",
        "edr.finances": "clarity-edr-finances",
        "tax.info": "clarity-tax-info",
        "treasury": "clarity-treasury",
        "licenses": "clarity-licenses",
        "persons": "clarity-persons",
        "used-vehicles": "clarity-used-vehicles",
        "vehicles.list": "clarity-vehicles-list",
    }

    def __init__(self):
        self.api_key = settings.CLARITY_API_KEY
        self.base_url = settings.CLARITY_BASE_URL.rstrip("/")
        self.timeout = 30.0

    # ── Low-level ────────────────────────────────────────────────────────

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=4, max=30),
        retry=retry_if_exception_type(ClarityRateLimitError),
    )
    async def _request(self, url: str, params: Dict[str, Any] | None = None) -> Dict:
        """GET request with API key."""
        p = {"key": self.api_key}
        if params:
            p.update(params)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url, params=p)

            if response.status_code == 429:
                logger.warning("Clarity rate limit hit, retrying...")
                raise ClarityRateLimitError("Rate limit exceeded")
            if response.status_code == 402:
                raise ClarityPaymentRequired(
                    f"Payment required for {url}"
                )
            if response.status_code == 404:
                return {"status": "not_found"}

            response.raise_for_status()
            return response.json()

    # ── Cache helpers (shared ApiResponseCache table) ────────────────────

    async def _get_from_cache(self, endpoint: str, query_key: str) -> Optional[tuple]:
        """Return (data, cached_at) or None."""
        async with get_db() as session:
            result = await session.execute(
                select(ApiResponseCache).where(
                    ApiResponseCache.endpoint == endpoint,
                    ApiResponseCache.query_key == query_key,
                )
            )
            cached = result.scalar_one_or_none()
            if cached:
                cached.hit_count += 1
                await session.commit()
                logger.info(
                    f"Clarity cache HIT {endpoint}/{query_key} "
                    f"(hits: {cached.hit_count})"
                )
                return (cached.response_data, cached.updated_at)
        return None

    async def _save_to_cache(self, endpoint: str, query_key: str, data: Dict):
        """Upsert into cache."""
        async with get_db() as session:
            result = await session.execute(
                select(ApiResponseCache).where(
                    ApiResponseCache.endpoint == endpoint,
                    ApiResponseCache.query_key == query_key,
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                existing.response_data = data
                existing.updated_at = datetime.utcnow()
            else:
                session.add(ApiResponseCache(
                    endpoint=endpoint,
                    query_key=query_key,
                    response_data=data,
                ))
            await session.commit()
            logger.info(f"Clarity cache SAVED {endpoint}/{query_key}")

    async def _delete_from_cache(self, endpoint: str, query_key: str):
        """Delete cache entry (for force_refresh)."""
        async with get_db() as session:
            result = await session.execute(
                select(ApiResponseCache).where(
                    ApiResponseCache.endpoint == endpoint,
                    ApiResponseCache.query_key == query_key,
                )
            )
            cached = result.scalar_one_or_none()
            if cached:
                await session.delete(cached)
                await session.commit()
                logger.info(f"Clarity cache DELETED {endpoint}/{query_key}")

    async def _cached_request(
        self,
        cache_endpoint: str,
        cache_key: str,
        url: str,
        params: Dict[str, Any] | None = None,
        force_refresh: bool = False,
    ) -> Optional[Dict]:
        """
        Generic: check cache → fetch if miss → save to cache → return.
        Returns dict with 'data' and 'cached_at'.
        """
        if force_refresh:
            await self._delete_from_cache(cache_endpoint, cache_key)
        else:
            cached = await self._get_from_cache(cache_endpoint, cache_key)
            if cached:
                data, cached_at = cached
                return {"data": data, "cached_at": cached_at}

        try:
            raw = await self._request(url, params)
            if raw.get("status") == "not_found":
                return None
            await self._save_to_cache(cache_endpoint, cache_key, raw)
            return {"data": raw, "cached_at": None}
        except ClarityPaymentRequired:
            logger.warning(f"Clarity 402 for {cache_endpoint}/{cache_key} — paid endpoint")
            return {"data": None, "cached_at": None, "error": "payment_required"}
        except Exception as e:
            logger.error(f"Clarity request failed {cache_endpoint}/{cache_key}: {e}")
            raise

    # ── Public API methods ───────────────────────────────────────────────

    async def get_company(
        self, code: str, force_refresh: bool = False
    ) -> Optional[Dict]:
        """
        edr.info/{code} — base EDR company data.
        Includes: name, status, KVED, founders, beneficiaries, capital, etc.
        """
        return await self._cached_request(
            cache_endpoint=self._ENDPOINTS["edr.info"],
            cache_key=code,
            url=f"{self.base_url}/edr.info/{code}",
            force_refresh=force_refresh,
        )

    async def get_finances(
        self,
        code: str,
        year: int | None = None,
        month: int | None = None,
        force_refresh: bool = False,
    ) -> Optional[Dict]:
        """
        edr.finances/{code} — full financial statements (balance, P&L).
        Returns line-level detail with row codes.
        """
        params: Dict[str, Any] = {}
        if year:
            params["year"] = str(year)
        if month:
            params["month"] = str(month)

        # Cache key includes period so different years don't collide
        period = f"{year or 'latest'}_{month or '12'}"
        cache_key = f"{code}:{period}"

        return await self._cached_request(
            cache_endpoint=self._ENDPOINTS["edr.finances"],
            cache_key=cache_key,
            url=f"{self.base_url}/edr.finances/{code}",
            params=params if params else None,
            force_refresh=force_refresh,
        )

    async def get_tax(
        self, code: str, force_refresh: bool = False
    ) -> Optional[Dict]:
        """
        tax.info/{code} — tax card: VAT, single tax, non-profit status.
        """
        return await self._cached_request(
            cache_endpoint=self._ENDPOINTS["tax.info"],
            cache_key=code,
            url=f"{self.base_url}/tax.info/{code}",
            force_refresh=force_refresh,
        )

    async def get_treasury(
        self, code: str, force_refresh: bool = False
    ) -> Optional[Dict]:
        """
        edr.info/{code}/treasury — budget payments (payee/payer), bank accounts.
        """
        return await self._cached_request(
            cache_endpoint=self._ENDPOINTS["treasury"],
            cache_key=code,
            url=f"{self.base_url}/edr.info/{code}/treasury",
            force_refresh=force_refresh,
        )

    async def get_licenses(
        self, code: str, force_refresh: bool = False
    ) -> Optional[Dict]:
        """
        edr.info/{code}/licenses — all licenses and permits.
        May require paid plan.
        """
        return await self._cached_request(
            cache_endpoint=self._ENDPOINTS["licenses"],
            cache_key=code,
            url=f"{self.base_url}/edr.info/{code}/licenses",
            force_refresh=force_refresh,
        )

    async def get_persons(
        self, code: str, force_refresh: bool = False
    ) -> Optional[Dict]:
        """
        edr.info/{code}/persons — related persons across registries.
        May require paid plan.
        """
        return await self._cached_request(
            cache_endpoint=self._ENDPOINTS["persons"],
            cache_key=code,
            url=f"{self.base_url}/edr.info/{code}/persons",
            force_refresh=force_refresh,
        )

    async def get_used_vehicles(
        self, code: str, force_refresh: bool = False
    ) -> Optional[Dict]:
        """
        edr.info/{code}/used-vehicles — vehicles registered for use.
        May require paid plan.
        """
        return await self._cached_request(
            cache_endpoint=self._ENDPOINTS["used-vehicles"],
            cache_key=code,
            url=f"{self.base_url}/edr.info/{code}/used-vehicles",
            force_refresh=force_refresh,
        )

    async def get_owned_vehicles(
        self, code: str, force_refresh: bool = False
    ) -> Optional[Dict]:
        """
        vehicles.list/{code} — vehicles owned by the company/person.
        May require paid plan.
        """
        return await self._cached_request(
            cache_endpoint=self._ENDPOINTS["vehicles.list"],
            cache_key=code,
            url=f"{self.base_url}/vehicles.list/{code}",
            force_refresh=force_refresh,
        )

    # ── Composite: fetch all available data at once ──────────────────────

    async def get_full_report(
        self, code: str, force_refresh: bool = False
    ) -> Dict[str, Any]:
        """
        Fetch all Clarity data for a company code.
        Returns dict keyed by endpoint name with results (or None/error).
        Skips endpoints that fail gracefully.
        """
        results: Dict[str, Any] = {"code": code}

        # Always available endpoints
        results["company"] = await self.get_company(code, force_refresh)
        results["finances"] = await self.get_finances(code, force_refresh=force_refresh)
        results["tax"] = await self.get_tax(code, force_refresh)
        results["treasury"] = await self.get_treasury(code, force_refresh)

        # Potentially paid endpoints — fetch but don't fail
        for name, method in [
            ("licenses", self.get_licenses),
            ("persons", self.get_persons),
            ("used_vehicles", self.get_used_vehicles),
            ("owned_vehicles", self.get_owned_vehicles),
        ]:
            try:
                results[name] = await method(code, force_refresh)
            except Exception as e:
                logger.warning(f"Clarity {name} failed for {code}: {e}")
                results[name] = None

        return results

    async def test_connection(self) -> bool:
        """Test API connectivity with a simple edr.info call."""
        if not self.api_key:
            logger.warning("Clarity API key not configured")
            return False
        try:
            # Use a well-known company to test
            resp = await self._request(
                f"{self.base_url}/edr.info/00032112"
            )
            ok = resp.get("status") != "not_found"
            logger.info(f"Clarity connection {'OK' if ok else 'FAILED'}")
            return ok
        except Exception as e:
            logger.error(f"Clarity connection failed: {e}")
            return False
