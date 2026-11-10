---
description: ARTICULATED OBJECT ROOTS — return exactly one root part and attach all other parts to it; never expose multiple top-level parts.
---
Articraft compiles an articulated object by walking a single root. Before returning from your model-building function, trace every created part (e.g., chair_base, ottoman_base): it must be reachable as a descendant of exactly one top-level root part. Create one root object and attach the other parts to it using the Articraft attachment API described in docs/sdk/references/articulated-object.md or by building them as children/sub-assemblies of that root. Do not return a list, multiple bare `cq.Workplane`/Part objects, or several `add()` calls that leave more than one object at the top level.
