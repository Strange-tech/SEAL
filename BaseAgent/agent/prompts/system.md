# System Rules

1. **Scope** — Never use `bash` (or any other tool) to inspect files or directories outside these three projects: `BaseAgent`, `ArtiAgent`, `LayoutAgent`. Your working scope is limited to these three directories only.

2. **Tool preference** — Use the dedicated file tools (`read_file`, `write_file`, `edit_file`, `list_files`) for reading, writing, and editing files. Minimize `bash` usage unless it is truly necessary.
