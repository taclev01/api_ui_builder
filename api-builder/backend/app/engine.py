from __future__ import annotations

import ast
import base64
import copy
import json
import math
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib import error, parse, request
from uuid import UUID

from psycopg import Connection

from . import repository as repo
from .config import settings

TEMPLATE_RE = re.compile(r"{{\s*(.*?)\s*}}")


@dataclass
class NodeDef:
    id: str
    node_type: str
    label: str
    config: dict[str, Any]
    raw: dict[str, Any]


@dataclass
class ExecutionContext:
    vars: dict[str, Any]
    nodes: dict[str, dict[str, Any]]
    system: dict[str, Any]

    def to_json(self) -> dict[str, Any]:
        return {
            "vars": self.vars,
            "nodes": self.nodes,
            "system": self.system,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any] | None) -> "ExecutionContext":
        payload = payload or {}
        vars_payload = payload.get("vars")
        nodes_payload = payload.get("nodes")
        system_payload = payload.get("system")
        return cls(
            vars=vars_payload if isinstance(vars_payload, dict) else {},
            nodes=nodes_payload if isinstance(nodes_payload, dict) else {},
            system=system_payload if isinstance(system_payload, dict) else {},
        )


class DotValue:
    def __init__(self, value: Any):
        self._value = value

    def __getattr__(self, item: str) -> Any:
        if isinstance(self._value, dict):
            return wrap_dot(self._value.get(item))
        raise AttributeError(item)

    def __getitem__(self, item: Any) -> Any:
        if isinstance(self._value, (dict, list)):
            return wrap_dot(self._value[item])
        raise TypeError(f"Unsupported indexing on {type(self._value).__name__}")

    def __iter__(self):  # type: ignore[no-untyped-def]
        if isinstance(self._value, list):
            return iter([wrap_dot(v) for v in self._value])
        if isinstance(self._value, dict):
            return iter(self._value)
        return iter([])

    def __len__(self) -> int:
        return len(self._value) if isinstance(self._value, (dict, list, str, tuple)) else 0

    def __bool__(self) -> bool:
        return bool(self._value)

    def __eq__(self, other: Any) -> bool:
        return self._value == unwrap_dot(other)

    def __lt__(self, other: Any) -> bool:
        return self._value < unwrap_dot(other)

    def __le__(self, other: Any) -> bool:
        return self._value <= unwrap_dot(other)

    def __gt__(self, other: Any) -> bool:
        return self._value > unwrap_dot(other)

    def __ge__(self, other: Any) -> bool:
        return self._value >= unwrap_dot(other)

    def __contains__(self, item: Any) -> bool:
        if isinstance(self._value, (dict, list, str, tuple)):
            return unwrap_dot(item) in self._value
        return False

    def __str__(self) -> str:
        return str(self._value)

    def __repr__(self) -> str:
        return repr(self._value)

    @property
    def value(self) -> Any:
        return self._value


def wrap_dot(value: Any) -> Any:
    if isinstance(value, DotValue):
        return value
    if isinstance(value, (dict, list)):
        return DotValue(value)
    return value


def unwrap_dot(value: Any) -> Any:
    if isinstance(value, DotValue):
        return value.value
    return value


def _node_from_graph(node: dict[str, Any]) -> NodeDef:
    data = node.get("data")
    if isinstance(data, dict):
        node_type = data.get("nodeType")
        config = data.get("config")
        label = data.get("label")
    else:
        node_type = node.get("type")
        config = node.get("config")
        label = node.get("label")

    return NodeDef(
        id=str(node.get("id")),
        node_type=str(node_type or node.get("type") or "unknown"),
        label=str(label or node_type or node.get("id") or "node"),
        config=config if isinstance(config, dict) else {},
        raw=node,
    )


def _normalize_edge(edge: dict[str, Any]) -> dict[str, Any]:
    data = edge.get("data")
    edge_data = data if isinstance(data, dict) else {}
    condition = edge_data.get("condition")
    if condition not in {"true", "false"}:
        source_handle = edge.get("sourceHandle")
        if source_handle in {"true", "false"}:
            condition = source_handle
        else:
            condition = None
    return {
        "id": str(edge.get("id")),
        "source": str(edge.get("source")),
        "target": str(edge.get("target")),
        "source_handle": edge.get("sourceHandle"),
        "target_handle": edge.get("targetHandle"),
        "condition": condition,
        "breakpoint": bool(edge_data.get("breakpoint")),
        "raw": edge,
    }


