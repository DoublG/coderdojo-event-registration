"""The reporting datasets (DATA_MODEL_REPORTS.md §30): the curated views the
organisation's reports are built on, the way SAP's analytical CDS views are.

A dataset is aggregated rows with a fixed set of columns: dimensions (a
category to group by, shown as text) and measures (a count or a sum). Every
column names the model field it comes from, and `reports.tests` checks each
against the privacy registry: never health, criminal-record or security
data. The rows go to the administrator's browser, where Perspective can
regroup them any way, so a dataset only ever holds what anyone with the
Reports area may see.

**Small groups are generalised on the server** (`generalise`): in a dataset
about children, a row counting fewer than `REPORT_MIN_GROUP` children gets
its most identifying dimension replaced by "Other" (the order is the
dataset's `generalise_order`) and is merged with the rows that now match,
until every row is big enough. What's still too small after the last
dimension is left out, and the page says how many children that was. The
totals stay right except for those."""

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.utils.functional import Promise
from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:
    from dojos.models import Dojo

DIMENSION = "dimension"
MEASURE = "measure"

# The stable keys of the two values every dimension can have; a saved report
# stores these instead of the text, which depends on the language.
OTHER = "__other__"
UNKNOWN = "__unknown__"
COMMON_VALUES: dict[str, str | Promise] = {
    OTHER: _("Other (small groups)"),
    UNKNOWN: _("Unknown"),
}


@dataclass(frozen=True)
class Column:
    """One column of a dataset. `source` is the (model label, field name)
    it's taken from, for the privacy check. A dimension with `values` shows
    each stored value as its label (translated); one without shows the
    value as it is (a dojo's or a province's name)."""

    key: str
    label: str | Promise
    kind: str
    source: tuple[str, str]
    values: dict[str, str | Promise] = field(default_factory=dict)

    def value_label(self, value: Any) -> str:
        if value is None or value == "":
            return str(COMMON_VALUES[UNKNOWN])
        value = str(value)
        if value in COMMON_VALUES:
            return str(COMMON_VALUES[value])
        if value in self.values:
            return str(self.values[value])
        return value


@dataclass
class Table:
    """What the data endpoint sends: one dict per row, keyed by column key,
    dimensions still as stable values, plus how many were left out."""

    rows: list[dict[str, Any]]
    hidden: int = 0


class Dataset:
    """A reporting dataset. Subclasses set the attributes and `query_rows`,
    which returns the aggregated rows keyed by column key."""

    key: str
    label: str | Promise
    description: str | Promise
    columns: list[Column]
    # About children: small groups are generalised (above).
    about_children = True
    # The measure that counts people, for the small-group rule.
    count_column = ""
    # Which dimension to replace by "Other" first, then next, ...
    generalise_order: list[str] = []
    # The dimension that names a dojo, and the lookup that filters the query
    # on one: a dataset with them can be shared with dojos, each champion
    # seeing their own dojo's rows only (reports.dojo_views). Empty: the
    # organisation's only.
    dojo_column = ""
    dojo_lookup = ""

    def query_rows(self, dojo: "Dojo | None" = None) -> list[dict[str, Any]]:
        """The aggregated rows; with `dojo`, only that dojo's (the filter is
        in the query, so nothing of another dojo is ever read)."""
        raise NotImplementedError

    @property
    def shareable(self) -> bool:
        return bool(self.dojo_column and self.dojo_lookup)

    def columns_for(self, dojo: "Dojo | None" = None) -> list[Column]:
        """The columns a viewer gets: without the dojo column on one dojo's
        figures, where it would say the same on every row."""
        if dojo is None:
            return self.columns
        return [column for column in self.columns if column.key != self.dojo_column]

    def column(self, key: str) -> Column:
        return next(column for column in self.columns if column.key == key)

    @property
    def dimensions(self) -> list[str]:
        return [column.key for column in self.columns if column.kind == DIMENSION]

    @property
    def measures(self) -> list[str]:
        return [column.key for column in self.columns if column.kind == MEASURE]

    def table(self, min_group: int | None = None, dojo: "Dojo | None" = None) -> Table:
        if dojo is not None:
            # A dojo's own figures: never merged (decided 11 October 2026), its
            # team already knows its children by name from the attendance list.
            if not self.shareable:
                raise ValueError(f"{self.key} has no dojo column")
            keys = [column.key for column in self.columns_for(dojo)]
            rows = [{key: row.get(key) for key in keys} for row in self.query_rows(dojo)]
            dimensions = [key for key in self.dimensions if key in keys]
            return Table(merge(rows, dimensions, self.measures))
        rows = self.query_rows()
        if not self.about_children:
            return Table(merge(rows, self.dimensions, self.measures))
        if min_group is None:
            min_group = settings.REPORT_MIN_GROUP
        return generalise(rows, self.dimensions, self.measures, self.count_column, self.generalise_order, min_group)

    def labelled(self, table: Table, dojo: "Dojo | None" = None) -> list[dict[str, Any]]:
        """The rows as Perspective gets them: keyed by the columns' labels in
        the current language, dimensions shown as their labels."""
        columns = [(column, str(column.label)) for column in self.columns_for(dojo)]
        return [
            {
                label: column.value_label(row.get(column.key))
                if column.kind == DIMENSION
                else row.get(column.key) or 0
                for column, label in columns
            }
            for row in table.rows
        ]


def merge(rows: Iterable[dict[str, Any]], dimensions: list[str], measures: list[str]) -> list[dict[str, Any]]:
    """Add up the rows that have the same value in every dimension."""
    merged: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        key = tuple(row.get(dimension) for dimension in dimensions)
        if key not in merged:
            merged[key] = {**{dimension: row.get(dimension) for dimension in dimensions}, **dict.fromkeys(measures, 0)}
        for measure in measures:
            merged[key][measure] += row.get(measure) or 0
    return list(merged.values())


def generalise(
    rows: list[dict[str, Any]],
    dimensions: list[str],
    measures: list[str],
    count_column: str,
    order: list[str],
    min_group: int,
) -> Table:
    """Replace, dimension by dimension in `order`, the value of every row
    counting fewer than `min_group` by OTHER and merge, until no small row
    is left or the order runs out; then leave out what's still small."""
    rows = merge(rows, dimensions, measures)
    for dimension in order:
        small = [row for row in rows if row[count_column] < min_group]
        if not small:
            break
        for row in small:
            row[dimension] = OTHER
        rows = merge(rows, dimensions, measures)
    kept = [row for row in rows if row[count_column] >= min_group]
    hidden = sum(row[count_column] for row in rows if row[count_column] < min_group)
    return Table(kept, hidden)


def choice_values(choices: Iterable[tuple[str, str | Promise]]) -> dict[str, str | Promise]:
    return {str(value): label for value, label in choices}


YES_NO: dict[str, str | Promise] = {"True": _("Yes"), "False": _("No")}
