# LWData Bot — Моніторинг контрагентів та судових справ

Telegram-бот (`@LWData_bot`) для автоматичного моніторингу судових справ, перевірки контрагентів і генерації PDF-звітів. Інтегрується з **OpenDataBot**, **Clarity Project** та **Worksection**.

---

## Функціональність

- **Моніторинг судових справ** — автоматична перевірка нових судових рішень для списку компаній (по ЄДРПОУ). Повідомлення в Telegram з оцінкою загрози.
- **Перевірка контрагентів** — пошук компаній та ФОП за ЄДРПОУ/ІПН/назвою. Детальна інформація: реєстр, засновники, бенефіціари, санкції, суди, податки.
- **PDF-звіт** — генерація повного звіту з усіх джерел (OpenDataBot + Clarity): реєстраційні дані, фактори ризику, фінансова звітність, автотранспорт, казначейство.
- **Deep Check** — фонова перевірка всіх пов'язаних компаній (засновники, правонаступники) з кешуванням.
- **Синхронізація з Worksection** — дедуплікація відомих судових справ через GitHub Gist.

---

## Системні вимоги

| Параметр | Мінімум | Рекомендовано |
|----------|---------|---------------|
| **CPU** | 1 vCPU | 2 vCPU |
| **RAM** | 1 GB | 2 GB |
| **Диск** | 10 GB SSD | 20 GB SSD |
| **ОС** | Ubuntu 22.04+ / Debian 11+ | Ubuntu 24.04 LTS |
| **Python** | 3.11+ | 3.12–3.13 |

### Реальне споживання (36 компаній на моніторингу)

| Ресурс | Використання |
|--------|--------------|
| RAM процесу | ~180 MB |
| CPU | < 1% (idle), до 5% при перевірках |
| База даних (SQLite) | ~2 MB |
| Кеш API відповідей | ~50 MB (залежить від кількості перевірок) |
| Virtual env | ~100 MB |
| Шрифти (DejaVuSans) | ~1.5 MB |

### Мережеві вимоги

| Сервіс | URL | Порт |
|--------|-----|------|
| Telegram API | api.telegram.org | 443 (HTTPS) |
| OpenDataBot API | opendatabot.com | 443 (HTTPS) |
| Clarity Project API | clarity-project.info | 443 (HTTPS) |
| GitHub Gist (WS sync) | gist.githubusercontent.com | 443 (HTTPS) |

**Firewall:** Потрібен лише вихідний HTTPS (порт 443). Вхідні порти не потрібні.

---

## Структура проекту

```
OpenDataBot/
├── run.py                          # Точка входу
├── requirements.txt                # Python залежності
├── .env                            # Конфігурація (НЕ в git)
├── .env.example                    # Шаблон конфігурації
├── court_monitor.db                # SQLite БД (створюється автоматично)
├── api_v3_spec.json                # OpenAPI spec OpenDataBot (для довідки)
│
├── src/
│   ├── main.py                     # Ініціалізація бота, планувальник
│   ├── config/
│   │   └── settings.py             # Pydantic Settings (всі env-змінні)
│   ├── bot/
│   │   ├── handlers.py             # Обробники Telegram команд
│   │   └── __init__.py             # Router
│   ├── clients/
│   │   ├── opendatabot.py          # HTTP клієнт OpenDataBot API v3
│   │   ├── clarity.py              # HTTP клієнт Clarity Project API
│   │   ├── worksection.py          # HTTP клієнт Worksection API
│   │   └── gist_client.py          # GitHub Gist клієнт (WS sync)
│   ├── services/
│   │   ├── monitoring.py           # Моніторинг судових справ (scheduler)
│   │   ├── notifier.py             # Відправка Telegram повідомлень
│   │   ├── pdf_generator.py        # Генерація PDF-звітів (fpdf2)
│   │   ├── clarity_adapter.py      # Clarity → PDF format adapter
│   │   ├── contractor_formatter.py # Форматування даних для Telegram
│   │   ├── deep_check.py           # Фонова перевірка пов'язаних компаній
│   │   ├── threat_analyzer.py      # Оцінка загрози судових справ
│   │   ├── worksection_sync.py     # Синхронізація з Worksection
│   │   └── fonts/                  # DejaVuSans шрифти для PDF
│   ├── storage/
│   │   ├── database.py             # SQLAlchemy async engine
│   │   ├── models.py               # ORM моделі (компанії, підписки, кеш)
│   │   └── repository.py           # Репозиторії (CRUD)
│   └── utils/                      # Утиліти (нормалізація номерів справ)
│
├── docs/                           # Документація API
├── logs/                           # Логи (створюються автоматично, з ротацією)
└── tests/                          # Тестові дані та кеші
```