def _index_graph(graph: dict[str, Any]) -> tuple[dict[str, NodeDef], dict[str, list[dict[str, Any]]]]:
    nodes = {_node.id: _node for _node in (_node_from_graph(n) for n in graph.get("nodes", []))}
    outgoing: dict[str, list[dict[str, Any]]] = {}
    for edge in graph.get("edges", []):
        normalized = _normalize_edge(edge)
        outgoing.setdefault(normalized["source"], []).append(normalized)
    return nodes, outgoing


def _write_snapshot_if_needed(conn: Connection, execution_id: UUID, context: ExecutionContext) -> None:
    next_idx = repo.get_next_event_index(conn, execution_id)
    if next_idx > 0 and next_idx % settings.snapshot_interval == 0:
        repo.create_snapshot(
            conn,
            execution_id=execution_id,
            event_index=next_idx - 1,
            context_json=context.to_json(),
        )
        repo.append_event(
            conn,
            execution_id=execution_id,
            event_type="SNAPSHOT_WRITTEN",
            payload={"event_index": next_idx - 1},
        )


def _context_env(context: ExecutionContext) -> dict[str, Any]:
    return {
        "vars": wrap_dot(context.vars),
        "nodes": wrap_dot(context.nodes),
        "system": wrap_dot(context.system),
        "input": wrap_dot(context.vars.get("input", {})),
        "last_response": wrap_dot(context.system.get("last_response")),
        "True": True,
        "False": False,
        "None": None,
    }


def _eval_expression(expression: str, context: ExecutionContext) -> Any:
    parsed = ast.parse(expression, mode="eval")
    # Hard limit on expression complexity for predictable runtime.
    if len(list(ast.walk(parsed))) > 250:
        raise RuntimeError("Expression is too complex")

    safe_globals = {"__builtins__": {}}
    safe_locals = _context_env(context) | {
        "len": len,
        "min": min,
        "max": max,
        "sum": sum,
        "any": any,
        "all": all,
        "int": int,
        "float": float,
        "str": str,
        "bool": bool,
        "abs": abs,
    }
    return unwrap_dot(eval(compile(parsed, "<expr>", "eval"), safe_globals, safe_locals))  # noqa: S307


def _split_path(path: str) -> list[str]:
    normalized = path.strip()
    if normalized.startswith("$."):
        normalized = normalized[2:]
    elif normalized.startswith("$"):
        normalized = normalized[1:]
    return [part for part in normalized.split(".") if part]


def _resolve_path(root: Any, path: str) -> Any:
    if path.strip() == "":
        return root
    current = root
    for part in _split_path(path):
        current = unwrap_dot(current)
        if isinstance(current, dict):
            current = current.get(part)
            continue
        if isinstance(current, list):
            try:
                idx = int(part)
            except ValueError:
                return None
            if idx < 0 or idx >= len(current):
                return None
            current = current[idx]
            continue
        return None
    return current


def _resolve_value(expr_or_path: str, context: ExecutionContext) -> Any:
    text = expr_or_path.strip()
    if text == "":
        return None
    if any(op in text for op in ("==", "!=", ">=", "<=", " and ", " or ", " not ", "(", ")")):
        return _eval_expression(text, context)
    if text.startswith(("vars.", "nodes.", "system.", "input.", "last_response.", "$")):
        root = {
            "vars": context.vars,
            "nodes": context.nodes,
            "system": context.system,
            "input": context.vars.get("input", {}),
            "last_response": context.system.get("last_response"),
        }
        return _resolve_path(root, text)
    return _resolve_path(context.to_json(), text)


def _render_template(value: Any, context: ExecutionContext) -> Any:
    if isinstance(value, str):
        def repl(match: re.Match[str]) -> str:
            resolved = _resolve_value(match.group(1), context)
            if resolved is None:
                return ""
            if isinstance(resolved, (dict, list)):
                return json.dumps(resolved)
            return str(resolved)

        if "{{" in value and "}}" in value:
            return TEMPLATE_RE.sub(repl, value)
        return value
    if isinstance(value, dict):
        return {k: _render_template(v, context) for k, v in value.items()}
    if isinstance(value, list):
        return [_render_template(item, context) for item in value]
    return value


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _resolve_auth_definitions(nodes: dict[str, NodeDef]) -> dict[str, dict[str, dict[str, Any]]]:
    defs: dict[str, dict[str, dict[str, Any]]] = {}
    for node in nodes.values():
        if node.node_type != "auth":
            continue
        auth_list_raw = node.config.get("authList")
        entries = auth_list_raw if isinstance(auth_list_raw, list) else []
        if not entries:
            entries = [
                {
                    "name": "default",
                    "authType": node.config.get("authType", "bearer"),
                    "tokenVar": node.config.get("tokenVar", "vars.token"),
                    "headerName": node.config.get("headerName", "Authorization"),
                }
            ]

        node_defs: dict[str, dict[str, Any]] = {}
        for idx, raw in enumerate(entries, start=1):
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("name") or f"auth_{idx}")
            node_defs[name] = raw
        defs[node.id] = node_defs
    return defs


