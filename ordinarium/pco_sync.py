from __future__ import annotations

import hashlib
import json
from datetime import datetime, time, timedelta, timezone
from html.parser import HTMLParser

from flask import current_app

from .db import get_db
from .plan_tokens import parse_json_object
from .pco_client import api_request, list_all_pages, PcoApiError
from .pco_store import (
    delete_service_pco_item_link,
    list_service_pco_item_links,
    upsert_service_pco_item_link,
)
from .text_rendering import build_rendered_ordinaries


class PcoSyncError(RuntimeError):
    pass


def _load_service_plan(service_id, user_id):
    db = get_db()
    saved = db.execute(
        """
        select
          services.id,
          services.rite,
          services.text_order,
          services.text_disabled,
          services.season,
          services.service_date,
          services.observance_handle,
          services.lesson_overrides,
          services.offertory_sentence_id,
          services.proper_overrides,
          services.service_option_values,
          users.greeting_response_form as owner_greeting_response_form
        from services
        left join users on users.id=services.user_id
        where services.id=? and services.user_id=?
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
        "greeting_response_form": saved["owner_greeting_response_form"],
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
    for position, item in enumerate(items):
        title = item.get("detailed_title") or item.get("title") or "Untitled"
        text = item.get("text") or ""
        html_details = _render_markdown_html(text)
        attributes = {
            "title": title,
            "html_details": html_details,
        }
        content_hash = _pco_item_content_hash(attributes)
        payloads.append(
            {
                "token": item.get("token"),
                "position": position,
                "content_hash": content_hash,
                "payload": {
                    "data": {
                        "type": "Item",
                        "attributes": attributes,
                    },
                },
            }
        )
    return payloads


def _pco_item_content_hash(attributes):
    normalized = json.dumps(
        {
            "title": attributes.get("title") or "",
            "html_details": attributes.get("html_details") or "",
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


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


def list_plan_templates(base_url, access_token, service_type_id):
    path = f"/services/v2/service_types/{service_type_id}/plan_templates"

    def fetch_page(next_url=None):
        return api_request(
            "GET",
            base_url,
            next_url or path,
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


def update_plan_item(
    base_url, access_token, service_type_id, plan_id, item_id, payload
):
    path = (
        f"/services/v2/service_types/{service_type_id}/plans/{plan_id}/items/{item_id}"
    )
    return api_request("PATCH", base_url, path, access_token, json=payload)


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


def import_plan_template(
    base_url, access_token, service_type_id, plan_id, plan_template_id
):
    if not plan_template_id:
        return None
    source_plan_id = str(plan_template_id)
    if source_plan_id.isdigit():
        source_plan_id = int(source_plan_id)
    payload = {
        "data": {
            "attributes": {
                "plan_id": source_plan_id,
                "copy_items": False,
                "copy_people": True,
                "copy_notes": True,
            }
        }
    }
    path = (
        f"/services/v2/service_types/{service_type_id}/plans/"
        f"{plan_id}/import_template"
    )
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
        _sync_pco_item_delta(
            service_id,
            base_url,
            access_token,
            service_type_id,
            plan_id,
            payloads,
        )
    except PcoApiError as exc:
        raise PcoSyncError(str(exc)) from exc
    return {
        "synced_at": datetime.utcnow().isoformat(),
        "item_count": len(payloads),
    }


def _sync_pco_item_delta(
    service_id,
    base_url,
    access_token,
    service_type_id,
    plan_id,
    payloads,
):
    db = get_db()
    existing_items = list_plan_items(base_url, access_token, service_type_id, plan_id)
    existing_item_ids = {
        str(item.get("id")) for item in existing_items if item.get("id") is not None
    }
    linked_rows = list_service_pco_item_links(service_id, db=db)
    linked_by_token = {row["ordinarium_token"]: row for row in linked_rows}
    desired_tokens = [payload["token"] for payload in payloads if payload.get("token")]

    if _requires_order_rebuild(payloads, linked_by_token, existing_item_ids):
        _rebuild_linked_plan_items(
            service_id,
            base_url,
            access_token,
            service_type_id,
            plan_id,
            payloads,
            linked_by_token,
            existing_item_ids,
            db,
        )
        return

    for row in linked_rows:
        token = row["ordinarium_token"]
        pco_item_id = str(row["pco_item_id"])
        if token in desired_tokens:
            continue
        if pco_item_id in existing_item_ids:
            delete_plan_item(
                base_url, access_token, service_type_id, plan_id, pco_item_id
            )
        delete_service_pco_item_link(service_id, token, db=db)

    for payload in payloads:
        token = payload.get("token")
        if not token:
            continue
        linked = linked_by_token.get(token)
        pco_item_id = str(linked["pco_item_id"]) if linked else ""
        if linked and pco_item_id in existing_item_ids:
            if linked.get("last_content_hash") != payload["content_hash"]:
                update_plan_item(
                    base_url,
                    access_token,
                    service_type_id,
                    plan_id,
                    pco_item_id,
                    payload["payload"],
                )
            upsert_service_pco_item_link(
                service_id,
                token,
                pco_item_id,
                last_content_hash=payload["content_hash"],
                last_position=payload["position"],
                db=db,
            )
            continue
        created = create_plan_item(
            base_url,
            access_token,
            service_type_id,
            plan_id,
            payload["payload"],
        )
        created_id = _extract_pco_item_id(created)
        if not created_id:
            raise PcoSyncError("PCO item creation failed.")
        upsert_service_pco_item_link(
            service_id,
            token,
            created_id,
            last_content_hash=payload["content_hash"],
            last_position=payload["position"],
            db=db,
        )


def _requires_order_rebuild(payloads, linked_by_token, existing_item_ids):
    desired_linked = [
        payload
        for payload in payloads
        if payload.get("token")
        and payload.get("token") in linked_by_token
        and str(linked_by_token[payload["token"]]["pco_item_id"]) in existing_item_ids
    ]
    if len(desired_linked) < 2:
        return any(
            linked_by_token[payload["token"]]["last_position"] != payload["position"]
            for payload in desired_linked
        )
    previous_order = sorted(
        desired_linked,
        key=lambda payload: (
            linked_by_token[payload["token"]]["last_position"]
            if linked_by_token[payload["token"]]["last_position"] is not None
            else payload["position"]
        ),
    )
    if [payload["token"] for payload in previous_order] != [
        payload["token"] for payload in desired_linked
    ]:
        return True
    return any(
        linked_by_token[payload["token"]]["last_position"] != payload["position"]
        for payload in desired_linked
    )


def _rebuild_linked_plan_items(
    service_id,
    base_url,
    access_token,
    service_type_id,
    plan_id,
    payloads,
    linked_by_token,
    existing_item_ids,
    db,
):
    for row in linked_by_token.values():
        pco_item_id = str(row["pco_item_id"])
        if pco_item_id in existing_item_ids:
            delete_plan_item(
                base_url, access_token, service_type_id, plan_id, pco_item_id
            )
        delete_service_pco_item_link(service_id, row["ordinarium_token"], db=db)
    for payload in payloads:
        token = payload.get("token")
        if not token:
            continue
        created = create_plan_item(
            base_url,
            access_token,
            service_type_id,
            plan_id,
            payload["payload"],
        )
        created_id = _extract_pco_item_id(created)
        if not created_id:
            raise PcoSyncError("PCO item creation failed.")
        upsert_service_pco_item_link(
            service_id,
            token,
            created_id,
            last_content_hash=payload["content_hash"],
            last_position=payload["position"],
            db=db,
        )


def _extract_pco_item_id(payload):
    data = payload.get("data") if payload else None
    if not data:
        return None
    item_id = data.get("id")
    if item_id is None:
        return None
    return str(item_id)