---

## Встановлення на сервері

### 1. Системні залежності

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git
```

### 2. Клонування репозиторію

```bash
cd /home/ubuntu
git clone https://github.com/alexqqqqqq777/OpenDataBot.git
cd OpenDataBot
```

### 3. Створення virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Конфігурація (.env)

```bash
cp .env.example .env
chmod 600 .env
nano .env   # заповнити всі ключі (див. розділ "Змінні середовища")
```

### 5. Тест запуску

```bash
source venv/bin/activate
python3 run.py
# Ctrl+C для зупинки після перевірки що бот стартує
```

### 6. Systemd сервіс

Створити файл `/etc/systemd/system/opendatabot.service`:

```ini
[Unit]
Description=OpenDataBot Telegram Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/OpenDataBot
Environment=PATH=/home/ubuntu/OpenDataBot/venv/bin
Environment=PYTHONUNBUFFERED=1
ExecStart=/home/ubuntu/OpenDataBot/venv/bin/python3 run.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable opendatabot
sudo systemctl start opendatabot
sudo systemctl status opendatabot
```

---

## Змінні середовища (.env)

### Обов'язкові

| Змінна | Опис | Приклад | Де отримати |
|--------|------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | Токен Telegram бота | `123456789:AABBcc...` | [@BotFather](https://t.me/BotFather) |
| `OPENDATABOT_API_KEY` | Ключ API OpenDataBot (моніторинг, підписки) | `abc123...` | [opendatabot.ua/api](https://opendatabot.ua/my/api) |
| `OPENDATABOT_FULL_API_KEY` | Ключ API OpenDataBot (повна перевірка компаній) | `xyz789...` | Той самий кабінет, може бути окремий тариф |
| `CLARITY_API_KEY` | Ключ API Clarity Project | `clr_...` | [clarity-project.info/info/api](https://clarity-project.info/info/api/) |

### Опціональні

| Змінна | Опис | За замовч. |
|--------|------|-----------|
| `DATABASE_URL` | Рядок підключення до БД | `sqlite:///./court_monitor.db` |
| `OPENDATABOT_BASE_URL` | Base URL OpenDataBot API | `https://opendatabot.com/api/v3` |
| `CLARITY_BASE_URL` | Base URL Clarity API | `https://clarity-project.info/api` |
| `TELEGRAM_ADMIN_IDS` | Telegram user ID адмінів (через кому) | _(порожньо)_ |
| `WORKSECTION_GIST_ID` | GitHub Gist ID для синхронізації справ з Worksection | _(порожньо)_ |
| `OPENDATABOT_CHECK_HOURS` | Години перевірки моніторингу (UTC) | `8,20` |
| `WORKSECTION_SYNC_HOURS` | Години синхронізації WS (UTC) | `7,19` |
| `INITIAL_RUN_MODE` | Режим першого запуску | `index_only` |
| `DANGEROUS_PLAINTIFFS` | Ключові слова небезпечних позивачів | `прокуратура,податкова,...` |
| `HIGH_PRIORITY_CASE_TYPES` | Типи справ з високим пріоритетом | `2,5` |
| `WORKSECTION_CASE_PATTERN` | Regex для номерів справ | `(\d{3,4}/\d+/\d{2}...)` |

### API ключі — тарифи та можливості

| Сервіс | Що дає | Вартість |
|--------|--------|----------|
| **OpenDataBot (monitor)** | Підписки на компанії, історія подій, судові рішення | Від 990 грн/міс |
| **OpenDataBot (full)** | Повна інформація компанія/ФОП, бенефіціари, санкції | Від 990 грн/міс |
| **Clarity Project** | ЄДР дані, засновники, фінзвітність, авто, казначейство, зв'язки | Від 500 грн/міс |