def _auth_headers(auth_ref: str, auth_defs: dict[str, dict[str, dict[str, Any]]], context: ExecutionContext) -> dict[str, str]:
    if not auth_ref:
        return {}
    if "::" not in auth_ref:
        return {}
    node_id, entry_name = auth_ref.split("::", 1)
    node_map = auth_defs.get(node_id)
    if not node_map:
        return {}
    entry = node_map.get(entry_name)
    if not entry:
        return {}

    auth_type = str(entry.get("authType", "bearer")).lower()
    header_name = str(entry.get("headerName", "Authorization"))
    token_ref = str(entry.get("tokenVar", "vars.token"))
    token_value = _resolve_value(token_ref, context)
    token_str = "" if token_value is None else str(token_value)

    if auth_type == "bearer":
        return {header_name: token_str if token_str.lower().startswith("bearer ") else f"Bearer {token_str}"}
    if auth_type in {"api_key", "apikey", "key"}:
        return {header_name: token_str}
    if auth_type == "basic":
        username = str(_resolve_value(str(entry.get("usernameVar", "vars.username")), context) or "")
        password = str(_resolve_value(str(entry.get("passwordVar", "vars.password")), context) or "")
        encoded = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        return {header_name: f"Basic {encoded}"}
    return {header_name: token_str}


