from fastapi import HTTPException
from sqlalchemy import func
from sqlmodel import select


def page_result(session, statement, page, page_size, serializer=None):
    total = session.exec(select(func.count()).select_from(statement.subquery())).one()
    rows = session.exec(statement.offset((page - 1) * page_size).limit(page_size)).all()
    return {
        "items": [serializer(row) if serializer else row.model_dump(mode="json") for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_or_404(session, model, identity):
    value = session.get(model, identity)
    if not value:
        raise HTTPException(404, "Record not found")
    return value
