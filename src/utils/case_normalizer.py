import re
from typing import Optional, List
from src.config import settings


def normalize_case_number(raw: str) -> Optional[str]:
    """
    Normalize court case number to canonical format.
    Examples:
        "№ 922/4626/23 " → "922/4626/23"
        "922/4627/23-ц" → "922/4627/23-ц"
        "справа 904/3388/23" → "904/3388/23"
    """
    if not raw:
        return None
    
    # Remove common prefixes and clean up
    cleaned = raw.strip()
    cleaned = re.sub(r'^[№#\s]+', '', cleaned)
    cleaned = re.sub(r'^справа\s*', '', cleaned, flags=re.IGNORECASE)
    
    # Extract case number pattern
    pattern = settings.WORKSECTION_CASE_PATTERN
    match = re.search(pattern, cleaned)
    
    if match:
        return match.group(1)
    
    return None


def extract_case_numbers(text: str) -> List[str]:
    """
    Extract all case numbers from text.
    """
    if not text:
        return []
    
    pattern = settings.WORKSECTION_CASE_PATTERN
    matches = re.findall(pattern, text)
    
    # Deduplicate while preserving order
    seen = set()
    result = []
    for m in matches:
        if m not in seen:
            seen.add(m)
            result.append(m)
    
    return result


def generate_case_key(case_id: str = None, case_number: str = None, court_code: str = None) -> str:
    """
    Generate unique key for a court case.
    Prefer case_id if available, otherwise use case_number + court_code.
    """
    if case_id:
        return f"odb:{case_id}"
    
    if case_number:
        normalized = normalize_case_number(case_number) or case_number
        if court_code:
            return f"case:{normalized}:{court_code}"
        return f"case:{normalized}"
    
    raise ValueError("Either case_id or case_number must be provided")


def validate_edrpou(edrpou: str) -> bool:
    """
    Validate Ukrainian EDRPOU code.
    EDRPOU is 8 digits for legal entities.
    """
    if not edrpou:
        return False
    
    cleaned = edrpou.strip()
    
    # Must be 8 digits
    if not re.match(r'^\d{8}$', cleaned):
        return False
    
    return True


def format_edrpou(edrpou: str) -> str:
    """Format EDRPOU to standard 8-digit format."""
    cleaned = re.sub(r'\D', '', edrpou)
    return cleaned.zfill(8)
