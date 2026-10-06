from sqlmodel import Session

from app.modules.catalog.models import Widget


def get_widget(session: Session, widget_id: int) -> Widget | None:
    return session.get(Widget, widget_id)
