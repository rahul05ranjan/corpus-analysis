PYTHON ?= python3
PY      = PYTHONPATH=src $(PYTHON)
SCAN    = $(PY) -m corpus_analysis.cli
AUDIT   = $(PY) -m corpus_analysis.audit_cli

# The corpus to measure. Override for any adapter root:
#   make stats ROOT=~/.claude/projects SINCE=7d
ROOT  ?=
SINCE ?=
ARGS  ?=
ROOT_ARG  = $(if $(ROOT),--root $(ROOT))
SINCE_ARG = $(if $(SINCE),--since $(SINCE))

.DEFAULT_GOAL := help
.PHONY: help check compile test lint fmt determinism sessions stats find report temporal \
        verify replay clean m3a-preflight m3a-preflight-pure m3a-run m3a-score \
        m3a-report m3a-smoke

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-14s\033[0m %s\n", $$1, $$2}'

check: compile test ## Compile + the full suite. What CI runs.

compile: ## Byte-compile the package, the shims, and the tests
	$(PY) -m compileall -q src tests bin experiments

test: ## unittest discovery: records, labels, scan, determinism, boundaries
	$(PY) -m unittest discover -s tests -v

lint: ## ruff check (dev-time only; never a runtime dependency)
	ruff check .

fmt: ## ruff format
	ruff format .

# Writes under the ignored out/ root, never shared /tmp: the output is corpus
# text. On a mismatch both files are kept there for diffing.
determinism: ## Scan a real corpus twice and compare. ROOT=... SINCE=...
	@mkdir -p out
	@$(SCAN) ingest $(ROOT_ARG) $(SINCE_ARG) $(ARGS) --out out/determinism.a >/dev/null
	@$(SCAN) ingest $(ROOT_ARG) $(SINCE_ARG) $(ARGS) --out out/determinism.b >/dev/null
	@cmp out/determinism.a out/determinism.b \
	  && { echo "determinism: byte-identical ($$(wc -l < out/determinism.a) turns)"; \
	       rm -f out/determinism.a out/determinism.b; } \
	  || { echo "determinism: OUTPUT DIFFERS; kept out/determinism.{a,b}" >&2; exit 1; }

sessions: ## List located sessions [read-only]
	@$(SCAN) sessions $(ROOT_ARG) $(SINCE_ARG) $(ARGS)

stats: ## Corpus totals as one JSON object [read-only]
	@$(SCAN) stats $(ROOT_ARG) $(SINCE_ARG) $(ARGS)

find: ## Candidate repair sequences, located behaviourally [read-only]
	@$(SCAN) find $(ROOT_ARG) $(SINCE_ARG) $(ARGS)

report: ## Markdown report; every figure carries its label [read-only]
	@$(SCAN) report $(ROOT_ARG) $(SINCE_ARG) $(ARGS)

# ZONE, not TZ: make imports TZ from the environment, so a host with TZ
# exported would silently pick its zone while the CLI documents an explicit one.
temporal: ## Clock/calendar heat tables. ZONE=IANA zone; ARGS=ingest files to merge
	@$(SCAN) temporal $(ROOT_ARG) $(SINCE_ARG) $(if $(ZONE),--tz $(ZONE)) $(ARGS)

verify: ## Re-read every span of a fixture from its source. FIXTURE=path
	@test -n "$(FIXTURE)" || { echo "usage: make verify FIXTURE=fx.json" >&2; exit 2; }
	@$(AUDIT) verify $(FIXTURE)

replay: ## Render a fixture's model-facing payload. FIXTURE=path
	@test -n "$(FIXTURE)" || { echo "usage: make replay FIXTURE=fx.json" >&2; exit 2; }
	@$(AUDIT) replay $(FIXTURE)

# ── M3a: the first prospective battery ───────────────────────────────────────
# The registration is frozen and unsigned. `m3a-run` refuses until preflight is
# clean. The current draft has populated decision fields but no operator
# signature. That refusal is the feature; there is no bypass.
M3A      = experiments/m3a
M3A_PURE_ARGS = $(M3A)/registration.json --fixture $(M3A)/fixture.json \
                --runtime $(M3A)/runtime.json --archive $(M3A)/raw --repo-root .

m3a-preflight: ## May the M3a battery run? Fails closed. [read-only]
	@$(M3A)/bin/m3a-run --dry-run

m3a-preflight-pure: ## Preflight without the git checks (no commands run) [read-only]
	@$(AUDIT) preflight $(M3A_PURE_ARGS)

m3a-smoke: ## Transport check against the local endpoint. NOT a draw.
	@$(M3A)/bin/transport-smoke $(ARGS)

m3a-run: ## Run the M3a battery. Refuses until the registration is signed.
	@$(M3A)/bin/m3a-run $(ARGS)

m3a-score: ## Score archived M3a draws against a labels file. LABELS=path
	@$(M3A)/bin/m3a-score $(if $(LABELS),--labels $(LABELS)) $(ARGS)

m3a-report: ## The frozen M3a registration and its hashes [read-only]
	@$(PY) -c "import hashlib,json; p='$(M3A)/registration.json'; \
	  d=json.load(open(p)); \
	  print(f'{\"registration_sha256\":22}', hashlib.sha256(open(p,\"rb\").read()).hexdigest()); \
	  [print(f'{k:22}', d[k]) for k in ('fixture_id','instrument_commit', \
	   'fixture_sha256','prompt_sha256','config_sha256','prior_turns_sha256', \
	   'payload_sha256','runtime_sha256','taxonomy_version','draws','status', \
	   'signed_off_by')]; \
	  print(); print('SIGNAL RULE', json.dumps(d['signal'])); \
	  print('RECURSION CAP', d['recursion_cap']); \
	  print('LABELLER', repr(d['labeller_id'])); \
	  print(); print('INSTRUMENT (the gate)'); \
	  [print(f'  {v[:12]}  {k}') for k,v in sorted(d['instrument_sha256'].items())]; \
	  print(); print('OPERATOR DECISIONS', len(d['operator_decisions'])); \
	  [print(' -', x) for x in d['operator_decisions']]"

clean: ## Remove caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .ruff_cache .pytest_cache
