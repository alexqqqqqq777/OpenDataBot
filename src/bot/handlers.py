import asyncio
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from src.storage import (
    AsyncSessionLocal, CompanyRepository, NotificationRepository,
    WorksectionCaseRepository, CourtCaseRepository, UserSubscriptionRepository,
    UserSettingsRepository, CaseSubscriptionRepository
)
from src.utils import validate_edrpou, format_edrpou
from src.clients import OpenDataBotClient, WorksectionClient
from src.bot.keyboards import (
    main_menu_keyboard, companies_menu_keyboard, cases_menu_keyboard,
    stats_keyboard, settings_keyboard, sync_keyboard,
    company_actions_keyboard, confirm_delete_keyboard, back_to_main_keyboard,
    cancel_keyboard, pagination_keyboard, threat_level_filter_keyboard,
    my_subs_keyboard, my_cases_keyboard, contractor_menu_keyboard, contractor_result_keyboard
)
from src.services.contractor_formatter import ContractorFormatter, PersonDataParser, CompanyDataParser
from src.utils import normalize_case_number
from src.config import settings
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

router = Router()


# === FSM States ===

class AddCompanyStates(StatesGroup):
    waiting_for_edrpou = State()
    waiting_for_name = State()


class SearchStates(StatesGroup):
    waiting_for_query = State()


class AddCaseStates(StatesGroup):
    waiting_for_case_number = State()
    waiting_for_case_name = State()


class ContractorCheckStates(StatesGroup):
    waiting_for_company_code = State()
    waiting_for_fop_code = State()
    waiting_for_person_pib = State()
    waiting_for_person_inn = State()
    waiting_for_user_inn = State()  # User's own INN for authorization
    waiting_for_user_name = State()  # User's own name for authorization
    waiting_for_passport = State()  # Passport number check
    waiting_for_auto_input = State()  # Auto-detect input type


def identify_input_type(text: str) -> tuple:
    """
    Автоматично визначає тип введеного номера.
    Returns: (type, normalized_value)
    Types: 'edrpou', 'inn', 'passport_old', 'passport_id', 'pib', 'unknown'
    """
    import re
    
    cleaned = text.strip().upper().replace(" ", "").replace("-", "")
    
    # ЄДРПОУ: рівно 8 цифр
    if re.match(r'^\d{8}$', cleaned):
        return ('edrpou', cleaned)
    
    # ІПН: рівно 10 цифр
    if re.match(r'^\d{10}$', cleaned):
        return ('inn', cleaned)
    
    # ID-картка: рівно 9 цифр
    if re.match(r'^\d{9}$', cleaned):
        return ('passport_id', cleaned)
    
    # Старий паспорт: 2 кириличні літери + 6 цифр
    if re.match(r'^[А-ЯІЇЄҐ]{2}\d{6}$', cleaned):
        return ('passport_old', cleaned)
    
    # Паспорт з латиницею (для сумісності)
    if re.match(r'^[A-Z]{2}\d{6}$', cleaned):
        return ('passport_old', cleaned)
    
    # ПІБ: містить літери та пробіли, мінімум 2 слова
    original = text.strip()
    if re.match(r'^[А-ЯІЇЄҐа-яіїєґA-Za-z\s\'-]+$', original) and len(original.split()) >= 2:
        return ('pib', original)
    
    return ('unknown', text.strip())


# === Start & Main Menu ===

@router.message(CommandStart())
async def cmd_start(message: Message):
    """Головне меню"""
    text = """
⚖️ <b>Моніторинг судових справ</b>

Вітаю! Я допоможу відстежувати судові справи ваших клієнтів.

🔔 <b>Автоматичні сповіщення</b> про нові справи
🏢 <b>Моніторинг компаній</b> за ЄДРПОУ
📊 <b>Аналіз загроз</b> та пріоритизація

Оберіть розділ:
"""
    await message.answer(text, reply_markup=main_menu_keyboard(), parse_mode="HTML")


@router.message(Command("menu"))
async def cmd_menu(message: Message):
    """Показати головне меню"""
    await message.answer(
        "🏠 <b>Головне меню</b>\n\nОберіть розділ:",
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "menu:main")
async def callback_main_menu(callback: CallbackQuery, state: FSMContext):
    """Повернення до головного меню"""
    await state.clear()
    await callback.message.edit_text(
        "🏠 <b>Головне меню</b>\n\nОберіть розділ:",
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "cancel")
async def callback_cancel(callback: CallbackQuery, state: FSMContext):
    """Скасування дії"""
    await state.clear()
    await callback.message.edit_text(
        "❌ Дію скасовано.\n\n🏠 <b>Головне меню</b>",
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


# === Help ===

@router.message(Command("help"))
@router.callback_query(F.data == "menu:help")
async def cmd_help(event: Message | CallbackQuery):
    """Допомога"""
    text = """
ℹ️ <b>Довідка</b>

<b>🏢 Компанії</b>
Додавайте компанії за ЄДРПОУ для моніторингу судових справ. Система автоматично відстежує нові справи.

<b>⚖️ Справи</b>
Переглядайте всі знайдені судові справи, фільтруйте за рівнем загрози та компаніями.

<b>🔔 Сповіщення</b>
Отримуйте миттєві сповіщення про нові справи з аналізом рівня загрози:
• 🚨 <b>CRITICAL</b> — кримінальні справи, компанія відповідач
• ⚠️ <b>HIGH</b> — позивач: правоохоронці, податкова
• 📋 <b>MEDIUM</b> — звичайні позови
• ℹ️ <b>LOW</b> — компанія позивач

<b>🔄 Синхронізація</b>
• Worksection — 7:00 та 19:00
• OpenDataBot — 8:00 та 20:00

<b>Команди:</b>
/menu — головне меню
/add — додати компанію
/cases — список справ
/stats — статистика
"""
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=back_to_main_keyboard(), parse_mode="HTML")
        await event.answer()
    else:
        await event.answer(text, reply_markup=back_to_main_keyboard(), parse_mode="HTML")


# === Companies Menu ===

@router.callback_query(F.data == "menu:companies")
async def callback_companies_menu(callback: CallbackQuery):
    """Меню компаній"""
    await callback.message.edit_text(
        "🏢 <b>Управління компаніями</b>\n\n"
        "Додавайте компанії для моніторингу судових справ за ЄДРПОУ.",
        reply_markup=companies_menu_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "company:add")
async def callback_add_company_start(callback: CallbackQuery, state: FSMContext):
    """Початок додавання компанії"""
    await state.set_state(AddCompanyStates.waiting_for_edrpou)
    await callback.message.edit_text(
        "➕ <b>Додавання компанії</b>\n\n"
        "Введіть ЄДРПОУ компанії (8 цифр):\n\n"
        "<i>Приклад: 12345678</i>",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AddCompanyStates.waiting_for_edrpou)
async def process_edrpou(message: Message, state: FSMContext):
    """Обробка ЄДРПОУ та додавання компанії"""
    edrpou = message.text.strip()
    
    if not validate_edrpou(edrpou):
        await message.answer(
            "❌ <b>Некоректний ЄДРПОУ</b>\n\n"
            "ЄДРПОУ має містити 8 цифр.\n"
            "Спробуйте ще раз:",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML"
        )
        return
    
    edrpou = format_edrpou(edrpou)
    
    async with AsyncSessionLocal() as session:
        repo = CompanyRepository(session)
        
        existing = await repo.get_company(edrpou)
        if existing:
            # Company exists - check if user already subscribed
            user_sub_repo = UserSubscriptionRepository(session)
            user_sub = await user_sub_repo.get_subscription(message.from_user.id, edrpou)
            
            if user_sub and user_sub.is_active:
                await message.answer(
                    f"ℹ️ Ви вже підписані на <code>{edrpou}</code>",
                    reply_markup=back_to_main_keyboard(),
                    parse_mode="HTML"
                )
            else:
                # Add user subscription
                await user_sub_repo.subscribe(message.from_user.id, edrpou)
                
                if not existing.is_active:
                    await repo.activate_company(edrpou)
                
                name = existing.company_name or "—"
                await message.answer(
                    f"✅ <b>Підписку додано!</b>\n\n"
                    f"├ ЄДРПОУ: <code>{edrpou}</code>\n"
                    f"├ Назва: {name}\n"
                    f"└ 🔔 Сповіщення: увімкнено",
                    reply_markup=back_to_main_keyboard(),
                    parse_mode="HTML"
                )
                logger.info(f"User {message.from_user.id} subscribed to existing company {edrpou}")
            
            await state.clear()
            return
        
        # New company - ask for name
        await state.update_data(edrpou=edrpou)
        await state.set_state(AddCompanyStates.waiting_for_name)
        await message.answer(
            f"✅ ЄДРПОУ: <code>{edrpou}</code>\n\n"
            "Компанія нова в системі.\n"
            "Введіть назву компанії:",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML"
        )


@router.message(AddCompanyStates.waiting_for_name)
async def process_company_name(message: Message, state: FSMContext):
    """Обробка назви нової компанії"""
    data = await state.get_data()
    edrpou = data.get('edrpou')
    company_name = message.text.strip()
    
    async with AsyncSessionLocal() as session:
        repo = CompanyRepository(session)
        
        await repo.add_company(
            edrpou=edrpou,
            company_name=company_name,
            user_id=message.from_user.id
        )
        
        # Create user subscription
        user_sub_repo = UserSubscriptionRepository(session)
        await user_sub_repo.subscribe(message.from_user.id, edrpou)
        
        # Create OpenDataBot subscription
        odb_status = "✅"
        try:
            odb = OpenDataBotClient()
            # ODB API strips leading zeros, so we need to normalize
            odb_key = edrpou.lstrip('0') or edrpou
            existing_subs = await odb.get_subscriptions(subscription_key=odb_key)
            if not existing_subs:
                await odb.create_subscription(
                    subscription_type='company',
                    subscription_key=odb_key
                )
                logger.info(f"OpenDataBot subscription created for {edrpou}")
        except Exception as odb_err:
            logger.error(f"Failed to create ODB subscription for {edrpou}: {odb_err}")
            odb_status = "❌"
        
        await message.answer(
            f"✅ <b>Компанію додано!</b>\n\n"
            f"├ ЄДРПОУ: <code>{edrpou}</code>\n"
            f"├ Назва: {company_name}\n"
            f"├ OpenDataBot: {odb_status}\n"
            f"└ 🔔 Сповіщення: увімкнено",
            reply_markup=back_to_main_keyboard(),
            parse_mode="HTML"
        )
        logger.info(f"Company added: {edrpou} by user {message.from_user.id}")
    
    await state.clear()


@router.message(Command("add"))
async def cmd_add_company(message: Message, state: FSMContext):
    """Швидке додавання компанії"""
    args = message.text.split(maxsplit=2)
    
    if len(args) < 2:
        await state.set_state(AddCompanyStates.waiting_for_edrpou)
        await message.answer(
            "➕ <b>Додавання компанії</b>\n\n"
            "Введіть ЄДРПОУ компанії (8 цифр):",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML"
        )
        return
    
    edrpou = format_edrpou(args[1].strip())
    company_name = args[2].strip() if len(args) > 2 else None
    
    if not validate_edrpou(edrpou):
        await message.answer("❌ Некоректний ЄДРПОУ. Має бути 8 цифр.")
        return
    
    async with AsyncSessionLocal() as session:
        repo = CompanyRepository(session)
        user_sub_repo = UserSubscriptionRepository(session)
        existing = await repo.get_company(edrpou)
        
        if existing:
            # Company exists - add user subscription
            user_sub = await user_sub_repo.get_subscription(message.from_user.id, edrpou)
            if user_sub and user_sub.is_active:
                await message.answer(
                    f"ℹ️ Ви вже підписані на <code>{edrpou}</code>",
                    reply_markup=back_to_main_keyboard(),
                    parse_mode="HTML"
                )
            else:
                await user_sub_repo.subscribe(message.from_user.id, edrpou)
                await message.answer(
                    f"✅ Підписку на <code>{edrpou}</code> додано!\n└ 🔔 Сповіщення: увімкнено",
                    reply_markup=back_to_main_keyboard(),
                    parse_mode="HTML"
                )
            return
        
        await repo.add_company(edrpou=edrpou, company_name=company_name, user_id=message.from_user.id)
        await user_sub_repo.subscribe(message.from_user.id, edrpou)
        
        # Create OpenDataBot subscription
        odb_status = "✅"
        try:
            odb = OpenDataBotClient()
            # ODB API strips leading zeros, so we need to normalize
            odb_key = edrpou.lstrip('0') or edrpou
            existing_subs = await odb.get_subscriptions(subscription_key=odb_key)
            if not existing_subs:
                await odb.create_subscription(subscription_type='company', subscription_key=odb_key)
        except:
            odb_status = "❌"
        
        await message.answer(
            f"✅ Компанію <code>{edrpou}</code> додано!\n├ OpenDataBot: {odb_status}\n└ 🔔 Сповіщення: увімкнено",
            reply_markup=back_to_main_keyboard(),
            parse_mode="HTML"
        )


