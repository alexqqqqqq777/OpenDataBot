# OpenDataBot API v3 - Мониторинг судебных дел

## Базовый URL
```
https://opendatabot.com/api/v3
```

## Аутентификация
Все запросы требуют параметр `apiKey` в query string.

---

## Эндпоинты мониторинга судебных дел

### 1. Получение статусов судебных дел

**GET** `/court-status`

Получение статусов судебных дел с возможностью фильтрации.

| Параметр | Тип | Обязательный | Описание |
|----------|-----|--------------|----------|
| `apiKey` | string | ✅ | API ключ |
| `case_number` | string | ❌ | Поиск по номеру дела |
| `text_involved` | string | ❌ | Поиск по стороне дела |
| `date_from` | string | ❌ | Фильтр по дате события (формат YYYY-MM-DD) |
| `date_to` | string | ❌ | Фильтр по дате события (формат YYYY-MM-DD) |
| `limit` | integer | ❌ | Количество записей |
| `offset` | integer | ❌ | Смещение |
| `order` | string | ❌ | Порядок сортировки (ASC/DESC) |

---

### 2. Создание подписки на мониторинг

**POST** `/subscriptions`

Создание подписки на мониторинг изменений.

| Параметр | Тип | Обязательный | Описание |
|----------|-----|--------------|----------|
| `apiKey` | string | ✅ | API ключ |
| `type` | string | ✅ | Тип подписки (см. ниже) |
| `subscriptionKey` | string | ✅ | Ключевой запрос подписки |
| `secondSide` | string | ❌ | Вторая сторона (для involved2sides) |
| `courtId` | string | ❌ | Код суда |
| `role` | string | ❌ | Роль субъекта |

#### Типы подписок для судебных дел:

| Тип | Описание |
|-----|----------|
| `court-by-text` | Новые судебные документы с текстом |
| `court-by-number` | Новые судебные документы по номеру дела |
| `court-by-json` | Новые судебные документы по JSON запросу |
| `court-by-involved` | Изменения по судебным заседаниям за стороной |
| `involved2sides` | Изменения по судебным заседаниям за 2-мя сторонами |
| `new-court-defendant` | Новые судебные дела в качестве ответчика |
| `new-court-plaintiff` | Новые судебные дела в качестве истца |

#### Параметры для `court-by-json`:

```json
{
  "text": "поисковый запрос",
  "judgment": 1,          // 1-Гражданские, 2-Уголовные, 3-Хозяйственные, 4-Административные, 5-Админправонарушения
  "justice": 1,           // 1-приговор, 2-постановление, 3-решение, 4-судебный приказ, 5-определение
  "adjudication_date_year": 1  // количество последних лет
}
```

---

### 3. Получение списка подписок

**GET** `/subscriptions`

| Параметр | Тип | Обязательный | Описание |
|----------|-----|--------------|----------|
| `apiKey` | string | ✅ | API ключ |
| `type` | string | ❌ | Фильтр по типу подписки |
| `subscriptionKey` | string | ❌ | Фильтр по ключу подписки |

---

### 4. Удаление подписки

**DELETE** `/subscriptions/{subscriptionId}`

| Параметр | Тип | Обязательный | Описание |
|----------|-----|--------------|----------|
| `apiKey` | string | ✅ | API ключ |
| `subscriptionId` | integer | ✅ | ID подписки (в path) |

---

### 5. Добавление комментария к подписке

**POST** `/subscriptions/comment/{subscriptionId}`

| Параметр | Тип | Обязательный | Описание |
|----------|-----|--------------|----------|
| `apiKey` | string | ✅ | API ключ |
| `subscriptionId` | integer | ✅ | ID подписки (в path) |
| `text` | string | ✅ | Текст комментария |

---

### 6. История изменений по подпискам

**GET** `/history`

Получение истории изменений по подпискам.

| Параметр | Тип | Обязательный | Описание |
|----------|-----|--------------|----------|
| `apiKey` | string | ✅ | API ключ |
| `from_id` | string | ❌ | Начальный notification_id |
| `subscription_id` | string | ❌ | Фильтр по ID подписки |
| `offset` | string | ❌ | Смещение |
| `limit` | string | ❌ | Количество записей |
| `date_start` | string | ❌ | Дата начала (формат Y-m-d) |
| `date_end` | string | ❌ | Дата окончания (формат Y-m-d) |
| `type` | string | ❌ | Тип уведомления |
| `debug` | boolean | ❌ | Режим тестирования |

#### Типы уведомлений для судебных дел:
- `court` — судебные решения
- `court_status` — статусы судебных дел
- `new_court_defendant` — новые дела как ответчик
- `new_court_plaintiff` — новые дела как истец
- `involved` — участие в деле
- `involved2sides` — две стороны

---

## Примеры запросов

### Создание подписки на мониторинг по номеру дела

```bash
curl -X POST "https://opendatabot.com/api/v3/subscriptions?apiKey=YOUR_API_KEY&type=court-by-number&subscriptionKey=761/12345/24"
```

### Создание подписки на мониторинг по стороне (ответчик)

```bash
curl -X POST "https://opendatabot.com/api/v3/subscriptions?apiKey=YOUR_API_KEY&type=new-court-defendant&subscriptionKey=12345678"
```

### Получение истории изменений по судебным делам

```bash
curl "https://opendatabot.com/api/v3/history?apiKey=YOUR_API_KEY&type=court&limit=100"
```

### Получение статуса судебного дела

```bash
curl "https://opendatabot.com/api/v3/court-status?apiKey=YOUR_API_KEY&case_number=761/12345/24"
```

---

## Коды ответов

| Код | Описание |
|-----|----------|
| 200 | Успешный запрос |
| 403 | API ключ не указан |
| 500 | Ошибка сервера / слишком много запросов |
| 503 | Сервис недоступен |

---

## Ссылки

- [Документация API](https://docs.opendatabot.com/?urls.primaryName=v3)
- [Судебный реестр](https://court.opendatabot.ua/)
