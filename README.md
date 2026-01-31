# OpenDataBot + Worksection Integration

Проект для мониторинга судебных дел через API OpenDataBot с интеграцией в Worksection.

## Структура проекта

```
OpebDataBot/
├── docs/
│   ├── COURT_MONITORING_API.md   # Документация по API мониторинга судебных дел
│   └── WORKSECTION_API.md        # Документация по Worksection API и OAuth 2.0
├── api_v3_spec.json              # Полная спецификация OpenAPI v3 OpenDataBot
└── README.md
```

## Функциональность

- Мониторинг судебных дел по номеру
- Мониторинг по стороне дела (истец/ответчик)
- Получение истории изменений
- Поиск по тексту судебных документов

## Получение API ключа

1. Зарегистрируйтесь на [opendatabot.ua](https://opendatabot.ua)
2. Получите тестовый доступ к API
3. Добавьте ключ в переменную окружения `OPENDATABOT_API_KEY`

## Документация

- [API мониторинга судебных дел](docs/COURT_MONITORING_API.md)
- [Официальная документация](https://docs.opendatabot.com/?urls.primaryName=v3)

## Типы мониторинга судебных дел

| Тип | Описание |
|-----|----------|
| `court-by-number` | По номеру дела |
| `court-by-text` | По тексту |
| `court-by-involved` | По стороне дела |
| `new-court-defendant` | Новые дела как ответчик |
| `new-court-plaintiff` | Новые дела как истец |
