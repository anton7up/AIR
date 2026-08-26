# AIR

Фундамент Telegram-сервиса, который помогает пользователю оценить влияние никотиновой
привычки и пройти программу отказа от никотина. Текущая версия включает Telegram-бота,
onboarding, расчёт расходов, интерактивную 30-дневную программу, журнал желания
никотина и персонализированный SOS.

Инструкция постоянного запуска на Ubuntu VPS через Docker Compose и Caddy:
[DEPLOYMENT.md](DEPLOYMENT.md).

## Что внутри

- aiogram 3 и конфигурируемый граф вопросов;
- отдельные стратегии расходов для сигарет, IQOS/Glo, вейпа, снюса и кальяна;
- async SQLAlchemy и SQLite с профилем программы и историей попыток отказа;
- FastAPI API и документация `/docs`;
- React Mini App с программой, прогрессом, SOS и профилем;
- pytest-тесты критичных расчётов и переходов onboarding.

SQLite используется через async-драйвер. Модели не зависят от SQLite-специфичных типов:
для перехода на PostgreSQL достаточно заменить `DATABASE_URL`, установить asyncpg и
подключить миграции (например, Alembic) перед production-запуском.

## Установка

Требуется Python 3.11 или новее.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Откройте созданный локальный файл `.env` и добавьте токен от BotFather:

```dotenv
BOT_TOKEN=ваш_реальный_токен
```

Не коммитьте `.env`: он уже добавлен в `.gitignore`. Приложение не пишет токен в логи.

## Запуск

Бот и API одним процессом:

```powershell
python -m app.main
```

Только API (BOT_TOKEN не требуется):

```powershell
uvicorn app.api.main:app --reload
```

После запуска API: `http://127.0.0.1:8000/health` и
`http://127.0.0.1:8000/docs`.

## Тесты

```powershell
pytest
```

## Настройка onboarding

Вопросы, варианты и переходы находятся в `app/onboarding/config.py`. Общие вопросы
переходят в ветку выбранного типа никотина, а каждая ветка завершается вопросом
`acquisition_source`. Handlers не содержат порядка вопросов. Проверка числового ввода
и навигация выполняются `OnboardingEngine`.

Формулы находятся в `app/services/expenses.py`. Упаковочные продукты используют общую
стратегию «единиц в день / единиц в упаковке × цена», кальян — самостоятельную недельную
стратегию. Её можно заменить без изменения Telegram handlers.

## Telegram Mini App

Mini App находится в `miniapp/` и построен на React, TypeScript и Vite. Он включает
Paywall, dashboard, программу, SOS, прогресс и профиль. Пользователь определяется по
подписанному Telegram `initData`; `BOT_TOKEN` используется только backend для проверки
подписи и никогда не передаётся frontend.

### Запуск backend

```powershell
cd C:\Projects\AIR
.\.venv\Scripts\python.exe -m app.main
```

Эта команда одновременно запускает Telegram-бота и API на `http://127.0.0.1:8000`.
Для запуска только API:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.api.main:app --reload
```

### Запуск Mini App для разработки

Установите Node.js 20 или новее, затем откройте второй терминал:

```powershell
cd C:\Projects\AIR\miniapp
npm install
Copy-Item .env.example .env
npm run dev
```

Откройте `http://127.0.0.1:5173`.

### Локальный тест без Telegram

В корневом `.env` временно включите строго локальный режим:

```dotenv
APP_ENV=development
DEV_AUTH_ENABLED=true
```

В `miniapp/.env` укажите Telegram ID пользователя, который уже прошёл onboarding и
присутствует в `air.db`:

```dotenv
VITE_API_URL=http://127.0.0.1:8000
VITE_DEV_TELEGRAM_ID=123456789
```

Перезапустите backend и Vite. На Paywall появится кнопка «Получить тестовый доступ».
Она создаёт/обновляет `Subscription` со статусом `active`. Отсчёт отказа начинается
только после кнопки «Начать отказ» в Дне 1. Этот механизм недоступен при
`APP_ENV=production`, даже если второй флаг включён по ошибке.

### Архитектура программы

Контент не зашит в React-экраны. День 1 находится в
`app/services/program/day_01.py`, Дни 2–30 сгруппированы по неделям в файлах
`days_02_07.py`, `days_08_14.py`, `days_15_21.py` и `days_22_30.py`.
`builders.py` содержит общие шаблоны обычного и checkpoint-дня,
`interactive_content.py` — конфигурацию интерактивов Дней 2–30,
`content.py` — редактируемые варианты и единый реестр, а `engine.py` — проверку
ответов, персонализацию, аналитику и переходы. Новый день добавляется как конфигурация
`ProgramDay` в реестр `PROGRAM_DAYS`.

Универсальный `ProgramStepRenderer` Mini App отображает как базовые шаги
`info`, `single_select`, `multi_select`, `scale`, `text`, `task`, `completion`,
так и содержательные шаги `theory`, `structured_input`, `personalized_insight`,
`selected_insights`, `checkpoint`, `personalized_cards` и
`personalized_summary`. Выборные сценарии используют универсальные типы
`plan_builder`, `scenario_choice`, `priority_select`, `action_picker`,
`ordered_select`, `comparison` и `result_card`; для Дней 2–30 клавиатура не нужна.
Ответы всех дней сохраняются в JSON-поле
`ProgramDayState.state_json`; отдельные таблицы или React-условия для каждого дня
не требуются. Дни 7, 14, 21 и 30 строят карточки только по существующим данным и
показывают нейтральный fallback, когда наблюдений недостаточно.

