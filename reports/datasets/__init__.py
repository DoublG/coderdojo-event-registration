"""The registry of reporting datasets (DATA_MODEL_REPORTS.md §30). A new
dataset is a module here, added to DATASETS; `reports.tests` checks its
columns against the privacy registry."""

from django.http import Http404

from .base import Dataset
from .engagement import EngagementDataset

DATASETS: dict[str, Dataset] = {dataset.key: dataset for dataset in (EngagementDataset(),)}


def get_dataset(key: str) -> Dataset:
    """The dataset `key`, or a 404 (a URL or a saved report naming one that
    doesn't exist any more)."""
    try:
        return DATASETS[key]
    except KeyError:
        raise Http404 from None
