"""
CRM v3: импорт лидов из AmoCRM (CSV/JSON загрузка без прямого API).
POST /api/admin/import/leads — только admin/owner/rop.
"""
import csv
import json
import io
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_admin_or_owner_or_rop
from app.database import crud
from app.database.models import User
from app.schemas.lead import ImportLeadsResponse
from app.utils.phone import normalize_phone
from app.services.auto_assign_service import try_auto_assign

router = APIRouter()

DEFAULT_CSV_FIELDS = [
    "name", "phone", "city", "object_type", "area", "status", "summary", "created_at", "external_id"
]


def _row_to_lead_data(row: dict, mapping: Optional[dict]) -> dict:
    """Из строки (dict) извлечь поля лида по mapping или по умолчанию. Ключи mapping: csv_header -> lead_field."""
    out = {}
    for key, val in (row or {}).items():
        if val is None or (isinstance(val, str) and not val.strip()):
            continue
        field = (mapping or {}).get(key.strip(), key.strip().lower().replace(" ", "_"))
        if field in ("name", "phone", "city", "object_type", "area", "summary", "status", "created_at", "external_id"):
            out[field] = val.strip() if isinstance(val, str) else val
    return out


def _parse_csv(content: bytes, mapping: Optional[dict]) -> list[dict]:
    """Распарсить CSV; первая строка — заголовки. Возвращает list of dict."""
    text = content.decode("utf-8-skip", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for r in reader:
        rows.append(_row_to_lead_data(r, mapping))
    return rows


def _parse_json(content: bytes, mapping: Optional[dict]) -> list[dict]:
    """Распарсить JSON — массив объектов. Возвращает list of dict."""
    data = json.loads(content.decode("utf-8"))
    if not isinstance(data, list):
        data = [data]
    rows = []
    for item in data:
        if isinstance(item, dict):
            rows.append(_row_to_lead_data(item, mapping))
        else:
            rows.append({})
    return rows


@router.post("/import/leads", response_model=ImportLeadsResponse, summary="Импорт лидов из CSV/JSON (AmoCRM)")
async def import_leads(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_or_owner_or_rop),
    file: UploadFile = File(..., description="CSV или JSON файл"),
    tenant_id: Optional[int] = Form(None, description="Обязателен, если у пользователя нет tenant"),
    source: str = Form("import_amocrm"),
    mode: str = Form("dry_run", description="dry_run | commit"),
    mapping: Optional[str] = Form(None, description="JSON: маппинг полей { \"csv_col\": \"lead_field\" }"),
    update_existing: bool = Form(False, description="При совпадении external_id — обновить лид (пока не реализовано)"),
):
    """
    Импорт лидов из CSV или JSON. Только admin/owner/rop.
    - **dry_run**: не писать в БД, вернуть preview (первые 20) и статистику ошибок.
    - **commit**: создать лиды, source=import_amocrm, external_source=amocrm; дедупликация по external_id или phone за 7 дней.
    """
    tid = tenant_id
    if tid is None:
        tenant = await crud.get_tenant_for_me(db, current_user.id)
        if not tenant:
            raise HTTPException(status_code=403, detail="tenant_id required when user has no tenant")
        tid = tenant.id

    tenant = await crud.get_tenant_by_id(db, tid)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    owner_id = getattr(tenant, "default_owner_user_id", None) or current_user.id

    mapping_obj = None
    if mapping and mapping.strip():
        try:
            mapping_obj = json.loads(mapping)
        except json.JSONDecodeError:
            raise HTTPException(status_code=422, detail="Invalid mapping JSON")

    content = await file.read()
    filename = (file.filename or "").lower()
    if filename.endswith(".json"):
        rows = _parse_json(content, mapping_obj)
    else:
        rows = _parse_csv(content, mapping_obj)

    preview = []
    created = 0
    skipped = 0
    errors = []
    max_errors = 50

    if mode == "dry_run":
        preview = rows[:20]
        for i, row in enumerate(rows):
            phone = (row.get("phone") or "").strip()
            if not phone:
                errors.append(f"Row {i+1}: missing phone")
                continue
            norm = normalize_phone(phone)
            if not norm:
                errors.append(f"Row {i+1}: invalid phone {phone[:20]}")
        return ImportLeadsResponse(
            ok=True,
            mode="dry_run",
            total_rows=len(rows),
            created=0,
            skipped=0,
            errors=errors[:max_errors],
            preview=preview,
        )

    # commit: нужен bot_user для импорта (один на tenant)
    bot_user = await crud.get_or_create_bot_user(
        db, user_id=f"import_tenant_{tid}", owner_id=owner_id, language="ru"
    )

    for i, row in enumerate(rows):
        if len(errors) >= max_errors:
            break
        name = (row.get("name") or "Импорт").strip() or "Импорт"
        phone_raw = (row.get("phone") or "").strip()
        if not phone_raw:
            errors.append(f"Row {i+1}: missing phone")
            skipped += 1
            continue
        phone_norm = normalize_phone(phone_raw)
        if not phone_norm:
            errors.append(f"Row {i+1}: invalid phone")
            skipped += 1
            continue

        external_id_val = (row.get("external_id") or "").strip() or None
        if external_id_val and await crud.lead_exists_by_external(db, tid, "amocrm", external_id_val):
            skipped += 1
            continue
        if not external_id_val and await crud.lead_exists_by_phone_recent(db, tid, phone_norm, days=7):
            skipped += 1
            continue

        try:
            lead = await crud.create_lead(
                db,
                owner_id=owner_id,
                bot_user_id=bot_user.id,
                name=name,
                phone=phone_norm,
                city=(row.get("city") or "").strip() or "",
                object_type=(row.get("object_type") or "").strip() or "",
                area=(row.get("area") or "").strip() or "",
                summary=(row.get("summary") or "").strip() or "",
                language="ru",
                tenant_id=tid,
                source=source,
                external_source="amocrm" if external_id_val else None,
                external_id=external_id_val,
            )
            created += 1
            await try_auto_assign(db, tid, lead, first_message_text=None)
        except Exception as e:
            errors.append(f"Row {i+1}: {type(e).__name__}: {str(e)[:80]}")
            skipped += 1

    return ImportLeadsResponse(
        ok=True,
        mode="commit",
        total_rows=len(rows),
        created=created,
        skipped=skipped,
        errors=errors[:max_errors],
        preview=[],
    )
