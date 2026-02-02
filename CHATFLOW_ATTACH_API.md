# ChatFlow-привязка tenant: поля backend и API

## Какие поля ждёт backend (таблица whatsapp_accounts)

| Поле в БД | Алиасы на входе (принимаются оба) |
|-----------|-----------------------------------|
| **chatflow_token** | `chatflow_token` или `token` |
| **chatflow_instance_id** | `chatflow_instance_id` или `instance_id` |
| **phone_number** | `phone_number` или `phone` |
| **is_active** | `is_active` или `active` |

Сохранение всегда в: `chatflow_token`, `chatflow_instance_id`, `phone_number`, `is_active`.

---

## Пример payload для attach (POST)

**POST** `/api/admin/tenants/{tenant_id}/whatsapp`

Можно слать в любом из вариантов имён (backend принимает оба):

```json
{
  "token": "your_chatflow_token",
  "instance_id": "instance_abc",
  "phone_number": "+77001234567",
  "active": true
}
```

или:

```json
{
  "chatflow_token": "your_chatflow_token",
  "chatflow_instance_id": "instance_abc",
  "phone_number": "+77001234567",
  "is_active": true
}
```

- При **active=true** обязательны непустые `chatflow_token` и `chatflow_instance_id` (иначе 422).
- При **active=false** можно не передавать token/instance_id; уже сохранённые значения не затираются.

---

## Ответ attach (POST)

```json
{
  "ok": true,
  "whatsapp": {
    "id": 1,
    "tenant_id": 1,
    "phone_number": "+77001234567",
    "active": true,
    "chatflow_instance_id": "instance_abc",
    "chatflow_token": "your_chatflow_token"
  }
}
```

---

## Ответ GET list

**GET** `/api/admin/tenants/{tenant_id}/whatsapp`

```json
{
  "ok": true,
  "whatsapp": [
    {
      "id": 1,
      "tenant_id": 1,
      "phone_number": "+77001234567",
      "active": true,
      "chatflow_instance_id": "instance_abc",
      "chatflow_token": "your_chatflow_token"
    }
  ],
  "total": 1
}
```

Те же поля, что и в объекте внутри ответа attach: `id`, `tenant_id`, `phone_number`, `active`, `chatflow_instance_id`, `chatflow_token`.

---

## Лог в attach

В логах сервера при вызове attach:

- `tenant_id`, `active`, `phone_number`, `token_len`, `instance_len`
- `json_keys` — список ключей пришедшего JSON (чтобы видеть расхождения с ожиданием).
