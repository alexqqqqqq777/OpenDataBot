# Спецификация проекта: Мониторинг судебных дел

## Анализ данных Worksection

### Структура проектов (клиенты)
- `LF "LIBERTY WAY"` — основной клиент
- `ТОВ "АПК "НОВААГРО"`, `ТОВ "ПК "НОВА"`, `ТОВ"ТБ "НОВААГРО"` и др.
- `Банкрутство` — отдельный проект для дел о банкротстве
- `ГРУПА "АГРОДАР"`, `Група "СОВТА"`, `НКХП` и др.

### Формат номеров дел в задачах
Номер дела находится в **названии задачи** (`name`), паттерны:
```
922/4626/23 (описание)
904/3388/23 заява на видачу вик. листа
758/5818/13-Ц Омельчук О.В.
922/215/23
```

**Regex для извлечения:**
```regex
(\d{3,4}\/\d+\/\d{2}(?:-[А-Яа-яЦц]+)?)
```

### Ключевые задачи-реестры
- `реєстр судових справ` — общий реестр дел
- `Контроль статусу судових справ` — контроль статусов
- `Моніторинг справ` — мониторинг
- `реєстр виконавчих проваджень` — исполнительные производства

---

## Улучшенный промт для MVP

```
Ты — senior backend engineer/architect. Сгенерируй рабочий MVP программы мониторинга судебных дел в Украине.

## КОНТЕКСТ
Инструмент для адвоката. Цель — оперативно узнавать о новых судебных делах против компаний клиентов (когда компания "атакована" со стороны правоохранителей, госорганов или других лиц).

## ЦЕЛЬ
1. Создать подписки в OpenDataBot на мониторинг судебных дел по списку ЕДРПОУ.
2. Получать уведомления о НОВЫХ делах через endpoint /history.
3. Синхронизировать "ручную базу дел" из Worksection для дедупликации.
4. Определять только НОВЫЕ дела (отсутствующие в Worksection и не отправленные ранее).
5. Отправлять уведомление в Telegram с полными данными по делу.
6. Определять роль компании (истец/ответчик) и уровень угрозы.

## ОГРАНИЧЕНИЯ
- Только API: OpenDataBot (подписки), Worksection (Admin API), Telegram.
- Идемпотентность обязательна — не дублировать уведомления.
- Код готов к запуску: .env конфиг, логирование, ретраи, обработка 429/5xx.
- Хранить состояние в MySQL (основная) с возможностью SQLite для dev.

## CONFIG (.env)
```env
# Мониторинг
EDRPOU_LIST=12345678,87654321,11111111
CHECK_INTERVAL_MINUTES=60
INITIAL_RUN_MODE=index_only  # index_only | notify_all

# API Keys
OPENDATABOT_API_KEY=<будет предоставлен>
WORKSECTION_API_KEY=962f86852377d3b3a64c117b795dc172
WORKSECTION_ACCOUNT=kraiz
TELEGRAM_BOT_TOKEN=<...>
TELEGRAM_CHAT_ID=<...>

# Worksection парсинг
WORKSECTION_CASE_PATTERN=(\d{3,4}\/\d+\/\d{2}(?:-[А-Яа-яЦц]+)?)
WORKSECTION_SOURCE_FIELD=name  # номер дела в названии задачи

# Приоритизация угроз
DANGEROUS_PLAINTIFFS=прокуратура,податкова,поліція,ДБР,НАБУ,СБУ,держгеокадастр
HIGH_PRIORITY_CASE_TYPES=2,5  # 2=уголовные, 5=админправонарушения
```

## ЛОГИКА ДАННЫХ

### 1. Нормализация номера дела
```python
def normalize_case_number(raw: str) -> str:
    # "№ 922/4626/23 " → "922/4626/23"
    # убрать №, пробелы, привести к виду "XXX/YYYY/ZZ"
    cleaned = re.sub(r'[№\s]', '', raw)
    match = re.search(r'(\d{3,4}/\d+/\d{2}(?:-[А-Яа-яЦц]+)?)', cleaned)
    return match.group(1) if match else None
