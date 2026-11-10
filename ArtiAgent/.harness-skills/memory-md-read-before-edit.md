---
description: EDITING MEMORY.MD — call read_file on MEMORY.md before attempting edit_file in the same session.
---
Before modifying `MEMORY.md`, always call `read_file('MEMORY.md')` first in the same session. The edit tool rejects writes to an unread MEMORY.md with the error: `MEMORY.md exists but has not been read in this session. Use read_file first before modifying.`
