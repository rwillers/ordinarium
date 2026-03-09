from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from html.parser import HTMLParser

from flask import current_app

from .db import get_db
from .plan_tokens import parse_json_object
from .pco_client import api_request, list_all_pages, PcoApiError
from .text_rendering import build_rendered_ordinaries


class PcoSyncError(RuntimeError):
    pass


def _load_service_plan(service_id, user_id):
    db = get_db()
    saved = db.execute(
        """
        select
          id,
          rite,
          text_order,
          text_disabled,
          season,
          service_date,
          observance_handle,
          lesson_overrides,
          offertory_sentence_id,
          proper_overrides,
          service_option_values
        from services
        where id=? and user_id=?
        limit 1
        """,
        (service_id, user_id),
    ).fetchone()
    if not saved:
        return None, []
    saved_data = {
        "observance_handle": saved["observance_handle"],
        "lesson_overrides": parse_json_object(saved["lesson_overrides"]),
        "offertory_sentence_id": saved["offertory_sentence_id"],
        "proper_overrides": parse_json_object(saved["proper_overrides"]),
        "service_option_values": parse_json_object(saved["service_option_values"]),
    }
    ordinaries = build_rendered_ordinaries(
        service_id,
        saved,
        saved_data,
        user_id=user_id,
        link_lesson_references=False,
    )
    return saved, ordinaries or []


def build_pco_item_payloads(items):
    payloads = []
    for item in items:
        title = item.get("detailed_title") or item.get("title") or "Untitled"
        text = item.get("text") or ""
        html_details = _render_markdown_html(text)
        payloads.append(
            {
                "data": {
                    "type": "Item",
                    "attributes": {
                        "title": title,
                        "html_details": html_details,
                    },
                }
            }
        )
    return payloads


def _render_markdown_html(value):
    if not value:
        return ""
    markdown_filter = current_app.jinja_env.filters.get("markdown")
    if not markdown_filter:
        return value
    rendered = str(markdown_filter(value))
    return _strip_pre_code_tags(rendered)


class _StripPreCodeTags(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"pre", "code"}:
            return
        attr_text = ""
        if attrs:
            attr_text = " " + " ".join(
                f'{name}="{value}"' for name, value in attrs if value is not None
            )
        self._parts.append(f"<{tag}{attr_text}>")

    def handle_endtag(self, tag):
        if tag in {"pre", "code"}:
            return
        self._parts.append(f"</{tag}>")

    def handle_startendtag(self, tag, attrs):
        if tag in {"pre", "code"}:
            return
        attr_text = ""
        if attrs:
            attr_text = " " + " ".join(
                f'{name}="{value}"' for name, value in attrs if value is not None
            )
        self._parts.append(f"<{tag}{attr_text} />")

    def handle_data(self, data):
        self._parts.append(data)

    def handle_entityref(self, name):
        self._parts.append(f"&{name};")

    def handle_charref(self, name):
        self._parts.append(f"&#{name};")

    def get_html(self):
        return "".join(self._parts)


def _strip_pre_code_tags(value):
    parser = _StripPreCodeTags()
    parser.feed(value)
    parser.close()
    return parser.get_html()


def list_service_types(base_url, access_token):
    def fetch_page(next_url=None):
        return api_request(
            "GET",
            base_url,
            next_url or "/services/v2/service_types",
            access_token,
            absolute_url=bool(next_url),
        )

    return list_all_pages(fetch_page)


def list_plan_items(base_url, access_token, service_type_id, plan_id):
    path = f"/services/v2/service_types/{service_type_id}/plans/{plan_id}/items"

    def fetch_page(next_url=None):
        return api_request(
            "GET",
            base_url,
            next_url or path,
            access_token,
            absolute_url=bool(next_url),
        )

    return list_all_pages(fetch_page)


