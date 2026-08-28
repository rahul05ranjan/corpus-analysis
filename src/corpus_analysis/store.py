"""Append-only NDJSON. The results ledger.

Nothing rewrites a line. A change is a new record carrying `ref`, and `items()`
folds those onto the record they reference. A log that is only ever appended to
is one a crash cannot half-write.

`key` is what makes a re-run safe. An append names the observation it records,
and a key already present is a no-op returning the record already there — so
idempotence is a property of the ledger rather than a discipline expected of
every caller.

The path is always explicit. A default under a state directory would put audit
results somewhere the user did not name, which is the one thing a tool pointed
at a private corpus must not do.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._keys = {r["key"]: r for r in self.records() if r.get("key")}

    def append(self, kind: str, body: dict, key: str | None = None,
               ref: str | None = None) -> dict:
        """One record. A repeated `key` returns the record already there."""
        if key and key in self._keys:
            return self._keys[key]
        ts = _now()
        rec = {
            "id": f"{ts}-{uuid.uuid4().hex[:8]}",
            "ts": ts,
            "kind": kind,
            "ref": ref,
            "body": body,
        }
        if key:
            rec["key"] = key
        self._write(rec)
        if key:
            self._keys[key] = rec
        return rec

    def _write(self, rec: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(rec, sort_keys=True, separators=(",", ":"),
                          default=str) + "\n"
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())

    def records(self) -> Iterator[dict]:
        """Every record, in append order. A truncated final line is skipped."""
        if not self.path.exists():
            return
        with self.path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue

    def items(self) -> dict[str, dict]:
        """Records with every later record that references them folded on."""
        items: dict[str, dict] = {}
        refs: list[dict] = []
        for r in self.records():
            if r.get("ref"):
                refs.append(r)
            else:
                items[r["id"]] = dict(r)
        for r in refs:
            target = items.get(r["ref"] or "")
            if target is None:
                continue
            target.setdefault("updates", []).append(r)
            target["updated_ts"] = r["ts"]
        return items

    def of_kind(self, kind: str) -> list[dict]:
        return [r for r in self.records() if r.get("kind") == kind]

    def has_key(self, key: str) -> bool:
        return key in self._keys
