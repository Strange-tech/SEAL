"""Prompt structuring layer for LayoutAgent.

Expands a terse user request into a short natural-language scene-graph brief
(nodes + edges) before the main agent loop, so the model has a concrete skeleton
of the room to build against instead of improvising from a one-word prompt.

When a reference image is provided, the expansion is image-grounded in three
steps so the brief reflects what the image actually shows instead of what the
text alone implies:

    1. distill the user text into a short noun "hint";
    2. read the image with the hint to focus attention -> factual scene description;
    3. expand the text into a scene-graph brief using the image description as a coarse prior.

The brief must name the nodes and edges explicitly, so the main agent can map
them onto room.py's build_scene_graph() returning {"nodes": [...], "edges": [...]}.
"""

from __future__ import annotations

from provider import image_path_to_data_url

HINT_PROMPT = """Extract a single short noun phrase from the user's request that names
the room or scene to reconstruct. Keep it to 1-4 words, no description, no punctuation.
Output only the phrase.

User request: {task}
"""

IMAGE_PROMPT = """You are examining a reference image for an indoor room reconstruction.
Focus on the room named by the hint and describe it as a scene graph (nodes + edges).

Your role is the VLM prior: for each object give (a) its semantic identity (what it is),
(b) a coarse spatial relation, and (c) a prior reasonable OBB — approximate real-world scale
(width / height / depth) and orientation (which way it faces / how it is aligned). This is only
a coarse prior; the reconstruction agent gets the accurate spatial relation from perception
(sam3_segment masks + da3_reconstruct metric depth + backproject_obb). So be conservative: report
only what is clearly and confidently visible, and do NOT invent counts, colors, materials, or
exact positions of small or ambiguous objects — when unsure, omit the detail rather than guessing.
If the image does not match the hint, describe what it really shows.

Cover these two things explicitly, using exactly these vocabularies.

1. Nodes — enumerate the clearly-visible surfaces and objects that should become scene-graph
   nodes. Use these node types only: wall, floor, door, window, object.
   For each node give: its type (semantic identity), approximate real-world size (width / height /
   depth), its orientation (the direction it faces / how it is aligned, e.g. "facing into the room,
   aligned with the back wall"), and its layout in the room — an absolute position (e.g. "against
   the back wall, centered horizontally, at floor level") or a position relative to other objects
   (e.g. "to the left of the window, resting on the countertop"), whichever is more accurate — use
   both when it helps pin the object down. Mention color / material only if clearly visible. Only
   declare a floor node if the floor is actually visible in frame; in a close-up the reference
   horizontal surface may be a countertop or tabletop instead.

2. Edges — for every spatial relation between two nodes, name the two nodes it connects and
   the relation type, using these edge types only:
   - embedded_in: a door/window embedded inside a wall;
   - adjacent: two elements next to each other horizontally (e.g. neighbouring walls);
   - supports: one object supported by another (e.g. a cup on a table, a picture on a wall); their OBB faces must be in tight contact (no gap);
   - overlaps_ok: an allowed overlap (e.g. a chair tucked under a table).

Hint: {hint}
"""

STRUCTURE_PROMPT = """You are writing a scene-graph design brief for an indoor room reconstruction.

Division of labour:
- The reference image description below is the VLM prior: it names each object's semantic identity,
  gives a coarse spatial relation, and supplies a prior reasonable OBB (scale + orientation).
- Perception (sam3_segment masks/boxes + da3_reconstruct metric depth + backproject_obb) supplies
  the accurate spatial relation (real position, and real scale/orientation when the object is fully
  in frame).

Write a concise natural-language brief (no code) from the prior. Keep the prior provisional — do
not assert exact counts, colors, materials, or precise positions the prior cannot be sure of; where
the request and prior conflict, state both and prefer the more conservative reading.

The brief MUST explicitly name:
1. Nodes — every element to create, each with its node type (wall / floor / door / window / object),
   its approximate prior OBB (scale: width / height / depth, and orientation), and its coarse layout
   in the room (absolute position, or position relative to other nodes, whichever is more accurate —
   use both when helpful).
2. Edges — every spatial relation, each with its type (embedded_in / adjacent / supports / overlaps_ok)
   and which two nodes it connects.

End with one short closing line telling the agent how to reconcile the two: use sam3_segment +
da3_reconstruct + backproject_obb for the accurate position (and for full scale/orientation when the
object is fully in frame); but when an object is only partially in frame so perception's OBB is
truncated and conflicts with the prior, fall back to this VLM prior for the object's complete scale
and orientation.

Output only the brief, no preamble.

User request: {task}

Reference image description (VLM prior):
{image_info}
"""

TEXT_ONLY_PROMPT = """You are writing a scene-graph design brief for an indoor room reconstruction.
Given the user's (possibly terse) request, expand it into a concise natural-language
specification (no code).

Cover, in plain language:
1. Nodes — every element to create, each with its node type (wall / floor / door / window / object),
   approximate size, and its layout in the room (absolute position, or position relative to other
   nodes, whichever is more accurate — use both when helpful).
2. Edges — every spatial relation, each with its type (embedded_in / adjacent / supports / overlaps_ok)
   and which two nodes it connects.
Rules: do NOT invent elements the real room does not need; keep it grounded and concrete.
If the request names a room shape (square / rectangle / L / U / T / L-shape / U-shape / etc.), that shape is the CLOSED boundary of the room: enumerate EVERY wall segment required to fully enclose the room with no gaps. A U-shaped room is a fully-enclosed room whose outline traces a U (two parallel legs plus a connecting bar): it needs the two outer side walls, the back wall, the two leg-end walls, and the two inner notch walls — never just 3 open walls.
Output only the brief, no preamble.
User request: {task}
"""

MAX_STRUCTURE_WORDS = 8


def should_structure(task: str) -> bool:
    """Structure only terse prompts; leave detailed prompts untouched."""
    return len((task or "").split()) <= MAX_STRUCTURE_WORDS


def _ask(provider, content) -> str:
    req = [{"role": "user", "content": content}]
    r = provider.send(req, None)
    return (r["choices"][0]["message"].get("content") or "").strip()


def structure_task(provider, task: str, image_path: str | None = None) -> str:
    """Expand `task` into a scene-graph brief, grounded in `image_path` when provided."""
    if not image_path:
        return _ask(provider, TEXT_ONLY_PROMPT.format(task=task))

    # 1) distill the text into a short noun hint that focuses the vision pass
    hint = _ask(provider, HINT_PROMPT.format(task=task)) or task

    # 2) read the image using the hint to focus attention
    image_content = [
        {"type": "text", "text": IMAGE_PROMPT.format(hint=hint)},
        {"type": "image_url", "image_url": {"url": image_path_to_data_url(image_path)}},
    ]
    image_info = _ask(provider, image_content)

    # 3) expand the text into a brief, guided by the image description
    return _ask(
        provider,
        STRUCTURE_PROMPT.format(
            task=task,
            image_info=image_info or "(image produced no description)",
        ),
    )