```

### 2. Уникальный ключ дела
```
PRIMARY: opendatabot_case_id (если есть)
FALLBACK: normalized_case_number + court_code
```

### 3. OpenDataBot Flow
```
1. POST /subscriptions — создать подписки:
   - type=new-court-defendant (компания — ответчик) ← ПРИОРИТЕТ
   - type=new-court-plaintiff (компания — истец)
   - subscriptionKey=EDRPOU
   
2. GET /history — получить новые события:
   - type=new_court_defendant,new_court_plaintiff
   - from_id=last_processed_id (для инкрементальности)
   
3. GET /court-status?case_number=XXX — детали дела
```

### 4. Worksection Sync
```
1. GET /api/admin/v2/?action=get_all_tasks&extra=text
2. Извлечь номера дел из task.name по WORKSECTION_CASE_PATTERN
3. Сохранить в worksection_cases(normalized_case_number, task_id, project_id, raw_name)
4. Запускать sync каждые N часов или по webhook
```

### 5. Определение "нового дела"
```python
def is_new_case(case) -> bool:
    norm = normalize_case_number(case.number)
    
    # Уже есть в Worksection?
    if db.worksection_cases.exists(normalized_case_number=norm):
        return False
    
    # Уже уведомляли?
    if db.notifications_sent.exists(case_key=case.unique_key):
        return False
    
    return True
```

### 6. Определение уровня угрозы
```python
def get_threat_level(case) -> str:
    # CRITICAL: уголовное дело + компания ответчик
    if case.judgment_type == 2 and case.company_role == 'defendant':
        return 'CRITICAL'
    
    # HIGH: компания ответчик + опасный истец
    if case.company_role == 'defendant':
        for pattern in DANGEROUS_PLAINTIFFS:
            if pattern in case.plaintiff.lower():
                return 'HIGH'
        return 'MEDIUM'
    
    # LOW: компания истец (контролируемая ситуация)
    return 'LOW'
```

## СХЕМА БД (MySQL)

```sql
-- Подписки OpenDataBot
CREATE TABLE opendatabot_subscriptions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    subscription_id VARCHAR(50) UNIQUE NOT NULL,
    edrpou VARCHAR(10) NOT NULL,
    subscription_type VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

-- Дела из Worksection (для дедупликации)
CREATE TABLE worksection_cases (
    id INT AUTO_INCREMENT PRIMARY KEY,
    normalized_case_number VARCHAR(50) NOT NULL,
    raw_name TEXT,
    task_id VARCHAR(20) NOT NULL,
    project_id VARCHAR(20),
    project_name VARCHAR(255),
    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY (normalized_case_number, task_id)
);

-- Кэш дел OpenDataBot
CREATE TABLE opendatabot_cases (
    id INT AUTO_INCREMENT PRIMARY KEY,
    case_id VARCHAR(100),
    normalized_case_number VARCHAR(50) NOT NULL,
    court_code VARCHAR(20),
    court_name VARCHAR(255),
    case_type INT,
    company_role ENUM('plaintiff', 'defendant', 'third_party'),
    plaintiff TEXT,
    defendant TEXT,
    subject TEXT,
    claim_amount DECIMAL(15,2),
    date_opened DATE,
    stage VARCHAR(100),
    judge VARCHAR(255),
    source_link VARCHAR(500),
    edrpou_matches JSON,  -- ["12345678", "87654321"]
    raw_data JSON,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY (case_id),
    INDEX (normalized_case_number)
);

