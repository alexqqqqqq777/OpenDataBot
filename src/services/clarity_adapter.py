"""Clarity Project API → OpenDataBot report format adapter.

Transforms raw Clarity edr.info response into the dict structure
expected by pdf_generator.generate_report_pdf().
"""

from __future__ import annotations

from datetime import datetime


_STATUS_UA: dict[str, str] = {
    "registered": "Зареєстровано",
    "terminated": "Припинено",
    "terminating": "В стані припинення",
    "bankruptcy": "Банкрутство",
    "cancelled": "Скасовано",
}

_FOUNDER_TYPE_UA: dict[str, str] = {
    "person": "Фізична особа",
    "company": "Юридична особа",
    "other": "Інше",
}

_SIGNER_TYPE_UA: dict[str, str] = {
    "director": "Керівник",
    "signer": "Підписант",
}


def clarity_company_to_report(raw: dict) -> dict:
    """Convert Clarity edr.info response → dict for generate_report_pdf.

    Args:
        raw: Full JSON response from clarity-project.info/api/edr.info/{code}

    Returns:
        dict compatible with pdf_generator.generate_report_pdf()
    """
    edr = raw.get("edr_data") or {}
    result: dict = {}

    # ── Scalar fields ────────────────────────────────────────────────────

    result["name"] = edr.get("name") or raw.get("name", "")
    if edr.get("shortName"):
        result["shortName"] = edr["shortName"]
    result["edrpou"] = edr.get("edr") or raw.get("edr", "")
    result["status"] = edr.get("statusName") or _STATUS_UA.get(
        edr.get("status", ""), edr.get("status", "")
    )
    if edr.get("director"):
        result["director"] = edr["director"]
    if edr.get("capital"):
        result["capital"] = f"{int(edr['capital']):,}".replace(",", " ") + " грн"
    if edr.get("address"):
        result["location"] = edr["address"]

    # Registration
    reg = edr.get("registration") or {}
    if reg.get("Date"):
        try:
            dt = datetime.fromtimestamp(int(reg["Date"]))
            result["registrationDate"] = dt.strftime("%d.%m.%Y")
        except (ValueError, TypeError, OSError):
            pass
    if reg.get("Number"):
        result["registrationNumber"] = reg["Number"]

    # Contacts
    contacts = edr.get("contacts", [])
    if contacts:
        result["phones"] = ", ".join(str(c) for c in contacts)

    # Prozorro contact
    if raw.get("contact"):
        result["ceoName"] = raw["contact"]

    # Primary activity
    for act in edr.get("activity", []):
        if str(act.get("IsMain")) == "1":
            result["primaryActivity"] = f"{act.get('ID', '')} {act.get('Name', '')}"
            break

    # ── Table fields ─────────────────────────────────────────────────────

    # Activities → [{code, name, isPrimary}]
    activities = edr.get("activity", [])
    if activities:
        result["activities"] = [
            {
                "code": a.get("ID", ""),
                "name": a.get("Name", ""),
                "isPrimary": str(a.get("IsMain")) == "1",
            }
            for a in activities
        ]

    # Heads (signers) → [{name, role, restriction}]
    signers = edr.get("signers", [])
    if signers:
        result["heads"] = [
            {
                "name": s.get("Name", ""),
                "role": _SIGNER_TYPE_UA.get(s.get("Type", ""), s.get("Type", "")),
                "restriction": s.get("Limit", ""),
            }
            for s in signers
        ]

    # Beneficiaries → [{name, role, amountPercent, amount, country}]
    ben_list = []
    for f in edr.get("founders", []):
        ben_list.append({
            "name": f.get("Name", ""),
            "role": "Засновник",
            "beneficiaryName": "",
            "amountPercent": f"{f['CapitalPart']}%" if f.get("CapitalPart") else "",
            "amount": f.get("Capital", 0),
            "country": f.get("Country", ""),
        })
    for b in edr.get("beneficiaries", []):
        ben_list.append({
            "name": b.get("Name", ""),
            "role": "Бенефіціар",
            "beneficiaryName": "",
            "amountPercent": "",
            "amount": 0,
            "country": b.get("Country", ""),
        })
    if ben_list:
        result["beneficiaries"] = ben_list

    # Predecessors / Assignees
    predecessors = []
    assignees = []
    for p in edr.get("predecessors", []):
        entry = {
            "code": p.get("RelatedEdr", ""),
            "name": p.get("RelatedName", ""),
        }
        if p.get("Type") == "assignee":
            assignees.append(entry)
        else:
            predecessors.append(entry)
    if predecessors:
        result["predecessors"] = predecessors
    if assignees:
        result["assignees"] = assignees

    # ── Factor signals ───────────────────────────────────────────────────

    factors = []

    # Tax debt
    td = raw.get("tax_debt")
    if td and td.get("value_total"):
        total = td["value_total"]
        factors.append({
            "type": "debt",
            "factorGroup": "tax",
            "indicator": "negative",
            "text": "Наявний податковий борг",
            "total": f"{total:,}".replace(",", " "),
            "local": f"{td.get('value_local', 0):,}".replace(",", " "),
            "government": f"{td.get('value_national', 0):,}".replace(",", " "),
        })

    # VAT
    vat = raw.get("vat")
    if vat:
        indicator = "positive" if not vat.get("CancelDate") else "negative"
        vat_factor: dict = {
            "type": "vat",
            "factorGroup": "tax",
            "indicator": indicator,
            "text": "Платник ПДВ",
        }
        if vat.get("VatNumber"):
            vat_factor["number"] = vat["VatNumber"]
        if vat.get("RegDate"):
            vat_factor["dateStart"] = vat["RegDate"]
        if vat.get("CancelDate"):
            vat_factor["dateCancellation"] = vat["CancelDate"]
            vat_factor["status"] = "cancellation"
        else:
            vat_factor["status"] = "apply"
        factors.append(vat_factor)

    # Single tax
    st = raw.get("single_tax")
    if st:
        factors.append({
            "type": "singletax",
            "factorGroup": "tax",
            "indicator": "positive",
            "text": "Єдиний податок",
            "group": st.get("group", ""),
            "rate": st.get("rate", ""),
            "dateStart": st.get("date_reg", ""),
        })

    # No VAT and no single tax → general system
    if not vat and not st:
        factors.append({
            "type": "system",
            "factorGroup": "tax",
            "indicator": "positive",
            "text": "Система оподаткування",
            "generalSystem": True,
        })

    # Licenses info
    lc = raw.get("licenses_count", 0)
    if lc and lc > 0:
        factors.append({
            "type": "info",
            "factorGroup": "edr",
            "indicator": "positive",
            "text": f"Ліцензії: {lc}",
        })

    # Non-profit
    np_data = raw.get("non_profit")
    if np_data:
        factors.append({
            "type": "info",
            "factorGroup": "tax",
            "indicator": "positive",
            "text": "Неприбуткова організація",
            "specificText": np_data.get("non_profit_name", ""),
        })

    # Available finances summary
    af = raw.get("available_finances", [])
    if af:
        years = sorted(set(f.get("year", "") for f in af), reverse=True)
        factors.append({
            "type": "info",
            "factorGroup": "edr",
            "indicator": "positive",
            "text": f"Фінансова звітність: {', '.join(years[:5])}",
        })

    # Owned property summary
    owned = raw.get("owned") or {}
    owned_parts = []
    if owned.get("vehicle"):
        owned_parts.append(f"Авто: {owned['vehicle']}")
    if owned.get("aircraft"):
        owned_parts.append(f"Авіа: {owned['aircraft']}")
    if owned.get("ships"):
        owned_parts.append(f"Судна: {owned['ships']}")
    if owned_parts:
        factors.append({
            "type": "info",
            "factorGroup": "edr",
            "indicator": "positive",
            "text": f"Власність: {', '.join(owned_parts)}",
        })

    # Termination check
    if edr.get("termination"):
        factors.append({
            "type": "info",
            "factorGroup": "edr",
            "indicator": "negative",
            "text": "Юридичну особу припинено",
        })

    if factors:
        result["factors"] = factors

    return result