@router.callback_query(F.data == "company:list")
async def callback_company_list(callback: CallbackQuery):
    """Список компаній (тільки для адміна)"""
    user_id = callback.from_user.id
    
    # Звичайний користувач бачить свої підписки
    if user_id not in settings.admin_ids:
        await show_my_subs_page(callback, 0)
        return
    
    async with AsyncSessionLocal() as session:
        repo = CompanyRepository(session)
        companies = await repo.get_all_companies()
        
        if not companies:
            await callback.message.edit_text(
                "📋 <b>Список компаній порожній</b>\n\n"
                "Натисніть «Додати компанію» щоб почати моніторинг.",
                reply_markup=companies_menu_keyboard(),
                parse_mode="HTML"
            )
            await callback.answer()
            return
        
        text = "📋 <b>Компанії на моніторингу:</b>\n\n"
        
        for i, c in enumerate(companies, 1):
            status = "🟢" if c.is_active else "🔴"
            name = c.company_name or "Без назви"
            text += f"{i}. {status} <code>{c.edrpou}</code>\n    └ {name}\n"
        
        active = sum(1 for c in companies if c.is_active)
        text += f"\n📊 Всього: {len(companies)} | Активних: {active}"
        
        await callback.message.edit_text(
            text,
            reply_markup=companies_menu_keyboard(),
            parse_mode="HTML"
        )
    await callback.answer()


@router.callback_query(F.data == "company:my_subs")
async def callback_my_subscriptions(callback: CallbackQuery):
    """Мої підписки - сторінка 0"""
    await show_my_subs_page(callback, 0)


@router.callback_query(F.data.startswith("mysubs:page:"))
async def callback_my_subs_page(callback: CallbackQuery):
    """Пагінація списку підписок"""
    page = int(callback.data.split(":")[2])
    await show_my_subs_page(callback, page)


async def show_my_subs_page(callback: CallbackQuery, page: int = 0):
    """Показати сторінку підписок"""
    user_id = callback.from_user.id
    per_page = 15
    
    async with AsyncSessionLocal() as session:
        user_sub_repo = UserSubscriptionRepository(session)
        company_repo = CompanyRepository(session)
        
        my_subs = await user_sub_repo.get_user_subscriptions(user_id)
        
        if not my_subs:
            await callback.message.edit_text(
                "🔔 <b>Мої підписки</b>\n\n"
                "У вас немає активних підписок.\n"
                "Додайте компанію для отримання сповіщень.",
                reply_markup=companies_menu_keyboard(),
                parse_mode="HTML"
            )
            await callback.answer()
            return
        
        total = len(my_subs)
        total_pages = (total + per_page - 1) // per_page
        page = max(0, min(page, total_pages - 1))
        
        start = page * per_page
        end = start + per_page
        page_subs = my_subs[start:end]
        
        text = f"🔔 <b>Мої підписки</b> ({total})\n\n"
        
        for sub in page_subs:
            company = await company_repo.get_company(sub.edrpou)
            name = company.company_name if company and company.company_name else "—"
            text += f"<code>{sub.edrpou}</code> {name}\n"
        
        await callback.message.edit_text(
            text,
            reply_markup=my_subs_keyboard(page, total_pages),
            parse_mode="HTML"
        )
    
    await callback.answer()


@router.callback_query(F.data == "company:odb_status")
async def callback_odb_status(callback: CallbackQuery):
    """Статус сервісу OpenDataBot"""
    await callback.message.edit_text("🔄 Перевіряю...", parse_mode="HTML")
    
    try:
        odb = OpenDataBotClient()
        subs = await odb.get_subscriptions()
        
        async with AsyncSessionLocal() as session:
            company_repo = CompanyRepository(session)
            user_sub_repo = UserSubscriptionRepository(session)
            
            local_companies = await company_repo.get_all_companies()
            my_subs = await user_sub_repo.get_user_subscriptions(callback.from_user.id)
        
        # ODB strips leading zeros, so normalize for comparison
        odb_keys = {s.get('subscriptionKey', '').lstrip('0') for s in subs}
        local_keys = {c.edrpou.lstrip('0') for c in local_companies}
        synced = len(odb_keys & local_keys)
        
        odb_count = len(subs)
        local_count = len(local_companies)
        my_count = len(my_subs)
        
        sync_status = "🟢" if synced == local_count else "🟡"
        
        text = f"""📡 <b>Статус сервісу</b>

<b>OpenDataBot API</b>
├ Підписок: <b>{odb_count}</b>
├ Синхронізовано: <b>{synced}/{local_count}</b> {sync_status}
└ Статус: 🟢 Активний

<b>База даних</b>
├ Компаній: <b>{local_count}</b>
└ Ваших підписок: <b>{my_count}</b>

<b>Розклад:</b>
├ 🔍 Перевірка: 8:00, 20:00
└ 📁 Worksection: 7:00, 19:00"""
        
        await callback.message.edit_text(
            text,
            reply_markup=companies_menu_keyboard(),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"ODB status error: {e}")
        await callback.message.edit_text(
            f"📡 <b>Статус сервісу</b>\n\n❌ Помилка: <code>{str(e)[:60]}</code>",
            reply_markup=companies_menu_keyboard(),
            parse_mode="HTML"
        )
    
    await callback.answer()


@router.callback_query(F.data.startswith("company:delete:"))
async def callback_delete_company(callback: CallbackQuery):
    """Підтвердження видалення"""
    edrpou = callback.data.split(":")[2]
    await callback.message.edit_text(
        f"⚠️ <b>Видалити компанію?</b>\n\n"
        f"ЄДРПОУ: <code>{edrpou}</code>\n\n"
        "Підписки OpenDataBot також будуть видалені.",
        reply_markup=confirm_delete_keyboard(edrpou),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("confirm:delete:"))
async def callback_confirm_delete(callback: CallbackQuery):
    """Підтвердження видалення компанії"""
    edrpou = callback.data.split(":")[2]
    
    async with AsyncSessionLocal() as session:
        repo = CompanyRepository(session)
        success = await repo.delete_company(edrpou)
        
        if success:
            await callback.message.edit_text(
                f"✅ Компанію <code>{edrpou}</code> видалено.",
                reply_markup=back_to_main_keyboard(),
                parse_mode="HTML"
            )
            logger.info(f"Company removed: {edrpou}")
        else:
            await callback.message.edit_text(
                f"❌ Компанію <code>{edrpou}</code> не знайдено.",
                reply_markup=back_to_main_keyboard(),
                parse_mode="HTML"
            )
    await callback.answer()


@router.callback_query(F.data.startswith("company:pause:"))
async def callback_pause_company(callback: CallbackQuery):
    """Призупинити моніторинг"""
    edrpou = callback.data.split(":")[2]
    
    async with AsyncSessionLocal() as session:
        repo = CompanyRepository(session)
        await repo.deactivate_company(edrpou)
    
    await callback.message.edit_text(
        f"⏸️ Моніторинг <code>{edrpou}</code> призупинено.",
        reply_markup=back_to_main_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("company:resume:"))
