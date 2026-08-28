"""corpus-analysis — agent transcript corpora as inspectable evidence.

Two layers, and the boundary between them is the point:

    corpus-scan    deterministic measurement. No model, no network, read-only.
                   Useful with nothing attached to it.
    corpus-audit   interpretation. Every claim it makes references a scan-layer
                   provenance id.

Stdlib only.
"""

__version__ = "0.2.0"
