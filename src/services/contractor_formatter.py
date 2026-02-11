"""
Форматер відповідей для перевірки контрагентів.
Багаторівнева інтерактивна система з кнопками.
"""
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


class CompanyDataParser:
    """Парсер та структуризатор даних про юридичну особу"""
    
    CATEGORY_NAMES = {
        'heads': ('👔 Керівництво', 'heads'),
        'beneficiaries': ('💰 Бенефіціари', 'beneficiaries'),
        'activities': ('📊 Види діяльності', 'activities'),
        'sanction': ('🚫 Санкції', 'sanction'),
        'debt': ('💳 Податковий борг', 'debt'),
        'courtCompany': ('⚖️ Судові справи', 'courtCompany'),
        'courtDecision': ('📜 Судові рішення', 'courtDecision'),
        'vat': ('💳 ПДВ', 'vat'),
        'history': ('📋 Історія змін', 'history'),
        'financialStatement': ('📈 Фінансова звітність', 'financialStatement'),
    }
    
    COURT_TYPE_NAMES = {
        'civil': 'Цивільні',
        'criminal': 'Кримінальні',
        'arbitrage': 'Господарські',
        'administrative': 'Адміністративні',
    }
    
    @classmethod
    def parse(cls, data: Dict) -> Dict:
        """Парсить дані юридичної особи"""
        registry = data.get('registry', {})
        factors = data.get('factors', [])
        
        result = {
            'name': registry.get('shortName') or registry.get('fullName', 'Невідомо'),
            'fullName': registry.get('fullName', ''),
            'code': registry.get('code', ''),
            'status': registry.get('status', ''),
            'location': registry.get('location', ''),
            'registrationDate': registry.get('registrationDate', ''),
            'capital': registry.get('capital'),
            'primaryActivity': registry.get('primaryActivity', ''),
            'ceoName': registry.get('ceoName', ''),
            'phones': registry.get('phones', []),
            'categories': {},
            'summary': {}
        }
        
        # Registry lists as categories
        if registry.get('heads'):
            result['categories']['heads'] = {
                'items': registry['heads'],
                'count': len(registry['heads']),
                'text': f"{len(registry['heads'])} осіб"
            }
        
        if registry.get('beneficiaries'):
            result['categories']['beneficiaries'] = {
                'items': registry['beneficiaries'],
                'count': len(registry['beneficiaries']),
                'text': f"{len(registry['beneficiaries'])} бенефіціарів"
            }
        
        if registry.get('activities'):
            result['categories']['activities'] = {
                'items': registry['activities'],
                'count': len(registry['activities']),
                'text': f"{len(registry['activities'])} видів"
            }
        
        # Factors
        for factor in factors:
            factor_type = factor.get('type', 'unknown')
            if factor_type in ('system',):
                continue
            
            items = factor.get('items', [])
            indicator = factor.get('indicator', 'neutral')
            
            result['categories'][factor_type] = {
                'factor': factor,
                'items': items,
                'count': len(items) if items else 1,
                'text': factor.get('text', ''),
                'indicator': indicator
            }
        
        # Add financial statement
        fin_statement = data.get('financialStatement', [])
        if fin_statement:
            result['categories']['financialStatement'] = {
                'items': fin_statement,
                'count': len(fin_statement),
                'text': f"Фінзвітність за {len(fin_statement)} років"
            }
        
        # Build summary
        for cat_type, cat_data in result['categories'].items():
            indicator = cat_data.get('indicator', 'neutral')
            icon = '🚨' if indicator == 'critical' else '⚠️' if indicator == 'warning' else 'ℹ️'
            result['summary'][cat_type] = {
                'icon': icon,
                'count': cat_data['count'],
                'name': cls.CATEGORY_NAMES.get(cat_type, (cat_type, cat_type))[0]
            }
        
        return result


class PersonDataParser:
    """Парсер та структуризатор даних про особу"""
    
    CATEGORY_NAMES = {
        'ceo': ('👔 Керівник компаній', 'ceo'),
        'beneficiaries': ('💰 Бенефіціар', 'beneficiaries'),
        'founders': ('🏛 Засновник', 'founders'),
        'fop': ('📋 ФОП', 'fop'),
        'session': ('⚖️ Судові засідання', 'session'),
        'courtStatus': ('📑 Судові справи', 'courtStatus'),
        'lawyer': ('👨‍⚖️ Адвокат', 'lawyer'),
        'wanted': ('🚨 Розшук', 'wanted'),
        'sanction': ('🚫 Санкції', 'sanction'),
    }
    
    @classmethod
    def parse(cls, data: Dict) -> Dict:
        """Парсить дані та групує по категоріях"""
        result = {
            'name': data.get('name', 'Невідомо'),
            'categories': {},
            'summary': {}
        }
        
        factors = data.get('factors', [])
        businessmen = data.get('businessmen', [])
        
        # Parse factors by type
        for factor in factors:
            factor_type = factor.get('type', 'unknown')
            items = factor.get('items', [])
            
            if factor_type not in result['categories']:
                result['categories'][factor_type] = {
                    'factor': factor,
                    'items': items,
                    'count': len(items) if items else 1,
                    'text': factor.get('text', ''),
                    'indicator': factor.get('indicator', 'neutral')
                }
            else:
                # Merge items
                result['categories'][factor_type]['items'].extend(items)
                result['categories'][factor_type]['count'] += len(items) if items else 1
        
        # Add businessmen as separate category
        if businessmen:
            result['categories']['businessmen'] = {
                'items': businessmen,
                'count': len(businessmen),
                'text': f'{len(businessmen)} ФОП',
                'indicator': 'neutral'
            }
        
        # Build summary
        for cat_type, cat_data in result['categories'].items():
            indicator = cat_data.get('indicator', 'neutral')
            icon = '🚨' if indicator == 'critical' else '⚠️' if indicator == 'warning' else 'ℹ️'
            result['summary'][cat_type] = {
                'icon': icon,
                'count': cat_data['count'],
                'name': cls.CATEGORY_NAMES.get(cat_type, (cat_type, cat_type))[0]
            }
        
        return result


