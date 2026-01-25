from flask import current_app
from flask_mail import Mail, Message

mail = Mail()


def init_mail(app):
    mail.init_app(app)


def send_email(recipient, subject, body):
    if not current_app.config.get("MAIL_SERVER"):
        current_app.logger.info(
            "Email to %s\nSubject: %s\n\n%s", recipient, subject, body
        )
        return True
    sender = (
        current_app.config.get("MAIL_DEFAULT_SENDER")
        or current_app.config.get("MAIL_USERNAME")
        or "no-reply@ordinarium"
    )
    message = Message(
        subject=subject,
        recipients=[recipient],
        body=body,
        sender=sender,
    )
    try:
        mail.send(message)
        return True
    except Exception:
        current_app.logger.exception("Failed to send email to %s", recipient)
        return False