### Персональный DEV preview программы

Backend включает DEV preview только при одновременном выполнении двух условий:
`DEV_PROGRAM_MODE=true` и Telegram ID входит в список `DEV_TELEGRAM_IDS`.
Разрешённый разработчик может открыть любой День 1–30 через отдельные endpoints
`/dev/program/{day}`. Ответы сохраняются в `dev_program_day_states`, поэтому reset,
повторное прохождение и завершение preview не меняют `ProgramDayState`,
`ProgramDayCompletion`, `program_started_at`, QuitAttempt или Progress.

Та же backend-проверка даёт разрешённому Telegram-пользователю виртуальный developer
access к продукту без платёжной операции и без записи `Subscription`. В production
идентичность по-прежнему берётся только из проверенного Telegram `initData`;
`DEV_AUTH_ENABLED=false` исключает доступ через dev-заголовок.

Для локального аккаунта добавьте в `.env` вручную:

```env
DEV_PROGRAM_MODE=true
DEV_TELEGRAM_IDS=ID_1,ID_2
```

Несколько ID перечисляются через запятую. При выключенном флаге или ID вне списка
DEV endpoints возвращают `403 Forbidden`; frontend не является источником прав.

Программа и попытка отказа имеют разные часы. `program_started_at` определяет доступный
день (разница календарного времени в полных 24-часовых периодах, от 1 до 30), а активный
`QuitAttempt` является источником текущей серии без никотина. Legacy-поле
`quit_started_at` синхронизируется только для обратной совместимости. Срыв закрывает
попытку, но не меняет программу и завершённые дни.

Основные API Mini App доступны под префиксом `/api/v1/mini-app`:

- `GET /program`, `POST /program/start`;
- `GET /program/{day}`, `POST /program/{day}/state`, `POST /program/{day}/complete`;
- `POST /nicotine-desire`, `GET /nicotine-desire/recent`;
- `GET /support-context`, `POST /sos/start`, `POST /sos/{id}/actions`,
  `POST /sos/{id}/actions/{action_id}/complete`, `PATCH /sos/{id}/trigger`,
  `POST /sos/{id}/complete`, `PATCH /motivation`;
- `POST /lapse`;
- `GET /quit-attempt/current`, `POST /quit-attempt/restart`.

### SOS 2.0

SOS сохраняет прежний вход: исходная оценка 1–10 и trigger создают одну `SosSession`,
в которой можно повторно использовать несколько `SosAction`. После каждого действия
сохраняются его собственные оценки до/после и необязательные JSON-метаданные, поэтому
эффект не приписывается последней технике всей сессии. Backend рассчитывает средний
эффект по инструменту и trigger и показывает персональную ⭐ только после минимум трёх
точных завершённых наблюдений. Legacy-действия без оценок остаются в счётчике
использования, но не участвуют в effectiveness.

### Тест внутри Telegram

Telegram открывает Web App только по публичному HTTPS URL:

1. Выполните production-сборку: `cd miniapp`, затем `npm run build`.
2. Перезапустите backend. Собранный интерфейс доступен на `/mini-app/`.
3. Откройте HTTPS-туннель к локальному порту `8000` удобным вам инструментом.
4. В корневом `.env` задайте `MINI_APP_URL=https://ваш-туннель/mini-app/`.
5. Перезапустите приложение и нажмите «Открыть AIR» в боте.

Внутри Telegram frontend отправит настоящий `initData`, а backend проверит подпись,
срок действия и Telegram ID. Для такого теста `DEV_AUTH_ENABLED` можно оставить `false`.

### Переменные окружения

Корневой `.env`:

- `BOT_TOKEN` — токен бота, только на backend;
- `DATABASE_URL` — подключение SQLAlchemy;
- `MINI_APP_URL` — публичный HTTPS URL Mini App;
- `APP_ENV` — `development` или `production`;
- `DEV_AUTH_ENABLED` — локальный тестовый доступ;
- `CORS_ORIGINS` — адреса Vite dev server;
- `TELEGRAM_INIT_DATA_MAX_AGE_SECONDS` — допустимый возраст `initData`;
- `SUPPORT_URL`, `TERMS_URL`, `PRIVACY_URL` — будущие юридические и support-ссылки.

Frontend `miniapp/.env`:

- `VITE_API_URL` — URL backend; для собранного same-origin приложения можно не задавать;
- `VITE_DEV_TELEGRAM_ID` — только для локального browser-теста.

### Проверки

Backend:

```powershell
python -m ruff check app tests
python -m mypy app
python -m pytest
```

Frontend:

```powershell
cd miniapp
npm run type-check
npm run lint
npm run build
```

### Перед реальными платежами

Потребуется платежный провайдер, серверное создание платежа, проверка webhook-подписи,
идемпотентное обновление `Subscription`, тарифы/чеки, обработка возвратов и production
миграции БД. Mini App уже опирается только на абстрактный статус доступа, поэтому менять
его экраны при подключении оплаты не потребуется.
