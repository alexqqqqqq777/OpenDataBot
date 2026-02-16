from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from typing import List, Optional


def my_subs_keyboard(page: int = 0, total_pages: int = 1, subs_on_page: list = None) -> InlineKeyboardMarkup:
    """Клавіатура для списку підписок з кнопками відписки та пагінацією"""
    builder = InlineKeyboardBuilder()
    
    # Кнопки відписки для кожної компанії на сторінці
    if subs_on_page:
        for sub in subs_on_page:
            builder.row(
                InlineKeyboardButton(
                    text=f"❌ {sub.edrpou}",
                    callback_data=f"unsub:company:{sub.edrpou}"
                )
            )
    
    # Pagination buttons
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"mysubs:page:{page-1}"))
    if total_pages > 1:
        nav_buttons.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="mysubs:info"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"mysubs:page:{page+1}"))
    
    if nav_buttons:
        builder.row(*nav_buttons)
    
    builder.row(InlineKeyboardButton(text="🔙 Меню компаній", callback_data="menu:companies"))
    
    return builder.as_markup()


def main_menu_keyboard(is_admin: bool = False) -> InlineKeyboardMarkup:
    """Головне меню бота"""
    builder = InlineKeyboardBuilder()
    
    # Основні функції - великі кнопки
    builder.row(
        InlineKeyboardButton(text="🔍 Перевірка контрагента", callback_data="menu:contractor")
    )
    builder.row(
        InlineKeyboardButton(text="🏢 Компанії", callback_data="menu:companies"),
        InlineKeyboardButton(text="⚖️ Справи", callback_data="menu:cases")
    )
    # Додаткові функції
    builder.row(
        InlineKeyboardButton(text="📊 Статистика", callback_data="menu:stats"),
        InlineKeyboardButton(text="⚙️ Налаштування", callback_data="menu:settings")
    )
    if is_admin:
        builder.row(
            InlineKeyboardButton(text="🔄 Синхронізація", callback_data="menu:sync"),
            InlineKeyboardButton(text="ℹ️ Допомога", callback_data="menu:help")
        )
    else:
        builder.row(
            InlineKeyboardButton(text="ℹ️ Допомога", callback_data="menu:help")
        )
    
    return builder.as_markup()


def companies_menu_keyboard(is_admin: bool = False) -> InlineKeyboardMarkup:
    """Меню управління компаніями"""
    builder = InlineKeyboardBuilder()
    
    if is_admin:
        builder.row(
            InlineKeyboardButton(text="➕ Додати компанію", callback_data="company:add"),
            InlineKeyboardButton(text="🔔 Мої підписки", callback_data="company:my_subs")
        )
        builder.row(
            InlineKeyboardButton(text="🌐 Всі компанії", callback_data="company:list"),
            InlineKeyboardButton(text="📡 Статус сервісу", callback_data="company:odb_status")
        )
    else:
        builder.row(
            InlineKeyboardButton(text="🔔 Мої підписки", callback_data="company:my_subs")
        )
        builder.row(
            InlineKeyboardButton(text="➕ Підписатися на компанію", callback_data="company:user_subscribe")
        )
    
    builder.row(
        InlineKeyboardButton(text="🔙 Головне меню", callback_data="menu:main")
    )
    
    return builder.as_markup()


