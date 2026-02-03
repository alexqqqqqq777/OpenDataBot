# Налаштування безпечного режиму (Gist Sync)

Цей режим дозволяє боту отримувати номери справ з Worksection **без прямого доступу до API**.
Ключ Worksection зберігається тільки в GitHub Secrets, а не на VPS сервері.

## Архітектура

```
┌─────────────────────────────────────────────────────────────┐
│                    GitHub (ваш контроль)                     │
│  ┌─────────────────┐      ┌─────────────────────────────┐   │
│  │ GitHub Actions  │      │ GitHub Gist                 │   │
│  │ (cron: 7:00,    │──────▶│ worksection_cases.json     │   │
│  │  19:00 UTC)     │      │ ["922/4626/23", ...]       │   │
│  └────────┬────────┘      └──────────────┬──────────────┘   │
│           │                              │                   │
│           ▼                              │                   │
│  ┌─────────────────┐                     │                   │
│  │ GitHub Secrets  │                     │                   │
│  │ WORKSECTION_    │                     │                   │
│  │ API_KEY 🔐      │                     │                   │
│  └─────────────────┘                     │                   │
└──────────────────────────────────────────┼───────────────────┘
                                           │
                                           ▼ (публічний доступ)
┌─────────────────────────────────────────────────────────────┐
│                    VPS сервер                                │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ OpenDataBot                                          │    │
│  │ - Читає Gist (тільки номери справ)                  │    │
│  │ - НЕ має доступу до Worksection API                 │    │
│  │ - НЕ бачить назви задач, описи, проекти             │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

## Крок 1: Створіть GitHub Gist

1. Перейдіть на https://gist.github.com
2. Створіть **публічний** Gist з файлом `worksection_cases.json`:
   ```json
   {
     "case_numbers": [],
     "count": 0,
     "updated_at": null
   }
   ```
3. Збережіть **Gist ID** з URL (напр. `https://gist.github.com/username/abc123def456` → ID = `abc123def456`)

## Крок 2: Створіть Personal Access Token

1. Перейдіть: GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Generate new token (classic)
3. Назва: `OpenDataBot Gist Sync`
4. Scope: ☑️ `gist` (тільки gist!)
5. Збережіть токен

## Крок 3: Налаштуйте GitHub Secrets

У вашому репозиторії: Settings → Secrets and variables → Actions → New repository secret

| Secret Name | Value |
|-------------|-------|
| `WORKSECTION_DOMAIN` | `yourcompany.worksection.com` (без https://) |
| `WORKSECTION_API_KEY` | Ваш ключ Worksection |
| `GIST_ID` | ID гіста з кроку 1 |
| `GIST_TOKEN` | Personal Access Token з кроку 2 |

## Крок 4: Налаштуйте VPS

На сервері в `.env` додайте:

```env
# Видаліть або закоментуйте:
# WORKSECTION_API_KEY=...
# WORKSECTION_ACCOUNT=...

# Додайте:
WORKSECTION_GIST_ID=abc123def456
```

Перезапустіть сервіс:
```bash
sudo systemctl restart opendatabot.service
```

## Крок 5: Запустіть перший sync

1. У репозиторії: Actions → Sync Worksection Cases to Gist → Run workflow
2. Перевірте що Gist оновився
3. Перевірте логи бота на сервері

## Перевірка

### На GitHub:
```
Actions → Sync Worksection Cases to Gist → (останній run) → logs
```

### На VPS:
```bash
# Перевірити режим
grep GIST_ID ~/OpenDataBot/.env

# Перевірити логи
sudo journalctl -u opendatabot.service -n 50 | grep -i gist
```

### Gist вміст:
```bash
curl -s "https://gist.githubusercontent.com/raw/YOUR_GIST_ID/worksection_cases.json" | jq
```

## Розклад

| Час (UTC) | Подія |
|-----------|-------|
| 7:00 | GitHub Actions → sync Worksection → Gist |
| 7:00 | Bot → sync from Gist → local DB |
| 8:00 | Bot → check OpenDataBot → notifications |
| 19:00 | GitHub Actions → sync Worksection → Gist |
| 19:00 | Bot → sync from Gist → local DB |
| 20:00 | Bot → check OpenDataBot → notifications |

## Безпека

✅ **Що захищено:**
- Ключ Worksection API тільки в GitHub Secrets
- VPS сервер не має доступу до Worksection
- Адмін сервера бачить тільки номери справ

❌ **Що НЕ захищено:**
- Номери справ (публічний Gist)
- Можна зробити Gist приватним, але тоді потрібен токен на VPS

## Приватний Gist (опціонально)

Якщо потрібно приховати навіть номери справ:

1. Створіть **секретний** Gist
2. Додайте на VPS:
   ```env
   WORKSECTION_GIST_ID=abc123def456
   GITHUB_GIST_TOKEN=ghp_xxxxx
   ```
3. Модифікуйте `gist_client.py` для автентифікації

## Troubleshooting

### GitHub Actions не запускається
- Перевірте що workflow файл в `.github/workflows/`
- Перевірте що репозиторій не архівний
- Спробуйте Run workflow вручну

### Gist не оновлюється
- Перевірте права токена (потрібен `gist` scope)
- Перевірте GIST_ID (правильний формат)
- Подивіться логи Actions

### Бот не бачить справи
- Перевірте `WORKSECTION_GIST_ID` в `.env`
- Перевірте що Gist доступний публічно
- Перевірте логи: `grep -i gist`

---

*Документ створено: 03.02.2026*
