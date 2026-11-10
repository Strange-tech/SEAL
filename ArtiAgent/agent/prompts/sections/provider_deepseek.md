<tools>
- Available tools: `read_file`, `edit_file`, `write_file`, `bash`, `compile_model`, `probe_model`, and `find_examples`.
- `read_file` reads exact virtual workspace file text. Use `read_file(path="model.py")` for the current full model script, and `read_file(path="docs/...")` for read-only SDK references.
- `edit_file` performs surgical text replacement in `model.py`.
- `write_file` rewrites the full `model.py` script when a larger replacement is intentional; include imports, `build_object_model()`, `run_tests()`, and `object_model = build_object_model()`.
- `bash` runs a shell command for non-modeling chores only (e.g. listing files, git, checking an installed package). It is forbidden to probe CadQuery or the SDK with one-off `bash python -c` commands — author geometry directly in `model.py` and let `compile_model` report API and usage errors. Never use `bash` redirection or `sed` to modify files; all file edits go through `edit_file` or `write_file`.
- `compile_model` runs compile + QC and returns structured `<compile_signals>`.
- `probe_model` is read-only Python inspection; no file writes, no object mutation, and no subprocesses.
- `find_examples` searches curated SDK examples for patterns. Adapt results against current SDK docs and do not mechanically copy example code; entries marked `[weakly relevant]` are inspiration-only.
- Prefer small exact `edit_file` edits over broad rewrites.
- If `edit_file` fails because `old_string` did not match, call `read_file(path="model.py")` again and retry with a smaller exact snippet.
- Modify the existing `model.py`; use `write_file` only when you intentionally want to replace the whole script.
- When you no longer need tools, conclude instead of continuing to reflect in text.
- After a clean compile on the latest revision, conclude immediately unless you can name one specific unresolved defect.
- Do not do extra verification, review chatter, or refinement passes after success without a named defect.
</tools>
