#!/usr/bin/env bash
set -euo pipefail
umask 077

# M3a interactive panel capture.
#
# Intended invocation from experiments/m3a/:
#
#   bash ./label-capture/m3a-label-capture.sh
#
# One invocation walks the complete preregistered order:
#
#   1. Human investigator
#   2. ChatGPT GPT-5.6 Sol / High / Temporary Chat
#   3. Claude Fable 5 / High / Incognito
#
# For model labellers the script launches the registered fresh-session URL
# before asking you to complete and capture the label run.
#
# Captured copies are canonically named, SHA256-pinned, provenance-recorded,
# and marked read-only. Source files are never modified.

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

need() {
    command -v "$1" >/dev/null 2>&1 || die "$1 is required"
}

need sha256sum
need python3
need stat
need find
need cp

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
M3A_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
REPO_DIR="$(cd -- "$M3A_DIR/../.." && pwd)"
ROOT="${M3A_LABEL_ROOT:-$SCRIPT_DIR/runs}"
ROOT="$(python3 -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve())' "$ROOT")"
PATH_PROBLEM="$(PYTHONPATH="$REPO_DIR/src" python3 -c \
    'from corpus_analysis.publication import publication_path_problem; import sys; print(publication_path_problem(sys.argv[1], sys.argv[2]))' \
    "$ROOT" "$REPO_DIR")"
[[ -z "$PATH_PROBLEM" ]] || die "$PATH_PROBLEM"

mkdir -p "$ROOT"
chmod 700 "$ROOT" 2>/dev/null || true

CHAT_URL='https://chatgpt.com/?temporary-chat=true'
CLAUDE_URL='https://claude.ai/new?incognito='

PANEL_BIN="$M3A_DIR/bin/m3a-panel"
#: Which archive the packet is rendered from. Defaults to the confirmatory
#: archive; point it at an ignored synthetic/self-test archive to exercise the
#: flow without spending a confirmatory draw.
ARCHIVE="${M3A_ARCHIVE:-$M3A_DIR/raw}"
PACKET=""          # set by render_packet, shown at every stage
PACKET_SHA=""
TEMPLATE_SHA=""

expand_home() {
    case "$1" in
        "~/"*) printf '%s/%s\n' "$HOME" "${1#~/}" ;;
        *) printf '%s\n' "$1" ;;
    esac
}

sha_file() {
    sha256sum -- "$1" | awk '{print $1}'
}

