"""
MODULE: In-app Notifications.
Creates notifications for individual users or for everyone holding a given role,
so that submitters and reviewers are kept informed without needing email/SMS
integration (which was not available in this training environment).
"""
from sqlalchemy.orm import Session
from app.models.models import Notification, User, RoleEnum


def notify_user(
    db: Session,
    user_id: str,
    message: str,
    notif_type: str = "INFO",
    related_entity_type: str | None = None,
    related_entity_id: str | None = None,
) -> Notification:
    notification = Notification(
        user_id=user_id,
        type=notif_type,
        message=message,
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
    )
    db.add(notification)
    db.commit()
    return notification


def notify_roles(
    db: Session,
    roles: list[RoleEnum],
    message: str,
    notif_type: str = "INFO",
    related_entity_type: str | None = None,
    related_entity_id: str | None = None,
    exclude_user_id: str | None = None,
) -> None:
    """Send the same notification to every active user holding one of the given roles."""
    users = db.query(User).filter(User.role.in_(roles), User.is_active == True).all()  # noqa: E712
    for user in users:
        if exclude_user_id and user.id == exclude_user_id:
            continue
        db.add(Notification(
            user_id=user.id,
            type=notif_type,
            message=message,
            related_entity_type=related_entity_type,
            related_entity_id=related_entity_id,
        ))
    db.commit()


def notify_institution_users(
    db: Session,
    institution_id: str,
    message: str,
    notif_type: str = "INFO",
    related_entity_type: str | None = None,
    related_entity_id: str | None = None,
) -> None:
    """Send the same notification to every active user belonging to a given institution."""
    users = db.query(User).filter(
        User.institution_id == institution_id, User.is_active == True  # noqa: E712
    ).all()
    for user in users:
        db.add(Notification(
            user_id=user.id,
            type=notif_type,
            message=message,
            related_entity_type=related_entity_type,
            related_entity_id=related_entity_id,
        ))
    db.commit()
