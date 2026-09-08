# JianYing 5.9 invariants

- Authoritative timeline: `draft_info.json`; supported `version` is `360000` at 30 fps.
- Segment-to-material links use `segment.material_id -> materials.*[].id`. `materials.videos[].material_id` is not the join key.
- Photo and video assets both live under `materials.videos`; select business material by `type=video` and the configured business track.
- Subtitle edits start from the selected text track and its referenced `materials.texts`, never every text material globally.
- Existing segment/material IDs, original media timeranges, and unknown fields are preserved.
- New time boundaries are calculated in frames and converted from absolute boundaries with `floor(frame * 1_000_000 / fps)`.
- Managed images include photo material, segment, track, speed, canvas, sticker animation, sound-channel mapping, vocal-separation material, and sidecar mappings.
- Managed ownership is recorded in `.jypre/state.json`. Without valid state, a lookalike asset is reported as unmanaged and is never deleted or adopted automatically.
- `template-2.tmp` is synchronized only when its pre-apply hash exactly equals `draft_info.json`.

The three local reference drafts establish these expected shapes:

| Draft | Tracks | Segments | Meaning |
|---|---:|---:|---|
| 1 | 3 | 127 | source |
| 2 | 4 | 128 | subtitles plus risk overlay |
| 3 | 5 | 138 | Draft 2 plus ten benefit-image segments |

`inspect` is safe for unsupported versions. `plan` and `apply` are intentionally version-gated.

