# Технічні вимоги до сервера для OpenDataBot

## Мінімальні вимоги

| Параметр | Мінімум | Рекомендовано |
|----------|---------|---------------|
| **CPU** | 1 vCPU | 2 vCPU |
| **RAM** | 512 MB | 1 GB |
| **Диск** | 5 GB SSD | 10 GB SSD |
| **ОС** | Ubuntu 22.04+ / Debian 11+ | Ubuntu 24.04 LTS |
| **Python** | 3.11+ | 3.13 |

## Поточне використання ресурсів

На основі реального моніторингу (сервер з 34 компаніями):

| Ресурс | Використання |
|--------|--------------|
| **RAM процесу** | ~160 MB |
| **CPU** | < 1% (idle) |
| **База даних** | ~200 KB |
| **Логи** | ~40 KB (з ротацією) |
| **Virtual env** | ~93 MB |
| **Загальний розмір** | ~100 MB |

## Мережеві вимоги

| Сервіс | Порт | Напрямок |
|--------|------|----------|
| Telegram API | 443 (HTTPS) | Вихідний |
| OpenDataBot API | 443 (HTTPS) | Вихідний |
| Worksection API | 443 (HTTPS) | Вихідний |

**Firewall:** Дозволити вихідні з'єднання на порт 443 (HTTPS)

## Залежності системи

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git
```

## Структура каталогів

```
/home/ubuntu/OpenDataBot/
├── venv/                    # Python virtual environment (~93 MB)
├── src/                     # Вихідний код
├── logs/                    # Логи (з ротацією)
├── court_monitor.db         # SQLite база даних
├── .env                     # Конфігурація (секрети)
├── requirements.txt         # Python залежності
└── run.py                   # Точка входу
```

## Systemd сервіс

```ini
# /etc/systemd/system/opendatabot.service
[Unit]
Description=OpenDataBot Telegram Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/OpenDataBot
ExecStart=/home/ubuntu/OpenDataBot/venv/bin/python3 run.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## Змінні середовища (.env)

```env
# Telegram
TELEGRAM_BOT_TOKEN=<token>
TELEGRAM_ADMIN_IDS=<user_id1>,<user_id2>

# APIs
OPENDATABOT_API_KEY=<key>
WORKSECTION_DOMAIN=<domain>
WORKSECTION_API_KEY=<key>

# Database
DATABASE_URL=sqlite+aiosqlite:///court_monitor.db

# Schedule (UTC hours)
WORKSECTION_HOURS=7,19
OPENDATABOT_HOURS=8,20
```

## Масштабування

| Кількість компаній | RAM | Диск |
|--------------------|-----|------|
| 1-50 | 512 MB | 5 GB |
| 50-200 | 1 GB | 10 GB |
| 200-1000 | 2 GB | 20 GB |
| 1000+ | 4 GB+ | 50 GB+ (PostgreSQL) |

> **Примітка:** При >500 компаній рекомендується міграція з SQLite на PostgreSQL.

## Рекомендовані VPS провайдери

| Провайдер | План | Ціна/міс |
|-----------|------|----------|
| Hetzner | CX11 (1 vCPU, 2 GB RAM) | ~€4 |
| DigitalOcean | Basic Droplet | ~$6 |
| Vultr | Cloud Compute | ~$6 |
| OVH | VPS Starter | ~€4 |

## Моніторинг та обслуговування

### Перевірка статусу
```bash
sudo systemctl status opendatabot.service
```

### Логи сервісу
```bash
sudo journalctl -u opendatabot.service -f
```

### Логи OpenDataBot API
```bash
tail -f ~/OpenDataBot/logs/opendatabot_history.log
```

### Бекап бази даних
```bash
cp ~/OpenDataBot/court_monitor.db ~/backups/court_monitor_$(date +%Y%m%d).db
```

## Безпека

- [ ] Налаштувати UFW firewall
- [ ] Використовувати SSH ключі замість паролів
- [ ] Регулярно оновлювати систему (`apt update && apt upgrade`)
- [ ] Зберігати `.env` файл з правами 600
- [ ] Не комітити секрети в git

---

*Документ створено: 03.02.2026*
*Версія: 1.0*