def _extract_items(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if payload is None:
        return []
    return [payload]


def _http_request(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    body: Any,
    timeout_ms: int,
) -> dict[str, Any]:
    body_bytes: bytes | None
    req_headers = {k: v for k, v in headers.items() if isinstance(k, str)}

    if body is None:
        body_bytes = None
    elif isinstance(body, (dict, list)):
        body_bytes = json.dumps(body).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    elif isinstance(body, (str, int, float, bool)):
        body_bytes = str(body).encode("utf-8")
    else:
        body_bytes = json.dumps(body, default=str).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")

    req = request.Request(url=url, data=body_bytes, method=method.upper(), headers=req_headers)
    started = time.perf_counter()
    timeout_seconds = max(1, timeout_ms) / 1000

    try:
        with request.urlopen(req, timeout=timeout_seconds) as resp:  # noqa: S310
            raw = resp.read()
            status_code = int(resp.status)
            response_headers = dict(resp.headers.items())
    except error.HTTPError as exc:
        raw = exc.read() if hasattr(exc, "read") else b""
        status_code = int(exc.code)
        response_headers = dict(exc.headers.items()) if exc.headers else {}
    except Exception as exc:
        raise RuntimeError(f"Request failed: {exc}") from exc

    duration_ms = int((time.perf_counter() - started) * 1000)
    content_type = (response_headers.get("Content-Type") or "").lower()
    text_body = raw.decode("utf-8", errors="replace")
    if "application/json" in content_type:
        try:
            parsed_body: Any = json.loads(text_body)
        except json.JSONDecodeError:
            parsed_body = text_body
    else:
        parsed_body = text_body

    return {
        "status_code": status_code,
        "headers": response_headers,
        "body": parsed_body,
        "url": url,
        "method": method.upper(),
        "duration_ms": duration_ms,
    }


def _with_resilience(
    *,
    context: ExecutionContext,
    node_id: str,
    retry_attempts: int,
    backoff: str,
    threshold: int,
    open_ms: int,
    fn: Any,
) -> dict[str, Any]:
    circuits = context.system.setdefault("circuit_breakers", {})
    circuit = circuits.setdefault(node_id, {"failures": 0, "open_until_ms": 0})
    now_ms = int(time.time() * 1000)
    open_until = _coerce_int(circuit.get("open_until_ms"), 0)
    if open_until > now_ms:
        raise RuntimeError(f"Circuit open for node {node_id} until {open_until}")

    attempts_total = max(0, retry_attempts) + 1
    last_error: Exception | None = None
    for attempt in range(1, attempts_total + 1):
        try:
            response = fn()
            status_code = _coerce_int(response.get("status_code"), 0)
            if status_code >= 500:
                raise RuntimeError(f"Upstream server error {status_code}")
            circuit["failures"] = 0
            circuit["open_until_ms"] = 0
            return response
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            failures = _coerce_int(circuit.get("failures"), 0) + 1
            circuit["failures"] = failures
            if threshold > 0 and failures >= threshold:
                circuit["open_until_ms"] = int(time.time() * 1000) + max(open_ms, 100)
            if attempt >= attempts_total:
                break
            sleep_s = 0.2 if backoff != "exponential" else 0.2 * (2 ** (attempt - 1))
            time.sleep(min(sleep_s, 2.5))
    raise RuntimeError(str(last_error) if last_error else "Request failed")


def _request_from_node(
    *,
    node: NodeDef,
    context: ExecutionContext,
    auth_defs: dict[str, dict[str, dict[str, Any]]],
    url: str | None = None,
    extra_query: dict[str, Any] | None = None,
) -> dict[str, Any]:
    method = str(node.config.get("method", "GET")).upper()
    timeout_ms = _coerce_int(node.config.get("timeoutMs"), 10000)
    retry_attempts = _coerce_int(node.config.get("retryAttempts"), 0)
    backoff = str(node.config.get("backoff", "exponential"))
    threshold = _coerce_int(node.config.get("circuitFailureThreshold"), 5)
    open_ms = _coerce_int(node.config.get("circuitOpenMs"), 30000)
    base_url = _render_template(url if url is not None else str(node.config.get("url", "")), context)
    if not isinstance(base_url, str) or base_url.strip() == "":
        raise RuntimeError(f"{node.node_type} node requires URL")

    final_url = base_url
    if extra_query:
        parsed = parse.urlparse(base_url)
        query = dict(parse.parse_qsl(parsed.query, keep_blank_values=True))
        for k, v in extra_query.items():
            if v is None:
                continue
            query[str(k)] = str(v)
        parsed = parsed._replace(query=parse.urlencode(query))
        final_url = parse.urlunparse(parsed)

    auth_ref = str(node.config.get("authRef", ""))
    headers_raw = node.config.get("headers")
    headers = _render_template(headers_raw, context) if isinstance(headers_raw, dict) else {}
    if not isinstance(headers, dict):
        headers = {}
    headers = {str(k): str(v) for k, v in headers.items()}
    headers |= _auth_headers(auth_ref, auth_defs, context)
    body = _render_template(node.config.get("body"), context)

    response = _with_resilience(
        context=context,
        node_id=node.id,
        retry_attempts=retry_attempts,
        backoff=backoff,
        threshold=threshold,
        open_ms=open_ms,
        fn=lambda: _http_request(
            method=method,
            url=final_url,
            headers=headers,
            body=body,
            timeout_ms=timeout_ms,
        ),
    )
    context.system["last_response"] = response
    context.system["last_response_node_id"] = node.id
    return response


def _execute_paginate_request(
    *,
    node: NodeDef,
    context: ExecutionContext,
    auth_defs: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, Any]:
    strategy = str(node.config.get("strategy", "next_url"))
    max_pages = max(1, _coerce_int(node.config.get("maxPages"), 25))
    page_size = max(1, _coerce_int(node.config.get("pageSize"), 100))
    items_path = str(node.config.get("itemsPath", "body.items"))
    next_path = str(node.config.get("nextCursorPath", "body.next"))
    has_more_path = str(node.config.get("hasMorePath", "body.has_more"))
    cursor_name = str(node.config.get("cursorParamName", "cursor"))
    page_name = str(node.config.get("pageParamName", "page"))
    size_name = str(node.config.get("pageSizeParamName", "page_size"))
    offset_name = str(node.config.get("offsetParamName", "offset"))
    limit_name = str(node.config.get("limitParamName", "limit"))

    next_url: str | None = None
    cursor: Any = None
    offset = 0
    page = 1

    all_items: list[Any] = []
    pages: list[dict[str, Any]] = []
    for _ in range(max_pages):
        query: dict[str, Any] = {}
        request_url: str | None = None
        if strategy == "next_url":
            request_url = next_url or None
        elif strategy == "cursor_param":
            query[size_name] = page_size
            if cursor is not None:
                query[cursor_name] = cursor
        elif strategy == "offset_limit":
            query[offset_name] = offset
            query[limit_name] = page_size
        else:  # page_number
            query[page_name] = page
            query[size_name] = page_size

        response = _request_from_node(
            node=node,
            context=context,
            auth_defs=auth_defs,
            url=request_url,
            extra_query=query,
        )
        pages.append(response)

        items = _extract_items(_resolve_path({"body": response.get("body")}, items_path))
        all_items.extend(items)

        if strategy == "next_url":
            next_url_raw = _resolve_path({"body": response.get("body")}, next_path)
            if not isinstance(next_url_raw, str) or next_url_raw.strip() == "":
                break
            next_url = next_url_raw
        elif strategy == "cursor_param":
            cursor = _resolve_path({"body": response.get("body")}, next_path)
            if cursor in (None, "", False):
                break
        elif strategy == "offset_limit":
            if len(items) < page_size:
                break
            offset += page_size
        else:
            has_more = _resolve_path({"body": response.get("body")}, has_more_path)
            if not _coerce_bool(has_more):
                break
            page += 1

    result = {
        "status_code": 200 if pages else 204,
        "pages_fetched": len(pages),
        "items": all_items,
        "pages": pages,
    }
    context.system["last_response"] = pages[-1] if pages else result
    context.system["last_response_node_id"] = node.id
    return result


def _execute_python_node(node: NodeDef, context: ExecutionContext) -> Any:
    code = str(node.config.get("code", ""))
    function_name = str(node.config.get("functionName", "run"))
    if not code.strip():
        raise RuntimeError(f"{node.node_type} requires Python code")

    safe_globals = {
        "__builtins__": {
            "len": len,
            "min": min,
            "max": max,
            "sum": sum,
            "any": any,
            "all": all,
            "int": int,
            "float": float,
            "str": str,
            "bool": bool,
            "dict": dict,
            "list": list,
            "set": set,
            "tuple": tuple,
            "enumerate": enumerate,
            "range": range,
            "abs": abs,
        },
        "json": json,
        "math": math,
        "datetime": datetime,
        "time": time,
    }
    local_ns: dict[str, Any] = {}
    exec(compile(code, f"<{node.id}>", "exec"), safe_globals, local_ns)  # noqa: S102

    fn = local_ns.get(function_name) or safe_globals.get(function_name)
    if not callable(fn):
        raise RuntimeError(f"Function '{function_name}' not found for node {node.id}")

    context_payload = context.to_json()
    result = fn(context_payload)
    return result


def _resolve_workflow_version_for_invocation(
    conn: Connection,
    node_config: dict[str, Any],
) -> dict[str, Any]:
    target_workflow_version_id = node_config.get("targetWorkflowVersionId")
    target_workflow_id = node_config.get("targetWorkflowId")
    published_only = _coerce_bool(node_config.get("publishedOnly", True))

    if isinstance(target_workflow_version_id, str) and target_workflow_version_id:
        version = repo.get_workflow_version(conn, UUID(target_workflow_version_id))
        if not version:
            raise RuntimeError("invoke_workflow target workflow version not found")
        return version

    if isinstance(target_workflow_id, str) and target_workflow_id:
        if published_only:
            version = repo.get_latest_published_workflow_version(conn, UUID(target_workflow_id))
        else:
            version = repo.get_latest_workflow_version(conn, UUID(target_workflow_id))
        if not version:
            raise RuntimeError("invoke_workflow target workflow version not found")
        return version

    raise RuntimeError("invoke_workflow requires targetWorkflowVersionId or targetWorkflowId")


def _select_next_edge(
    *,
    node: NodeDef,
    outgoing: dict[str, list[dict[str, Any]]],
    node_output: dict[str, Any],
) -> dict[str, Any] | None:
    edges = outgoing.get(node.id, [])
    if not edges:
        return None
    if node.node_type == "if":
        result = _coerce_bool(node_output.get("result"))
        desired = "true" if result else "false"
        for edge in edges:
            if edge.get("condition") == desired:
                return edge
    return edges[0]


def _apply_parameter_defaults(nodes: dict[str, NodeDef], context: ExecutionContext) -> None:
    for node in nodes.values():
        if node.node_type != "parameters":
            continue
        params_raw = node.config.get("parameters")
        params = params_raw if isinstance(params_raw, list) else []
        for raw in params:
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("name", "")).strip()
            if not name:
                continue
            if name not in context.vars:
                context.vars[name] = raw.get("defaultValue")