def cases_menu_keyboard() -> InlineKeyboardMarkup:
    """Меню судових справ"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="🚨 Критичні справи", callback_data="cases:critical"),
        InlineKeyboardButton(text="⚠️ Нові справи", callback_data="cases:new")
    )
    builder.row(
        InlineKeyboardButton(text="📋 Всі справи", callback_data="cases:all")
    )
    builder.row(
        InlineKeyboardButton(text="📌 Мої справи (моніторинг)", callback_data="cases:my_monitored")
    )
    builder.row(
        InlineKeyboardButton(text="➕ Додати справу", callback_data="cases:add_case")
    )
    builder.row(
        InlineKeyboardButton(text="🔙 Головне меню", callback_data="menu:main")
    )
    
    return builder.as_markup()


def my_cases_keyboard(page: int = 0, total_pages: int = 1, cases: list = None) -> InlineKeyboardMarkup:
    """Клавіатура для списку моніторингу справ з кнопками видалення"""
    builder = InlineKeyboardBuilder()
    
    # Кнопки видалення для кожної справи на сторінці
    if cases:
        for c in cases:
            short_num = c.case_number[-12:] if len(c.case_number) > 12 else c.case_number
            builder.row(
                InlineKeyboardButton(
                    text=f"❌ {short_num}", 
                    callback_data=f"case:unsub:{c.case_number}"
                )
            )
    
    # Пагінація
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"mycases:page:{page-1}"))
    if total_pages > 1:
        nav_buttons.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="mycases:info"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"mycases:page:{page+1}"))
    
    if nav_buttons:
        builder.row(*nav_buttons)
    
    builder.row(InlineKeyboardButton(text="➕ Додати справу", callback_data="cases:add_case"))
    builder.row(InlineKeyboardButton(text="🔙 Меню справ", callback_data="menu:cases"))
    
    return builder.as_markup()


def contractor_menu_keyboard() -> InlineKeyboardMarkup:
    """Меню перевірки контрагента - тільки назад"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="� Назад", callback_data="menu:main")
    )
    
    return builder.as_markup()


def contractor_result_keyboard(show_pdf: bool = False) -> InlineKeyboardMarkup:
    """Клавіатура після результату перевірки"""
    builder = InlineKeyboardBuilder()
    
    if show_pdf:
        builder.row(
            InlineKeyboardButton(text="📄 PDF звіт", callback_data="pdf:report")
        )
    builder.row(
        InlineKeyboardButton(text="🔍 Нова перевірка", callback_data="menu:contractor")
    )
    builder.row(
        InlineKeyboardButton(text="🔙 Головне меню", callback_data="menu:main")
    )
    
    return builder.as_markup()


def contractor_result_with_refresh_keyboard(refresh_callback: str, is_cached: bool = False, show_pdf: bool = False) -> InlineKeyboardMarkup:
    """Клавіатура з кнопкою оновлення для результату перевірки"""
    builder = InlineKeyboardBuilder()
    
    if show_pdf:
        builder.row(
            InlineKeyboardButton(text="📄 PDF звіт", callback_data="pdf:report")
        )
    if is_cached:
        builder.row(
            InlineKeyboardButton(text="🔄 Оновити дані", callback_data=refresh_callback)
        )
    
    builder.row(
        InlineKeyboardButton(text="🔍 Нова перевірка", callback_data="menu:contractor")
    )
    builder.row(
        InlineKeyboardButton(text="🔙 Головне меню", callback_data="menu:main")
    )
    
    return builder.as_markup()


def stats_keyboard() -> InlineKeyboardMarkup:
    """Меню статистики"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="📈 Загальна статистика", callback_data="stats:general")
    )
    builder.row(
        InlineKeyboardButton(text="🔙 Головне меню", callback_data="menu:main")
    )
    
    return builder.as_markup()


def settings_keyboard(receive_all: bool = False) -> InlineKeyboardMarkup:
    """Меню налаштувань"""
    builder = InlineKeyboardBuilder()
    
    # Toggle for receive all notifications
    if receive_all:
        toggle_text = "🔔 Всі сповіщення: ✅ УВІМК"
        toggle_data = "settings:toggle_all:off"
    else:
        toggle_text = "🔕 Всі сповіщення: ❌ ВИМК"
        toggle_data = "settings:toggle_all:on"
    
    builder.row(
        InlineKeyboardButton(text=toggle_text, callback_data=toggle_data)
    )
    builder.row(
        InlineKeyboardButton(text="⏰ Розклад", callback_data="settings:schedule"),
        InlineKeyboardButton(text="🔑 API статус", callback_data="settings:api_status")
    )
    builder.row(
        InlineKeyboardButton(text="🔙 Головне меню", callback_data="menu:main")
    )
    
    return builder.as_markup()


def sync_keyboard() -> InlineKeyboardMarkup:
    """Меню синхронізації"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="🔄 Worksection", callback_data="sync:worksection"),
        InlineKeyboardButton(text="🔄 OpenDataBot", callback_data="sync:opendatabot")
    )
    builder.row(
        InlineKeyboardButton(text="🔄 Повна синхронізація", callback_data="sync:full")
    )
    builder.row(
        InlineKeyboardButton(text="🔙 Головне меню", callback_data="menu:main")
    )
    
    return builder.as_markup()


