from flask import request, session
from models import AuditLog, db


def log_action(action: str, detail: str = None, user_id: int = None) -> None:
    entry = AuditLog(
        user_id=user_id or session.get("user_id"),
        action=action,
        detail=detail,
        ip=request.remote_addr,
    )
    db.session.add(entry)
    db.session.commit()