next_draw_id() {
    local max=0 d n
    shopt -s nullglob
    for d in "$ROOT"/d[0-9][0-9][0-9]*; do
        [[ -d "$d" ]] || continue
        n="${d##*/d}"
        [[ "$n" =~ ^[0-9]+$ ]] || continue
        n=$((10#$n))
        (( n > max )) && max="$n"
    done
    shopt -u nullglob
    printf 'd%03d\n' "$((max + 1))"
}

# A draw with a started-but-unfinished panel. Suggested ahead of a new draw id,
# because the common reason to run this twice is finishing what is open.
incomplete_draw() {
    local d k
    shopt -s nullglob
    for d in "$ROOT"/d[0-9][0-9][0-9]*; do
        [[ -d "$d" ]] || continue
        for k in "$d"/k[0-9]*; do
            [[ -d "$k" ]] || continue
            [[ -f "$k/PANEL.SHA256SUMS" ]] && continue
            shopt -u nullglob
            printf '%s\n' "${d##*/}"
            return 0
        done
    done
    shopt -u nullglob
    return 1
}

prompt_draw() {
    local suggested input
    suggested="$(incomplete_draw)" || suggested="$(next_draw_id)"
    read -r -p "Draw ID [$suggested]: " input || true
    input="${input:-$suggested}"
    [[ "$input" =~ ^d[0-9]{3,}$ ]] || die "draw id must look like d001"
    printf '%s\n' "$input"
}

prompt_round() {
    local input
    read -r -p "Round [1]: " input || true
    input="${input:-1}"
    [[ "$input" =~ ^[1-9][0-9]*$ ]] || die "round must be a positive integer"
    printf '%s\n' "$input"
}

prompt_existing_file() {
    local what="$1"
    local path=""
    while true; do
        # A closed stdin is no answer, not a wrong one. The stage is abandoned:
        # nothing is frozen and the operator's own files are untouched, so it
        # can be redone on resume.
        if ! read -r -e -p "$what path: " path; then
            printf '\n' >&2
            die "input closed before $what was given; this stage froze nothing"
        fi
        path="$(expand_home "$path")"
        if [[ -f "$path" && -s "$path" ]]; then
            printf '%s\n' "$path"
            return 0
        fi
        printf 'Required non-empty file not found: %s\n' "$path" >&2
    done
}

validate_json() {
    python3 - "$1" <<'PY'
import json, sys
with open(sys.argv[1], "r", encoding="utf-8") as f:
    data = json.load(f)
if not isinstance(data, dict):
    raise SystemExit("label JSON must be an object")
required = ("labeller_id", "outcome", "target_repaired", "bridges_present", "new_bridges")
missing = [k for k in required if k not in data]
if missing:
    raise SystemExit("label JSON missing required field(s): " + ", ".join(missing))
if not isinstance(data["target_repaired"], bool):
    raise SystemExit("target_repaired must be boolean")
for key in ("bridges_present", "new_bridges"):
    if not isinstance(data[key], list) or not all(isinstance(x, str) for x in data[key]):
        raise SystemExit(f"{key} must be an array of strings")
PY
}

validate_image() {
    local path="$1"
    local ext="${path##*.}"
    ext="$(printf '%s' "$ext" | tr '[:upper:]' '[:lower:]')"
    case "$ext" in
        png|jpg|jpeg|webp) printf '%s\n' "$ext" ;;
        *) die "screenshot must be PNG/JPG/JPEG/WEBP: $path" ;;
    esac
}

launch_url() {
    local url="$1"
    if command -v xdg-open >/dev/null 2>&1; then
        nohup xdg-open "$url" >/dev/null 2>&1 &
    elif command -v kde-open5 >/dev/null 2>&1; then
        nohup kde-open5 "$url" >/dev/null 2>&1 &
    elif command -v gio >/dev/null 2>&1; then
        nohup gio open "$url" >/dev/null 2>&1 &
    elif command -v firefox >/dev/null 2>&1; then
        nohup firefox "$url" >/dev/null 2>&1 &
    elif command -v chromium >/dev/null 2>&1; then
        nohup chromium "$url" >/dev/null 2>&1 &
    else
        printf '\nCould not launch browser automatically. Open manually:\n  %s\n\n' "$url" >&2
        return 1
    fi
}

write_provenance() {
    local out="$1"
    local run_id="$2"
    local draw="$3"
    local round="$4"
    local labeller_id="$5"
    local display="$6"
    local provider="$7"
    local model="$8"
    local reasoning="$9"
    local session_mode="${10}"
    local launch_url="${11}"
    local label_path="${12}"
    local transcript_path="${13:-}"
    local screenshot_path="${14:-}"

    python3 - \
        "$out.tmp" "$run_id" "$draw" "$round" "$labeller_id" "$display" \
        "$provider" "$model" "$reasoning" "$session_mode" "$launch_url" \
        "$label_path" "$transcript_path" "$screenshot_path" <<'PY'
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys

(
    out, run_id, draw_id, round_s, labeller_id, display, provider, model,
    reasoning, session_mode, launch_url, label_path, transcript_path,
    screenshot_path
) = sys.argv[1:]

def entry(path_s):
    p = Path(path_s)
    return {
        "file": p.name,
        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        "bytes": p.stat().st_size,
    }

obj = {
    "run_id": run_id,
    "draw_id": draw_id,
    "round": int(round_s),
    "labeller_id": labeller_id,
    "labeller_display": display,
    "labeller_type": "human" if provider == "human" else "model",
    "provider": provider,
    "model_displayed": None if model == "" else model,
    "reasoning_displayed": None if reasoning == "" else reasoning,
    "session_mode": None if session_mode == "" else session_mode,
    "launch_url": None if launch_url == "" else launch_url,
    "captured_at_utc": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
    "structured_label": entry(label_path),
    "capture_policy": {
        "structured_label_required": True,
        "transcript_required": bool(transcript_path),
        "screenshot_required": bool(screenshot_path),
    },
}
if transcript_path:
    obj["transcript"] = entry(transcript_path)
if screenshot_path:
    obj["screenshots"] = [entry(screenshot_path)]

Path(out).write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

    mv "$out.tmp" "$out"
    chmod 600 "$out"
}

