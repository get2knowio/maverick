"""JSON extraction, repair, and schema coercion for ACP agent output.

Agent responses often contain JSON embedded in prose, and LLM output
is frequently truncated mid-structure or uses Python-style escapes.
These helpers try hard to recover a validatable Pydantic model from
whatever the agent produced.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ValidationError

from maverick.exceptions.agent import MalformedResponseError
from maverick.executor.errors import OutputSchemaValidationError
from maverick.logging import get_logger

logger = get_logger(__name__)


def extract_json_output(
    text: str,
    output_schema: type[BaseModel],
    step_name: str,
) -> BaseModel:
    """Extract and validate the last JSON block from agent output text.

    Tries fenced ```json ... ``` code blocks first, then falls back to the
    last brace-matched ``{...}`` block in the text.

    Args:
        text: Raw accumulated text from the ACP agent.
        output_schema: Pydantic BaseModel subclass to validate against.
        step_name: DSL step name (for error context).

    Returns:
        Validated Pydantic model instance.

    Raises:
        MalformedResponseError: If no JSON block is found or parsing fails.
        OutputSchemaValidationError: If the extracted JSON fails schema validation.
    """
    json_str: str | None = None

    # Strategy 1: fenced ```json ... ``` code block (take the last one)
    fenced_matches = list(re.finditer(r"```json\s*([\s\S]*?)```", text, re.IGNORECASE))
    if fenced_matches:
        json_str = fenced_matches[-1].group(1).strip()

    # Strategy 2: last brace-matched {...} block
    if json_str is None:
        json_str = extract_last_json_object(text)

    if json_str is None:
        raise MalformedResponseError(
            message=(
                f"Step '{step_name}': no JSON block found in agent output. "
                "Expected a ```json ... ``` block or a top-level JSON object."
            ),
            raw_response=text[:500] if text else None,
        )

    # ---- Stage 1: Parse JSON string to Python dict ----
    raw_data = parse_json_lenient(json_str, step_name)

    # ---- Stage 2: Validate, with coercion fallback ----
    try:
        return output_schema.model_validate(raw_data)
    except ValidationError:
        pass

    # Coerce agent output to match schema (e.g., dicts → strings in
    # array-of-string fields). This handles the systematic mismatch where
    # agents produce rich objects that the schema types as flat strings.
    try:
        schema = output_schema.model_json_schema()
        coerced = coerce_to_schema(raw_data, schema)
        return output_schema.model_validate(coerced)
    except ValidationError as exc:
        raise OutputSchemaValidationError(step_name, output_schema, exc) from exc


def parse_json_lenient(json_str: str, step_name: str) -> Any:
    """Parse a JSON string, attempting truncation repair on failure.

    Pipeline:
    1. Try ``json.loads()`` directly.
    2. On failure, attempt to repair truncated output (close open strings,
       arrays, objects) and retry.
    3. If both fail, raise ``MalformedResponseError``.

    Args:
        json_str: Raw JSON string extracted from agent output.
        step_name: Step name for logging context.

    Returns:
        Parsed Python data (dict/list).

    Raises:
        MalformedResponseError: If the JSON cannot be parsed even after repair.
    """
    # Fast path
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as first_err:
        logger.debug(
            "acp_executor.json_parse_failed",
            step_name=step_name,
            error=str(first_err),
            json_len=len(json_str),
        )

    # Common LLM quirk: agents produce Python-style escaped single quotes
    # (\') which are invalid in JSON.  Strip the backslash — single quotes
    # are legal unescaped in JSON strings.
    sanitized = json_str.replace("\\'", "'")
    if sanitized != json_str:
        try:
            result = json.loads(sanitized)
            logger.info(
                "acp_executor.json_sanitized_single_quotes",
                step_name=step_name,
            )
            return result
        except json.JSONDecodeError:
            pass

    # Repair path — close truncated structures
    repaired = repair_truncated_json(json_str)
    if repaired is not None:
        try:
            result = json.loads(repaired)
            logger.warning(
                "acp_executor.json_repaired",
                step_name=step_name,
                original_len=len(json_str),
                repaired_len=len(repaired),
            )
            return result
        except json.JSONDecodeError:
            pass

    raise MalformedResponseError(
        message=(
            f"Step '{step_name}': extracted JSON could not be parsed "
            f"(possibly truncated agent output, {len(json_str)} chars). "
            f"Tail: ...{json_str[-200:]!r}"
        ),
        raw_response=json_str[-500:] if len(json_str) > 500 else json_str,
    )


def repair_truncated_json(text: str) -> str | None:
    """Attempt to repair JSON truncated mid-output by closing open structures.

    Handles common truncation patterns where the agent hit a token limit
    mid-JSON: unclosed strings, arrays, and objects. Walks the text tracking
    string/escape state and brace depth, then appends closing delimiters.

    Args:
        text: Potentially truncated JSON string.

    Returns:
        Repaired JSON string, or None if repair is not feasible.
    """
    if not text or not text.lstrip().startswith("{"):
        return None

    repaired = text.rstrip()

    in_string = False
    escaped = False
    brace_depth = 0
    bracket_depth = 0

    for ch in repaired:
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            if in_string:
                escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            brace_depth += 1
        elif ch == "}":
            brace_depth -= 1
        elif ch == "[":
            bracket_depth += 1
        elif ch == "]":
            bracket_depth -= 1

    if in_string:
        repaired += '"'

    # Strip trailing comma (invalid before closing delimiter)
    stripped = repaired.rstrip()
    if stripped.endswith(","):
        repaired = stripped[:-1]

    # Close unclosed brackets then braces (innermost first)
    repaired += "]" * bracket_depth
    repaired += "}" * brace_depth

    return repaired


def coerce_to_schema(data: Any, schema: dict[str, Any]) -> Any:
    """Best-effort coercion of parsed JSON to match a JSON Schema.

    Handles the common agent mismatch where dict/list values appear where
    the schema expects strings, by converting them to compact JSON strings.

    Args:
        data: Parsed JSON data.
        schema: JSON Schema dict from Pydantic's ``model_json_schema()``.

    Returns:
        Coerced data that is more likely to pass validation.
    """
    schema_type = schema.get("type")

    if schema_type == "object":
        if not isinstance(data, dict):
            return data
        props = schema.get("properties", {})
        result = {}
        for key, value in data.items():
            if key in props:
                result[key] = coerce_to_schema(value, props[key])
            else:
                result[key] = value
        return result

    if schema_type == "array":
        if not isinstance(data, (list, tuple)):
            return data
        items_schema = schema.get("items", {})
        return [coerce_to_schema(item, items_schema) for item in data]

    if schema_type == "string":
        if isinstance(data, str):
            return data
        return json.dumps(data, ensure_ascii=False)

    return data


def extract_last_json_object(text: str) -> str | None:
    """Find the last balanced ``{...}`` object in text.

    Scans the text from right to left for ``}`` characters, then walks
    backwards matching braces to find the corresponding opening ``{``.

    Args:
        text: Text to scan for a JSON object.

    Returns:
        The last balanced JSON object string, or None if not found.
    """
    last_close = text.rfind("}")
    if last_close == -1:
        return None

    depth = 0
    in_string = False

    for i in range(last_close, -1, -1):
        ch = text[i]
        if ch == '"':
            # Count preceding backslashes to determine if this quote is escaped.
            num_backslashes = 0
            j = i - 1
            while j >= 0 and text[j] == "\\":
                num_backslashes += 1
                j -= 1
            if num_backslashes % 2 == 0:
                in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "}":
            depth += 1
        elif ch == "{":
            depth -= 1
            if depth == 0:
                candidate = text[i : last_close + 1]
                try:
                    json.loads(candidate)
                    return candidate
                except (json.JSONDecodeError, ValueError):
                    return None

    return None