class ContractorFormatter:
    """Форматує дані контрагента для відображення в Telegram"""
    
    MAX_MESSAGE_LENGTH = 4000  # Telegram limit is 4096, leave margin
    
    @classmethod
    def format_full_company(cls, data: Dict) -> List[str]:
        """
        Форматує повну інформацію про юридичну особу.
        Повертає список повідомлень (розбитий по категоріях).
        """
        messages = []
        
        registry = data.get('registry', {})
        factors = data.get('factors', [])
        
        # === Основна інформація ===
        main_info = cls._format_main_info(registry)
        messages.append(main_info)
        
        # === Керівництво та засновники ===
        management = cls._format_management(registry)
        if management:
            messages.append(management)
        
        # === Фактори ризику ===
        risk_factors = cls._format_risk_factors(factors)
        if risk_factors:
            messages.append(risk_factors)
        
        # === Види діяльності ===
        activities = cls._format_activities(registry)
        if activities:
            messages.append(activities)
        
        return messages
    
    @classmethod
    def _format_main_info(cls, registry: Dict) -> str:
        """Форматує основну інформацію про компанію"""
        status_emoji = cls._get_status_emoji(registry.get('status', ''))
        
        # Capital formatting
        capital = registry.get('capital') or registry.get('authorisedCapital', {}).get('value')
        capital_str = f"{capital:,.0f} грн".replace(',', ' ') if capital else "—"
        
        # Registration date
        reg_date = registry.get('registrationDate', '—')
        
        # Address
        address = registry.get('location') or registry.get('address', {}).get('address', '—')
        
        text = f"""🏢 <b>ПЕРЕВІРКА КОНТРАГЕНТА</b>

<b>{registry.get('fullName', 'Невідомо')}</b>
{f"({registry.get('shortName')})" if registry.get('shortName') else ""}

{status_emoji} <b>Статус:</b> {registry.get('status', 'невідомо')}
📋 <b>ЄДРПОУ:</b> <code>{registry.get('code', '—')}</code>
📅 <b>Дата реєстрації:</b> {reg_date}
💰 <b>Статутний капітал:</b> {capital_str}
📍 <b>Адреса:</b> {address}
📞 <b>Телефони:</b> {', '.join(registry.get('phones', [])) or '—'}
📧 <b>Email:</b> {registry.get('email') or '—'}

<b>Основний вид діяльності:</b>
└ {registry.get('primaryActivity', '—')}"""
        
        return text
    
    @classmethod
    def _format_management(cls, registry: Dict) -> Optional[str]:
        """Форматує інформацію про керівництво та засновників"""
        heads = registry.get('heads', [])
        beneficiaries = registry.get('beneficiaries', [])
        
        if not heads and not beneficiaries:
            return None
        
        text = "👥 <b>КЕРІВНИЦТВО ТА ВЛАСНИКИ</b>\n\n"
        
        # Керівники
        if heads:
            text += "<b>Керівництво:</b>\n"
            for head in heads[:5]:  # Limit to 5
                role = head.get('role', '')
                name = head.get('name', '')
                restriction = head.get('restriction', '')
                emoji = "👤" if head.get('type') == 'head' else "✍️"
                text += f"{emoji} {name}\n   └ {role}"
                if restriction and restriction != "Відомості відсутні":
                    text += f" ⚠️ {restriction}"
                text += "\n"
        
        # Засновники/бенефіціари
        if beneficiaries:
            text += "\n<b>Засновники/Бенефіціари:</b>\n"
            for ben in beneficiaries[:5]:  # Limit to 5
                name = ben.get('name', '')
                role = ben.get('role', '')
                percent = ben.get('amountPercent')
                amount = ben.get('amount')
                
                text += f"👤 {name}\n   └ {role}"
                if percent:
                    text += f" ({percent}%)"
                if amount:
                    text += f" — {amount:,.0f} грн".replace(',', ' ')
                text += "\n"
        
        return text
    
    @classmethod
    def _format_risk_factors(cls, factors: List[Dict]) -> Optional[str]:
        """Форматує фактори ризику"""
        if not factors:
            return None
        
        text = "⚠️ <b>ФАКТОРИ РИЗИКУ</b>\n\n"
        
        # Group by factor type
        sanctions = []
        tax_issues = []
        court_issues = []
        other = []
        
        for factor in factors:
            factor_type = factor.get('type', '')
            factor_group = factor.get('factorGroup', '')
            
            if factor_group == 'sanction' or factor_type == 'sanction':
                sanctions.append(factor)
            elif factor_group == 'tax' or factor_type in ('vat', 'tax'):
                tax_issues.append(factor)
            elif factor_group == 'court' or 'court' in factor_type.lower():
                court_issues.append(factor)
            else:
                other.append(factor)
        
        # Sanctions (most critical)
        if sanctions:
            text += "🚫 <b>Санкції:</b>\n"
            for s in sanctions:
                icon = s.get('icon', '⚠️')
                sanction_text = s.get('text', '')
                text += f"{icon} {sanction_text}\n"
            text += "\n"
        
        # Tax issues
        if tax_issues:
            text += "💳 <b>Податки:</b>\n"
            for t in tax_issues:
                if t.get('type') == 'system':
                    continue  # Skip system errors
                icon = t.get('icon', 'ℹ️')
                tax_text = t.get('text') or t.get('specificText', '')
                text += f"{icon} {tax_text}\n"
            text += "\n"
        
        # Court issues
        if court_issues:
            text += "⚖️ <b>Судові справи:</b>\n"
            for c in court_issues:
                icon = c.get('icon', 'ℹ️')
                court_text = c.get('text', '')
                count = c.get('count')
                if count:
                    text += f"{icon} {court_text}\n"
            text += "\n"
        
        # Check if we have any real content
        if len(text.strip()) <= len("⚠️ <b>ФАКТОРИ РИЗИКУ</b>"):
            return "✅ <b>ФАКТОРИ РИЗИКУ</b>\n\nФакторів ризику не виявлено."
        
        return text
    
    @classmethod
    def _format_activities(cls, registry: Dict) -> Optional[str]:
        """Форматує види діяльності (КВЕД)"""
        activities = registry.get('activities', [])
        
        if not activities:
            return None
        
        text = "📊 <b>ВИДИ ДІЯЛЬНОСТІ (КВЕД)</b>\n\n"
        
        # Primary first
        for act in activities:
            if act.get('isPrimary'):
                text += f"⭐ <b>{act.get('code')}</b> {act.get('name')}\n"
                break
        
        # Others
        other_activities = [a for a in activities if not a.get('isPrimary')]
        if other_activities:
            text += "\n<b>Інші види:</b>\n"
            for act in other_activities[:10]:  # Limit to 10
                text += f"• {act.get('code')} {act.get('name')}\n"
            
            if len(other_activities) > 10:
                text += f"\n<i>... та ще {len(other_activities) - 10} видів діяльності</i>"
        
        return text
    
    @classmethod
    def _get_status_emoji(cls, status: str) -> str:
        """Повертає емодзі для статусу компанії"""
        status_lower = status.lower() if status else ''
        
        if 'зареєстр' in status_lower:
            return "🟢"
        elif 'припинен' in status_lower or 'ліквід' in status_lower:
            return "🔴"
        elif 'процес' in status_lower or 'банкрут' in status_lower:
            return "🟡"
        else:
            return "⚪"
    
    # === FOP Formatting ===
    
    @classmethod
    def format_fop(cls, data: Dict, cached_at=None) -> List[str]:
        """Форматує інформацію про ФОП"""
        if not data:
            return ["❌ Немає даних"]
        
        # Handle nested registry structure
        registry = data.get('registry', data)
        
        full_name = registry.get('fullName', registry.get('name', 'Невідомо'))
        code = registry.get('code', '—')
        status = registry.get('status', 'невідомо')
        location = registry.get('location', '—')
        primary_activity = registry.get('primaryActivity', '—')
        birth_date = registry.get('birthDate', '')
        email = registry.get('email', '')
        phones = registry.get('phones', [])
        
        # Get registration date from nested structure
        registration = registry.get('registration', {})
        reg_date = registration.get('date', registry.get('registrationDate', '—'))
        
        status_emoji = cls._get_status_emoji(status)
        
        text = f"""👤 <b>ПЕРЕВІРКА ФОП</b>

<b>{full_name}</b>

{status_emoji} <b>Статус:</b> {status}
📋 <b>ІПН:</b> <code>{code}</code>"""
        
        if birth_date:
            text += f"\n🎂 <b>Дата народження:</b> {birth_date}"
        
        text += f"\n📅 <b>Дата реєстрації:</b> {reg_date}"
        text += f"\n📍 <b>Адреса:</b> {location}"
        
        if email:
            text += f"\n📧 <b>Email:</b> {email}"
        
        if phones:
            text += f"\n📞 <b>Телефон:</b> {', '.join(phones)}"
        
        text += f"\n\n<b>Основний вид діяльності:</b>\n└ {primary_activity}"
        
        # Factors (tax info)
        factors = data.get('factors', [])
        if factors:
            text += "\n\n<b>📊 Податковий статус:</b>"
            for f in factors:
                if f.get('type') == 'singletax':
                    icon = f.get('icon', '✅')
                    text += f"\n{icon} {f.get('text', '')}"
        
        # Activities (other KVEDs)
        activities = registry.get('activities', [])
        other_activities = [a for a in activities if not a.get('isPrimary')]
        if other_activities:
            text += "\n\n<b>Інші види діяльності:</b>"
            for act in other_activities[:5]:
                text += f"\n• {act.get('code', '')} {act.get('name', '')}"
            if len(other_activities) > 5:
                text += f"\n<i>... та ще {len(other_activities) - 5}</i>"
        
        # Show cache info
        if cached_at:
            cache_date = cached_at.strftime('%d.%m.%Y %H:%M') if hasattr(cached_at, 'strftime') else str(cached_at)[:16]
            text += f"\n\n📦 <i>Дані станом на: {cache_date}</i>"
        
        return [text]
    
    # === Person Formatting ===
    
    @classmethod
    def format_person(cls, data: Dict) -> List[str]:
        """Форматує інформацію про фізичну особу"""
        messages = []
        
        # Main info
        pib = data.get('name', 'Невідомо')
        
        text = f"""👤 <b>ПЕРЕВІРКА ОСОБИ</b>

<b>{pib}</b>

"""
        
        # Group factors by type
        factors = data.get('factors', [])
        
        # Critical factors first (wanted, sanctions)
        critical = [f for f in factors if f.get('indicator') == 'critical' or f.get('type') == 'wanted']
        if critical:
            text += "🚨 <b>КРИТИЧНА ІНФОРМАЦІЯ:</b>\n"
            for f in critical:
                text += f"❗️ {f.get('text', '')}\n"
                if f.get('statusText'):
                    text += f"   └ {f.get('statusText')}\n"
                if f.get('articleCrim'):
                    text += f"   └ Стаття: {f.get('articleCrim')}\n"
            text += "\n"
        
        # Lawyer info
        lawyers = [f for f in factors if f.get('type') == 'lawyer']
        if lawyers:
            for l in lawyers:
                text += f"⚖️ <b>Адвокат</b>\n"
                text += f"   └ Посвідчення №{l.get('certnum', '')} від {l.get('certat', '')[:10] if l.get('certat') else ''}\n"
                text += f"   └ {l.get('racalc', '')}\n\n"
        
        messages.append(text)
        
        # Companies where person is CEO/founder/beneficiary
        company_factors = [f for f in factors if f.get('type') in ('ceo', 'beneficiaries', 'founders')]
        if company_factors:
            comp_text = "🏢 <b>ЗВ'ЯЗКИ З КОМПАНІЯМИ</b>\n\n"
            for cf in company_factors:
                items = cf.get('items', [])
                role_name = {
                    'ceo': 'Керівник',
                    'beneficiaries': 'Бенефіціар', 
                    'founders': 'Засновник'
                }.get(cf.get('type'), cf.get('type'))
                
                if items:
                    comp_text += f"<b>{role_name}:</b>\n"
                    for item in items[:5]:
                        status = "🟢" if item.get('status') == 'зареєстровано' else "🔴" if 'припинен' in str(item.get('status', '')).lower() else "⚪"
                        comp_text += f"{status} {item.get('companyName', item.get('name', ''))}\n"
                        comp_text += f"   └ ЄДРПОУ: <code>{item.get('companyCode', item.get('code', ''))}</code>\n"
                    if len(items) > 5:
                        comp_text += f"   <i>...та ще {len(items) - 5}</i>\n"
                    comp_text += "\n"
            messages.append(comp_text)
        
        # Court sessions
        court_factors = [f for f in factors if f.get('type') == 'session']
        if court_factors:
            court_text = "⚖️ <b>СУДОВІ СПРАВИ</b>\n\n"
            for cf in court_factors:
                items = cf.get('items', [])
                for item in items[:5]:
                    court_text += f"📋 <b>{item.get('caseNumber', '')}</b>\n"
                    court_text += f"   └ {item.get('courtName', '')}\n"
                    court_text += f"   └ {item.get('description', '')[:80]}{'...' if len(item.get('description', '')) > 80 else ''}\n"
                    court_text += f"   └ Стадія: {item.get('stageName', '')}\n\n"
                if len(items) > 5:
                    court_text += f"<i>...та ще {len(items) - 5} справ</i>\n"
            messages.append(court_text)
        
        # Businessmen (FOP activities)
        businessmen = data.get('businessmen', [])
        if businessmen:
            fop_text = "📊 <b>ПІДПРИЄМНИЦЬКА ДІЯЛЬНІСТЬ (ФОП)</b>\n\n"
            for biz in businessmen[:5]:
                status_emoji = cls._get_status_emoji(biz.get('status', ''))
                fop_text += f"{status_emoji} <b>{biz.get('name', '')}</b>\n"
                fop_text += f"   └ ІПН: <code>{biz.get('code', '')}</code>\n"
                fop_text += f"   └ Статус: {biz.get('status', '')}\n"
                fop_text += f"   └ КВЕД: {biz.get('primaryActivity', '')}\n\n"
            messages.append(fop_text)
        
        return messages
    
    @classmethod
    def format_person_by_inn(cls, data: Dict, cached_at=None) -> List[str]:
        """Форматує інформацію про особу за ІПН"""
        messages = []
        
        if not data:
            return ["❌ Немає даних"]
        
        code = data.get('code', '')
        birth_date = data.get('birthDate', '')
        correct_inn = data.get('correctINN', False)
        items = data.get('items', [])
        
        text = f"""👤 <b>ПЕРЕВІРКА ЗА ІПН</b>

<b>ІПН:</b> <code>{code}</code>
"""
        if birth_date:
            text += f"<b>Дата народження:</b> {birth_date}\n"
        
        text += f"<b>ІПН валідний:</b> {'✅ Так' if correct_inn else '❌ Ні'}\n\n"
        
        # Parse items
        TYPE_NAMES = {
            'fop': '📋 ФОП',
            'drorm': '🏠 Нерухомість (ДРРП)',
            'realty': '🏠 Нерухомість',
            'penalty': '⚠️ Штрафи',
            'bankruptcy': '💸 Банкрутство',
            'sanction': '🚫 Санкції',
            'rnboSanction': '🛡 Санкції РНБО',
            'courtAssignments': '⚖️ Судові призначення',
            'wantedMvs': '🔍 Розшук МВС',
            'declarations': '📄 Декларації',
            'corruptors': '🚨 Корупціонери',
            'lustrated': '📛 Люстровані',
            'taxDebts': '💰 Податкові борги',
            'enforcementProceedings': '📋 Виконавчі провадження',
            'asvp': '📋 АСВП',
            'erb': '📋 ЄРБ (боржники)',
        }
        
        has_data = False
        text += "<b>Результати перевірки:</b>\n\n"
        
        for item in items:
            item_type = item.get('type', '')
            count = item.get('count', 0)
            item_text = item.get('text', '')
            status_service = item.get('statusService', True)
            
            type_name = TYPE_NAMES.get(item_type, item_type)
            
            if count > 0:
                has_data = True
                text += f"{type_name}: <b>{count} записів</b>\n"
                if item_text:
                    text += f"   └ {item_text}\n"
            else:
                emoji = "✅" if status_service else "❓"
                text += f"{emoji} {type_name}: немає записів\n"
                if item_text:
                    text += f"   └ <i>{item_text}</i>\n"
        
        if not has_data:
            text += "\n✅ <b>Ризик-факторів не виявлено</b>"
        
        # Show cache info
        if cached_at:
            cache_date = cached_at.strftime('%d.%m.%Y %H:%M') if hasattr(cached_at, 'strftime') else str(cached_at)[:16]
            text += f"\n\n📦 <i>Дані станом на: {cache_date}</i>"
        
        messages.append(text)
        return messages
    
    @classmethod
    def format_not_found(cls, search_type: str, query: str) -> str:
        """Форматує повідомлення про відсутність результатів"""
        type_names = {
            'company': 'юридичну особу',
            'fop': 'ФОП',
            'person': 'особу',
            'inn': 'дані за ІПН'
        }
        
        return f"""❌ <b>Не знайдено</b>

Не вдалося знайти {type_names.get(search_type, 'дані')} за запитом:
<code>{query}</code>

Перевірте правильність введених даних та спробуйте ще раз."""
    
    @classmethod
    def format_error(cls, error: str) -> str:
        """Форматує повідомлення про помилку"""
        return f"""❌ <b>Помилка</b>

{error}

Спробуйте пізніше або зверніться до адміністратора."""
    
    # === БАГАТОРІВНЕВА СИСТЕМА ===
    
    @classmethod
    def format_person_summary(cls, parsed_data: Dict) -> str:
        """Рівень 1: Короткий огляд особи з кнопками категорій"""
        name = parsed_data.get('name', 'Невідомо')
        summary = parsed_data.get('summary', {})
        
        text = f"👤 <b>ПЕРЕВІРКА ОСОБИ</b>\n\n"
        text += f"<b>{name}</b>\n\n"
        
        # Critical alerts first
        categories = parsed_data.get('categories', {})
        if 'wanted' in categories:
            factor = categories['wanted'].get('factor', {})
            text += f"🚨 <b>УВАГА:</b> {factor.get('text', '')}\n\n"
        
        if 'sanction' in categories:
            factor = categories['sanction'].get('factor', {})
            text += f"🚫 <b>Санкції:</b> {factor.get('text', '')}\n\n"
        
        # Lawyer info inline
        if 'lawyer' in categories:
            factor = categories['lawyer'].get('factor', {})
            text += f"👨‍⚖️ <b>Адвокат</b> — посв. №{factor.get('certnum', '')}\n\n"
        
        # Show cache info
        cached_at = parsed_data.get('cached_at')
        if cached_at:
            cache_date = cached_at.strftime('%d.%m.%Y %H:%M') if hasattr(cached_at, 'strftime') else str(cached_at)[:16]
            text += f"\n📦 <i>Дані станом на: {cache_date}</i>\n\n"
        
        text += "<b>Оберіть категорію для деталей:</b>"
        
        return text
    
    @classmethod
    def person_categories_keyboard(cls, parsed_data: Dict) -> InlineKeyboardMarkup:
        """Клавіатура з категоріями для особи"""
        builder = InlineKeyboardBuilder()
        summary = parsed_data.get('summary', {})
        
        # Order: critical first, then by count
        order = ['wanted', 'sanction', 'courtStatus', 'session', 'ceo', 'founders', 'beneficiaries', 'fop', 'businessmen', 'lawyer']
        
        for cat_type in order:
            if cat_type in summary:
                info = summary[cat_type]
                count = info['count']
                name = info['name']
                icon = info['icon']
                
                # Skip lawyer if count is 1 (already shown in summary)
                if cat_type == 'lawyer':
                    continue
                
                btn_text = f"{name} ({count})" if count > 1 else name
                builder.row(InlineKeyboardButton(
                    text=btn_text,
                    callback_data=f"person:cat:{cat_type}:0"
                ))
        
        # PDF report button
        builder.row(InlineKeyboardButton(
            text="📄 PDF звіт",
            callback_data="pdf:report"
        ))
        
        # Always show refresh button
        builder.row(InlineKeyboardButton(
            text="🔄 Оновити дані",
            callback_data="person:refresh"
        ))
        
        builder.row(
            InlineKeyboardButton(text="🔍 Нова перевірка", callback_data="menu:contractor"),
            InlineKeyboardButton(text="🏠 Меню", callback_data="menu:main")
        )
        
        return builder.as_markup()
    
    @classmethod
    def format_category_list(cls, parsed_data: Dict, category: str, page: int = 0, page_size: int = 5) -> str:
        """Рівень 2: Список елементів категорії"""
        categories = parsed_data.get('categories', {})
        cat_data = categories.get(category, {})
        items = cat_data.get('items', [])
        factor = cat_data.get('factor', {})
        
        cat_name = PersonDataParser.CATEGORY_NAMES.get(category, (category, category))[0]
        
        text = f"{cat_name}\n\n"
        
        # === Категорії без items - дані в самому factor ===
        if category in ('ceo', 'founders', 'beneficiaries'):
            # Компанії - дані в factor
            code = factor.get('code', '')
            name = factor.get('fullName', '') or factor.get('shortName', '')
            status = factor.get('companyStatus', '')
            activities = factor.get('activities', '')
            region = factor.get('regionName', '')
            
            emoji = "🟢" if 'зареєстр' in status.lower() else "🔴" if 'припинен' in status.lower() else "⚪"
            text += f"{emoji} <b>{name}</b>\n"
            text += f"├ ЄДРПОУ: <code>{code}</code>\n"
            text += f"├ Статус: {status}\n"
            if activities:
                text += f"├ Діяльність: {activities}\n"
            if region:
                text += f"└ Регіон: {region}\n"
            return text
        
        if category == 'fop':
            # ФОП - дані в factor
            name = factor.get('fullName', '')
            location = factor.get('location', '')
            activities = factor.get('activities', '')
            status = factor.get('status', 'активний')
            
            emoji = cls._get_status_emoji(status)
            text += f"{emoji} <b>{name}</b>\n"
            text += f"├ Статус: {status}\n"
            if activities:
                text += f"├ КВЕД: {activities}\n"
            if location:
                text += f"└ Адреса: {location}\n"
            return text
        
        if category == 'lawyer':
            # Адвокат - дані в factor
            name = factor.get('fullName', '')
            certnum = factor.get('certnum', '')
            certat = factor.get('certat', '')[:10] if factor.get('certat') else ''
            racalc = factor.get('racalc', '')
            certcalc = factor.get('certcalc', '')
            region = factor.get('regionName', '')
            
            text += f"👨‍⚖️ <b>{name}</b>\n\n"
            text += f"├ Посвідчення: №{certnum}\n"
            text += f"├ Дата видачі: {certat}\n"
            text += f"├ Видано: {certcalc}\n"
            text += f"├ Рада: {racalc}\n"
            text += f"└ Регіон: {region}\n"
            return text
        
        if category == 'wanted':
            # Розшук - детальна інформація
            name = factor.get('fullName', '')
            birth = factor.get('birthDate', '')
            article = factor.get('articleCrim', '')
            place = factor.get('lostPlace', '')
            ovd = factor.get('ovd', '')
            cat = factor.get('category', '')
            status_text = factor.get('statusText', '')
            restraint = factor.get('restraint', '')
            
            text += f"🚨 <b>{name}</b>\n\n"
            text += f"├ Дата народження: {birth}\n"
            text += f"├ Стаття: <b>{article}</b>\n"
            text += f"├ Категорія: {cat}\n"
            text += f"├ Місце: {place}\n"
            text += f"├ Орган: {ovd}\n"
            text += f"├ Запобіжний захід: {restraint}\n"
            text += f"└ <b>{status_text}</b>\n"
            return text
        
        # === Категорії з items ===
        if not items:
            text += factor.get('text', 'Немає деталей')
            return text
        
        start = page * page_size
        end = start + page_size
        page_items = items[start:end]
        
        for i, item in enumerate(page_items, start + 1):
            if category == 'session':
                # Судові засідання - ключ number, не caseNumber
                case_num = item.get('number', item.get('caseNumber', '—'))
                involved = item.get('involved', '')
                forma = item.get('forma', '')
                specific = item.get('specificText', '')
                
                # Витягуємо роль особи з involved
                role = "Учасник"
                if 'представник' in involved.lower():
                    role = "Представник"
                elif 'позивач' in involved.lower():
                    role = "Позивач"
                elif 'відповідач' in involved.lower():
                    role = "Відповідач"
                
                text += f"<b>{i}. {case_num}</b>\n"
                text += f"   ├ {forma}\n"
                text += f"   ├ Роль: {role}\n"
                text += f"   └ {specific[:60]}{'...' if len(specific) > 60 else ''}\n\n"
                
            elif category == 'courtStatus':
                # Судові справи зі статусом
                case_num = item.get('caseNumber', '—')
                court = item.get('courtName', '')
                stage = item.get('stageName', '')
                participants = item.get('participants', '')
                specific = item.get('specificText', '')
                desc = item.get('description', '')
                
                # Витягуємо роль
                role = "Учасник"
                if 'позивач' in participants.lower():
                    role = "Позивач"
                elif 'відповідач' in participants.lower():
                    role = "Відповідач"
                elif 'представник' in participants.lower():
                    role = "Представник"
                elif 'адвокат' in participants.lower():
                    role = "Адвокат"
                
                text += f"<b>{i}. {case_num}</b>\n"
                text += f"   ├ {court}\n"
                text += f"   ├ Роль: <b>{role}</b>\n"
                text += f"   ├ Суть: {desc[:50]}{'...' if len(desc) > 50 else ''}\n"
                text += f"   └ Стадія: {stage}\n\n"
            else:
                text += f"• {item}\n"
        
        total = len(items)
        total_pages = (total + page_size - 1) // page_size
        text += f"\n<i>Сторінка {page + 1}/{total_pages} (всього: {total})</i>"
        
        return text
    
    @classmethod
    def category_list_keyboard(cls, category: str, page: int, total_items: int, page_size: int = 5) -> InlineKeyboardMarkup:
        """Клавіатура для списку категорії з пагінацією"""
        builder = InlineKeyboardBuilder()
        total_pages = (total_items + page_size - 1) // page_size
        
        # Pagination
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(text="◀️", callback_data=f"person:cat:{category}:{page-1}"))
        nav.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="person:noop"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton(text="▶️", callback_data=f"person:cat:{category}:{page+1}"))
        
        if nav:
            builder.row(*nav)
        
        builder.row(InlineKeyboardButton(text="🔙 Назад до категорій", callback_data="person:back"))
        
        return builder.as_markup()
    
    @classmethod
    def format_court_case_detail(cls, item: Dict) -> str:
        """Рівень 3: Детальна інформація про судову справу"""
        text = f"📋 <b>Справа {item.get('caseNumber', '')}</b>\n\n"
        text += f"<b>Суд:</b> {item.get('courtName', '—')}\n"
        text += f"<b>Суддя:</b> {item.get('judge', '—')}\n"
        text += f"<b>Стадія:</b> {item.get('stageName', '—')}\n"
        text += f"<b>Дата:</b> {item.get('registrationDate', '—')}\n\n"
        text += f"<b>Опис:</b>\n{item.get('description', '—')}\n\n"
        
        participants = item.get('participants', '')
        if participants:
            text += f"<b>Учасники:</b>\n{participants[:500]}{'...' if len(participants) > 500 else ''}\n"
        
        return text
    
    # === БАГАТОРІВНЕВА СИСТЕМА ДЛЯ КОМПАНІЙ ===
    
    @classmethod
    def format_company_summary(cls, parsed_data: Dict) -> str:
        """Рівень 1: Короткий огляд компанії з кнопками категорій"""
        name = parsed_data.get('name', 'Невідомо')
        full_name = parsed_data.get('fullName', '')
        code = parsed_data.get('code', '')
        status = parsed_data.get('status', '')
        location = parsed_data.get('location', '')
        capital = parsed_data.get('capital')
        primary = parsed_data.get('primaryActivity', '')
        ceo = parsed_data.get('ceoName', '')
        reg_date = parsed_data.get('registrationDate', '')
        
        status_emoji = cls._get_status_emoji(status)
        capital_str = f"{capital:,.0f} грн".replace(',', ' ') if capital else "—"
        
        text = f"🏢 <b>ПЕРЕВІРКА КОМПАНІЇ</b>\n\n"
        text += f"<b>{full_name}</b>\n"
        if name != full_name:
            text += f"({name})\n"
        text += f"\n"
        
        text += f"{status_emoji} <b>Статус:</b> {status}\n"
        text += f"📋 <b>ЄДРПОУ:</b> <code>{code}</code>\n"
        text += f"📅 <b>Реєстрація:</b> {reg_date}\n"
        text += f"💰 <b>Капітал:</b> {capital_str}\n"
        text += f"👔 <b>Керівник:</b> {ceo}\n"
        text += f"📍 <b>Адреса:</b> {location[:80]}{'...' if len(location) > 80 else ''}\n"
        text += f"\n<b>Основний КВЕД:</b> {primary}\n"
        
        # === РИЗИК ФАКТОРИ ===
        categories = parsed_data.get('categories', {})
        risk_factors = []
        
        if 'sanction' in categories:
            risk_factors.append(f"🚫 {categories['sanction'].get('text', 'Санкції')}")
        
        if 'debt' in categories:
            risk_factors.append(f"💳 {categories['debt'].get('text', 'Податковий борг')}")
        
        if 'courtCompany' in categories:
            cat = categories['courtCompany']
            items = cat.get('items', [])
            total = sum(item.get('count', 0) for item in items)
            if total > 0:
                risk_factors.append(f"⚖️ Судові процеси: {total} справ")
        
        if 'courtDecision' in categories:
            risk_factors.append(f"📜 {categories['courtDecision'].get('text', '')}")
        
        text += "\n<b>⚠️ РИЗИК ФАКТОРИ:</b>\n"
        if risk_factors:
            for rf in risk_factors:
                text += f"  • {rf}\n"
        else:
            text += "  ✅ Ризик факторів не виявлено\n"
        
        # Show cache info
        cached_at = parsed_data.get('cached_at')
        if cached_at:
            cache_date = cached_at.strftime('%d.%m.%Y %H:%M') if hasattr(cached_at, 'strftime') else str(cached_at)[:16]
            text += f"\n📦 <i>Дані станом на: {cache_date}</i>\n"
        
        text += "\n<b>Оберіть категорію для деталей:</b>"
        
        return text
    
    @classmethod
    def company_categories_keyboard(cls, parsed_data: Dict) -> InlineKeyboardMarkup:
        """Клавіатура з категоріями для компанії"""
        builder = InlineKeyboardBuilder()
        summary = parsed_data.get('summary', {})
        cached_at = parsed_data.get('cached_at')
        
        order = ['sanction', 'debt', 'courtCompany', 'courtDecision', 'financialStatement', 'vat', 'heads', 'beneficiaries', 'activities', 'history']
        
        for cat_type in order:
            if cat_type in summary:
                info = summary[cat_type]
                count = info['count']
                name = info['name']
                
                btn_text = f"{name} ({count})" if count > 1 else name
                builder.row(InlineKeyboardButton(
                    text=btn_text,
                    callback_data=f"company:cat:{cat_type}:0"
                ))
        
        # PDF report button
        builder.row(InlineKeyboardButton(
            text="📄 PDF звіт",
            callback_data="pdf:report"
        ))
        
        # Add refresh button if data is from cache
        if cached_at:
            builder.row(InlineKeyboardButton(
                text="🔄 Оновити дані",
                callback_data="company:refresh"
            ))
        
        builder.row(
            InlineKeyboardButton(text="🔍 Нова перевірка", callback_data="menu:contractor"),
            InlineKeyboardButton(text="🏠 Меню", callback_data="menu:main")
        )
        
        return builder.as_markup()
    
    @classmethod
    def format_company_category(cls, parsed_data: Dict, category: str, page: int = 0, page_size: int = 5) -> str:
        """Рівень 2: Список елементів категорії компанії"""
        categories = parsed_data.get('categories', {})
        cat_data = categories.get(category, {})
        items = cat_data.get('items', [])
        factor = cat_data.get('factor', {})
        
        cat_name = CompanyDataParser.CATEGORY_NAMES.get(category, (category, category))[0]
        text = f"{cat_name}\n\n"
        
        # Категорії без items або з особливим форматуванням
        if category in ('sanction', 'vat', 'debt'):
            factor_text = cat_data.get('text', '') or factor.get('text', '')
            text += f"{factor_text}\n"
            return text
        
        if category == 'courtCompany':
            factor_text = cat_data.get('text', '') or factor.get('text', '')
            code = parsed_data.get('code', '')
            text += f"{factor_text}\n\n"
            
            if items:
                text += "<b>Категорії справ:</b>\n"
                for item in items:
                    court_type = item.get('type', '')
                    count = item.get('count', 0)
                    live_count = item.get('liveCount', 0)
                    type_name = CompanyDataParser.COURT_TYPE_NAMES.get(court_type, item.get('text', court_type))
                    
                    if count > 0:
                        active = f" (активних: {live_count})" if live_count > 0 else ""
                        text += f"  • <b>{type_name}:</b> {count} справ{active}\n"
            
            # Link to OpenDataBot website for details
            if code:
                text += f"\n🔗 <a href='https://opendatabot.ua/c/{code}'>Детальніше на OpenDataBot</a>"
            return text
        
        if category == 'courtDecision':
            factor_text = cat_data.get('text', '') or factor.get('text', '')
            code = parsed_data.get('code', '')
            text += f"{factor_text}\n"
            
            if code:
                text += f"\n🔗 <a href='https://opendatabot.ua/c/{code}'>Детальніше на OpenDataBot</a>"
            return text
        
        if category == 'financialStatement':
            if items:
                # Show latest year
                latest = items[0]
                year = latest.get('year', '')
                revenue = latest.get('revenue')
                profit = latest.get('profit')
                employees = latest.get('employees')
                balance = latest.get('balance')
                
                text += f"<b>Останній звіт: {year} рік</b>\n\n"
                if revenue:
                    text += f"📊 Дохід: <b>{revenue:,.0f} грн</b>\n".replace(',', ' ')
                if profit:
                    emoji = "📈" if profit > 0 else "📉"
                    text += f"{emoji} Прибуток: <b>{profit:,.0f} грн</b>\n".replace(',', ' ')
                if employees:
                    text += f"👥 Працівників: {employees}\n"
                if balance:
                    text += f"💰 Баланс: {balance:,.0f} грн\n".replace(',', ' ')
                
                # Financial ratios
                ratios = latest.get('financialRatios', {})
                if ratios:
                    text += f"\n<b>Фінансові показники:</b>\n"
                    if ratios.get('currentLiquidityRatio'):
                        text += f"  • Ліквідність: {ratios['currentLiquidityRatio']:.2f}\n"
                    if ratios.get('productProfitability'):
                        text += f"  • Рентабельність: {ratios['productProfitability']:.2f}%\n"
            return text
        
        if category == 'history':
            # Show list of dates with summary - user can click for details
            if items:
                text += "<b>Оберіть дату для деталей:</b>\n\n"
                for i, item in enumerate(items[:10]):
                    date = item.get('date', '')
                    changes = item.get('changes', [])
                    # Summary of changes
                    change_types = set()
                    for ch in changes:
                        field = ch.get('field', '')
                        if 'founder' in field:
                            change_types.add('засновники')
                        elif 'ceo' in field or 'head' in field:
                            change_types.add('керівництво')
                        elif 'capital' in field:
                            change_types.add('капітал')
                        elif 'activity' in field:
                            change_types.add('КВЕД')
                        elif 'location' in field or 'address' in field:
                            change_types.add('адреса')
                        else:
                            change_types.add('інше')
                    
                    summary = ', '.join(list(change_types)[:2])
                    text += f"📅 <b>{date}</b> — {len(changes)} змін\n"
                    text += f"   └ {summary}\n\n"
                
                if len(items) > 10:
                    text += f"<i>...та ще {len(items) - 10} записів</i>\n"
                
                text += "\n<i>Натисніть кнопку дати нижче для повних деталей</i>"
            return text
        
        if not items:
            text += cat_data.get('text', 'Немає даних')
            return text
        
        start = page * page_size
        end = start + page_size
        page_items = items[start:end]
        
        for i, item in enumerate(page_items, start + 1):
            if category == 'heads':
                name = item.get('name', '')
                role = item.get('role', '')
                restriction = item.get('restriction', '')
                emoji = "👔" if item.get('type') == 'head' else "✍️"
                text += f"{emoji} <b>{name}</b>\n"
                text += f"   └ {role}"
                if restriction and restriction != "Відомості відсутні":
                    text += f" ⚠️ {restriction}"
                text += "\n\n"
                
            elif category == 'beneficiaries':
                name = item.get('name', '')
                role = item.get('role', '')
                percent = item.get('amountPercent')
                amount = item.get('amount')
                ben_code = item.get('code', '')
                is_person = item.get('person', False)
                indirect = item.get('indirectInterest')
                
                emoji = "👤" if is_person else "🏢"
                text += f"{emoji} <b>{name}</b>\n"
                if ben_code:
                    text += f"   ├ ЄДРПОУ: <code>{ben_code}</code>\n"
                text += f"   ├ {role}"
                if percent:
                    text += f" ({percent}%)"
                if indirect:
                    text += f" [непряма: {indirect}%]"
                if amount:
                    text += f"\n   └ Частка: {amount:,.0f} грн".replace(',', ' ')
                else:
                    text += "\n"
                text += "\n"
                
            elif category == 'activities':
                code = item.get('code', '')
                name = item.get('name', '')
                is_primary = item.get('isPrimary', False)
                emoji = "⭐" if is_primary else "•"
                text += f"{emoji} <b>{code}</b> {name}\n"
            else:
                text += f"• {item}\n"
        
        total = len(items)
        total_pages = (total + page_size - 1) // page_size
        if total_pages > 1:
            text += f"\n<i>Сторінка {page + 1}/{total_pages} (всього: {total})</i>"
        
        return text
    
    @classmethod
    def company_category_keyboard(cls, category: str, page: int, total_items: int, page_size: int = 5, parsed_data: Dict = None) -> InlineKeyboardMarkup:
        """Клавіатура для списку категорії компанії"""
        builder = InlineKeyboardBuilder()
        
        # Special handling for history - add date buttons
        if category == 'history' and parsed_data:
            categories = parsed_data.get('categories', {})
            history_data = categories.get('history', {})
            items = history_data.get('items', [])
            
            # Add buttons for each date (max 5)
            for i, item in enumerate(items[:5]):
                date = item.get('date', '')
                changes_count = len(item.get('changes', []))
                builder.row(InlineKeyboardButton(
                    text=f"📅 {date} ({changes_count} змін)",
                    callback_data=f"company:history:{i}"
                ))
            
            if len(items) > 5:
                builder.row(InlineKeyboardButton(
                    text=f"📋 Показати ще ({len(items) - 5})",
                    callback_data=f"company:history:more"
                ))
        else:
            total_pages = (total_items + page_size - 1) // page_size
            
            if total_pages > 1:
                nav = []
                if page > 0:
                    nav.append(InlineKeyboardButton(text="◀️", callback_data=f"company:cat:{category}:{page-1}"))
                nav.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="company:noop"))
                if page < total_pages - 1:
                    nav.append(InlineKeyboardButton(text="▶️", callback_data=f"company:cat:{category}:{page+1}"))
                builder.row(*nav)
        
        builder.row(InlineKeyboardButton(text="🔙 Назад до категорій", callback_data="company:back"))
        
        return builder.as_markup()
    
    @classmethod
    def format_history_detail(cls, item: Dict) -> str:
        """Форматує повні деталі змін за конкретну дату"""
        date = item.get('date', '')
        changes = item.get('changes', [])
        
        text = f"📅 <b>Зміни за {date}</b>\n\n"
        
        for change in changes:
            change_text = change.get('text', '')
            old_val = change.get('oldValue', '')
            new_val = change.get('newValue', '')
            field = change.get('field', '')
            
            # Icon based on field type
            if 'founder' in field:
                icon = "🏢"
            elif 'ceo' in field or 'head' in field:
                icon = "👔"
            elif 'capital' in field:
                icon = "💰"
            elif 'activity' in field:
                icon = "📊"
            elif 'location' in field or 'address' in field:
                icon = "📍"
            else:
                icon = "•"
            
            text += f"{icon} <b>{change_text}</b>\n"
            
            if old_val and new_val:
                text += f"   Було: <code>{old_val}</code>\n"
                text += f"   Стало: <code>{new_val}</code>\n"
            elif new_val:
                text += f"   + <code>{new_val}</code>\n"
            elif old_val:
                text += f"   - <code>{old_val}</code>\n"
            
            text += "\n"
        
        return text
    
    @classmethod
    def history_detail_keyboard(cls) -> InlineKeyboardMarkup:
        """Клавіатура для деталей історії"""
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="🔙 Назад до списку", callback_data="company:cat:history:0"))
        builder.row(InlineKeyboardButton(text="🏠 До категорій", callback_data="company:back"))
        return builder.as_markup()