def company_actions_keyboard(edrpou: str, is_active: bool = True) -> InlineKeyboardMarkup:
    """Дії з компанією"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="📋 Справи компанії", callback_data=f"company:cases:{edrpou}"),
        InlineKeyboardButton(text="ℹ️ Інформація", callback_data=f"company:info:{edrpou}")
    )
    
    if is_active:
        builder.row(
            InlineKeyboardButton(text="⏸️ Призупинити", callback_data=f"company:pause:{edrpou}")
        )
    else:
        builder.row(
            InlineKeyboardButton(text="▶️ Відновити", callback_data=f"company:resume:{edrpou}")
        )
    
    builder.row(
        InlineKeyboardButton(text="🗑️ Видалити", callback_data=f"company:delete:{edrpou}")
    )
    builder.row(
        InlineKeyboardButton(text="🔙 До списку", callback_data="company:list")
    )
    
    return builder.as_markup()


def case_actions_keyboard(case_id: str) -> InlineKeyboardMarkup:
    """Дії зі справою"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="📄 Детальніше", callback_data=f"case:details:{case_id}"),
        InlineKeyboardButton(text="🔗 Джерело", callback_data=f"case:source:{case_id}")
    )
    builder.row(
        InlineKeyboardButton(text="📝 Додати в Worksection", callback_data=f"case:to_ws:{case_id}"),
        InlineKeyboardButton(text="✅ Позначити оброблено", callback_data=f"case:processed:{case_id}")
    )
    builder.row(
        InlineKeyboardButton(text="🔙 До списку", callback_data="cases:all")
    )
    
    return builder.as_markup()


def confirm_delete_keyboard(edrpou: str) -> InlineKeyboardMarkup:
    """Підтвердження видалення"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="✅ Так, видалити", callback_data=f"confirm:delete:{edrpou}"),
        InlineKeyboardButton(text="❌ Скасувати", callback_data=f"company:view:{edrpou}")
    )
    
    return builder.as_markup()


def confirm_unsub_keyboard(edrpou: str) -> InlineKeyboardMarkup:
    """Підтвердження відписки"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="✅ Так, відписатися", callback_data=f"confirm:unsub:{edrpou}"),
        InlineKeyboardButton(text="❌ Скасувати", callback_data="company:my_subs")
    )
    
    return builder.as_markup()


def pagination_keyboard(
    current_page: int, 
    total_pages: int, 
    callback_prefix: str
) -> InlineKeyboardMarkup:
    """Пагінація"""
    builder = InlineKeyboardBuilder()
    
    buttons = []
    
    if current_page > 1:
        buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"{callback_prefix}:{current_page-1}"))
    
    buttons.append(InlineKeyboardButton(text=f"{current_page}/{total_pages}", callback_data="noop"))
    
    if current_page < total_pages:
        buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"{callback_prefix}:{current_page+1}"))
    
    builder.row(*buttons)
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="menu:main"))
    
    return builder.as_markup()


def back_to_main_keyboard() -> InlineKeyboardMarkup:
    """Кнопка повернення до головного меню"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 Головне меню", callback_data="menu:main"))
    return builder.as_markup()


def cancel_keyboard() -> InlineKeyboardMarkup:
    """Кнопка скасування"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Скасувати", callback_data="cancel"))
    return builder.as_markup()


def threat_level_filter_keyboard() -> InlineKeyboardMarkup:
    """Фільтр за рівнем загрози"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="🚨 Критичні", callback_data="filter:threat:CRITICAL"),
        InlineKeyboardButton(text="⚠️ Високі", callback_data="filter:threat:HIGH")
    )
    builder.row(
        InlineKeyboardButton(text="📋 Середні", callback_data="filter:threat:MEDIUM"),
        InlineKeyboardButton(text="ℹ️ Низькі", callback_data="filter:threat:LOW")
    )
    builder.row(
        InlineKeyboardButton(text="📊 Всі рівні", callback_data="filter:threat:ALL")
    )
    builder.row(
        InlineKeyboardButton(text="🔙 Назад", callback_data="menu:cases")
    )
    
    return builder.as_markup()