def list_plans_for_date(base_url, access_token, service_type_id, service_date):
    path = f"/services/v2/service_types/{service_type_id}/plans"

    def fetch_page(next_url=None, params=None):
        return api_request(
            "GET",
            base_url,
            next_url or path,
            access_token,
            params=params,
            absolute_url=bool(next_url),
        )

    params = {"per_page": 100}
    try:
        payload = fetch_page(params=params)
        data = payload.get("data") or []
        links = payload.get("links") or {}
        next_url = links.get("next")
        while next_url:
            payload = fetch_page(next_url=next_url, params=None)
            data.extend(payload.get("data") or [])
            next_url = (payload.get("links") or {}).get("next")
    except PcoApiError as exc:
        if exc.status_code != 400:
            raise
        data = list_all_pages(lambda next_url: fetch_page(next_url=next_url))

    filtered = []
    for plan in data:
        attributes = plan.get("attributes") or {}
        sort_date = attributes.get("sort_date") or ""
        if sort_date and sort_date.startswith(service_date):
            filtered.append(
                {
                    "id": plan.get("id"),
                    "title": attributes.get("title") or "Untitled plan",
                    "sort_date": sort_date,
                }
            )
    return filtered


def delete_plan_item(base_url, access_token, service_type_id, plan_id, item_id):
    path = (
        f"/services/v2/service_types/{service_type_id}/plans/{plan_id}/items/{item_id}"
    )
    api_request("DELETE", base_url, path, access_token)


def create_plan_item(base_url, access_token, service_type_id, plan_id, payload):
    path = f"/services/v2/service_types/{service_type_id}/plans/{plan_id}/items"
    return api_request("POST", base_url, path, access_token, json=payload)


def fetch_plan(base_url, access_token, service_type_id, plan_id):
    path = f"/services/v2/service_types/{service_type_id}/plans/{plan_id}"
    return api_request("GET", base_url, path, access_token)


def create_plan(
    base_url, access_token, service_type_id, title, plan_date, series_title
):
    attributes = {"title": title}
    if series_title:
        attributes["series_title"] = series_title
    payload = {"data": {"type": "Plan", "attributes": attributes}}
    path = f"/services/v2/service_types/{service_type_id}/plans"
    return api_request("POST", base_url, path, access_token, json=payload)


def create_plan_time(
    base_url,
    access_token,
    service_type_id,
    plan_id,
    plan_date,
    plan_time,
    tz_offset_minutes,
):
    starts_at, ends_at = _build_plan_time_range(plan_date, plan_time, tz_offset_minutes)
    payload = {
        "data": {
            "type": "PlanTime",
            "attributes": {
                "time_type": "service",
                "starts_at": starts_at,
                "ends_at": ends_at,
            },
        }
    }
    path = f"/services/v2/service_types/{service_type_id}/plans/{plan_id}/plan_times"
    return api_request("POST", base_url, path, access_token, json=payload)


def _build_plan_time_range(plan_date, plan_time, tz_offset_minutes):
    if not plan_date or not plan_time:
        raise PcoSyncError("Plan date and time are required.")
    if tz_offset_minutes is None:
        raise PcoSyncError("Timezone offset is required.")
    try:
        service_date = datetime.fromisoformat(plan_date).date()
    except ValueError as exc:
        raise PcoSyncError("Plan date must be in YYYY-MM-DD format.") from exc
    try:
        service_time = time.fromisoformat(plan_time)
    except ValueError as exc:
        raise PcoSyncError("Plan time must be in HH:MM format.") from exc
    try:
        offset_minutes = int(tz_offset_minutes)
    except (TypeError, ValueError) as exc:
        raise PcoSyncError("Timezone offset must be an integer.") from exc
    start_local = datetime.combine(service_date, service_time)
    start_dt = (start_local + timedelta(minutes=offset_minutes)).replace(
        tzinfo=timezone.utc
    )
    end_dt = start_dt + timedelta(hours=1)
    start_str = start_dt.isoformat(timespec="seconds").replace("+00:00", "Z")
    end_str = end_dt.isoformat(timespec="seconds").replace("+00:00", "Z")
    return start_str, end_str


def sync_service_plan(
    service_id,
    user_id,
    access_token,
    base_url,
    service_type_id,
    plan_id,
):
    _service, items = _load_service_plan(service_id, user_id)
    if not _service:
        raise PcoSyncError("Service not found.")
    payloads = build_pco_item_payloads(items)
    try:
        existing_items = list_plan_items(
            base_url, access_token, service_type_id, plan_id
        )
        for item in existing_items:
            delete_plan_item(
                base_url, access_token, service_type_id, plan_id, item["id"]
            )
        for payload in payloads:
            create_plan_item(base_url, access_token, service_type_id, plan_id, payload)
    except PcoApiError as exc:
        raise PcoSyncError(str(exc)) from exc
    return {
        "synced_at": datetime.utcnow().isoformat(),
        "item_count": len(payloads),
    }
