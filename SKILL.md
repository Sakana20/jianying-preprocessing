---
name: jianying-preprocessing
description: Inspect, validate, plan, apply, verify, and roll back deterministic preprocessing of existing JianYing 5.9 drafts, including media relink diagnostics, subtitle styling/highlights, benefit images, risk overlays, and configured end frames. Use for 剪映工程预处理 or jypre CLI workflows; do not use to create a new edit from raw media.
metadata:
  short-description: Preprocess existing JianYing drafts
---

# JianYing Preprocessing

Use the repository CLI; do not hand-edit Draft JSON.

```bash
python3 scripts/preprocess_draft.py list-configs --config-root configs
python3 scripts/preprocess_draft.py validate-config --config-root configs --config-set taobao-flash-v1
python3 scripts/preprocess_draft.py inspect --draft /absolute/path/to/draft
python3 scripts/preprocess_draft.py plan --job /absolute/path/to/job.json --output /absolute/path/to/plan.json
python3 scripts/preprocess_draft.py apply --job /absolute/path/to/job.json --plan /absolute/path/to/plan.json
python3 scripts/preprocess_draft.py validate --draft /absolute/path/to/draft --job /absolute/path/to/job.json
python3 scripts/preprocess_draft.py rollback --draft /absolute/path/to/draft --run-id RUN_ID
```

## Required workflow

- Treat source drafts as read-only unless the user has explicitly selected them as mutation targets. Prefer a clone supplied by the upstream workflow.
- Run `validate-config`, `inspect`, and `plan` before `apply`.
- `apply` requires a saved plan whose Draft and component hashes still match; it creates an atomic backup under `.jypre/backups/`.
- Never infer product names, benefits, image roles, or configuration values from filenames or natural language. A job selects one approved config set and contains no business-content overrides.
- Manage config sets through `configs/catalog.jsonc`; each project keeps all editable settings in one commented `config.jsonc`.
- Never bypass macOS TCC, rewrite its database, recursively change permissions, or delete an unmanaged lookalike layer.
- Only JianYing 5.9 / Draft version 360000 / 30 fps / exact configured canvas is writable in v1. Other drafts remain inspectable.

Read [references/config-and-job.md](references/config-and-job.md) when authoring a config or job. Read [references/draft-v5.9.md](references/draft-v5.9.md) when diagnosing validation or ownership failures.