> **Примітка:** `OPENDATABOT_API_KEY` та `OPENDATABOT_FULL_API_KEY` можуть бути однаковими, якщо один тарифний план покриває обидва типи запитів.

---

## Міграція з існуючого сервера

### 1. Бекап на старому сервері

```bash
# На старому сервері
sudo systemctl stop opendatabot
cp /home/ubuntu/OpenDataBot/court_monitor.db ~/court_monitor_backup.db
cp /home/ubuntu/OpenDataBot/.env ~/env_backup
```

### 2. Перенесення файлів

```bash
# З локальної машини
scp -i ~/.ssh/your_key ubuntu@OLD_SERVER:/home/ubuntu/court_monitor_backup.db ./
scp -i ~/.ssh/your_key ubuntu@OLD_SERVER:/home/ubuntu/env_backup ./

scp -i ~/.ssh/your_key ./court_monitor_backup.db ubuntu@NEW_SERVER:/home/ubuntu/OpenDataBot/court_monitor.db
scp -i ~/.ssh/your_key ./env_backup ubuntu@NEW_SERVER:/home/ubuntu/OpenDataBot/.env
```

### 3. На новому сервері

```bash
cd /home/ubuntu/OpenDataBot
chmod 600 .env
sudo systemctl start opendatabot
sudo journalctl -u opendatabot -f   # перевірити логи
```

### Що зберігається в БД (court_monitor.db)

| Таблиця | Опис |
|---------|------|
| `monitored_companies` | Список компаній на моніторингу (ЄДРПОУ, назва) |
| `opendatabot_subscriptions` | Підписки ODB (subscription_id → edrpou) |
| `worksection_cases` | Номери справ з Worksection (дедуплікація) |
| `court_cases` | Знайдені судові справи |
| `notifications_sent` | Історія відправлених повідомлень |
| `sync_state` | Стан синхронізації (last_notification_id і т.д.) |
| `user_subscriptions` | Підписки користувачів на компанії |
| `user_settings` | Налаштування користувачів |
| `case_subscriptions` | Підписки на конкретні справи |
| `api_response_cache` | Кеш відповідей API (ODB + Clarity) |
| `user_identities` | Зв'язок Telegram → контакт |

---

## Обслуговування

### Перевірка статусу
```bash
sudo systemctl status opendatabot
```

### Логи
```bash
# Системний журнал (останні 50 записів)
sudo journalctl -u opendatabot --no-pager -n 50

# Логи ODB API (з ротацією, макс 10MB × 5)
tail -f /home/ubuntu/OpenDataBot/logs/opendatabot_history.log
```

### Оновлення коду
```bash
cd /home/ubuntu/OpenDataBot
git fetch origin main && git reset --hard origin/main
sudo systemctl restart opendatabot
```

### Бекап
```bash
mkdir -p ~/backups
cp /home/ubuntu/OpenDataBot/court_monitor.db ~/backups/court_monitor_$(date +%Y%m%d).db
```

### Перевірка диску
```bash
df -h /
du -sh /home/ubuntu/OpenDataBot/
```

---

## Розклад автоматичних задач (UTC)

| Час (UTC) | Задача |
|-----------|--------|
| 07:00, 19:00 | Синхронізація справ з Worksection (через Gist) |
| 08:00, 20:00 | Перевірка нових судових подій через OpenDataBot |

---

## Масштабування

| Кількість компаній | RAM | Диск | БД |
|--------------------|-----|------|----|
| 1–50 | 1 GB | 10 GB | SQLite |
| 50–200 | 2 GB | 20 GB | SQLite |
| 200–500 | 2 GB | 30 GB | SQLite / PostgreSQL |
| 500+ | 4 GB+ | 50 GB+ | PostgreSQL |

---

## Документація

- [Моніторинг судових справ — OpenDataBot API](docs/COURT_MONITORING_API.md)
- [Worksection API інтеграція](docs/WORKSECTION_API.md)
- [Clarity Project API](docs/clarity_api.md)
- [Gist-based синхронізація](docs/GIST_SETUP.md)
- [Системні вимоги (детально)](docs/SERVER_REQUIREMENTS.md)

---

*Версія: 2.0 | Оновлено: 16.02.2026*
