"""The interpretive layer. Optional, and every claim it makes cites provenance.

Nothing here is deterministic in the way `scan/` is — an outcome label is a
reader's judgment. What is deterministic is the machinery around it: a fixture
freezes bytes, a replay renders the same payload every time, and a registration
decides whether a draw counts as confirmatory before it is taken.
"""

from .challenge import (
    OUTCOMES,
    TAXONOMY_VERSION,
    Chain,
    InvalidRound,
    Round,
    summarize,
)
from .fixtures import EvidenceSpan, Fixture, freeze, verify
from .registration import Registration, is_confirmatory, register, validate

__all__ = [
    "OUTCOMES",
    "TAXONOMY_VERSION",
    "Chain",
    "EvidenceSpan",
    "Fixture",
    "InvalidRound",
    "Registration",
    "Round",
    "freeze",
    "is_confirmatory",
    "register",
    "summarize",
    "validate",
    "verify",
]