finalize_dir() {
    local dir="$1"
    local stem="$2"
    local sums="$dir/$stem.SHA256SUMS"

    (
        cd "$dir"
        find . -maxdepth 1 -type f \
            \( -name "$stem.label.json" \
               -o -name "$stem.transcript.txt" \
               -o -name "$stem.screen-*" \
               -o -name "$stem.provenance.json" \) \
            -printf '%f\n' \
            | LC_ALL=C sort \
            | while IFS= read -r f; do sha256sum -- "$f"; done
    ) > "$sums.tmp"

    [[ -s "$sums.tmp" ]] || die "nothing captured for $stem"
    mv "$sums.tmp" "$sums"
    chmod 600 "$sums"

    find "$dir" -maxdepth 1 -type f -name "$stem.*" -exec chmod 0444 {} +

    printf '\nSHA256-pinned artifacts:\n'
    sed 's/^/  /' "$sums"
}

capture_investigator() {
    local run_root="$1" draw="$2" round="$3"
    local id="investigator"
    local stem="m3a-${draw}-k${round}-${id}"
    local dir="$run_root/$id"
    mkdir -p "$dir"
    chmod 700 "$dir"

    printf '\n============================================================\n'
    printf '1 / 3 — HUMAN INVESTIGATOR\n'
    printf '============================================================\n'
    printf 'Freeze the human investigator'\''s label before viewing either model labeller.\n'
    printf 'No transcript or screenshot is required for the human investigator.\n\n'
    show_packet
    printf '\n'

    local label_src
    label_src="$(prompt_existing_file "Human investigator structured label JSON")"
    validate_json "$label_src"

    local label="$dir/$stem.label.json"
    local prov="$dir/$stem.provenance.json"

    cp -- "$label_src" "$label"
    chmod 600 "$label"

    write_provenance \
        "$prov" "$stem" "$draw" "$round" \
        "investigator" "Human investigator" "human" "" "" "" "" \
        "$label" "" ""

    finalize_dir "$dir" "$stem"
    printf '\nHuman investigator label frozen. Do not modify captured originals.\n'
}