def _execute_node(
    conn: Connection,
    execution_id: UUID,
    node: NodeDef,
    context: ExecutionContext,
    auth_defs: dict[str, dict[str, dict[str, Any]]],
    call_depth: int,
    correlation_id: str | None,
) -> dict[str, Any]:
    config = node.config

    if node.node_type in {"auth", "parameters", "start"}:
        return {"node_type": node.node_type}

    if node.node_type == "delay":
        ms = max(0, _coerce_int(config.get("ms"), 0))
        time.sleep(ms / 1000)
        return {"slept_ms": ms}

    if node.node_type == "define_variable":
        name = str(config.get("name", "")).strip()
        source = str(config.get("source", "last_response"))
        selector = str(config.get("selector", ""))
        default_value = config.get("defaultValue")

        if source == "last_response":
            base = context.system.get("last_response")
        elif source == "node_output":
            base = context.nodes
        else:
            base = context.to_json()

        value = _resolve_path(base, selector) if selector else base
        if value is None and default_value is not None:
            value = default_value
        if name:
            context.vars[name] = value
        return {"name": name, "value": value}

    if node.node_type == "if":
        expression = str(config.get("expression", "False"))
        result = _coerce_bool(_eval_expression(expression, context))
        return {"expression": expression, "result": result}

    if node.node_type == "for_each_parallel":
        list_expr = str(config.get("listExpr", "vars.items"))
        item_name = str(config.get("itemName", "item")).strip() or "item"
        values = _resolve_value(list_expr, context)
        items = _extract_items(values)
        context.system.setdefault("parallel", {})[node.id] = {
            "item_name": item_name,
            "items": items,
            "count": len(items),
        }
        context.vars[f"{item_name}_items"] = items
        return {"item_name": item_name, "count": len(items)}

    if node.node_type == "join":
        strategy = str(config.get("mergeStrategy", "collect_list"))
        parallel = context.system.get("parallel", {})
        merged: Any = parallel
        if strategy == "last_write_wins":
            merged = {k: v for k, v in parallel.items()}
        elif strategy == "merge_objects":
            flat: dict[str, Any] = {}
            for payload in parallel.values():
                if isinstance(payload, dict):
                    flat |= payload
            merged = flat
        context.vars["joined"] = merged
        return {"merge_strategy": strategy, "joined": merged}

    if node.node_type in {"start_request", "form_request"}:
        return _request_from_node(node=node, context=context, auth_defs=auth_defs)

    if node.node_type == "paginate_request":
        return _execute_paginate_request(node=node, context=context, auth_defs=auth_defs)

    if node.node_type == "python_request":
        result = _execute_python_node(node, context)
        if isinstance(result, dict) and "status_code" in result and "body" in result:
            context.system["last_response"] = result
            context.system["last_response_node_id"] = node.id
            return result
        wrapped = {"status_code": 200, "body": result}
        context.system["last_response"] = wrapped
        context.system["last_response_node_id"] = node.id
        return wrapped

    if node.node_type == "start_python":
        result = _execute_python_node(node, context)
        if isinstance(result, dict):
            vars_payload = result.get("vars")
            if isinstance(vars_payload, dict):
                context.vars.update(vars_payload)
            else:
                context.vars.update(result)
        return {"result": result}

    if node.node_type == "invoke_workflow":
        child_version = _resolve_workflow_version_for_invocation(conn, config)
        input_mode = str(config.get("inputMode", "inherit"))
        input_source = str(config.get("inputSource", "vars.input"))
        if input_mode == "from_var":
            child_input = _resolve_value(input_source, context)
        else:
            child_input = copy.deepcopy(context.vars.get("input", {}))
        if not isinstance(child_input, dict):
            raise RuntimeError("invoke_workflow input must resolve to a JSON object")

        child_correlation_id = correlation_id or str(execution_id)
        repo.append_event(
            conn,
            execution_id=execution_id,
            event_type="INVOKE_WORKFLOW_STARTED",
            node_id=node.id,
            payload={
                "target_workflow_version_id": str(child_version["id"]),
                "target_workflow_id": str(child_version["workflow_id"]),
            },
        )

        child_execution = repo.create_execution(
            conn,
            workflow_version_id=child_version["id"],
            input_json=child_input,
            debug_mode=False,
            parent_execution_id=execution_id,
            trigger_type="workflow",
            trigger_payload={
                "invoked_by_execution_id": str(execution_id),
                "invoked_by_node_id": node.id,
                "call_depth": call_depth + 1,
            },
            idempotency_key=None,
            correlation_id=child_correlation_id,
        )

        run_execution(
            conn,
            execution_id=child_execution["id"],
            workflow_version=child_version,
            input_json=child_input,
            call_depth=call_depth + 1,
            parent_execution_id=execution_id,
            correlation_id=child_correlation_id,
        )

        child_status = repo.get_execution(conn, child_execution["id"])
        if not child_status or child_status["status"] != "completed":
            raise RuntimeError("invoke_workflow child execution failed")

        repo.append_event(
            conn,
            execution_id=execution_id,
            event_type="INVOKE_WORKFLOW_SUCCEEDED",
            node_id=node.id,
            payload={"child_execution_id": str(child_execution["id"])},
        )
        child_context = child_status.get("final_context_json")
        context.vars["last_child_execution_id"] = str(child_execution["id"])
        return {
            "child_execution_id": str(child_execution["id"]),
            "child_workflow_version_id": str(child_version["id"]),
            "child_final_context": child_context,
        }

    if node.node_type == "save":
        key = str(config.get("key", "result")).strip() or "result"
        source_path = str(config.get("from", ""))
        value = _resolve_value(source_path, context) if source_path else context.system.get("last_response")
        repo.create_saved_output(conn, execution_id=execution_id, key=key, value_json=value)
        saved_outputs = context.system.setdefault("saved_outputs", {})
        saved_outputs[key] = value
        return {"key": key, "value": value}

    if node.node_type == "end":
        return {"ended": True}

    if node.node_type == "raise_error":
        message = _render_template(str(config.get("message", "raise_error node triggered")), context)
        raise RuntimeError(str(message))

    raise RuntimeError(f"Unsupported node type: {node.node_type}")


