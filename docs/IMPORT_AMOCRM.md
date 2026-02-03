# Импорт лидов из AmoCRM (CSV/JSON)

Импорт выполняется через загрузку файла без прямого API AmoCRM — так проще и надёжнее на первом этапе.

## Endpoint

- **POST** `/api/admin/import/leads`  
  Доступ: только **admin**, **owner** или **rop** (JWT).

## Параметры (multipart/form-data)

| Параметр | Тип | Обязательный | Описание |
|----------|-----|--------------|----------|
| `file` | файл | да | CSV или JSON |
| `tenant_id` | int | нет* | ID tenant. *Обязателен, если у пользователя нет привязки к tenant.* |
| `source` | string | нет | По умолчанию `import_amocrm` |
| `mode` | string | нет | `dry_run` (по умолчанию) или `commit` |
| `mapping` | string (JSON) | нет | Маппинг колонок на поля лида: `{"csv_col": "lead_field"}` |
| `update_existing` | bool | нет | Пока не используется |

## Режимы

- **dry_run** — в БД ничего не записывается. В ответе: `preview` (первые 20 строк), `total_rows`, список `errors` (некорректный телефон, отсутствие телефона и т.д.).
- **commit** — создаются лиды с `source=import_amocrm`, `external_source=amocrm`, при наличии — `external_id`. Дедупликация: по `external_id` (если передан) или по телефону за последние 7 дней.

## Форматы файла

### CSV

- Первая строка — заголовки.
- По умолчанию ожидаются колонки: `name`, `phone`, `city`, `object_type`, `area`, `status`, `summary`, `created_at`, `external_id` (например `amocrm_lead_id`).
- Если названия колонок другие — передайте `mapping`, например:  
  `{"Имя": "name", "Телефон": "phone", "Город": "city", "ID в Amo": "external_id"}`.

### JSON

- Массив объектов: `[{...}, {...}]`.
- Ключи объектов — как поля лида или через `mapping`.

## Нормализация телефона

- Принимаются форматы: `8xxxxxxxxxx`, `+7xxxxxxxxxx`, `7xxxxxxxxxx`.
- Сохраняется в виде `7xxxxxxxxxx` (без `+`). Пустые или слишком короткие номера приводят к ошибке в строке и пропуску (или к записи в `errors` в dry_run).

## Примеры

### cURL (dry_run)

```bash
curl -X POST "https://your-api/api/admin/import/leads" \
  -H "Authorization: Bearer YOUR_JWT" \
  -F "file=@leads.csv" \
  -F "tenant_id=2" \
  -F "mode=dry_run"
```

### cURL (commit)

```bash
curl -X POST "https://your-api/api/admin/import/leads" \
  -H "Authorization: Bearer YOUR_JWT" \
  -F "file=@leads.csv" \
  -F "tenant_id=2" \
  -F "mode=commit"
```

### Маппинг (если колонки нестандартные)

```json
{"Имя": "name", "Телефон": "phone", "Город": "city", "Тип объекта": "object_type", "ID заявки": "external_id"}
```

Передаётся как строка в поле `mapping`.

## Ответ

- `ok`: true  
- `mode`: `dry_run` | `commit`  
- `total_rows`: количество обработанных строк  
- `created`: сколько лидов создано (только при `commit`)  
- `skipped`: сколько пропущено (дубликаты, ошибки)  
- `errors`: массив строк (до 50)  
- `preview`: при `dry_run` — первые 20 строк после маппинга  

## События

На каждый созданный лид создаётся событие `lead_events` с типом `created` и `payload={"source": "import_amocrm"}`. После создания для лида может сработать автоназначение по правилам (если настроено).