-- Отправленные уведомления
CREATE TABLE notifications_sent (
    id INT AUTO_INCREMENT PRIMARY KEY,
    case_key VARCHAR(100) NOT NULL UNIQUE,
    normalized_case_number VARCHAR(50),
    threat_level ENUM('CRITICAL', 'HIGH', 'MEDIUM', 'LOW'),
    telegram_message_id VARCHAR(50),
    payload_hash VARCHAR(64),
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Состояние синхронизации
CREATE TABLE sync_state (
    id INT AUTO_INCREMENT PRIMARY KEY,
    key_name VARCHAR(50) UNIQUE NOT NULL,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- Инициализация sync_state
INSERT INTO sync_state (key_name, value) VALUES
('opendatabot_last_notification_id', '0'),
('worksection_last_sync', '1970-01-01 00:00:00'),
('initial_run_completed', 'false');
```

## АРХИТЕКТУРА МОДУЛЕЙ

```
src/
├── config/
│   └── settings.py          # Pydantic Settings из .env
├── clients/
│   ├── opendatabot.py       # OpenDataBot API client
│   ├── worksection.py       # Worksection Admin API client
│   └── telegram.py          # Telegram Bot client
├── storage/
│   ├── database.py          # SQLAlchemy setup
│   ├── models.py            # ORM models
│   └── repository.py        # CRUD operations
├── services/
│   ├── subscription_manager.py   # Управление подписками OpenDataBot
│   ├── worksection_sync.py       # Синхронизация Worksection
│   ├── case_processor.py         # Обработка новых дел
│   ├── threat_analyzer.py        # Анализ уровня угрозы
│   └── notifier.py               # Отправка в Telegram
├── utils/
│   ├── case_normalizer.py   # Нормализация номеров дел
│   └── retry.py             # Retry decorator
├── main.py                  # Entry point + scheduler
└── test_connections.py      # Тест доступов
```

## TELEGRAM СООБЩЕНИЕ

```
🚨 CRITICAL: Новое уголовное дело!

📋 Дело: 922/4626/23
⚖️ Суд: Господарський суд Харківської області
👨‍⚖️ Суддя: Трофімов С.В.

📌 Компания: ТОВ "АГРОФІРМА "ТЗК"
🎯 Роль: ОТВЕТЧИК

👤 Истец: ГУ Держгеокадастру у Харківській області
📝 Предмет: Про витребування з чужого незаконного володіння

💰 Сумма иска: 1,500,000 грн
📅 Дата открытия: 2023-11-13
📊 Стадия: Розгляд справи

🔗 Источник: https://reyestr.court.gov.ua/...

ЕДРПОУ совпадения: 12345678
⏰ Обнаружено: 2026-01-31 15:00
```

## ПЕРВЫЙ ЗАПУСК (TEST MODE)

```python
# test_connections.py
async def test_all():
    # 1. Тест Worksection
    ws = WorksectionClient()
    projects = await ws.get_projects()
    print(f"✅ Worksection: {len(projects)} проектов")
    
    # 2. Тест OpenDataBot (когда будет ключ)
    odb = OpenDataBotClient()
    # Создать тестовую подписку
    sub = await odb.create_subscription(
        type='new-court-defendant',
        subscription_key='TEST_EDRPOU'
    )
    print(f"✅ OpenDataBot: подписка {sub.id}")
    
    # 3. Тест Telegram
    tg = TelegramClient()
    await tg.send_message("🔧 Тест подключения успешен!")
    print("✅ Telegram: сообщение отправлено")
    
    # 4. Тест БД
    db.sync_state.set('test_key', 'test_value')
    print("✅ Database: запись/чтение работает")
```

## DOCKER

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY src/ ./src/
COPY .env .

CMD ["python", "-m", "src.main"]
```

```yaml
# docker-compose.yml
version: '3.8'
services:
  app:
    build: .
    env_file: .env
    depends_on:
      - db
    restart: unless-stopped
    
  db:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: ${DB_PASSWORD}
      MYSQL_DATABASE: court_monitor
    volumes:
      - mysql_data:/var/lib/mysql
    
volumes:
  mysql_data:
```
```

## ЧТО НУЖНО ДЛЯ ЗАПУСКА

1. ✅ Worksection API Key: `962f86852377d3b3a64c117b795dc172`
2. ⏳ OpenDataBot API Key: ждём
3. ⏳ Telegram Bot Token + Chat ID
4. ⏳ Список ЕДРПОУ для мониторинга
5. ⏳ MySQL сервер (или Docker)