def run_execution(
    conn: Connection,
    execution_id: UUID,
    workflow_version: dict[str, Any],
    input_json: dict[str, Any],
    *,
    call_depth: int = 0,
    parent_execution_id: UUID | None = None,
    correlation_id: str | None = None,
    start_node_id: str | None = None,
    context_override: ExecutionContext | None = None,
    is_resume: bool = False,
) -> None:
    if call_depth > settings.max_call_depth:
        raise RuntimeError(f"Maximum workflow call depth exceeded: {settings.max_call_depth}")

    graph = workflow_version["graph_json"]
    nodes, outgoing = _index_graph(graph)
    auth_defs = _resolve_auth_definitions(nodes)
    current_node_id = start_node_id or graph.get("entry_node_id")

    if not current_node_id or current_node_id not in nodes:
        repo.append_event(
            conn,
            execution_id=execution_id,
            event_type="NODE_FAILED",
            payload={"error": "Missing or invalid entry_node_id"},
        )
        repo.update_execution_status(conn, execution_id=execution_id, status="failed")
        return

    if context_override is not None:
        context = context_override
    else:
        vars_payload = copy.deepcopy(input_json) if isinstance(input_json, dict) else {}
        vars_payload["input"] = copy.deepcopy(input_json) if isinstance(input_json, dict) else {}
        context = ExecutionContext(
            vars=vars_payload,
            nodes={},
            system={
                "execution_id": str(execution_id),
                "call_depth": call_depth,
                "parent_execution_id": str(parent_execution_id) if parent_execution_id else None,
                "correlation_id": correlation_id,
                "saved_outputs": {},
                "parallel": {},
            },
        )
        _apply_parameter_defaults(nodes, context)

    if not is_resume:
        repo.append_event(
            conn,
            execution_id=execution_id,
            event_type="RUN_STARTED",
            payload={
                "workflow_version_id": str(workflow_version["id"]),
                "call_depth": call_depth,
                "parent_execution_id": str(parent_execution_id) if parent_execution_id else None,
                "correlation_id": correlation_id,
            },
        )

    while True:
        node = nodes[current_node_id]
        repo.update_execution_status(
            conn,
            execution_id=execution_id,
            status="running",
            current_node_id=current_node_id,
            final_context_json=context.to_json(),
        )
        repo.append_event(
            conn,
            execution_id=execution_id,
            event_type="NODE_STARTED",
            node_id=current_node_id,
            payload={"node_type": node.node_type, "label": node.label},
        )

        try:
            output = _execute_node(
                conn=conn,
                execution_id=execution_id,
                node=node,
                context=context,
                auth_defs=auth_defs,
                call_depth=call_depth,
                correlation_id=correlation_id,
            )
            context.nodes[current_node_id] = {
                "status": "success",
                "node_type": node.node_type,
                "label": node.label,
                "output": output,
            }
            repo.append_event(
                conn,
                execution_id=execution_id,
                event_type="NODE_SUCCEEDED",
                node_id=current_node_id,
                payload={"node_type": node.node_type, "output": output},
            )
        except Exception as exc:  # noqa: BLE001
            context.nodes[current_node_id] = {
                "status": "failed",
                "node_type": node.node_type,
                "label": node.label,
                "error": str(exc),
            }
            repo.append_event(
                conn,
                execution_id=execution_id,
                event_type="NODE_FAILED",
                node_id=current_node_id,
                payload={"node_type": node.node_type, "error": str(exc)},
            )
            repo.update_execution_status(
                conn,
                execution_id=execution_id,
                status="failed",
                current_node_id=current_node_id,
                final_context_json=context.to_json(),
            )
            _write_snapshot_if_needed(conn, execution_id, context)
            raise

        if node.node_type == "end":
            repo.append_event(conn, execution_id=execution_id, event_type="RUN_COMPLETED")
            repo.update_execution_status(
                conn,
                execution_id=execution_id,
                status="completed",
                current_node_id=current_node_id,
                final_context_json=context.to_json(),
            )
            _write_snapshot_if_needed(conn, execution_id, context)
            return

        edge = _select_next_edge(node=node, outgoing=outgoing, node_output=context.nodes[current_node_id]["output"])
        if edge is None:
            repo.append_event(
                conn,
                execution_id=execution_id,
                event_type="RUN_COMPLETED",
                payload={"reason": "No outgoing edge", "at_node_id": current_node_id},
            )
            repo.update_execution_status(
                conn,
                execution_id=execution_id,
                status="completed",
                current_node_id=current_node_id,
                final_context_json=context.to_json(),
            )
            _write_snapshot_if_needed(conn, execution_id, context)
            return

        if edge.get("breakpoint"):
            repo.append_event(
                conn,
                execution_id=execution_id,
                event_type="BREAKPOINT_PAUSED",
                edge_id=edge.get("id"),
                payload={"source": edge.get("source"), "target": edge.get("target")},
            )
            repo.update_execution_status(
                conn,
                execution_id=execution_id,
                status="paused",
                current_node_id=edge.get("target"),
                final_context_json=context.to_json(),
            )
            _write_snapshot_if_needed(conn, execution_id, context)
            return

        repo.append_event(
            conn,
            execution_id=execution_id,
            event_type="EDGE_TRAVERSED",
            edge_id=edge.get("id"),
            payload={"source": edge.get("source"), "target": edge.get("target")},
        )
        current_node_id = str(edge["target"])
        _write_snapshot_if_needed(conn, execution_id, context)


