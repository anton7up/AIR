# AIR: production deployment на Ubuntu 24.04

Production состоит из двух контейнеров: `caddy` принимает трафик на 80/443 и
проксирует его во внутренний `air:8000`; `air` одним процессом запускает FastAPI и
Telegram-бота. React/Vite собирается при Docker build, затем FastAPI раздаёт готовый
`miniapp/dist` по `/mini-app/`. В runtime-образе Node.js отсутствует.

## Домен и DNS

Для постоянного публичного HTTPS создайте у DNS-провайдера запись `A`, например:

```text
air.example.com -> 77.233.213.6
```

Не создавайте `AAAA`, если на VPS нет рабочего IPv6. После обновления DNS Caddy сам
получит и будет продлевать TLS-сертификат. Без домена можно предварительно проверить
сервер по HTTP/IP, но это не постоянный Telegram Mini App URL с публичным HTTPS.

## Production `.env`

Создайте `/opt/air/.env` только на VPS. Замените домен и токен:

```dotenv
PUBLIC_HOST=air.example.com
BOT_TOKEN=ВСТАВИТЬ_ТОКЕН_ОТ_BOTFATHER
DATABASE_URL=sqlite+aiosqlite:////data/air.db
MINI_APP_URL=https://air.example.com/mini-app/
API_HOST=0.0.0.0
API_PORT=8000
LOG_LEVEL=INFO
APP_ENV=production
DEV_AUTH_ENABLED=false
DEV_PROGRAM_MODE=true
DEV_TELEGRAM_IDS=749408538
CORS_ORIGINS=https://air.example.com
TELEGRAM_INIT_DATA_MAX_AGE_SECONDS=86400
SUPPORT_URL=
TERMS_URL=
PRIVACY_URL=
YOOKASSA_SHOP_ID=ВСТАВИТЬ_SHOP_ID
YOOKASSA_SECRET_KEY=ВСТАВИТЬ_СЕКРЕТНЫЙ_КЛЮЧ
YOOKASSA_RETURN_URL=https://air.example.com/mini-app/?payment=return
```

Compose принудительно задаёт контейнерные `API_HOST`, `API_PORT` и `DATABASE_URL`.
`BOT_TOKEN` остаётся только на backend. В production заголовок `X-Dev-Telegram-Id`
не даёт доступ: backend принимает его лишь при сочетании `APP_ENV=development` и
`DEV_AUTH_ENABLED=true`. DEV preview работает только при `DEV_PROGRAM_MODE=true` и
наличии ID из проверенного Telegram `initData` в `DEV_TELEGRAM_IDS`.

Ключ ЮKassa остаётся только в `/opt/air/.env` и не попадает во frontend или Git.
После запуска добавьте в кабинете ЮKassa webhook
`https://air.example.com/api/v1/payments/yookassa/webhook` для событий
`payment.succeeded` и `payment.canceled`. Для текущего production-домена AIR это
`https://airtgbot.ru/api/v1/payments/yookassa/webhook`.

## UFW

Выполняйте в уже открытой SSH-сессии. Сначала разрешите SSH и проверьте правило, только
после этого включайте firewall:

```bash
sudo apt-get update
sudo apt-get install -y ufw
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw status verbose
sudo ufw enable
sudo ufw status numbered
```

Не разрешайте `8000/tcp`. Если SSH работает на другом порту, до `ufw enable` разрешите
его вместо 22.

## Перенос с Windows

PowerShell:

```powershell
Set-Location C:\Projects\AIR
tar.exe -czf C:\Projects\air-deploy.tar.gz --exclude=.env --exclude=.venv --exclude=.git --exclude=.idea --exclude=.vscode --exclude=__pycache__ --exclude=.pytest_cache --exclude=.mypy_cache --exclude=.ruff_cache '--exclude=.test-tmp*' '--exclude=*.db*' --exclude=data --exclude=backups --exclude=miniapp/node_modules --exclude=miniapp/dist --exclude=miniapp/.env .
tar.exe -tzf C:\Projects\air-deploy.tar.gz | Select-String -Pattern '(^|/)\.env$|\.db($|-)|node_modules|\.venv' -CaseSensitive
scp C:\Projects\air-deploy.tar.gz root@77.233.213.6:/tmp/air-deploy.tar.gz
```

Команда `Select-String` не должна ничего вывести. Архив не содержит локальные секреты,
БД, зависимости и готовую локальную сборку.

## Первый запуск

Сначала дождитесь, чтобы DNS указывал на `77.233.213.6`, затем:

