from __future__ import annotations

import requests

from .pco_client import PcoApiError


class RetryablePcoJobError(RuntimeError):
    def __init__(self, message, *, category="network", retry_after_seconds=30):
        super().__init__(message)
        self.category = category
        self.retry_after_seconds = retry_after_seconds


class TerminalPcoAuthError(RuntimeError):
    pass


class TerminalPcoJobError(RuntimeError):
    def __init__(self, message, *, category="validation"):
        super().__init__(message)
        self.category = category


def raise_if_retryable_pco_error(error):
    cause = getattr(error, "__cause__", None)
    if cause is not None and cause is not error:
        raise_if_retryable_pco_error(cause)
    if isinstance(error, RetryablePcoJobError):
        raise error
    if isinstance(error, requests.RequestException):
        raise RetryablePcoJobError(str(error), category="network") from error
    if not isinstance(error, PcoApiError):
        return
    if error.status_code == 429:
        retry_after = _retry_after(error.payload) or 30
        raise RetryablePcoJobError(
            str(error), category="rate_limit", retry_after_seconds=retry_after
        ) from error
    if error.status_code is None or error.status_code >= 500:
        raise RetryablePcoJobError(str(error), category="provider") from error


def pco_error_category(error):
    if isinstance(error, RetryablePcoJobError):
        return error.category
    if isinstance(error, PcoApiError):
        if error.status_code in {401, 403}:
            return "auth"
        if error.status_code in {400, 404}:
            return "validation"
    return "validation"


def raise_if_terminal_pco_auth(error):
    cause = getattr(error, "__cause__", None)
    if cause is not None and cause is not error:
        raise_if_terminal_pco_auth(cause)
    if isinstance(error, PcoApiError) and error.status_code in {401, 403}:
        raise TerminalPcoAuthError(str(error)) from error


def raise_if_terminal_pco_error(error):
    cause = getattr(error, "__cause__", None)
    if cause is not None and cause is not error:
        raise_if_terminal_pco_error(cause)
    if isinstance(error, PcoApiError) and error.status_code in {400, 404}:
        raise TerminalPcoJobError(str(error), category="validation") from error
    if error.__class__.__name__ != "PcoSyncError":
        return
    message = str(error) or "Planning Center sync validation failed."
    category = (
        "manual_resolution"
        if "manual resolution" in message.lower()
        or "uncertain result" in message.lower()
        else "validation"
    )
    raise TerminalPcoJobError(message, category=category) from error


def _retry_after(payload):
    if not isinstance(payload, dict):
        return None
    value = payload.get("retry_after") or payload.get("retry_after_seconds")
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return max(1, min(parsed, 3600))
