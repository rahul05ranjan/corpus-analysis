# M3a interactive label capture

Run from the experiment directory:

```text
experiments/m3a/
```

with exactly:

```bash
bash ./label-capture/m3a-label-capture.sh
```

The script prompts for the draw ID and round, then forces the complete order:

```text
1. Human investigator
2. ChatGPT GPT-5.6 Sol / High / Temporary Chat
3. Claude Fable 5 / High / Incognito
```

There is no stage menu.

## Human investigator

Required:

- structured label JSON

Not required:

- transcript
- screenshot

Human investigator's label is copied, hashed, provenance-recorded, and frozen before ChatGPT is launched.

## ChatGPT

The script launches:

```text
https://chatgpt.com/?temporary-chat=true
```

Then requires paths to:

- structured label JSON
- complete copied transcript `.txt`
- screenshot (`png`, `jpg`, `jpeg`, or `webp`)

The captured copies are SHA256-pinned before Claude is launched.

## Claude

The script launches:

```text
https://claude.ai/new?incognito=
```

Then requires paths to:

- structured label JSON
- complete copied transcript `.txt`
- screenshot

## Output

Default private root:

```text
experiments/m3a/label-capture/runs/
```

`M3A_LABEL_ROOT` selects another capture root. A repository-local override must
remain under `label-capture/runs/` or `label-capture/labels-private/`; other
repository paths are refused. `M3A_ARCHIVE` selects the draw archive read while
rendering packets.

Example:

```text
label-capture/runs/d001/k1/
├── PANEL.SHA256SUMS
├── investigator/
│   ├── m3a-d001-k1-investigator.label.json
│   ├── m3a-d001-k1-investigator.provenance.json
│   └── m3a-d001-k1-investigator.SHA256SUMS
├── gpt56sol-high/
│   ├── m3a-d001-k1-gpt56sol-high.label.json
│   ├── m3a-d001-k1-gpt56sol-high.transcript.txt
│   ├── m3a-d001-k1-gpt56sol-high.screen-01.png
│   ├── m3a-d001-k1-gpt56sol-high.provenance.json
│   └── m3a-d001-k1-gpt56sol-high.SHA256SUMS
└── fable5-high/
    └── ...
```

The source files you point at are never modified. Captured copies become mode
`0444` after hashing. Resuming an incomplete stage removes that stage's partial
capture directory before copying it again; a completed frozen stage is never
replaced.

The script does not call either model or API itself. It only launches the
registered browser URL and captures the artifacts you save.