```bash
ssh root@77.233.213.6
mkdir -p /opt/air/data /opt/air/backups
tar -xzf /tmp/air-deploy.tar.gz -C /opt/air
cd /opt/air
cp .env.example .env
nano .env
chown -R 10001:10001 /opt/air/data /opt/air/backups
chmod 700 /opt/air/data /opt/air/backups
chmod 600 /opt/air/.env
docker compose version
docker compose config --quiet
docker compose build
docker compose up -d
docker compose ps
docker compose logs --tail=100 air
docker compose logs --tail=100 caddy
curl -fsS https://air.example.com/health
curl -I https://air.example.com/mini-app/
```

В двух последних командах замените домен. Healthcheck возвращает `{"status":"ok"}`,
а Mini App — HTTP 200. API docs находятся на `/docs`.

## Новая БД или перенос существующей

Вариант A — новая БД: ничего не копируйте. AIR создаст
`/opt/air/data/air.db`; bind mount переживает restart и rebuild.

Вариант B — до первого запуска передайте существующую БД:

```powershell
scp C:\Projects\AIR\air.db root@77.233.213.6:/opt/air/data/air.db
```

На VPS:

```bash
chown 10001:10001 /opt/air/data/air.db
chmod 600 /opt/air/data/air.db
```

Если AIR уже работает, сначала сделайте backup и остановите `air`, затем заменяйте БД.

## Управление, логи и обновление

```bash
cd /opt/air
docker compose restart
docker compose ps
docker compose logs -f --tail=200 air
docker compose logs -f --tail=200 caddy
```

`Ctrl+C` закрывает просмотр логов, но не контейнеры.

## Обновление через GitHub Container Registry

Push в ветку `main` запускает `.github/workflows/docker-publish.yml`. GitHub собирает
образ `ghcr.io/anton7up/air:latest`, поэтому слабому VPS не приходится выполнять
долгий `docker compose build`.

Для приватного пакета один раз авторизуйте VPS в GHCR с GitHub Personal Access Token,
имеющим только право `read:packages`. Не записывайте токен в `.env` проекта:

```bash
read -s -p 'GitHub token: ' GHCR_TOKEN && echo
printf '%s' "$GHCR_TOKEN" | docker login ghcr.io -u anton7up --password-stdin
unset GHCR_TOKEN
```

После успешной сборки в GitHub Actions обновляйте сервер так:

```bash
cd /opt/air
mkdir -p backups
cp -a data/air.db "backups/air-before-update-$(date +%Y%m%d-%H%M%S).db"
git pull --ff-only
docker compose pull air
docker compose up -d --no-build
docker compose ps
curl -fsS https://airtgbot.ru/health
docker compose logs --tail=100 air
```

Старый способ через архив по-прежнему доступен. Передайте новый архив, сделайте
backup и выполните:

```bash
cd /opt/air
tar -xzf /tmp/air-deploy.tar.gz -C /opt/air
docker compose config --quiet
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 air
```

`data` и `backups` исключены из архива, поэтому обновление кода их не перезаписывает.

## Backup SQLite

Команда использует SQLite online backup и создаёт согласованный снимок при работающем
AIR:

```bash
cd /opt/air
BACKUP_FILE="/backups/air-$(date +%Y%m%d-%H%M%S).db"
docker compose exec -T -e BACKUP_FILE="$BACKUP_FILE" air python -c "import os, sqlite3; source = sqlite3.connect('/data/air.db'); target = sqlite3.connect(os.environ['BACKUP_FILE']); source.backup(target); target.close(); source.close()"
ls -lh /opt/air/backups
```

Скопировать backup на Windows можно так:

```powershell
scp root@77.233.213.6:/opt/air/backups/air-YYYYMMDD-HHMMSS.db C:\Projects\
```

## Restore SQLite

Замените имя backup реальным:

```bash
cd /opt/air
docker compose stop air
cp /opt/air/data/air.db "/opt/air/backups/pre-restore-$(date +%Y%m%d-%H%M%S).db"
cp /opt/air/backups/air-YYYYMMDD-HHMMSS.db /opt/air/data/air.db
chown 10001:10001 /opt/air/data/air.db
chmod 600 /opt/air/data/air.db
docker compose start air
docker compose ps
docker compose logs --tail=100 air
```

## Telegram и BotFather

`MINI_APP_URL=https://air.example.com/mini-app/`. Кнопка «Открыть AIR» берёт этот URL
автоматически. Для существующей inline Web App-кнопки отдельная настройка обычно не
нужна. Если нужен постоянный пункт меню, в `@BotFather` используйте `/setmenubutton` и
задайте тот же HTTPS URL.

Проверяйте внутри Telegram: пройдите onboarding, нажмите «Открыть AIR», затем откройте
Home, Программу, SOS, Progress и Profile. Обычный браузер не передаёт Telegram
`initData`; API в production должен вернуть 401, а не авторизовать dev-пользователя.