def clarity_treasury_to_report(raw: dict) -> dict:
    """Convert Clarity treasury response → additional sections for report.

    Args:
        raw: JSON response from clarity-project.info/api/edr.info/{code}/treasury

    Returns:
        dict with 'treasury_by_year', 'bank_accounts' tables ready for PDF.
    """
    result: dict = {}

    # ── Bank accounts ────────────────────────────────────────────────────
    accounts = raw.get("bank_accounts", [])
    if accounts:
        result["bank_accounts"] = [
            {
                "account": a.get("Account", ""),
                "mfo": a.get("Mfo", ""),
                "updated": a.get("Updated", ""),
            }
            for a in accounts
        ]

    # ── Treasury payments aggregated by year ─────────────────────────────
    by_date = raw.get("by_date", [])
    if by_date:
        years: dict[str, dict] = {}
        for entry in by_date:
            date_str = entry.get("Date", "")
            year = date_str[:4] if date_str else "?"
            if year not in years:
                years[year] = {
                    "payer_amount": 0.0, "payer_count": 0,
                    "payee_amount": 0.0, "payee_count": 0,
                }
            years[year]["payer_amount"] += entry.get("PayerAmount", 0) or 0
            years[year]["payer_count"] += entry.get("PayerCount", 0) or 0
            years[year]["payee_amount"] += entry.get("PayeeAmount", 0) or 0
            years[year]["payee_count"] += entry.get("PayeeCount", 0) or 0

        result["treasury_by_year"] = [
            {
                "year": y,
                "payee_amount": round(d["payee_amount"], 2),
                "payee_count": d["payee_count"],
                "payer_amount": round(d["payer_amount"], 2),
                "payer_count": d["payer_count"],
            }
            for y, d in sorted(years.items(), reverse=True)
        ]

        # Summary scalars
        total_payee = sum(d["payee_amount"] for d in years.values())
        total_payer = sum(d["payer_amount"] for d in years.values())
        total_txn = sum(d["payee_count"] + d["payer_count"] for d in years.values())
        result["_treasury_total_payee"] = f"{total_payee:,.2f}".replace(",", " ") + " грн"
        result["_treasury_total_payer"] = f"{total_payer:,.2f}".replace(",", " ") + " грн"
        result["_treasury_total_txn"] = str(total_txn)

    # Role flags
    if raw.get("is_payee"):
        result["_treasury_role"] = "Отримувач бюджетних коштів"
    elif raw.get("is_payer"):
        result["_treasury_role"] = "Платник до бюджету"

    return result
