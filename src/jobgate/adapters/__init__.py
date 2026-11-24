"""ATS adapters. Add a source by registering its adapter here."""

from jobgate.adapters.ashby import AshbyAdapter
from jobgate.adapters.base import Adapter
from jobgate.adapters.greenhouse import GreenhouseAdapter
from jobgate.adapters.lever import LeverAdapter

ADAPTERS: dict[str, Adapter] = {
    adapter.ats: adapter for adapter in (GreenhouseAdapter(), LeverAdapter(), AshbyAdapter())
}

__all__ = ["ADAPTERS", "Adapter", "AshbyAdapter", "GreenhouseAdapter", "LeverAdapter"]
