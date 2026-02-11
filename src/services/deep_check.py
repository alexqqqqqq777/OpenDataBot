"""
Deep check service: when checking a company, automatically check all
related companies/persons found in the response (with cache).

This populates the cache for graph building — every node on the
connections graph will have data ready.
"""

import asyncio
import logging
import re
from typing import Set, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Valid EDRPOU: 8 digits
_EDRPOU_RE = re.compile(r"^\d{8}$")


def extract_related_codes(
    odb_data: Optional[Dict] = None,
    clarity_data: Optional[Dict] = None,
    exclude_code: str = "",
) -> Set[str]:
    """
    Extract all related EDRPOU codes from ODB and/or Clarity company data.

    Sources:
      ODB full-company → registry.assignees[].code, registry.predecessors[].code,
                          registry.beneficiaries[].code
      Clarity edr_data → predecessors[].RelatedEdr, founders[].Edrpou,
                          beneficiaries[].Edrpou, branches[].Edrpou
    """
    codes: Set[str] = set()

    # ── OpenDataBot ──────────────────────────────────────────────────
    if odb_data:
        reg = odb_data.get("registry", {})

        for key in ("assignees", "predecessors"):
            for item in reg.get(key, []):
                _add(codes, item.get("code"))

        for b in reg.get("beneficiaries", []):
            _add(codes, b.get("code"))

        # Court sides
        for factor in odb_data.get("factors", []):
            if factor.get("type") in ("courtCompany", "courtDecision"):
                for item in factor.get("items", []):
                    for side in item.get("sides", []):
                        _add(codes, side.get("code"))

    # ── Clarity ──────────────────────────────────────────────────────
    if clarity_data:
        edr_data = clarity_data.get("edr_data", {})
        if isinstance(edr_data, str):
            import json
            try:
                edr_data = json.loads(edr_data)
            except (json.JSONDecodeError, TypeError):
                edr_data = {}

        for p in edr_data.get("predecessors", []):
            _add(codes, p.get("RelatedEdr"))

        for f in edr_data.get("founders", []):
            _add(codes, f.get("Edrpou"))

        for b in edr_data.get("beneficiaries", []):
            _add(codes, b.get("Edrpou"))

        for br in edr_data.get("branches", []):
            _add(codes, br.get("Edrpou"))

    # Remove the company itself
    codes.discard(exclude_code)

    return codes


def _add(codes: Set[str], value: Any):
    """Add to set if valid EDRPOU."""
    if value and isinstance(value, str) and _EDRPOU_RE.match(value.strip()):
        codes.add(value.strip())


async def deep_check_related(
    code: str,
    odb_data: Optional[Dict] = None,
    clarity_data: Optional[Dict] = None,
    max_concurrent: int = 3,
) -> Dict[str, Dict]:
    """
    Given the main company data, extract all related EDRPOU codes and
    check each one via both OpenDataBot and Clarity (with cache).

    Returns dict: {edrpou: {"odb": response_or_None, "clarity": response_or_None}}
    """
    from src.clients.opendatabot import OpenDataBotClient
    from src.clients.clarity import ClarityClient

    related_codes = extract_related_codes(odb_data, clarity_data, exclude_code=code)

    if not related_codes:
        logger.info(f"Deep check {code}: no related codes found")
        return {}

    logger.info(f"Deep check {code}: found {len(related_codes)} related codes: {related_codes}")

    odb_client = OpenDataBotClient()
    clarity_client = ClarityClient()

    semaphore = asyncio.Semaphore(max_concurrent)
    results: Dict[str, Dict] = {}

    async def _check_one(related_code: str):
        async with semaphore:
            result = {"odb": None, "clarity": None}
            try:
                result["odb"] = await odb_client.get_full_company(related_code)
            except Exception as e:
                logger.warning(f"Deep check ODB {related_code}: {e}")

            try:
                result["clarity"] = await clarity_client.get_company(related_code)
            except Exception as e:
                logger.warning(f"Deep check Clarity {related_code}: {e}")

            results[related_code] = result
            logger.info(
                f"Deep check {related_code}: "
                f"odb={'cached' if result['odb'] and result['odb'].get('cached_at') else 'fresh' if result['odb'] else 'fail'}, "
                f"clarity={'cached' if result['clarity'] and result['clarity'].get('cached_at') else 'fresh' if result['clarity'] else 'fail'}"
            )

    tasks = [_check_one(c) for c in related_codes]
    await asyncio.gather(*tasks, return_exceptions=True)

    cached_count = sum(
        1 for r in results.values()
        if (r.get("odb") and r["odb"].get("cached_at"))
    )
    fresh_count = len(results) - cached_count
    logger.info(
        f"Deep check {code} complete: {len(results)} companies checked "
        f"({cached_count} from cache, {fresh_count} fresh API calls)"
    )

    return results
