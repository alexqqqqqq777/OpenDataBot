# Worksection API - Документация

## Обзор

Worksection — система управления проектами и задачами. API позволяет:
- Создавать/редактировать задачи и проекты
- Управлять участниками
- Работать с комментариями, файлами, метками
- Отслеживать время и расходы

---

## Аутентификация

### Два способа авторизации:

| Тип | URL | Права |
|-----|-----|-------|
| **Admin Token** | `https://youraccount.worksection.com/api/admin/v2/` | Максимальные права |
| **OAuth 2.0 Token** | `https://youraccount.worksection.com/api/oauth2` | Ограниченные (по роли) |

---

## OAuth 2.0 Flow

### 1. Начальные настройки

Получить `client_id` и `client_secret` в разделе **Аккаунт > API**

### 2. Авторизация пользователя

Перенаправить пользователя на:
```
https://worksection.com/oauth2/authorize?client_id=<client_id>&redirect_uri=<redirect_uri>&response_type=code
```

### 3. Получение токена доступа

**POST** `https://worksection.com/oauth2/token`

```bash
curl -X POST -d "client_id=<client_id>&client_secret=<client_secret>&grant_type=authorization_code&code=<authorization_code>&redirect_uri=<redirect_uri>" https://worksection.com/oauth2/token
```

**Ответ:**
```json
{
    "token_type": "Bearer",
    "expires_in": 86400,
    "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9...",
    "refresh_token": "def502005534a202e9e8effa05cdbad564015604f34...",
    "account_url": "https://authorizeduseraccount.worksection.com"
}
```

### 4. Использование токена

```bash
curl -X GET -H "Authorization: Bearer <token_value>" \
  "https://youraccount.worksection.com/api/oauth2?action=get_tasks&id_project=193"
```

Или через query параметр:
```
https://youraccount.worksection.com/api/oauth2?action=get_tasks&id_project=193&access_token=<token_value>
```

### 5. Обновление токена

**POST** `https://worksection.com/oauth2/refresh`

```bash
curl -X POST -d "client_id=<client_id>&client_secret=<client_secret>&grant_type=refresh_token&refresh_token=<refresh_token>" https://worksection.com/oauth2/refresh
```

### 6. Информация о пользователе

**POST** `https://worksection.com/oauth2/resource`

```bash
curl -X POST -d "client_id=<client_id>&client_secret=<client_secret>&access_token=<access_token>" https://worksection.com/oauth2/resource
```

**Ответ:**
```json
{
    "id": "11",
    "first_name": "Valdemaar",
    "last_name": "Pupkoff",
    "email": "user@example.com",
    "account_url": "https://authorizeduseraccount.worksection.com"
}
```

---

## Admin API (с hash)

### Формирование запроса

```php
$query_params = 'action=get_tasks&id_project=26';
$api_key = '7776461cd931e7b1c8e9632ff8e979ce';
$hash = md5($query_params . $api_key);
```

**URL:**
```
https://youraccount.worksection.com/api/admin/v2/?action=get_tasks&id_project=26&hash=ec3ab2c28f21b4a07424f8ed688d6644
```

---

## Основные методы API

### Задачи (Tasks)

| Метод | Action | Описание |
|-------|--------|----------|
| GET | `get_all_tasks` | Все задачи аккаунта |
| GET | `get_tasks` | Задачи проекта |
| GET | `get_task` | Отдельная задача |
| POST | `post_task` | Создать задачу |
| POST | `update_task` | Редактировать задачу |
| POST | `complete_task` | Закрыть задачу |
| POST | `reopen_task` | Переоткрыть задачу |
| GET | `search_tasks` | Поиск задач |

### Создание задачи: `post_task`

```
?action=post_task&id_project=PROJECT_ID&title=TASK_NAME
```

| Параметр | Обязательный | Описание |
|----------|--------------|----------|
| `id_project` | ✅ | ID проекта |
| `title` | ✅ | Название задачи |
| `id_parent` | ❌ | ID родительской задачи (для подзадач) |
| `email_user_from` | ❌ | Email автора |
| `email_user_to` | ❌ | Email ответственного (ANY/NOONE) |
| `priority` | ❌ | Приоритет (0..10) |
| `text` | ❌ | Описание задачи |
| `todo[]` | ❌ | Чекбоксы в описании |
| `datestart` | ❌ | Дата старта (DD.MM.YYYY) |
| `dateend` | ❌ | Дата завершения (DD.MM.YYYY) |
| `subscribe` | ❌ | Email подписчиков (через запятую) |
| `hidden` | ❌ | Email для ограничения видимости |
| `max_time` | ❌ | Плановое время |
| `max_money` | ❌ | Плановые расходы |
| `tags` | ❌ | Теги (через запятую) |

**Ответ:**
```json
{
    "status": "ok",
    "data": {
        "id": "TASK_ID",
        "name": "TASK_NAME",
        "page": "/project/PROJECT_ID/TASK_ID/",
        "status": "active",
        "priority": "5",
        "user_from": {
            "id": "USER_ID",
            "email": "USER_EMAIL",
            "name": "USER_NAME"
        },
        "user_to": {
            "id": "USER_ID",
            "email": "USER_EMAIL",
            "name": "USER_NAME"
        },
        "project": {
            "id": "PROJECT_ID",
            "name": "PROJECT_NAME",
            "page": "/project/PROJECT_ID/"
        },
        "text": "TASK_TEXT",
        "date_added": "YYYY-MM-DD HH:II",
        "date_start": "YYYY-MM-DD",
        "date_end": "YYYY-MM-DD"
    }
}
```

### Получение задач: `get_all_tasks`

```
?action=get_all_tasks&filter=active&extra=text,files
```

| Параметр | Описание |
|----------|----------|
| `filter` | `active` — только открытые |
| `extra` | Дополнительные данные: `text`, `files`, `relations`, `subtasks` |

---

## Другие разделы API

| Раздел | Документация |
|--------|--------------|
| Участники | `/faq/api-user.html` |
| Проекты | `/faq/api-projects.html` |
| Комментарии | `/faq/api-comments.html` |
| Метки | `/faq/api-tags.html` |
| Расходы | `/faq/api-costs.html` |
| Таймеры | `/faq/api-timers.html` |
| Файлы | `/faq/api-files.html` |
| Вебхуки | `/faq/webhooks.html` |

---

## Лимиты и оптимизация

- Используйте **вебхуки** вместо polling
- Используйте **групповые запросы** с фильтрами вместо отдельных запросов
- При превышении лимитов — обратитесь в поддержку

---

## Ссылки

- [OAuth 2.0](https://worksection.com/ua/faq/oauth.html)
- [Начало работы с API](https://worksection.com/ua/faq/api-start.html)
- [Задачи API](https://worksection.com/ua/faq/api-task.html)
- [Postman коллекции](https://worksection.com/ua/faq/postman.html)