def continue_execution_from_pause(
    conn: Connection,
    execution_id: UUID,
    workflow_version: dict[str, Any],
    action: str,
) -> None:
    if action == "abort":
        repo.append_event(conn, execution_id=execution_id, event_type="RUN_ABORTED")
        repo.update_execution_status(conn, execution_id=execution_id, status="aborted")
        return

    execution = repo.get_execution(conn, execution_id)
    if not execution:
        raise RuntimeError("Execution not found")

    context_json = execution.get("final_context_json")
    context = ExecutionContext.from_json(context_json if isinstance(context_json, dict) else {})
    start_node_id = execution.get("current_node_id")
    if not isinstance(start_node_id, str) or not start_node_id:
        raise RuntimeError("Execution has no resume node")

    repo.append_event(
        conn,
        execution_id=execution_id,
        event_type="RUN_RESUMED",
        payload={"mode": action, "resume_node_id": start_node_id},
    )

    run_execution(
        conn,
        execution_id=execution_id,
        workflow_version=workflow_version,
        input_json=context.vars.get("input", {}) if isinstance(context.vars.get("input"), dict) else {},
        call_depth=_coerce_int(context.system.get("call_depth"), 0),
        parent_execution_id=execution.get("parent_execution_id"),
        correlation_id=execution.get("correlation_id"),
        start_node_id=start_node_id,
        context_override=context,
        is_resume=True,
    )