capture_model() {
    local run_root="$1" draw="$2" round="$3" which="$4"

    local id display provider model reasoning session_mode url
    case "$which" in
        chat)
            id="gpt56sol-high"
            display="ChatGPT GPT-5.6 Sol — High — Temporary Chat"
            provider="OpenAI"
            model="GPT-5.6 Sol"
            reasoning="High"
            session_mode="Temporary Chat"
            url="$CHAT_URL"
            ;;
        claude)
            id="fable5-high"
            display="Claude Fable 5 — High — Incognito"
            provider="Anthropic"
            model="Claude Fable 5"
            reasoning="High"
            session_mode="Incognito"
            url="$CLAUDE_URL"
            ;;
        *) die "internal model stage error: $which" ;;
    esac

    local n
    [[ "$which" == "chat" ]] && n=2 || n=3

    local stem="m3a-${draw}-k${round}-${id}"
    local dir="$run_root/$id"
    mkdir -p "$dir"
    chmod 700 "$dir"

    printf '\n============================================================\n'
    printf '%d / 3 — %s\n' "$n" "$display"
    printf '============================================================\n'
    printf 'Launching registered fresh-session URL:\n  %s\n\n' "$url"
    launch_url "$url" || true

    show_packet
    printf '\n'
    printf 'Complete the independent label run now.\n'
    printf 'Do NOT inspect another labeller'\''s captured output.\n'
    printf 'Save:\n'
    printf '  1. structured label JSON\n'
    printf '  2. complete copied transcript as TXT\n'
    printf '  3. screenshot showing the visible run/model/session context\n\n'

    local label_src txt_src image_src ext

    label_src="$(prompt_existing_file "Structured label JSON")"
    validate_json "$label_src"

    txt_src="$(prompt_existing_file "Full transcript TXT")"

    image_src="$(prompt_existing_file "Screenshot image")"
    ext="$(validate_image "$image_src")"

    local label="$dir/$stem.label.json"
    local transcript="$dir/$stem.transcript.txt"
    local screenshot="$dir/$stem.screen-01.$ext"
    local prov="$dir/$stem.provenance.json"

    cp -- "$label_src" "$label"
    cp -- "$txt_src" "$transcript"
    cp -- "$image_src" "$screenshot"
    chmod 600 "$label" "$transcript" "$screenshot"

    write_provenance \
        "$prov" "$stem" "$draw" "$round" \
        "$id" "$display" "$provider" "$model" "$reasoning" "$session_mode" "$url" \
        "$label" "$transcript" "$screenshot"

    finalize_dir "$dir" "$stem"
    printf '\n%s frozen. Do not modify captured originals.\n' "$display"
}

panel_finalize() {
    local run_root="$1"
    local sums="$run_root/PANEL.SHA256SUMS"

    (
        cd "$run_root"
        find investigator gpt56sol-high fable5-high -type f \
            \( -name '*.label.json' \
               -o -name '*.transcript.txt' \
               -o -name '*.screen-*' \
               -o -name '*.provenance.json' \
               -o -name '*.SHA256SUMS' \) \
            -printf '%p\n' \
            | LC_ALL=C sort \
            | while IFS= read -r f; do sha256sum -- "$f"; done
    ) > "$sums.tmp"

    [[ -s "$sums.tmp" ]] || die "panel manifest would be empty"
    mv "$sums.tmp" "$sums"
    chmod 0444 "$sums"

    printf '\n============================================================\n'
    printf 'PANEL CAPTURE COMPLETE\n'
    printf '============================================================\n'
    printf 'Panel root:\n  %s\n' "$run_root"
    printf 'Panel SHA256 manifest:\n  %s\n' "$sums"
}

# One packet per draw and round, rendered once and read by all three labellers.
# The registered claim is that the three labels answer the same question, and
# the cheapest way to hold that is for the same frozen bytes to be read three
# times. On resume the existing packet is reused, never re-rendered.
render_packet() {
    local run_root="$1" draw="$2" round="$3"
    local stem="m3a-${draw}-k${round}"
    local packet="$run_root/$stem.packet.txt"
    local meta="$run_root/$stem.packet.json"
    local -a target_arg=()

    if [[ ! -f "$packet" ]]; then
        if (( round > 1 )); then
            printf '\nRound %s is challenged on the finalized panel new_bridges[0]\n' "$round"
            printf 'of round %s — the quote as the panel resolved it, not one\n' "$((round - 1))"
            printf 'labeller'\''s wording.\n'
            local target=""
            if ! read -r -e -p "Finalized target quote: " target; then
                printf '\n' >&2
                die "input closed before the round $round target was given"
            fi
            [[ -n "$target" ]] || die "a round after the first needs its challenged bridge"
            target_arg=(--target "$target")
        fi
        if ! "$PANEL_BIN" --archive "$ARCHIVE" packet --draw "$draw" --k "$round" \
                "${target_arg[@]+"${target_arg[@]}"}" --out "$packet" 2>"$meta"; then
            printf '%s\n' "$(cat "$meta" 2>/dev/null)" >&2
            rm -f -- "$packet" "$meta"
            die "could not render the labelling packet for $draw k$round"
        fi
        chmod 0444 -- "$packet" "$meta"
    fi

    PACKET="$packet"
    PACKET_SHA="$(sha_file "$packet")"
    TEMPLATE_SHA="$(sha_file "$M3A_DIR/labelling/prompt-v1.txt")"
}

