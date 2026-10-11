"""A saved report's settings, independent of the language (DATA_MODEL_REPORTS.md
§30). Perspective names a column by the label it shows, which depends on the
administrator's language, and so do filter values such as an engagement
stage. So a report is stored with stable references instead: a column as
`col:<key>`, a translated value as `val:<key>`. `to_stored` turns what the
viewer's `save()` gave (in the current language) into that; `to_viewer`
turns it back for the current language, and drops what refers to a column
the dataset doesn't have any more (a report never breaks on a changed
dataset; the page says what was dropped)."""

import json
from typing import Any

from .datasets.base import COMMON_VALUES, DIMENSION, Dataset

COLUMN = "col:"
VALUE = "val:"
MAX_BYTES = 64 * 1024

# Settings the site decides itself, never stored with a report: the theme
# follows the site's, the title is the report's name, the table is the
# page's one table of figures.
NOT_STORED = ("theme", "title", "settings", "table")

# The keys whose value is a list of column names.
COLUMN_LISTS = ("columns", "group_by", "split_by")
# The keys whose value is a dict keyed by column name.
COLUMN_DICTS = ("aggregates", "columns_config", "plugin_config")


class ConfigError(ValueError):
    pass


def parse(raw: str) -> dict[str, Any]:
    """The viewer's JSON from a form, checked for size and shape."""
    if len(raw.encode()) > MAX_BYTES:
        raise ConfigError("too large")
    try:
        config = json.loads(raw)
    except ValueError as error:
        raise ConfigError("not JSON") from error
    if not isinstance(config, dict):
        raise ConfigError("not an object")
    return config


class _Names:
    def __init__(self, dataset: Dataset):
        self.dataset = dataset
        self.key_of = {str(column.label): column.key for column in dataset.columns}
        self.label_of = {column.key: str(column.label) for column in dataset.columns}

    def value_key(self, column_key: str, label: Any) -> Any:
        if not isinstance(label, str):
            return label
        column = next((c for c in self.dataset.columns if c.key == column_key), None)
        if column is None or column.kind != DIMENSION:
            return label
        for key, value_label in {**COMMON_VALUES, **column.values}.items():
            if str(value_label) == label:
                return VALUE + key
        return label

    def value_label(self, column_key: str, stored: Any) -> Any:
        if not isinstance(stored, str) or not stored.startswith(VALUE):
            return stored
        return self.dataset.column(column_key).value_label(stored[len(VALUE) :])


def to_stored(config: dict[str, Any], dataset: Dataset) -> dict[str, Any]:
    names = _Names(dataset)

    def ref(name: Any) -> Any:
        return COLUMN + names.key_of[name] if isinstance(name, str) and name in names.key_of else name

    stored = {key: value for key, value in config.items() if key not in NOT_STORED}
    for key in COLUMN_LISTS:
        if isinstance(stored.get(key), list):
            stored[key] = [ref(name) for name in stored[key]]
    for key in COLUMN_DICTS:
        if isinstance(stored.get(key), dict):
            stored[key] = {ref(name): value for name, value in stored[key].items()}
    if isinstance(stored.get("sort"), list):
        stored["sort"] = [
            [ref(item[0]), *item[1:]] if isinstance(item, list) and item else item for item in stored["sort"]
        ]
    if isinstance(stored.get("filter"), list):
        filters = []
        for item in stored["filter"]:
            if isinstance(item, list) and len(item) >= 3 and item[0] in names.key_of:
                column_key = names.key_of[item[0]]
                value = item[2]
                value = (
                    [names.value_key(column_key, v) for v in value]
                    if isinstance(value, list)
                    else names.value_key(column_key, value)
                )
                item = [COLUMN + column_key, item[1], value, *item[3:]]
            filters.append(item)
        stored["filter"] = filters
    if isinstance(stored.get("expressions"), dict):
        stored["expressions"] = {
            name: _replace_quoted(expression, {label: COLUMN + key for label, key in names.key_of.items()})
            for name, expression in stored["expressions"].items()
            if isinstance(expression, str)
        }
    return stored


def to_viewer(stored: dict[str, Any], dataset: Dataset) -> tuple[dict[str, Any], list[str]]:
    """The config for `viewer.restore()` in the current language, and the
    column keys it referred to that the dataset doesn't have any more."""
    names = _Names(dataset)
    missing: list[str] = []

    def known(name: Any) -> bool:
        if isinstance(name, str) and name.startswith(COLUMN):
            if name[len(COLUMN) :] in names.label_of:
                return True
            missing.append(name[len(COLUMN) :])
            return False
        return True

    def label(name: Any) -> Any:
        return names.label_of[name[len(COLUMN) :]] if isinstance(name, str) and name.startswith(COLUMN) else name

    config = dict(stored)
    for key in COLUMN_LISTS:
        if isinstance(config.get(key), list):
            config[key] = [label(name) for name in config[key] if known(name)]
    for key in COLUMN_DICTS:
        if isinstance(config.get(key), dict):
            config[key] = {label(name): value for name, value in config[key].items() if known(name)}
    if isinstance(config.get("sort"), list):
        config["sort"] = [
            [label(item[0]), *item[1:]] if isinstance(item, list) and item else item
            for item in config["sort"]
            if not (isinstance(item, list) and item and not known(item[0]))
        ]
    if isinstance(config.get("filter"), list):
        filters = []
        for item in config["filter"]:
            if isinstance(item, list) and len(item) >= 3 and isinstance(item[0], str) and item[0].startswith(COLUMN):
                if not known(item[0]):
                    continue
                column_key = item[0][len(COLUMN) :]
                value = item[2]
                value = (
                    [names.value_label(column_key, v) for v in value]
                    if isinstance(value, list)
                    else names.value_label(column_key, value)
                )
                item = [label(item[0]), item[1], value, *item[3:]]
            filters.append(item)
        config["filter"] = filters
    if isinstance(config.get("expressions"), dict):
        expressions = {}
        for name, expression in config["expressions"].items():
            refs = _quoted_refs(expression)
            if all(known(ref) for ref in refs):
                expressions[name] = _replace_quoted(expression, {ref: label(ref) for ref in refs})
        config["expressions"] = expressions
    return config, sorted(set(missing))


def _replace_quoted(expression: str, mapping: dict[str, str]) -> str:
    """Replace "name" (a column reference inside a Perspective expression)."""
    for old, new in mapping.items():
        expression = expression.replace(f'"{old}"', f'"{new}"')
    return expression


def _quoted_refs(expression: str) -> list[str]:
    parts = expression.split('"')
    return [part for part in parts[1::2] if part.startswith(COLUMN)]
