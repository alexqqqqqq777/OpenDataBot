from typing import Dict, Any, List
from src.config import settings
import logging

logger = logging.getLogger(__name__)


class ThreatLevel:
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


def analyze_threat(case_data: Dict[str, Any], company_edrpou: str) -> Dict[str, Any]:
    """
    Analyze court case and determine threat level.
    
    Threat levels:
    - CRITICAL: Criminal case (Кримінальне)
    - HIGH: Company is defendant + dangerous plaintiff (law enforcement)
    - MEDIUM: Commercial/civil case, company is defendant
    - LOW: Company is plaintiff (controlled situation)
    
    Returns:
        Dict with threat_level, company_role, case_category and analysis details
    """
    result = {
        "threat_level": ThreatLevel.MEDIUM,
        "company_role": "defendant",  # Default for monitoring
        "case_category": "civil",
        "dangerous_plaintiff": False,
        "is_criminal": False,
        "analysis_notes": []
    }
    
    # Determine case category from form/type
    case_form = (case_data.get('case_type_name') or case_data.get('form') or '').lower()
    
    if 'кримінальн' in case_form:
        result["is_criminal"] = True
        result["case_category"] = "criminal"
        result["threat_level"] = ThreatLevel.CRITICAL
        result["analysis_notes"].append("Кримінальне провадження")
    elif 'господарськ' in case_form:
        result["case_category"] = "commercial"
        result["analysis_notes"].append("Господарське судочинство")
    elif 'адміністративн' in case_form:
        result["case_category"] = "administrative"
        result["analysis_notes"].append("Адміністративне судочинство")
    elif 'цивільн' in case_form:
        result["case_category"] = "civil"
        result["analysis_notes"].append("Цивільне судочинство")
    
    # Determine company role if parties info available
    plaintiff = (case_data.get('plaintiff') or '').lower()
    defendant = (case_data.get('defendant') or '').lower()
    
    if plaintiff or defendant:
        if company_edrpou in defendant or _contains_company_by_edrpou(defendant, company_edrpou):
            result["company_role"] = "defendant"
        elif company_edrpou in plaintiff or _contains_company_by_edrpou(plaintiff, company_edrpou):
            result["company_role"] = "plaintiff"
            if not result["is_criminal"]:
                result["threat_level"] = ThreatLevel.LOW
        else:
            result["company_role"] = "party"
    
    # Check for dangerous plaintiffs (only if not already CRITICAL)
    if not result["is_criminal"]:
        for pattern in settings.dangerous_plaintiffs_list:
            if pattern in plaintiff:
                result["dangerous_plaintiff"] = True
                result["threat_level"] = ThreatLevel.HIGH
                result["analysis_notes"].append(f"Держорган: {pattern}")
                break
    
    return result


def _contains_company_by_edrpou(text: str, edrpou: str) -> bool:
    """Check if text mentions EDRPOU"""
    return edrpou in text.replace(' ', '')


def _get_case_type_name(case_type: int) -> str:
    """Get human-readable case type name"""
    types = {
        1: "Цивільні справи",
        2: "Кримінальні справи",
        3: "Господарські справи",
        4: "Адміністративні справи",
        5: "Справи про адмінправопорушення"
    }
    return types.get(case_type, f"Тип {case_type}")


def get_threat_emoji(threat_level: str) -> str:
    """Get emoji for threat level"""
    emojis = {
        ThreatLevel.CRITICAL: "🚨",
        ThreatLevel.HIGH: "⚠️",
        ThreatLevel.MEDIUM: "📋",
        ThreatLevel.LOW: "ℹ️"
    }
    return emojis.get(threat_level, "📋")


def get_role_description(role: str, lang: str = "ua") -> str:
    """Get human-readable role description"""
    if lang == "ua":
        roles = {
            "defendant": "ВІДПОВІДАЧ",
            "plaintiff": "ПОЗИВАЧ",
            "third_party": "Третя сторона"
        }
    else:
        roles = {
            "defendant": "ОТВЕТЧИК",
            "plaintiff": "ИСТЕЦ", 
            "third_party": "Третья сторона"
        }
    return roles.get(role, role)
