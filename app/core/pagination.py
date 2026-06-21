import base64
import json
from datetime import datetime
from typing import Any
from uuid import UUID


def encode_cursor(sort_value: Any, id_value: UUID) -> str:

    payload = {
        "v": (
            sort_value.isoformat()
            if isinstance(sort_value, datetime)
            else str(sort_value)
        ),
        "id": str(id_value),
    }
    raw = json.dumps(payload).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8")


def decode_cursor(cursor: str) -> tuple[str, UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("utf-8"))
        payload = json.loads(raw)
        return payload["v"], UUID(payload["id"])
    except Exception:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="Invalid pagination cursor")
