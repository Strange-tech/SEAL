"""Prompt structuring layer.

Expands a terse user request into a short natural-language design brief
(parts/links, joints, materials, size) before the main agent loop, so the model
has a concrete skeleton to build against instead of improvising from a one-word
prompt.

When a reference image is provided, the expansion is image-grounded in three
steps so the brief reflects what the image actually shows instead of what the
text alone implies:

    1. distill the user text into a short noun "hint";
    2. read the image with the hint to focus attention -> factual description;
    3. expand the text into a brief using the image description as authority.

This keeps the text brief and the reference image from contradicting each other,
and stops the image from being silently ignored.
"""

from __future__ import annotations

from provider import image_path_to_data_url

HINT_PROMPT = """Extract a single short noun phrase from the user's request that names
the object to build. Keep it to 1-4 words, no description, no punctuation.
Output only the phrase.

User request: {task}
"""

IMAGE_PROMPT = """You are examining a reference image for a 3D articulated object.
Focus on the object named by the hint and describe it as an articulated assembly.
Report only what is actually visible; do not invent. If the image does not match
the hint, describe what it really shows.

Cover these four things explicitly:

1. Links — enumerate every rigid body / part you can see. For each: its shape,
   color, material, and which one is the base (root) that the rest attach to.

2. Joints — for each connection between links: which two links it joins, and how
   it moves (hinge / slide / fixed), plus the approximate axis of motion.

3. Positions — where each link sits relative to the base (or in absolute terms):
   above / below / left / right / front / back, and rough distances or proportions.

4. Text & labels — report any visible lettering, logos, or printed/molded labels
   with their exact wording and where each sits on the object.

Hint: {hint}
"""

STRUCTURE_PROMPT = """You are writing a design brief for a 3D articulated object.

Given the user's request and the reference image description below, write a
concise natural-language design brief (no code). Treat the image description as
the authoritative source: keep what it describes, and expand or correct the
request where the two conflict or where the request is too vague.

When the reference or request shows visible lettering, logos, or printed/molded
labels, specify them as engraved/molded lettering, and list the exact strings plus where each sits. 
Do NOT describe them as "surface graphics" or imply flat decals.

Output only the brief, no preamble.

User request: {task}

Reference image description:
{image_info}
"""

TEXT_ONLY_PROMPT = """You are writing a design brief for a 3D articulated object.
Given the user's (possibly terse) request, expand it into a concise natural-language
specification. Cover, in plain language (no code):
1. Parts / links — each rigid body, its approximate shape and function, and which one is the base/root.
2. Joints — how parts connect and move (hinge / slide / fixed), including which part each joint attaches.
3. Materials & appearance.
4. Overall size and proportions.
5. Lettering & labels — if the object conventionally carries lettering, logos, or labels, specify them as engraved/molded lettering (never "surface graphics"), and name the strings.
Rules: do NOT invent parts the real object does not need; keep it grounded and concrete.
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
    """Expand `task` into a design brief, grounded in `image_path` when provided."""
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
