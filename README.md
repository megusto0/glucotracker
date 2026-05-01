# Glucotracker

Glucotracker - личный дневник питания для человека с СД1. Приложение помогает фиксировать еду, фото, БЖУ, углеводы, локальную базу продуктов, контекст CGM/инсулина из Nightscout и формировать информационные отчёты.

Важно: проект не рассчитывает дозы инсулина, не предлагает болюсы, коррекции или медицинские решения. Все показатели про инсулин и `Наблюдаемый УК` являются только контекстом для дневника и обсуждения с врачом.

## Что умеет

- Журнал питания: ручные записи, быстрые продукты, шаблоны, черновики, принятые записи, правка названия, даты/времени и веса.
- Распознавание по фото через Gemini: этикетки, частичные этикетки, блюда на тарелке, несколько фото, одинаковые упаковки, пересчёт по видимому весу/объёму.
- Повтор еды: дублирование записи, повтор по новому весу и быстрый повтор одной распознанной штуки/упаковки, например `1 × 20 г` из записи `3 × 20 г`.
- Backend-owned математика: frontend может редактировать черновик, но итоговые БЖУ, ккал, дневные итоги и label/product расчёты пересчитывает backend.
- Локальная база еды: продукты, алиасы, ресторанные/личные шаблоны, автодополнение по обычному тексту и префиксам.
- Nightscout: опциональный read-only импорт CGM и инсулина, ручная отправка еды в Nightscout, история пищевых эпизодов с мини-графиками глюкозы.
- Отчёты и экспорт: PDF A4 для эндокринолога и TXT-дневник еды по всем дням с принятыми записями.
- Desktop UI: Tauri 2 + React, русский интерфейс, локальное сохранение PDF/TXT через системный диалог.

## Архитектура

Backend является главным продуктовым слоем. Он хранит данные, владеет API-семантикой, расчётами, распознаванием, импортом Nightscout и отчётной агрегацией. Desktop - заменяемый клиент.

- `backend/` - FastAPI, SQLAlchemy/Alembic, application services, Gemini, Nightscout, тесты.
- `desktop/` - Tauri 2, React, TypeScript, Tailwind, generated OpenAPI types.
- `docs/` - архитектура, API-контракт, дизайн, manual testing, OpenAPI schema.
- `scripts/` - вспомогательные скрипты и локальные генераторы.

Ключевые документы:

- [docs/architecture.md](docs/architecture.md)
- [docs/api-contract.md](docs/api-contract.md)
- [docs/project-explainer.txt](docs/project-explainer.txt)
- [docs/manual-testing.md](docs/manual-testing.md)

## Backend

Быстрый запуск на Windows PowerShell:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
$env:GLUCOTRACKER_TOKEN = "dev"
uvicorn glucotracker.main:app --reload
```

Проверка:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/meals -Headers @{ Authorization = "Bearer dev" }
```

## Распознавание Фото

Gemini используется только backend-ом. Ключи и модели не должны попадать во frontend.

```powershell
$env:GEMINI_API_KEY = "your-key"
$env:GEMINI_MODEL = "gemini-3-flash-preview"
$env:GEMINI_CHEAP_MODEL = "gemini-3.1-flash-lite-preview"
$env:GEMINI_FALLBACK_MODEL = "gemini-2.5-flash"
```

Pipeline:

1. UI создаёт черновик и загружает фото.
2. Backend отправляет фото и контекст в Gemini.
3. Gemini возвращает структурированные предположения и evidence.
4. Backend нормализует ответ, пересчитывает label/product математику и сохраняет черновики.
5. Пользователь проверяет, редактирует и принимает запись.

Для этикеток backend пересчитывает значения из фактов на 100 г/100 мл/порцию. Для блюд на тарелке Gemini даёт оценку и компоненты; backend может заменить известные компоненты значениями из локальной базы без двойного счёта.

## Журнал И Повторы

Журнал работает с выбранным локальным днём. Если открыт 28 апреля и пользователь добавляет фото или ручную запись, новая запись получает дату 28 апреля с текущим временем. Это намеренное поведение для дозаполнения старых дней. Если запись попала не в тот день, в правой панели записи можно изменить `Дата и время записи`; backend пересчитает дневные итоги для старого и нового дня.

В правой панели записи доступны:

- правка названия;
- правка даты и времени;
- правка веса текущей позиции, если у позиции есть граммы;
- `Повтор по весу`: backend создаёт новую принятую запись из существующей позиции и пропорционально пересчитывает макросы;
- быстрый повтор одной распознанной штуки/упаковки, если в evidence есть количество и вес единицы, например для халвы `3 × 20 г` появляется действие `Добавить 1 упаковку · 20 г`.

Frontend не пересчитывает БЖУ для повторов. Он отправляет `grams` в backend endpoint `POST /meal_items/{id}/copy_by_weight`, а backend создаёт новую запись, копирует источник/фото и пересчитывает значения.

## Nightscout

Nightscout необязателен. Если настройки пустые, локальный дневник работает, а sync/import endpoints возвращают понятную ошибку.

```powershell
$env:NIGHTSCOUT_URL = "https://your-nightscout.example"
$env:NIGHTSCOUT_API_SECRET = "your-secret"
```

Glucotracker:

- отправляет еду в Nightscout как treatment без инсулина;
- импортирует CGM и insulin treatments только для read-only контекста;
- хранит импортированные события локально;
- группирует еду в пищевые эпизоды для истории и отчётов.

## Отчёты

Endpoint `GET /reports/endocrinologist?from=YYYY-MM-DD&to=YYYY-MM-DD` возвращает готовые данные отчёта. Frontend только рендерит PDF и сохраняет файл.

В настройках также есть TXT-экспорт еды по всем дням с принятыми записями. Файл сохраняется локально через системный диалог Tauri и содержит строки еды, позиции, макросы и дневные итоги.

Правила отчёта:

- `Наблюдаемый УК`, не “рекомендуемый”.
- Формула: `Σ углеводы / Σ meal-linked insulin`.
- Unlinked insulin/corrections входят в дневной инсулин, но не искажают observed ratio по завтраку/обеду/ужину.
- CGM, TIR и glucose before/after считаются backend-ом.
- PDF информационный и не является медицинской рекомендацией.

## Desktop

```powershell
cd desktop
npm install
npm run tauri dev
```

Если backend API изменился, обновить OpenAPI и TypeScript-типы:

```powershell
cd backend
@'
import json
from pathlib import Path
from glucotracker.main import app
Path("../docs/openapi.json").write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2), encoding="utf-8")
'@ | .\.venv\Scripts\python.exe -

cd ..\desktop
npm run api:types
```

## Seed Data

Загрузить шаблоны продуктов/ресторанов:

```powershell
cd backend
.\.venv\Scripts\python.exe -m glucotracker.infra.db.seed
```

## Проверки

Backend:

```powershell
cd backend
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest -q
```

Desktop:

```powershell
cd desktop
npm test -- --run
npm run build
```

Tauri/Rust:

```powershell
cd desktop\src-tauri
cargo check
```

## Docker Compose

```powershell
cd backend
docker compose up --build
```

Compose предназначен для развёртывания backend на Ubuntu-сервере. SQLite-данные хранятся в `backend/data/`.

## Безопасность И Ограничения

- Никаких рекомендаций по инсулину, болюсам, коррекциям или лечению.
- Gemini API key и Nightscout secret только на backend.
- Unknown nutrient values хранятся как `null`, не как `0`.
- Frontend не владеет финальной macro math.
- Локальное время дневника не должно сдвигаться через UTC-конвертацию.