async def callback_resume_company(callback: CallbackQuery):
    """Відновити моніторинг"""
    edrpou = callback.data.split(":")[2]
    
    async with AsyncSessionLocal() as session:
        repo = CompanyRepository(session)
        await repo.activate_company(edrpou)
    
    await callback.message.edit_text(
        f"▶️ Моніторинг <code>{edrpou}</code> відновлено.",
        reply_markup=back_to_main_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


# === Cases Menu ===

@router.callback_query(F.data == "menu:cases")
async def callback_cases_menu(callback: CallbackQuery):
    """Меню справ"""
    await callback.message.edit_text(
        "⚖️ <b>Судові справи</b>\n\n"
        "Переглядайте знайдені справи, фільтруйте за рівнем загрози.",
        reply_markup=cases_menu_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "cases:critical")
async def callback_critical_cases(callback: CallbackQuery):
    """Критичні справи"""
    async with AsyncSessionLocal() as session:
        repo = CourtCaseRepository(session)
        cases = await repo.get_cases_by_threat_level("CRITICAL", limit=10)
        
        if not cases:
            await callback.message.edit_text(
                "🚨 <b>Критичні справи</b>\n\n"
                "✅ Критичних справ не знайдено!",
                reply_markup=cases_menu_keyboard(),
                parse_mode="HTML"
            )
            await callback.answer()
            return
        
        text = "🚨 <b>Критичні справи:</b>\n\n"
        for c in cases:
            text += f"• <code>{c.normalized_case_number}</code>\n"
            text += f"  {c.court_name or 'Суд не вказано'}\n"
            text += f"  📅 {c.fetched_at.strftime('%d.%m.%Y')}\n\n"
        
        await callback.message.edit_text(text, reply_markup=cases_menu_keyboard(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "cases:new")
async def callback_new_cases(callback: CallbackQuery):
    """Нові справи"""
    async with AsyncSessionLocal() as session:
        repo = CourtCaseRepository(session)
        cases = await repo.get_cases_by_status("new", limit=10)
        
        if not cases:
            text = "� <b>Нові справи</b>\n\n✅ Нових справ немає!"
        else:
            text = "📋 <b>Нові справи:</b>\n\n"
            for c in cases:
                level_emoji = {"CRITICAL": "🚨", "HIGH": "⚠️", "MEDIUM": "📋", "LOW": "ℹ️"}.get(c.threat_level, "📋")
                text += f"{level_emoji} <code>{c.normalized_case_number}</code>\n"
                text += f"  {c.court_name or ''}\n\n"
        
        await callback.message.edit_text(text, reply_markup=cases_menu_keyboard(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "cases:all")
async def callback_all_cases(callback: CallbackQuery):
    """Всі справи"""
    async with AsyncSessionLocal() as session:
        repo = CourtCaseRepository(session)
        cases = await repo.get_recent_cases(limit=15)
        
        if not cases:
            text = "📋 <b>Справи</b>\n\nСправ поки немає."
        else:
            text = "📋 <b>Останні справи:</b>\n\n"
            for c in cases:
                level_emoji = {"CRITICAL": "🚨", "HIGH": "⚠️", "MEDIUM": "📋", "LOW": "ℹ️"}.get(c.threat_level, "📋")
                ws_mark = "📁" if c.is_in_worksection else ""
                text += f"{level_emoji} <code>{c.normalized_case_number}</code> {ws_mark}\n"
        
        await callback.message.edit_text(text, reply_markup=cases_menu_keyboard(), parse_mode="HTML")
    await callback.answer()


@router.message(Command("cases"))
async def cmd_cases(message: Message):
    """Команда /cases"""
    await message.answer(
        "⚖️ <b>Судові справи</b>\n\n"
        "Оберіть категорію:",
        reply_markup=cases_menu_keyboard(),
        parse_mode="HTML"
    )


# === Statistics ===

@router.callback_query(F.data == "menu:stats")
async def callback_stats_menu(callback: CallbackQuery):
    """Меню статистики"""
    await callback.message.edit_text(
        "📊 <b>Статистика</b>\n\n"
        "Оберіть тип звіту:",
        reply_markup=stats_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "stats:general")
@router.message(Command("stats"))
async def callback_general_stats(event: Message | CallbackQuery):
    """Загальна статистика"""
    async with AsyncSessionLocal() as session:
        company_repo = CompanyRepository(session)
        notification_repo = NotificationRepository(session)
        ws_repo = WorksectionCaseRepository(session)
        case_repo = CourtCaseRepository(session)
        
        companies = await company_repo.get_all_companies()
        active = sum(1 for c in companies if c.is_active)
        
        recent = await notification_repo.get_recent_notifications(100)
        ws_cases = await ws_repo.get_all_case_numbers()
        
        # Count by threat level
        critical = sum(1 for n in recent if n.threat_level == "CRITICAL")
        high = sum(1 for n in recent if n.threat_level == "HIGH")
        
        text = "� <b>Загальна статистика</b>\n\n"
        text += f"🏢 <b>Компанії:</b> {len(companies)} (активних: {active})\n"
        text += f"📁 <b>Справ у Worksection:</b> {len(ws_cases)}\n"
        text += f"📨 <b>Сповіщень:</b> {len(recent)}\n\n"
        
        text += "<b>За рівнем загрози:</b>\n"
        text += f"🚨 Критичних: {critical}\n"
        text += f"⚠️ Високих: {high}\n"
        text += f"📋 Інших: {len(recent) - critical - high}\n"
        
        if recent:
            text += "\n<b>Останні сповіщення:</b>\n"
            for n in recent[:5]:
                emoji = {"CRITICAL": "🚨", "HIGH": "⚠️", "MEDIUM": "📋", "LOW": "ℹ️"}.get(n.threat_level, "📋")
                text += f"{emoji} {n.normalized_case_number} — {n.sent_at.strftime('%d.%m %H:%M')}\n"
        
        kb = stats_keyboard() if isinstance(event, CallbackQuery) else back_to_main_keyboard()
        
        if isinstance(event, CallbackQuery):
            await event.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
            await event.answer()
        else:
            await event.answer(text, reply_markup=kb, parse_mode="HTML")


# === Settings Menu ===

@router.callback_query(F.data == "menu:settings")
async def callback_settings_menu(callback: CallbackQuery):
    """Меню налаштувань"""
    async with AsyncSessionLocal() as session:
        settings_repo = UserSettingsRepository(session)
        receive_all = await settings_repo.get_receive_all(callback.from_user.id)
    
    mode_text = "✅ <b>Всі сповіщення</b>" if receive_all else "🔕 <b>Фільтр Worksection</b>"
    
    await callback.message.edit_text(
        f"⚙️ <b>Налаштування</b>\n\n"
        f"Поточний режим: {mode_text}\n\n"
        f"<i>• Всі сповіщення — отримувати ВСІ справи без фільтрації\n"
        f"• Фільтр Worksection — тільки НОВІ справи (відсутні в Worksection)</i>",
        reply_markup=settings_keyboard(receive_all),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("settings:toggle_all:"))
async def callback_toggle_all_notifications(callback: CallbackQuery):
    """Переключення режиму отримання всіх сповіщень"""
    action = callback.data.split(":")[-1]  # "on" or "off"
    new_value = action == "on"
    
    async with AsyncSessionLocal() as session:
        settings_repo = UserSettingsRepository(session)
        await settings_repo.set_receive_all(callback.from_user.id, new_value)
    
    if new_value:
        text = "✅ <b>Режим змінено!</b>\n\nТепер ви отримуватимете <b>ВСІ</b> сповіщення про судові справи, включно з тими, що вже є в Worksection."
    else:
        text = "🔕 <b>Режим змінено!</b>\n\nТепер ви отримуватимете сповіщення тільки про <b>НОВІ</b> справи, яких немає в Worksection."
    
    await callback.message.edit_text(
        text,
        reply_markup=settings_keyboard(new_value),
        parse_mode="HTML"
    )
    await callback.answer("Налаштування збережено!")


@router.callback_query(F.data == "settings:api_status")
async def callback_api_status(callback: CallbackQuery):
    """Статус API підключень"""
    await callback.message.edit_text("🔄 Перевіряю підключення...", parse_mode="HTML")
    
    results = []
    
    # Test Worksection
    try:
        ws = WorksectionClient()
        ws_ok = await ws.test_connection()
        results.append("✅ <b>Worksection:</b> OK" if ws_ok else "❌ <b>Worksection:</b> Помилка")
    except Exception as e:
        results.append(f"❌ <b>Worksection:</b> {str(e)[:50]}")
    
    # Test OpenDataBot
    try:
        odb = OpenDataBotClient()
        odb_ok = await odb.test_connection()
        results.append("✅ <b>OpenDataBot:</b> OK" if odb_ok else "⚠️ <b>OpenDataBot:</b> Немає API ключа")
    except Exception as e:
        results.append(f"❌ <b>OpenDataBot:</b> {str(e)[:50]}")
    
    # Test Database
    try:
        async with AsyncSessionLocal() as session:
            from sqlalchemy import text
            await session.execute(text("SELECT 1"))
        results.append("✅ <b>База даних:</b> OK")
    except Exception as e:
        results.append(f"❌ <b>База даних:</b> {str(e)[:50]}")
    
    await callback.message.edit_text(
        "🔧 <b>Статус підключень:</b>\n\n" + "\n".join(results),
        reply_markup=settings_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "settings:schedule")
async def callback_schedule_info(callback: CallbackQuery):
    """Інформація про розклад"""
    from src.config import settings
    
    text = "⏰ <b>Розклад синхронізації</b>\n\n"
    text += f"📥 <b>Worksection:</b> {', '.join(f'{h}:00' for h in settings.worksection_hours)}\n"
    text += f"🔍 <b>OpenDataBot:</b> {', '.join(f'{h}:00' for h in settings.opendatabot_hours)}\n\n"
    text += "<i>Worksection синхронізується перед перевіркою OpenDataBot для актуальної дедуплікації.</i>"
    
    await callback.message.edit_text(text, reply_markup=settings_keyboard(), parse_mode="HTML")
    await callback.answer()


# === Sync Menu ===

@router.callback_query(F.data == "menu:sync")
async def callback_sync_menu(callback: CallbackQuery):
    """Меню синхронізації"""
    await callback.message.edit_text(
        "🔄 <b>Синхронізація</b>\n\n"
        "Запустіть синхронізацію вручну.",
        reply_markup=sync_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "sync:worksection")
async def callback_sync_worksection(callback: CallbackQuery):
    """Синхронізація Worksection"""
    from src.services.worksection_sync import sync_worksection_cases, is_gist_mode
    
    mode = "Gist 🔒" if is_gist_mode() else "API"
    await callback.message.edit_text(f"🔄 Синхронізую Worksection ({mode})...", parse_mode="HTML")
    
    try:
        count = await sync_worksection_cases()
        mode_info = "\n🔒 <i>Режим: Gist (безпечний)</i>" if is_gist_mode() else ""
        await callback.message.edit_text(
            f"✅ <b>Worksection синхронізовано!</b>\n\n"
            f"📁 Оброблено справ: {count}{mode_info}",
            reply_markup=sync_keyboard(),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Sync error: {e}")
        await callback.message.edit_text(
            f"❌ Помилка синхронізації:\n{e}",
            reply_markup=sync_keyboard(),
            parse_mode="HTML"
        )
    await callback.answer()


@router.callback_query(F.data == "sync:opendatabot")
async def callback_sync_opendatabot(callback: CallbackQuery):
    """Перевірка OpenDataBot"""
    from src.services.monitoring import run_monitoring_cycle
    
    await callback.message.edit_text("🔄 Перевіряю OpenDataBot...", parse_mode="HTML")
    
    try:
        notifications = await run_monitoring_cycle(callback.bot)
        await callback.message.edit_text(
            f"✅ <b>OpenDataBot перевірено!</b>\n\n"
            f"📨 Нових сповіщень: {notifications}",
            reply_markup=sync_keyboard(),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"ODB check error: {e}")
        await callback.message.edit_text(
            f"❌ Помилка перевірки:\n{str(e)[:200]}",
            reply_markup=sync_keyboard(),
            parse_mode="HTML"
        )
    await callback.answer()


@router.callback_query(F.data == "sync:full")
async def callback_sync_full(callback: CallbackQuery):
    """Повна синхронізація"""
    from src.services.worksection_sync import sync_worksection_cases
    from src.services.monitoring import run_monitoring_cycle
    
    await callback.message.edit_text("� Повна синхронізація...\n\n1️⃣ Worksection...", parse_mode="HTML")
    
    try:
        ws_count = await sync_worksection_cases()
        await callback.message.edit_text(
            f"🔄 Повна синхронізація...\n\n"
            f"1️⃣ Worksection: ✅ {ws_count} справ\n"
            f"2️⃣ OpenDataBot...",
            parse_mode="HTML"
        )
        
        notifications = await run_monitoring_cycle(callback.bot)
        
        await callback.message.edit_text(
            f"✅ <b>Повну синхронізацію завершено!</b>\n\n"
            f"📁 Worksection: {ws_count} справ\n"
            f"📨 Нових сповіщень: {notifications}",
            reply_markup=sync_keyboard(),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Full sync error: {e}")
        await callback.message.edit_text(
            f"❌ Помилка синхронізації:\n{str(e)[:200]}",
            reply_markup=sync_keyboard(),
            parse_mode="HTML"
        )
    await callback.answer()


# === Legacy Commands (для сумісності) ===

@router.message(Command("test"))
async def cmd_test(message: Message):
    """Тест підключень"""
    await message.answer("🔄 Перевіряю підключення...", reply_markup=back_to_main_keyboard())
    
    results = []
    try:
        ws = WorksectionClient()
        ws_ok = await ws.test_connection()
        results.append("✅ Worksection: OK" if ws_ok else "❌ Worksection: Помилка")
    except Exception as e:
        results.append(f"❌ Worksection: {e}")
    
    try:
        odb = OpenDataBotClient()
        odb_ok = await odb.test_connection()
        results.append("✅ OpenDataBot: OK" if odb_ok else "⚠️ OpenDataBot: Немає ключа")
    except Exception as e:
        results.append(f"❌ OpenDataBot: {e}")
    
    await message.answer("🔧 <b>Статус:</b>\n\n" + "\n".join(results), reply_markup=back_to_main_keyboard(), parse_mode="HTML")


@router.message(Command("sync"))
async def cmd_sync(message: Message):
    """Синхронізація"""
    await message.answer(
        "🔄 <b>Синхронізація</b>\n\nОберіть тип:",
        reply_markup=sync_keyboard(),
        parse_mode="HTML"
    )


@router.message(Command("list"))
async def cmd_list(message: Message):
    """Список компаній (тільки для адміна)"""
    user_id = message.from_user.id
    
    # Тільки адмін бачить всі компанії
    if user_id not in settings.admin_ids:
        async with AsyncSessionLocal() as session:
            user_sub_repo = UserSubscriptionRepository(session)
            company_repo = CompanyRepository(session)
            my_subs = await user_sub_repo.get_user_subscriptions(user_id)
            
            if not my_subs:
                await message.answer(
                    "🔔 <b>Мої підписки</b>\n\nУ вас немає активних підписок.",
                    reply_markup=main_menu_keyboard(),
                    parse_mode="HTML"
                )
                return
            
            text = "🔔 <b>Мої підписки:</b>\n\n"
            for i, sub in enumerate(my_subs, 1):
                company = await company_repo.get_company(sub.edrpou)
                name = company.company_name if company else "Невідома"
                text += f"{i}. <code>{sub.edrpou}</code>\n    └ {name}\n"
            
            await message.answer(text, reply_markup=main_menu_keyboard(), parse_mode="HTML")
        return
    
    async with AsyncSessionLocal() as session:
        repo = CompanyRepository(session)
        companies = await repo.get_all_companies()
        
        if not companies:
            await message.answer(
                "📋 <b>Список порожній</b>\n\nДодайте компанію через меню.",
                reply_markup=main_menu_keyboard(),
                parse_mode="HTML"
            )
            return
        
        text = "📋 <b>Компанії:</b>\n\n"
        for c in companies:
            status = "🟢" if c.is_active else "🔴"
            text += f"{status} <code>{c.edrpou}</code> — {c.company_name or 'Без назви'}\n"
        
        await message.answer(text, reply_markup=main_menu_keyboard(), parse_mode="HTML")


# === Case Subscriptions (Моніторинг конкретних справ) ===

@router.callback_query(F.data == "cases:my_monitored")
async def callback_my_monitored_cases(callback: CallbackQuery):
    """Список справ на моніторингу"""
    async with AsyncSessionLocal() as session:
        case_repo = CaseSubscriptionRepository(session)
        cases = await case_repo.get_user_cases(callback.from_user.id)
    
    if not cases:
        await callback.message.edit_text(
            "📌 <b>Мої справи (моніторинг)</b>\n\n"
            "У вас немає справ на моніторингу.\n\n"
            "<i>Додайте номер справи, щоб отримувати сповіщення про будь-які зміни по ній.</i>",
            reply_markup=my_cases_keyboard(),
            parse_mode="HTML"
        )
        await callback.answer()
        return
    
    page_cases = cases[:10]
    total_pages = (len(cases) + 9) // 10
    
    text = "📌 <b>Мої справи (моніторинг)</b>\n\n"
    text += "<i>Натисніть ❌ щоб видалити справу з моніторингу:</i>\n\n"
    for i, c in enumerate(page_cases, 1):
        name = f" — {c.case_name}" if c.case_name else ""
        text += f"{i}. <code>{c.case_number}</code>{name}\n"
    
    if len(cases) > 10:
        text += f"\n<i>...та ще {len(cases) - 10} справ</i>"
    
    await callback.message.edit_text(
        text,
        reply_markup=my_cases_keyboard(0, total_pages, page_cases),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "mycases:info")
async def callback_my_cases_info(callback: CallbackQuery):
    """Інформація про пагінацію (ігнорування)"""
    await callback.answer()


@router.callback_query(F.data.startswith("mycases:page:"))
async def callback_my_cases_page(callback: CallbackQuery):
    """Пагінація списку справ на моніторингу"""
    page = int(callback.data.split(":")[-1])
    
    async with AsyncSessionLocal() as session:
        case_repo = CaseSubscriptionRepository(session)
        cases = await case_repo.get_user_cases(callback.from_user.id)
    
    if not cases:
        await callback.answer("Список порожній")
        return
    
    start_idx = page * 10
    page_cases = cases[start_idx:start_idx + 10]
    total_pages = (len(cases) + 9) // 10
    
    text = "📌 <b>Мої справи (моніторинг)</b>\n\n"
    text += "<i>Натисніть ❌ щоб видалити справу з моніторингу:</i>\n\n"
    for i, c in enumerate(page_cases, start_idx + 1):
        name = f" — {c.case_name}" if c.case_name else ""
        text += f"{i}. <code>{c.case_number}</code>{name}\n"
    
    await callback.message.edit_text(
        text,
        reply_markup=my_cases_keyboard(page, total_pages, page_cases),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "cases:add_case")
async def callback_add_case_start(callback: CallbackQuery, state: FSMContext):
    """Початок додавання справи на моніторинг"""
    await state.set_state(AddCaseStates.waiting_for_case_number)
    await callback.message.edit_text(
        "➕ <b>Додавання справи на моніторинг</b>\n\n"
        "Введіть номер судової справи:\n\n"
        "<i>Приклад: 922/1234/25 або 910/12345/24</i>",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AddCaseStates.waiting_for_case_number)
async def process_case_number(message: Message, state: FSMContext):
    """Обробка номера справи"""
    raw_number = message.text.strip()
    normalized = normalize_case_number(raw_number)
    
    if not normalized:
        await message.answer(
            "❌ <b>Некоректний номер справи</b>\n\n"
            "Номер має бути у форматі: XXX/XXXX/XX\n"
            "Спробуйте ще раз:",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML"
        )
        return
    
    async with AsyncSessionLocal() as session:
        case_repo = CaseSubscriptionRepository(session)
        
        # Check if already subscribed
        if await case_repo.is_subscribed(message.from_user.id, normalized):
            await state.clear()
            await message.answer(
                f"ℹ️ Ви вже відстежуєте справу <code>{normalized}</code>",
                reply_markup=my_cases_keyboard(),
                parse_mode="HTML"
            )
            return
    
    await state.update_data(case_number=normalized)
    await state.set_state(AddCaseStates.waiting_for_case_name)
    await message.answer(
        f"✅ Номер справи: <code>{normalized}</code>\n\n"
        "Введіть назву/опис справи (або надішліть '-' щоб пропустити):",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML"
    )


@router.message(AddCaseStates.waiting_for_case_name)
async def process_case_name(message: Message, state: FSMContext):
    """Збереження справи на моніторинг"""
    data = await state.get_data()
    case_number = data.get('case_number')
    case_name = message.text.strip() if message.text.strip() != '-' else None
    
    async with AsyncSessionLocal() as session:
        case_repo = CaseSubscriptionRepository(session)
        await case_repo.subscribe(message.from_user.id, case_number, case_name)
    
    await state.clear()
    
    name_text = f"\n├ Опис: {case_name}" if case_name else ""
    await message.answer(
        f"✅ <b>Справу додано на моніторинг!</b>\n\n"
        f"├ Номер: <code>{case_number}</code>{name_text}\n"
        f"└ 🔔 Сповіщення: увімкнено\n\n"
        f"<i>Ви отримаєте сповіщення про будь-які зміни по цій справі.</i>",
        reply_markup=my_cases_keyboard(),
        parse_mode="HTML"
    )
    logger.info(f"User {message.from_user.id} subscribed to case {case_number}")


@router.callback_query(F.data.startswith("case:unsub:"))
async def callback_unsubscribe_case(callback: CallbackQuery):
    """Відписка від справи"""
    case_number = callback.data.split(":", 2)[-1]
    
    async with AsyncSessionLocal() as session:
        case_repo = CaseSubscriptionRepository(session)
        await case_repo.unsubscribe(callback.from_user.id, case_number)
    
    await callback.answer(f"Справу {case_number} видалено з моніторингу")
    
    # Refresh list
    async with AsyncSessionLocal() as session:
        case_repo = CaseSubscriptionRepository(session)
        cases = await case_repo.get_user_cases(callback.from_user.id)
    
    if not cases:
        await callback.message.edit_text(
            "📌 <b>Мої справи (моніторинг)</b>\n\n"
            "У вас немає справ на моніторингу.",
            reply_markup=my_cases_keyboard(),
            parse_mode="HTML"
        )
    else:
        page_cases = cases[:10]
        total_pages = (len(cases) + 9) // 10
        text = "📌 <b>Мої справи (моніторинг)</b>\n\n"
        text += "<i>Натисніть ❌ щоб видалити справу з моніторингу:</i>\n\n"
        for i, c in enumerate(page_cases, 1):
            name = f" — {c.case_name}" if c.case_name else ""
            text += f"{i}. <code>{c.case_number}</code>{name}\n"
        
        await callback.message.edit_text(
            text, 
            reply_markup=my_cases_keyboard(0, total_pages, page_cases), 
            parse_mode="HTML"
        )


# === Contractor Check (Перевірка контрагента) ===

def _format_api_limits_info(stats: dict) -> str:
    """Інформативне відображення лімітів API"""
    if not stats:
        return ""

    _TITLES = {
        "CHECKS": "Перевірки",
        "PERSONINN": "ІПН",
        "PASSPORT": "Паспорт",
    }

    lines: list[str] = []
    any_exhausted = False

    for item in stats.get('limits', []):
        name = item.get('name', '')
        if name not in _TITLES:
            continue
        used = item.get('used', 0)
        limit = item.get('month_limit', 0)
        if limit == 0:
            continue
        remaining = max(0, limit - used)
        label = _TITLES[name]
        if remaining == 0:
            lines.append(f"  ⛔ {label}: {used}/{limit} — вичерпано")
            any_exhausted = True
        elif remaining <= 5:
            lines.append(f"  ⚠️ {label}: {used}/{limit} (залишилось {remaining})")
        else:
            lines.append(f"  ✅ {label}: {used}/{limit}")

    if not lines:
        return ""

    header = "⛔ <b>Ліміти API:</b>" if any_exhausted else "📊 <b>Ліміти API:</b>"
    return header + "\n" + "\n".join(lines)


@router.callback_query(F.data == "menu:contractor")
async def callback_contractor_menu(callback: CallbackQuery, state: FSMContext):
    """Меню перевірки контрагента"""
    await state.clear()
    await state.set_state(ContractorCheckStates.waiting_for_auto_input)
    
    # Отримуємо статистику лімітів
    client = OpenDataBotClient()
    stats = await client.get_api_statistics()
    limits_text = _format_api_limits_info(stats)
    
    text = (
        "🔍 <b>Перевірка контрагента</b>\n\n"
        "Введіть один з ідентифікаторів:\n"
        "• <b>ЄДРПОУ</b> — код компанії (8 цифр)\n"
        "• <b>ІПН</b> — код фізособи/ФОП (10 цифр)\n"
        "• <b>Паспорт</b> — серія+номер або ID-картка\n"
        "• <b>ПІБ</b> — прізвище та ім'я особи\n"
    )
    
    if limits_text:
        text += f"\n{limits_text}"
    
    await callback.message.edit_text(
        text,
        reply_markup=contractor_menu_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "contractor:company")
async def callback_contractor_company(callback: CallbackQuery, state: FSMContext):
    """Запит коду ЄДРПОУ для перевірки юридичної особи"""
    await state.set_state(ContractorCheckStates.waiting_for_company_code)
    await callback.message.edit_text(
        "🏢 <b>Перевірка юридичної особи</b>\n\n"
        "Введіть код ЄДРПОУ компанії (8 цифр):",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "contractor:fop")
async def callback_contractor_fop(callback: CallbackQuery, state: FSMContext):
    """Запит коду ІПН для перевірки ФОП"""
    await state.set_state(ContractorCheckStates.waiting_for_fop_code)
    await callback.message.edit_text(
        "👤 <b>Перевірка ФОП</b>\n\n"
        "Введіть ІПН ФОП (10 цифр) або номер паспорта:",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "contractor:person")
async def callback_contractor_person(callback: CallbackQuery, state: FSMContext):
    """Запит ПІБ для перевірки фізичної особи"""
    await state.set_state(ContractorCheckStates.waiting_for_person_pib)
    await callback.message.edit_text(
        "🔎 <b>Перевірка фізичної особи</b>\n\n"
        "Введіть ПІБ особи (Прізвище Ім'я По батькові):",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "contractor:inn")
async def callback_contractor_inn(callback: CallbackQuery, state: FSMContext):
    """Запит ІПН для перевірки фізичної особи"""
    await state.set_state(ContractorCheckStates.waiting_for_person_inn)
    await callback.message.edit_text(
        "🔢 <b>Перевірка за ІПН</b>\n\n"
        "Введіть ІПН фізичної особи (10 цифр):",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "contractor:passport")
async def callback_contractor_passport(callback: CallbackQuery, state: FSMContext):
    """Запит номера паспорта для перевірки"""
    await state.set_state(ContractorCheckStates.waiting_for_passport)
    await callback.message.edit_text(
        "🛂 <b>Перевірка паспорта</b>\n\n"
        "Перевірка чи паспорт в базі недійсних документів.\n\n"
        "Введіть номер паспорта (наприклад: СН123456 або 123456789):",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(ContractorCheckStates.waiting_for_auto_input)
async def process_auto_input(message: Message, state: FSMContext):
    """Автоматична ідентифікація типу введеного номера та запуск відповідної перевірки"""
    text = message.text.strip()
    input_type, value = identify_input_type(text)
    
    if input_type == 'edrpou':
        # Перевірка юридичної особи
        await state.clear()
        await message.answer("🏢 Визначено: <b>ЄДРПОУ</b>\n🔄 Виконую перевірку...", parse_mode="HTML")
        await _process_company_check(message, state, value)
        
    elif input_type == 'inn':
        # Об'єднана перевірка ФОП + фіз.особа
        await message.answer("🔢 Визначено: <b>ІПН</b>\n🔄 Виконую комплексну перевірку...", parse_mode="HTML")
        await _process_combined_inn_check(message, state, value)
        
    elif input_type in ('passport_old', 'passport_id'):
        # Перевірка паспорта
        await state.clear()
        await message.answer("🛂 Визначено: <b>Паспорт</b>\n🔄 Перевіряю...", parse_mode="HTML")
        await _process_passport_check(message, state, value)
        
    elif input_type == 'pib':
        # Перевірка за ПІБ
        await state.clear()
        await message.answer("👤 Визначено: <b>ПІБ</b>\n🔄 Виконую перевірку...", parse_mode="HTML")
        await _process_person_pib_check(message, state, value)
        
    else:
        await message.answer(
            "❓ Не вдалося визначити тип номера.\n\n"
            "Підтримувані формати:\n"
            "• ЄДРПОУ: 8 цифр (12345678)\n"
            "• ІПН: 10 цифр (1234567890)\n"
            "• Паспорт: СН123456 або 9 цифр\n"
            "• ПІБ: Прізвище Ім'я По батькові\n\n"
            "Спробуйте ще раз або оберіть тип перевірки:",
            reply_markup=contractor_menu_keyboard(),
            parse_mode="HTML"
        )


async def _process_company_check(message: Message, state: FSMContext, code: str):
    """Внутрішня функція перевірки компанії"""
    try:
        client = OpenDataBotClient()
        response = await client.get_full_company(code)
        
        if not response:
            await message.answer(
                ContractorFormatter.format_not_found('company', code),
                reply_markup=contractor_result_keyboard(),
                parse_mode="HTML"
            )
            return
        
        data = response.get('data')
        cached_at = response.get('cached_at')
        
        parsed_data = CompanyDataParser.parse(data)
        parsed_data['query_code'] = code
        parsed_data['cached_at'] = cached_at
        
        # Fetch Clarity data in parallel (cached)
        clarity_raw = None
        try:
            from src.clients.clarity import ClarityClient
            clarity_client = ClarityClient()
            clarity_resp = await clarity_client.get_company(code)
            if clarity_resp and clarity_resp.get('data'):
                clarity_raw = clarity_resp['data']
        except Exception as e:
            logger.warning(f"Clarity fetch for {code}: {e}")
        
        await state.update_data(
            company_code=code, company_cached_at=cached_at,
            company_data=parsed_data,
            pdf_data={'company': data, 'clarity': clarity_raw},
            pdf_code=code, pdf_type='company'
        )
        
        summary_text = ContractorFormatter.format_company_summary(parsed_data)
        keyboard = ContractorFormatter.company_categories_keyboard(parsed_data)
        await message.answer(summary_text, reply_markup=keyboard, parse_mode="HTML")
        
        logger.info(f"User {message.from_user.id} auto-checked company {code}")
        
        # Background: deep-check all related companies (with cache)
        try:
            from src.services.deep_check import deep_check_related
            asyncio.create_task(
                deep_check_related(code, odb_data=data, clarity_data=clarity_raw)
            )
        except Exception as e:
            logger.warning(f"Deep check launch for {code}: {e}")
        
    except Exception as e:
        logger.error(f"Company check error for {code}: {e}")
        await message.answer(
            ContractorFormatter.format_error(str(e)),
            reply_markup=contractor_result_keyboard(),
            parse_mode="HTML"
        )


async def _process_combined_inn_check(message: Message, state: FSMContext, code: str):
    """Комплексна перевірка ІПН: ФОП + фіз.особа"""
    # Get user identity for authorization
    from src.storage.models import UserIdentity
    from src.storage.database import get_db
    from sqlalchemy import select
    
    user_id = message.from_user.id
    user_identity = None
    
    async with get_db() as session:
        result = await session.execute(
            select(UserIdentity).where(UserIdentity.telegram_user_id == user_id)
        )
        user_identity = result.scalar_one_or_none()
    
    if not user_identity:
        # First time - ask for user's data
        await state.update_data(target_inn=code)
        await state.set_state(ContractorCheckStates.waiting_for_user_inn)
        await message.answer(
            "🔐 <b>Одноразова авторизація</b>\n\n"
            "Для отримання повної інформації (включно з нерухомістю) "
            "потрібно підтвердити вашу особу.\n\n"
            "<b>Введіть ваш ІПН:</b>\n"
            "<i>(ці дані зберігаються та використовуються автоматично)</i>",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML"
        )
        return
    
    await state.clear()
    
    try:
        client = OpenDataBotClient()
        
        # 1. Check FOP
        fop_response = await client.get_fop(code)
        fop_data = fop_response.get('data') if fop_response else None
        fop_cached_at = fop_response.get('cached_at') if fop_response else None
        
        # 2. Check person by INN with authorization
        person_response = await client.get_person_by_inn(
            code,
            user_name=user_identity.full_name,
            user_code=user_identity.inn
        )
        person_data = person_response.get('data') if person_response else None
        person_cached_at = person_response.get('cached_at') if person_response else None
        
        # Format combined response
        # Determine FOP status from fop_data OR from person-by-ipn items
        is_fop = False
        fop_status = None
        fop_name = None
        
        if fop_data:
            registry = fop_data.get('registry', fop_data)
            fop_status = registry.get('status') or fop_data.get('status', '')
            fop_name = registry.get('fullName') or registry.get('name') or fop_data.get('name')
            if fop_status and fop_status not in ('', 'не знайдено'):
                is_fop = True
        
        # Fallback: check person-by-ipn items for FOP info
        if not is_fop and person_data:
            for item in person_data.get('items', []):
                if item.get('type') == 'fop' and item.get('count', 0) > 0:
                    is_fop = True
                    fop_status = item.get('status', 'зареєстровано')
                    fop_name = item.get('name')
                    break
        
        text = f"""🔢 <b>КОМПЛЕКСНА ПЕРЕВІРКА ЗА ІПН</b>

<b>ІПН:</b> <code>{code}</code>
"""
        
        if is_fop:
            # Show FOP info
            status_emoji = "🟢" if fop_status == "зареєстровано" else "🔴" if fop_status == "припинено" else "🟡"
            text += f"\n{status_emoji} <b>ФОП: ТАК</b>\n"
            
            if fop_name:
                text += f"\n<b>{fop_name}</b>\n"
            text += f"└ Статус: {fop_status}\n"
            
            if fop_data:
                registry = fop_data.get('registry', fop_data)
                text += f"└ Дата реєстрації: {registry.get('registrationDate', fop_data.get('registrationDate', '—'))}\n"
                activities = registry.get('activities', fop_data.get('activities', []))
                if activities:
                    primary = activities[0]
                    text += f"└ КВЕД: {primary.get('code', '')} {primary.get('name', '')}\n"
        else:
            text += "\n❌ <b>ФОП: НІ</b> (не зареєстрований як ФОП)\n"
        
        # Add person-by-inn data
        if person_data:
            text += f"\n<b>Дата народження:</b> {person_data.get('birthDate', '—')}\n"
            text += f"<b>ІПН валідний:</b> {'✅' if person_data.get('correctINN') else '❌'}\n\n"
            
            # Registry check markers with proper semantics
            NEGATIVE_TYPES = {'penalty', 'bankruptcy', 'sanction', 'rnboSanction'}
            INFO_TYPES = {'drorm', 'realty'}
            TYPE_NAMES = {
                'drorm': '🏠 Нерухомість',
                'realty': '🏠 Нерухомість',
                'bankruptcy': '💸 Банкрутство',
                'penalty': '⚠️ Штрафи',
                'sanction': '🚫 Санкції',
                'rnboSanction': '🛡 Санкції РНБО',
            }
            
            items = person_data.get('items', [])
            if items:
                text += "<b>Реєстри:</b>\n"
                for item in items:
                    itype = item.get('type', '')
                    count = item.get('count', 0)
                    if itype == 'fop':
                        continue  # Already shown above
                    name = TYPE_NAMES.get(itype, itype)
                    if itype in NEGATIVE_TYPES:
                        # Negative: green=clean, red=found
                        marker = "✅ Чисто" if count == 0 else f"🔴 Знайдено ({count})"
                    elif itype in INFO_TYPES:
                        # Informational: just show count, no good/bad
                        marker = f"ℹ️ Знайдено ({count})" if count > 0 else "— Не знайдено"
                    else:
                        marker = f"ℹ️ {count}" if count > 0 else "—"
                    text += f"└ {name}: {marker}\n"
        
        # Cache info
        cached = fop_cached_at or person_cached_at
        if cached:
            text += f"\n<i>📅 Дані з кешу: {cached.strftime('%d.%m.%Y %H:%M')}</i>"
        
        # Save raw data for PDF
        pdf_data = {}
        if fop_data:
            pdf_data['fop'] = fop_data
        if person_data:
            pdf_data['person_inn'] = person_data
        await state.update_data(pdf_data=pdf_data, pdf_code=code, pdf_type='inn')
        
        from src.bot.keyboards import contractor_result_with_refresh_keyboard
        kb = contractor_result_with_refresh_keyboard(f"combined:refresh:{code}", is_cached=cached is not None, show_pdf=True)
        
        await message.answer(text, reply_markup=kb, parse_mode="HTML")
        logger.info(f"User {user_id} auto-checked combined INN {code}")
        
    except Exception as e:
        logger.error(f"Combined INN check error for {code}: {e}")
        await message.answer(
            ContractorFormatter.format_error(str(e)),
            reply_markup=contractor_result_keyboard(),
            parse_mode="HTML"
        )


async def _process_passport_check(message: Message, state: FSMContext, passport: str):
    """Внутрішня функція перевірки паспорта"""
    try:
        client = OpenDataBotClient()
        response = await client.get_passport(passport)
        
        if not response:
            await message.answer(
                "❌ Не вдалося перевірити паспорт",
                reply_markup=contractor_result_keyboard(),
                parse_mode="HTML"
            )
            return
        
        data = response.get('data', {})
        cached_at = response.get('cached_at')
        count = data.get('count', 0)
        
        if count == 0:
            text = f"""🛂 <b>ПЕРЕВІРКА ПАСПОРТА</b>

<b>Номер:</b> <code>{passport}</code>

✅ <b>Паспорт НЕ в базі недійсних</b>

Документ не знайдено серед втрачених, викрадених або недійсних паспортів."""
        else:
            items = data.get('data', [])
            text = f"""🛂 <b>ПЕРЕВІРКА ПАСПОРТА</b>

<b>Номер:</b> <code>{passport}</code>

⚠️ <b>УВАГА! Паспорт в базі недійсних!</b>

Знайдено записів: {count}
"""
            for item in items[:5]:
                text += f"\n• {item.get('status', '')} - {item.get('date', '')}"
        
        if cached_at:
            text += f"\n\n<i>📅 Дані з кешу: {cached_at.strftime('%d.%m.%Y %H:%M')}</i>"
        
        # Save raw data for PDF
        await state.update_data(pdf_data={'passport': data}, pdf_code=passport, pdf_type='passport')
        
        from src.bot.keyboards import contractor_result_with_refresh_keyboard
        kb = contractor_result_with_refresh_keyboard(f"passport:refresh:{passport}", is_cached=cached_at is not None, show_pdf=True)
        
        await message.answer(text, reply_markup=kb, parse_mode="HTML")
        logger.info(f"User {message.from_user.id} auto-checked passport {passport}")
        
    except Exception as e:
        logger.error(f"Passport check error for {passport}: {e}")
        await message.answer(
            ContractorFormatter.format_error(str(e)),
            reply_markup=contractor_result_keyboard(),
            parse_mode="HTML"
        )


async def _process_person_pib_check(message: Message, state: FSMContext, pib: str):
    """Внутрішня функція перевірки за ПІБ"""
    try:
        client = OpenDataBotClient()
        response = await client.get_person(pib)
        
        if not response:
            await message.answer(
                ContractorFormatter.format_not_found('person', pib),
                reply_markup=contractor_result_keyboard(),
                parse_mode="HTML"
            )
            return
        
        data = response.get('data')
        cached_at = response.get('cached_at')
        
        parsed_data = PersonDataParser.parse(data)
        parsed_data['name'] = pib
        parsed_data['query_pib'] = pib
        parsed_data['cached_at'] = cached_at
        
        await state.update_data(
            person_pib=pib, person_cached_at=cached_at,
            person_data=parsed_data,
            pdf_data={'person': data}, pdf_code=pib, pdf_type='person'
        )
        
        summary_text = ContractorFormatter.format_person_summary(parsed_data)
        keyboard = ContractorFormatter.person_categories_keyboard(parsed_data)
        await message.answer(summary_text, reply_markup=keyboard, parse_mode="HTML")
        
        logger.info(f"User {message.from_user.id} auto-checked person {pib}")
        
    except Exception as e:
        logger.error(f"Person PIB check error for {pib}: {e}")
        await message.answer(
            ContractorFormatter.format_error(str(e)),
            reply_markup=contractor_result_keyboard(),
            parse_mode="HTML"
        )


@router.callback_query(F.data == "pdf:report")
async def callback_pdf_report(callback: CallbackQuery, state: FSMContext):
    """Генерація PDF звіту з даних останньої перевірки"""
    from aiogram.types import BufferedInputFile
    from src.services.pdf_generator import generate_report_pdf
    
    state_data = await state.get_data()
    pdf_data = state_data.get('pdf_data')
    pdf_code = state_data.get('pdf_code', 'report')
    pdf_type = state_data.get('pdf_type', 'unknown')
    
    if not pdf_data:
        await callback.answer("Немає даних для звіту", show_alert=True)
        return
    
    await callback.answer("📄 Генерую PDF...", show_alert=False)
    
    try:
        # Collect all datasets (filter out None values)
        datasets = [v for v in pdf_data.values() if v is not None]
        
        # Title based on type
        titles = {
            'company': 'ЗВІТ ПЕРЕВІРКИ КОМПАНІЇ',
            'fop': 'ЗВІТ ПЕРЕВІРКИ ФОП',
            'inn': 'ЗВІТ ПЕРЕВІРКИ ЗА ІПН',
            'passport': 'ПЕРЕВІРКА ПАСПОРТА',
            'person': 'ЗВІТ ПЕРЕВІРКИ ОСОБИ',
        }
        title = titles.get(pdf_type, 'ЗВІТ ПЕРЕВІРКИ КОНТРАГЕНТА')
        
        pdf_bytes = await generate_report_pdf(*datasets, title=title, code=str(pdf_code))
        
        doc = BufferedInputFile(pdf_bytes, filename=f"report_{pdf_code}.pdf")
        await callback.message.answer_document(doc, caption=f"📄 {title}")
        
        logger.info(f"User {callback.from_user.id} generated PDF for {pdf_type}/{pdf_code}")
        
    except Exception as e:
        logger.error(f"PDF generation error: {e}")
        await callback.answer(f"Помилка: {str(e)[:50]}", show_alert=True)


@router.callback_query(F.data.startswith("combined:refresh:"))
async def callback_combined_refresh(callback: CallbackQuery, state: FSMContext):
    """Примусове оновлення комплексної перевірки ІПН"""
    parts = callback.data.split(":")
    code = parts[2] if len(parts) > 2 else None
    
    if not code:
        await callback.answer("Код не знайдено", show_alert=True)
        return
    
    await callback.answer("🔄 Оновлюю дані...", show_alert=False)
    
    # Get user identity
    from src.storage.models import UserIdentity
    from src.storage.database import get_db
    from sqlalchemy import select
    
    user_id = callback.from_user.id
    user_identity = None
    
    async with get_db() as session:
        result = await session.execute(
            select(UserIdentity).where(UserIdentity.telegram_user_id == user_id)
        )
        user_identity = result.scalar_one_or_none()
    
    if not user_identity:
        await callback.answer("Спочатку пройдіть авторизацію", show_alert=True)
        return
    
    try:
        client = OpenDataBotClient()
        
        # Force refresh both
        fop_response = await client.get_fop(code, force_refresh=True)
        person_response = await client.get_person_by_inn(
            code,
            force_refresh=True,
            user_name=user_identity.full_name,
            user_code=user_identity.inn
        )
        
        fop_data = fop_response.get('data') if fop_response else None
        person_data = person_response.get('data') if person_response else None
        
        # Determine FOP status from fop_data OR from person-by-ipn items
        is_fop = False
        fop_status = None
        fop_name = None
        
        if fop_data:
            registry = fop_data.get('registry', fop_data)
            fop_status = registry.get('status') or fop_data.get('status', '')
            fop_name = registry.get('fullName') or registry.get('name') or fop_data.get('name')
            if fop_status and fop_status not in ('', 'не знайдено'):
                is_fop = True
        
        if not is_fop and person_data:
            for item in person_data.get('items', []):
                if item.get('type') == 'fop' and item.get('count', 0) > 0:
                    is_fop = True
                    fop_status = item.get('status', 'зареєстровано')
                    fop_name = item.get('name')
                    break
        
        text = f"""🔢 <b>КОМПЛЕКСНА ПЕРЕВІРКА ЗА ІПН</b>

<b>ІПН:</b> <code>{code}</code>
"""
        
        if is_fop:
            status_emoji = "🟢" if fop_status == "зареєстровано" else "🔴" if fop_status == "припинено" else "🟡"
            text += f"\n{status_emoji} <b>ФОП: ТАК</b>\n"
            if fop_name:
                text += f"\n<b>{fop_name}</b>\n"
            text += f"└ Статус: {fop_status}\n"
        else:
            text += "\n❌ <b>ФОП: НІ</b>\n"
        
        if person_data:
            text += f"\n<b>Дата народження:</b> {person_data.get('birthDate', '—')}\n"
            
            NEGATIVE_TYPES = {'penalty', 'bankruptcy', 'sanction', 'rnboSanction'}
            INFO_TYPES = {'drorm', 'realty'}
            TYPE_NAMES = {
                'drorm': '🏠 Нерухомість',
                'realty': '🏠 Нерухомість',
                'bankruptcy': '💸 Банкрутство',
                'penalty': '⚠️ Штрафи',
                'sanction': '🚫 Санкції',
                'rnboSanction': '🛡 Санкції РНБО',
            }
            
            items = person_data.get('items', [])
            if items:
                text += "\n<b>Реєстри:</b>\n"
                for item in items:
                    itype = item.get('type', '')
                    if itype == 'fop':
                        continue
                    count = item.get('count', 0)
                    name = TYPE_NAMES.get(itype, itype)
                    if itype in NEGATIVE_TYPES:
                        marker = "✅ Чисто" if count == 0 else f"🔴 Знайдено ({count})"
                    elif itype in INFO_TYPES:
                        marker = f"ℹ️ Знайдено ({count})" if count > 0 else "— Не знайдено"
                    else:
                        marker = f"ℹ️ {count}" if count > 0 else "—"
                    text += f"└ {name}: {marker}\n"
        
        # Save raw data for PDF
        pdf_data = {}
        if fop_data:
            pdf_data['fop'] = fop_data
        if person_data:
            pdf_data['person_inn'] = person_data
        await state.update_data(pdf_data=pdf_data, pdf_code=code, pdf_type='inn')
        
        from src.bot.keyboards import contractor_result_with_refresh_keyboard
        kb = contractor_result_with_refresh_keyboard(f"combined:refresh:{code}", is_cached=False, show_pdf=True)
        
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        logger.info(f"User {user_id} refreshed combined INN {code}")
        
    except Exception as e:
        logger.error(f"Combined refresh error for {code}: {e}")
        await callback.answer(f"Помилка: {str(e)[:50]}", show_alert=True)


@router.message(ContractorCheckStates.waiting_for_passport)
async def process_contractor_passport(message: Message, state: FSMContext):
    """Обробка перевірки паспорта"""
    passport = message.text.strip().upper().replace(" ", "")
    
    if len(passport) < 6:
        await message.answer(
            "❌ Некоректний номер паспорта.\n"
            "Спробуйте ще раз:",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML"
        )
        return
    
    await state.clear()
    await message.answer("🔄 Перевіряю паспорт...", parse_mode="HTML")
    
    try:
        client = OpenDataBotClient()
        response = await client.get_passport(passport)
        
        if not response:
            await message.answer(
                "❌ Не вдалося перевірити паспорт",
                reply_markup=contractor_result_keyboard(),
                parse_mode="HTML"
            )
            return
        
        data = response.get('data', {})
        cached_at = response.get('cached_at')
        count = data.get('count', 0)
        
        if count == 0:
            text = f"""🛂 <b>ПЕРЕВІРКА ПАСПОРТА</b>

<b>Номер:</b> <code>{passport}</code>

✅ <b>Паспорт НЕ в базі недійсних</b>

Документ не знайдено серед втрачених, викрадених або недійсних паспортів."""
        else:
            items = data.get('data', [])
            text = f"""🛂 <b>ПЕРЕВІРКА ПАСПОРТА</b>

<b>Номер:</b> <code>{passport}</code>

⚠️ <b>УВАГА! Паспорт в базі недійсних!</b>

Знайдено записів: {count}
"""
            for item in items[:5]:
                text += f"\n• {item.get('status', '')} - {item.get('date', '')}"
        
        if cached_at:
            text += f"\n\n<i>📅 Дані з кешу: {cached_at.strftime('%d.%m.%Y %H:%M')}</i>"
        
        from src.bot.keyboards import contractor_result_with_refresh_keyboard
        kb = contractor_result_with_refresh_keyboard(f"passport:refresh:{passport}", is_cached=cached_at is not None)
        
        await message.answer(text, reply_markup=kb, parse_mode="HTML")
        logger.info(f"User {message.from_user.id} checked passport {passport}")
        
    except Exception as e:
        logger.error(f"Passport check error for {passport}: {e}")
        await message.answer(
            ContractorFormatter.format_error(str(e)),
            reply_markup=contractor_result_keyboard(),
            parse_mode="HTML"
        )


@router.callback_query(F.data.startswith("passport:refresh:"))
async def callback_passport_refresh(callback: CallbackQuery, state: FSMContext):
    """Примусове оновлення даних паспорта"""
    parts = callback.data.split(":")
    passport = parts[2] if len(parts) > 2 else None
    
    if not passport:
        await callback.answer("Номер не знайдено", show_alert=True)
        return
    
    await callback.answer("🔄 Оновлюю дані...", show_alert=False)
    
    try:
        client = OpenDataBotClient()
        response = await client.get_passport(passport, force_refresh=True)
        
        if not response:
            await callback.answer("Не вдалося отримати дані", show_alert=True)
            return
        
        data = response.get('data', {})
        count = data.get('count', 0)
        
        if count == 0:
            text = f"""🛂 <b>ПЕРЕВІРКА ПАСПОРТА</b>

<b>Номер:</b> <code>{passport}</code>

✅ <b>Паспорт НЕ в базі недійсних</b>

Документ не знайдено серед втрачених, викрадених або недійсних паспортів."""
        else:
            items = data.get('data', [])
            text = f"""🛂 <b>ПЕРЕВІРКА ПАСПОРТА</b>

<b>Номер:</b> <code>{passport}</code>

⚠️ <b>УВАГА! Паспорт в базі недійсних!</b>

Знайдено записів: {count}
"""
            for item in items[:5]:
                text += f"\n• {item.get('status', '')} - {item.get('date', '')}"
        
        from src.bot.keyboards import contractor_result_with_refresh_keyboard
        kb = contractor_result_with_refresh_keyboard(f"passport:refresh:{passport}", is_cached=False)
        
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        logger.info(f"User {callback.from_user.id} refreshed passport {passport}")
        
    except Exception as e:
        logger.error(f"Passport refresh error for {passport}: {e}")
        await callback.answer(f"Помилка: {str(e)[:50]}", show_alert=True)


@router.message(ContractorCheckStates.waiting_for_company_code)
async def process_contractor_company(message: Message, state: FSMContext):
    """Обробка запиту перевірки юридичної особи - багаторівнева система"""
    code = message.text.strip()
    
    if not validate_edrpou(code):
        await message.answer(
            "❌ Некоректний код ЄДРПОУ. Має бути 8 цифр.\n"
            "Спробуйте ще раз:",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML"
        )
        return
    
    await message.answer("🔄 Виконую перевірку...", parse_mode="HTML")
    
    try:
        client = OpenDataBotClient()
        response = await client.get_full_company(code)
        
        if not response:
            await state.clear()
            await message.answer(
                ContractorFormatter.format_not_found('company', code),
                reply_markup=contractor_result_keyboard(),
                parse_mode="HTML"
            )
            return
        
        data = response.get('data')
        cached_at = response.get('cached_at')
        
        # Parse and store data for navigation
        parsed_data = CompanyDataParser.parse(data)
        parsed_data['query_code'] = code  # Store for refresh
        parsed_data['cached_at'] = cached_at
        
        # Fetch Clarity data (cached)
        clarity_raw = None
        try:
            from src.clients.clarity import ClarityClient
            clarity_client = ClarityClient()
            clarity_resp = await clarity_client.get_company(code)
            if clarity_resp and clarity_resp.get('data'):
                clarity_raw = clarity_resp['data']
        except Exception as e:
            logger.warning(f"Clarity fetch for {code}: {e}")
        
        await state.update_data(
            company_data=parsed_data,
            pdf_data={'company': data, 'clarity': clarity_raw},
            pdf_code=code, pdf_type='company'
        )
        
        # Show summary with category buttons
        summary_text = ContractorFormatter.format_company_summary(parsed_data)
        keyboard = ContractorFormatter.company_categories_keyboard(parsed_data)
        
        await message.answer(summary_text, reply_markup=keyboard, parse_mode="HTML")
        
        logger.info(f"User {message.from_user.id} checked company {code}")
        
        # Background: deep-check all related companies (with cache)
        try:
            from src.services.deep_check import deep_check_related
            asyncio.create_task(
                deep_check_related(code, odb_data=data, clarity_data=clarity_raw)
            )
        except Exception as e:
            logger.warning(f"Deep check launch for {code}: {e}")
        
    except Exception as e:
        logger.error(f"Contractor check error for {code}: {e}")
        await state.clear()
        await message.answer(
            ContractorFormatter.format_error(str(e)),
            reply_markup=contractor_result_keyboard(),
            parse_mode="HTML"
        )


@router.callback_query(F.data.startswith("company:cat:"))
async def callback_company_category(callback: CallbackQuery, state: FSMContext):
    """Показ списку елементів категорії компанії (Рівень 2)"""
    parts = callback.data.split(":")
    category = parts[2]
    page = int(parts[3]) if len(parts) > 3 else 0
    
    data = await state.get_data()
    parsed_data = data.get('company_data')
    
    if not parsed_data:
        await callback.answer("Дані застаріли. Виконайте пошук знову.", show_alert=True)
        return
    
    categories = parsed_data.get('categories', {})
    cat_data = categories.get(category, {})
    items = cat_data.get('items', [])
    
    text = ContractorFormatter.format_company_category(parsed_data, category, page)
    keyboard = ContractorFormatter.company_category_keyboard(category, page, len(items), parsed_data=parsed_data)
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("company:history:"))
async def callback_company_history_detail(callback: CallbackQuery, state: FSMContext):
    """Показ деталей змін за конкретну дату (Рівень 3)"""
    parts = callback.data.split(":")
    index_str = parts[2]
    
    data = await state.get_data()
    parsed_data = data.get('company_data')
    
    if not parsed_data:
        await callback.answer("Дані застаріли. Виконайте пошук знову.", show_alert=True)
        return
    
    categories = parsed_data.get('categories', {})
    history_data = categories.get('history', {})
    items = history_data.get('items', [])
    
    if index_str == 'more':
        # Show more dates (page 2)
        text = "📋 <b>Більше записів:</b>\n\n"
        for i, item in enumerate(items[5:10], 5):
            date = item.get('date', '')
            changes = item.get('changes', [])
            text += f"📅 <b>{date}</b> — {len(changes)} змін\n\n"
        keyboard = ContractorFormatter.history_detail_keyboard()
    else:
        index = int(index_str)
        if index < len(items):
            item = items[index]
            text = ContractorFormatter.format_history_detail(item)
            keyboard = ContractorFormatter.history_detail_keyboard()
        else:
            await callback.answer("Запис не знайдено", show_alert=True)
            return
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "company:back")
async def callback_company_back(callback: CallbackQuery, state: FSMContext):
    """Повернення до огляду категорій компанії (Рівень 1)"""
    data = await state.get_data()
    parsed_data = data.get('company_data')
    
    if not parsed_data:
        await callback.answer("Дані застаріли. Виконайте пошук знову.", show_alert=True)
        return
    
    summary_text = ContractorFormatter.format_company_summary(parsed_data)
    keyboard = ContractorFormatter.company_categories_keyboard(parsed_data)
    
    await callback.message.edit_text(summary_text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "company:noop")
async def callback_company_noop(callback: CallbackQuery):
    """Пуста дія для інформаційних кнопок компанії"""
    await callback.answer()


@router.callback_query(F.data == "company:refresh")
async def callback_company_refresh(callback: CallbackQuery, state: FSMContext):
    """Примусове оновлення даних компанії з API"""
    data = await state.get_data()
    parsed_data = data.get('company_data')
    
    if not parsed_data:
        await callback.answer("Дані застаріли. Виконайте пошук знову.", show_alert=True)
        return
    
    code = parsed_data.get('query_code')
    if not code:
        await callback.answer("Код компанії не знайдено.", show_alert=True)
        return
    
    await callback.answer("🔄 Оновлюю дані з реєстру...", show_alert=False)
    
    try:
        client = OpenDataBotClient()
        response = await client.get_full_company(code, force_refresh=True)
        
        if not response:
            await callback.answer("Не вдалося отримати дані.", show_alert=True)
            return
        
        new_data = response.get('data')
        
        # Parse and update state
        new_parsed = CompanyDataParser.parse(new_data)
        new_parsed['query_code'] = code
        new_parsed['cached_at'] = None  # Fresh data
        await state.update_data(
            company_data=new_parsed,
            pdf_data={'company': new_data}, pdf_code=code, pdf_type='company'
        )
        
        # Show updated summary
        summary_text = ContractorFormatter.format_company_summary(new_parsed)
        keyboard = ContractorFormatter.company_categories_keyboard(new_parsed)
        
        await callback.message.edit_text(summary_text, reply_markup=keyboard, parse_mode="HTML")
        logger.info(f"User {callback.from_user.id} refreshed company {code}")
        
    except Exception as e:
        logger.error(f"Company refresh error for {code}: {e}")
        await callback.answer(f"Помилка оновлення: {str(e)[:50]}", show_alert=True)


@router.message(ContractorCheckStates.waiting_for_fop_code)
async def process_contractor_fop(message: Message, state: FSMContext):
    """Обробка запиту перевірки ФОП"""
    code = message.text.strip()
    
    await state.clear()
    await message.answer("🔄 Виконую перевірку...", parse_mode="HTML")
    
    try:
        client = OpenDataBotClient()
        response = await client.get_fop(code)
        
        if not response:
            await message.answer(
                ContractorFormatter.format_not_found('fop', code),
                reply_markup=contractor_result_keyboard(),
                parse_mode="HTML"
            )
            return
        
        data = response.get('data')
        cached_at = response.get('cached_at')
        
        # Save raw data for PDF
        await state.update_data(pdf_data={'fop': data}, pdf_code=code, pdf_type='fop')
        
        messages = ContractorFormatter.format_fop(data, cached_at)
        
        from src.bot.keyboards import contractor_result_with_refresh_keyboard
        for i, msg in enumerate(messages):
            if i == len(messages) - 1:
                kb = contractor_result_with_refresh_keyboard(f"fop:refresh:{code}", is_cached=True, show_pdf=True)
            else:
                kb = None
            await message.answer(msg, reply_markup=kb, parse_mode="HTML")
        
        logger.info(f"User {message.from_user.id} checked FOP {code}")
        
    except Exception as e:
        logger.error(f"FOP check error for {code}: {e}")
        await message.answer(
            ContractorFormatter.format_error(str(e)),
            reply_markup=contractor_result_keyboard(),
            parse_mode="HTML"
        )


@router.callback_query(F.data.startswith("fop:refresh:"))
async def callback_fop_refresh(callback: CallbackQuery, state: FSMContext):
    """Примусове оновлення даних ФОП"""
    parts = callback.data.split(":")
    code = parts[2] if len(parts) > 2 else None
    
    if not code:
        await callback.answer("Код не знайдено", show_alert=True)
        return
    
    await callback.answer("🔄 Оновлюю дані з реєстру...", show_alert=False)
    
    try:
        client = OpenDataBotClient()
        response = await client.get_fop(code, force_refresh=True)
        
        if not response:
            await callback.answer("Не вдалося отримати дані", show_alert=True)
            return
        
        data = response.get('data')
        
        # Save raw data for PDF
        await state.update_data(pdf_data={'fop': data}, pdf_code=code, pdf_type='fop')
        
        messages = ContractorFormatter.format_fop(data, cached_at=None)
        
        from src.bot.keyboards import contractor_result_with_refresh_keyboard
        kb = contractor_result_with_refresh_keyboard(f"fop:refresh:{code}", is_cached=False, show_pdf=True)
        
        await callback.message.edit_text(messages[0], reply_markup=kb, parse_mode="HTML")
        logger.info(f"User {callback.from_user.id} refreshed FOP {code}")
        
    except Exception as e:
        logger.error(f"FOP refresh error for {code}: {e}")
        await callback.answer(f"Помилка: {str(e)[:50]}", show_alert=True)


@router.message(ContractorCheckStates.waiting_for_person_pib)
async def process_contractor_person(message: Message, state: FSMContext):
    """Обробка запиту перевірки фізичної особи за ПІБ - багаторівнева система"""
    pib = message.text.strip()
    
    if len(pib) < 5:
        await message.answer(
            "❌ ПІБ занадто короткий. Введіть повні дані.\n"
            "Спробуйте ще раз:",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML"
        )
        return
    
    await message.answer("🔄 Виконую перевірку...", parse_mode="HTML")
    
    try:
        client = OpenDataBotClient()
        response = await client.get_person(pib)
        
        if not response:
            await state.clear()
            await message.answer(
                ContractorFormatter.format_not_found('person', pib),
                reply_markup=contractor_result_keyboard(),
                parse_mode="HTML"
            )
            return
        
        data = response.get('data')
        cached_at = response.get('cached_at')
        
        # Parse and store data in state for navigation
        parsed_data = PersonDataParser.parse(data)
        parsed_data['name'] = pib
        parsed_data['query_pib'] = pib
        parsed_data['cached_at'] = cached_at
        await state.update_data(
            person_data=parsed_data,
            pdf_data={'person': data}, pdf_code=pib, pdf_type='person'
        )
        
        # Show summary with category buttons
        summary_text = ContractorFormatter.format_person_summary(parsed_data)
        keyboard = ContractorFormatter.person_categories_keyboard(parsed_data)
        
        await message.answer(summary_text, reply_markup=keyboard, parse_mode="HTML")
        
        logger.info(f"User {message.from_user.id} checked person {pib[:20]}...")
        
    except Exception as e:
        logger.error(f"Person check error for {pib}: {e}")
        await state.clear()
        await message.answer(
            ContractorFormatter.format_error(str(e)),
            reply_markup=contractor_result_keyboard(),
            parse_mode="HTML"
        )


@router.callback_query(F.data.startswith("person:cat:"))
async def callback_person_category(callback: CallbackQuery, state: FSMContext):
    """Показ списку елементів категорії (Рівень 2)"""
    parts = callback.data.split(":")
    category = parts[2]
    page = int(parts[3]) if len(parts) > 3 else 0
    
    data = await state.get_data()
    parsed_data = data.get('person_data')
    
    if not parsed_data:
        await callback.answer("Дані застаріли. Виконайте пошук знову.", show_alert=True)
        return
    
    categories = parsed_data.get('categories', {})
    cat_data = categories.get(category, {})
    items = cat_data.get('items', [])
    
    text = ContractorFormatter.format_category_list(parsed_data, category, page)
    keyboard = ContractorFormatter.category_list_keyboard(category, page, len(items))
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "person:back")
async def callback_person_back(callback: CallbackQuery, state: FSMContext):
    """Повернення до огляду категорій (Рівень 1)"""
    data = await state.get_data()
    parsed_data = data.get('person_data')
    
    if not parsed_data:
        await callback.answer("Дані застаріли. Виконайте пошук знову.", show_alert=True)
        return
    
    summary_text = ContractorFormatter.format_person_summary(parsed_data)
    keyboard = ContractorFormatter.person_categories_keyboard(parsed_data)
    
    await callback.message.edit_text(summary_text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "person:noop")
async def callback_person_noop(callback: CallbackQuery):
    """Пуста дія для інформаційних кнопок"""
    await callback.answer()


@router.callback_query(F.data == "person:refresh")
async def callback_person_refresh(callback: CallbackQuery, state: FSMContext):
    """Примусове оновлення даних особи за ПІБ"""
    data = await state.get_data()
    parsed_data = data.get('person_data')
    
    if not parsed_data:
        await callback.answer("Дані застаріли. Виконайте пошук знову.", show_alert=True)
        return
    
    pib = parsed_data.get('query_pib') or parsed_data.get('name')
    if not pib:
        await callback.answer("ПІБ не знайдено", show_alert=True)
        return
    
    await callback.answer("🔄 Оновлюю дані з реєстру...", show_alert=False)
    
    try:
        client = OpenDataBotClient()
        response = await client.get_person(pib, force_refresh=True)
        
        if not response:
            await callback.answer("Не вдалося отримати дані", show_alert=True)
            return
        
        new_data = response.get('data')
        
        # Parse and update state
        new_parsed = PersonDataParser.parse(new_data)
        new_parsed['name'] = pib
        new_parsed['query_pib'] = pib
        new_parsed['cached_at'] = None
        await state.update_data(
            person_data=new_parsed,
            pdf_data={'person': new_data}, pdf_code=pib, pdf_type='person'
        )
        
        # Show updated summary
        summary_text = ContractorFormatter.format_person_summary(new_parsed)
        keyboard = ContractorFormatter.person_categories_keyboard(new_parsed)
        
        await callback.message.edit_text(summary_text, reply_markup=keyboard, parse_mode="HTML")
        logger.info(f"User {callback.from_user.id} refreshed person {pib[:20]}...")
        
    except Exception as e:
        logger.error(f"Person refresh error for {pib}: {e}")
        await callback.answer(f"Помилка: {str(e)[:50]}", show_alert=True)


@router.message(ContractorCheckStates.waiting_for_person_inn)
async def process_contractor_inn(message: Message, state: FSMContext):
    """Обробка запиту перевірки фізичної особи за ІПН"""
    code = message.text.strip()
    
    if not code.isdigit() or len(code) != 10:
        await message.answer(
            "❌ Некоректний ІПН. Має бути 10 цифр.\n"
            "Спробуйте ще раз:",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML"
        )
        return
    
    # Check if user has identity saved
    from src.storage.models import UserIdentity
    from src.storage.database import get_db
    from sqlalchemy import select
    
    user_id = message.from_user.id
    user_identity = None
    
    async with get_db() as session:
        result = await session.execute(
            select(UserIdentity).where(UserIdentity.telegram_user_id == user_id)
        )
        user_identity = result.scalar_one_or_none()
    
    if not user_identity:
        # First time - ask for user's own INN
        await state.update_data(target_inn=code)
        await state.set_state(ContractorCheckStates.waiting_for_user_inn)
        await message.answer(
            "� <b>Одноразова авторизація</b>\n\n"
            "Для отримання повної інформації (включно з нерухомістю) "
            "потрібно підтвердити вашу особу.\n\n"
            "<b>Введіть ваш ІПН:</b>\n"
            "<i>(ці дані зберігаються та використовуються автоматично)</i>",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML"
        )
        return
    
    # User has identity - proceed with full check
    await state.clear()
    await message.answer("� Виконую перевірку...", parse_mode="HTML")
    
    try:
        client = OpenDataBotClient()
        response = await client.get_person_by_inn(
            code, 
            user_name=user_identity.full_name,
            user_code=user_identity.inn
        )
        
        if not response:
            await message.answer(
                ContractorFormatter.format_not_found('inn', code),
                reply_markup=contractor_result_keyboard(),
                parse_mode="HTML"
            )
            return
        
        data = response.get('data')
        cached_at = response.get('cached_at')
        
        # Store for refresh + PDF
        await state.update_data(
            inn_code=code, inn_cached_at=cached_at,
            pdf_data={'person_inn': data}, pdf_code=code, pdf_type='inn'
        )
        
        messages = ContractorFormatter.format_person_by_inn(data, cached_at)
        
        from src.bot.keyboards import contractor_result_with_refresh_keyboard
        for i, msg in enumerate(messages):
            if i == len(messages) - 1:
                kb = contractor_result_with_refresh_keyboard(f"inn:refresh:{code}", is_cached=True, show_pdf=True)
            else:
                kb = None
            await message.answer(msg, reply_markup=kb, parse_mode="HTML")
        
        logger.info(f"User {message.from_user.id} checked INN {code}")
        
    except Exception as e:
        logger.error(f"INN check error for {code}: {e}")
        await message.answer(
            ContractorFormatter.format_error(str(e)),
            reply_markup=contractor_result_keyboard(),
            parse_mode="HTML"
        )


@router.message(ContractorCheckStates.waiting_for_user_inn)
async def process_user_inn(message: Message, state: FSMContext):
    """Збереження ІПН користувача для авторизації"""
    user_inn = message.text.strip()
    
    if not user_inn.isdigit() or len(user_inn) != 10:
        await message.answer(
            "❌ Некоректний ІПН. Має бути 10 цифр.\n"
            "Спробуйте ще раз:",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML"
        )
        return
    
    await state.update_data(user_inn=user_inn)
    await state.set_state(ContractorCheckStates.waiting_for_user_name)
    await message.answer(
        "✅ ІПН збережено!\n\n"
        "<b>Тепер введіть ваше ПІБ:</b>\n"
        "<i>(повністю, як у паспорті)</i>",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML"
    )


@router.message(ContractorCheckStates.waiting_for_user_name)
async def process_user_name(message: Message, state: FSMContext):
    """Збереження ПІБ користувача та виконання запиту"""
    user_name = message.text.strip()
    
    if len(user_name) < 5:
        await message.answer(
            "❌ ПІБ занадто короткий.\n"
            "Введіть повне ПІБ:",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML"
        )
        return
    
    data = await state.get_data()
    user_inn = data.get('user_inn')
    target_inn = data.get('target_inn')
    user_id = message.from_user.id
    
    # Save user identity to database
    from src.storage.models import UserIdentity
    from src.storage.database import get_db
    
    async with get_db() as session:
        identity = UserIdentity(
            telegram_user_id=user_id,
            full_name=user_name,
            inn=user_inn
        )
        session.add(identity)
        await session.commit()
    
    await state.clear()
    await message.answer(
        "✅ <b>Дані збережено!</b>\n"
        "Тепер всі запити будуть виконуватись автоматично.\n\n"
        "🔄 Виконую перевірку...",
        parse_mode="HTML"
    )
    
    # Now perform the original check
    try:
        client = OpenDataBotClient()
        response = await client.get_person_by_inn(
            target_inn,
            user_name=user_name,
            user_code=user_inn
        )
        
        if not response:
            await message.answer(
                ContractorFormatter.format_not_found('inn', target_inn),
                reply_markup=contractor_result_keyboard(),
                parse_mode="HTML"
            )
            return
        
        resp_data = response.get('data')
        cached_at = response.get('cached_at')
        
        # Save raw data for PDF
        await state.update_data(
            pdf_data={'person_inn': resp_data}, pdf_code=target_inn, pdf_type='inn'
        )
        
        messages = ContractorFormatter.format_person_by_inn(resp_data, cached_at)
        
        from src.bot.keyboards import contractor_result_with_refresh_keyboard
        for i, msg in enumerate(messages):
            if i == len(messages) - 1:
                kb = contractor_result_with_refresh_keyboard(f"inn:refresh:{target_inn}", is_cached=True, show_pdf=True)
            else:
                kb = None
            await message.answer(msg, reply_markup=kb, parse_mode="HTML")
        
        logger.info(f"User {user_id} completed identity setup and checked INN {target_inn}")
        
    except Exception as e:
        logger.error(f"INN check error after identity setup: {e}")
        await message.answer(
            ContractorFormatter.format_error(str(e)),
            reply_markup=contractor_result_keyboard(),
            parse_mode="HTML"
        )


@router.callback_query(F.data.startswith("inn:refresh:"))
async def callback_inn_refresh(callback: CallbackQuery, state: FSMContext):
    """Примусове оновлення даних за ІПН"""
    parts = callback.data.split(":")
    code = parts[2] if len(parts) > 2 else None
    
    if not code:
        await callback.answer("Код не знайдено", show_alert=True)
        return
    
    await callback.answer("🔄 Оновлюю дані з реєстру...", show_alert=False)
    
    # Get user identity for authorization
    from src.storage.models import UserIdentity
    from src.storage.database import get_db
    from sqlalchemy import select
    
    user_id = callback.from_user.id
    user_identity = None
    
    async with get_db() as session:
        result = await session.execute(
            select(UserIdentity).where(UserIdentity.telegram_user_id == user_id)
        )
        user_identity = result.scalar_one_or_none()
    
    try:
        client = OpenDataBotClient()
        
        if user_identity:
            response = await client.get_person_by_inn(
                code, 
                force_refresh=True,
                user_name=user_identity.full_name,
                user_code=user_identity.inn
            )
        else:
            response = await client.get_person_by_inn(code, force_refresh=True)
        
        if not response:
            await callback.answer("Не вдалося отримати дані", show_alert=True)
            return
        
        data = response.get('data')
        
        # Save raw data for PDF
        await state.update_data(
            pdf_data={'person_inn': data}, pdf_code=code, pdf_type='inn'
        )
        
        messages = ContractorFormatter.format_person_by_inn(data, cached_at=None)
        
        from src.bot.keyboards import contractor_result_with_refresh_keyboard
        kb = contractor_result_with_refresh_keyboard(f"inn:refresh:{code}", is_cached=False, show_pdf=True)
        
        await callback.message.edit_text(messages[0], reply_markup=kb, parse_mode="HTML")
        logger.info(f"User {callback.from_user.id} refreshed INN {code}")
        
    except Exception as e:
        logger.error(f"INN refresh error for {code}: {e}")
        await callback.answer(f"Помилка: {str(e)[:50]}", show_alert=True)
