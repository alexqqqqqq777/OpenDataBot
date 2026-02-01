from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from src.storage import (
    AsyncSessionLocal, CompanyRepository, NotificationRepository,
    WorksectionCaseRepository, CourtCaseRepository, UserSubscriptionRepository
)
from src.utils import validate_edrpou, format_edrpou
from src.clients import OpenDataBotClient, WorksectionClient
from src.bot.keyboards import (
    main_menu_keyboard, companies_menu_keyboard, cases_menu_keyboard,
    stats_keyboard, settings_keyboard, sync_keyboard,
    company_actions_keyboard, confirm_delete_keyboard, back_to_main_keyboard,
    cancel_keyboard, pagination_keyboard, threat_level_filter_keyboard,
    my_subs_keyboard
)
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
            existing_subs = await odb.get_subscriptions(subscription_key=edrpou)
            if not existing_subs:
                await odb.create_subscription(
                    subscription_type='company',
                    subscription_key=edrpou
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
            existing_subs = await odb.get_subscriptions(subscription_key=edrpou)
            if not existing_subs:
                await odb.create_subscription(subscription_type='company', subscription_key=edrpou)
        except:
            odb_status = "❌"
        
        await message.answer(
            f"✅ Компанію <code>{edrpou}</code> додано!\n├ OpenDataBot: {odb_status}\n└ 🔔 Сповіщення: увімкнено",
            reply_markup=back_to_main_keyboard(),
            parse_mode="HTML"
        )


@router.callback_query(F.data == "company:list")
async def callback_company_list(callback: CallbackQuery):
    """Список компаній"""
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
        
        odb_count = len(subs)
        local_count = len(local_companies)
        my_count = len(my_subs)
        
        text = f"""📡 <b>Статус сервісу</b>

<b>OpenDataBot API</b>
├ Всього підписок: <b>{odb_count}</b>
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
    await callback.message.edit_text(
        "⚙️ <b>Налаштування</b>\n\n"
        "Керуйте параметрами системи.",
        reply_markup=settings_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


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
    from src.services.worksection_sync import sync_worksection_cases
    
    await callback.message.edit_text("🔄 Синхронізую Worksection...", parse_mode="HTML")
    
    try:
        count = await sync_worksection_cases()
        await callback.message.edit_text(
            f"✅ <b>Worksection синхронізовано!</b>\n\n"
            f"📁 Оброблено справ: {count}",
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
        notifications = await run_monitoring_cycle()
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
        
        notifications = await run_monitoring_cycle()
        
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
    """Список компаній"""
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