show_packet() {
    printf 'Packet file — paste its contents unchanged:\n'
    printf '  %s\n' "$PACKET"
    printf '  prompt_template_sha256  %s\n' "$TEMPLATE_SHA"
    printf '  rendered_packet_sha256  %s\n' "$PACKET_SHA"
}

# A stage is frozen once its SHA256SUMS exists: finalize_dir writes that last,
# after the copies are hashed and made read-only. Anything else in the
# directory is an interrupted stage that froze nothing.
stage_frozen() {
    local run_root="$1" draw="$2" round="$3" id="$4"
    [[ -f "$run_root/$id/m3a-${draw}-k${round}-${id}.SHA256SUMS" ]]
}

# An interrupted stage left copies that were never hashed. The operator's own
# files are untouched originals, so clearing the partial copies loses nothing
# and lets the stage be redone; a frozen stage is never touched.
discard_partial() {
    local dir="$1" id="$2"
    [[ -d "$dir" ]] || return 0
    printf 'Discarding an interrupted %s capture (nothing was frozen): %s\n' "$id" "$dir"
    chmod -R u+w "$dir" 2>/dev/null || true
    rm -rf -- "$dir"
}

main() {
    printf '\nM3a preregistered labeller capture\n'
    printf 'Working experiment: %s\n' "$M3A_DIR"
    printf 'Capture root:      %s\n' "$ROOT"
    printf 'Draw archive:      %s\n\n' "$ARCHIVE"

    local draw round run_root
    draw="$(prompt_draw)"
    round="$(prompt_round)"
    run_root="$ROOT/$draw/k$round"

    mkdir -p "$run_root"
    chmod 700 "$ROOT/$draw" "$run_root" 2>/dev/null || true

    if [[ -f "$run_root/PANEL.SHA256SUMS" ]]; then
        die "panel already complete for $draw k$round: $run_root"
    fi

    # Resume, not restart. Which stage runs next is read off what is already
    # frozen, never chosen, so there is no menu. A frozen stage is skipped and
    # never redone, and the ordering claim — each label frozen and hashed before
    # the next labeller launches — holds across a break of any length.
    render_packet "$run_root" "$draw" "$round"

    local ids=(investigator chat claude)
    local canon=(investigator gpt56sol-high fable5-high)
    local i frozen=0
    for i in 0 1 2; do
        if stage_frozen "$run_root" "$draw" "$round" "${canon[$i]}"; then
            (( frozen == i )) || die \
                "capture is out of order: ${canon[$i]} is frozen but an earlier stage is not"
            frozen=$((i + 1))
        fi
    done

    if (( frozen > 0 )); then
        printf 'Resuming %s k%s. Already frozen:' "$draw" "$round"
        for i in $(seq 0 $((frozen - 1))); do printf ' %s' "${canon[$i]}"; done
        if (( frozen == ${#canon[@]} )); then
            printf '\nAll stages are frozen; finalizing the panel manifest.\n'
        else
            printf '\nNext: %s\n' "${canon[$frozen]}"
        fi
    fi

    for i in 0 1 2; do
        (( i < frozen )) && continue
        discard_partial "$run_root/${canon[$i]}" "${canon[$i]}"
        if [[ "${ids[$i]}" == "investigator" ]]; then
            capture_investigator "$run_root" "$draw" "$round"
        else
            capture_model "$run_root" "$draw" "$round" "${ids[$i]}"
        fi
    done
    panel_finalize "$run_root"
}

main "$@"
