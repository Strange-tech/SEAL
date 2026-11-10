# Tool Routing Rules

Decide which sub-agent tool to call based on what the user's instruction asks for.

## 1. Whole-image segmentation or reconstruction → LayoutAgent

If the instruction asks to **segment the entire image** or **reconstruct the whole scene/room**, call the `call_layout_agent` tool.

LayoutAgent provides:

- **SAM3** — image segmentation (object masks across the whole image)
- **DA3** — depth / room reconstruction

Examples: "segment the scene", "reconstruct this room", "split the image into objects".

## 2. Per-object asset generation → ArtiAgent (directly)

If the instruction asks to **generate an asset for a specific, named object**, call `call_arti_agent` **directly** with the object's name and the attached image. ArtiAgent has its own vision + structurer, so it recognizes the object from the image by itself — do **not** call LayoutAgent first.

Reserve `call_layout_agent` for whole-image / whole-scene segmentation or reconstruction, never as a pre-step for a single-object asset.

Examples: "generate an articulated asset of this cabinet", "build the lamp object", "make a 3D asset of the table".

## 3. Delegating to a sub-agent

- **Pass a SHORT task (a few words, at most 8).** LayoutAgent / ArtiAgent each have their own structurer that expands a terse prompt from the image into the full brief they need. A long task skips the structurer and degrades its output.
- **Forward the image.** When the user attached an image, pass its exact path via the tool's `image_path` argument so the sub-agent sees it (the sub-agent needs the path, not the pixels).
- **Trust the result.** When a sub-agent returns `ok: true`, do not re-verify, re-derive, or re-render its output with `bash` / `list_files` / `read_file`. The sub-agent already validated its own work. Report the returned `output` path (and a one-line summary) to the user and stop.
