---
description: CADQUERY VECTOR CONSTRUCTION — pass three separate floats or a 3-tuple to cq.Vector; OCC gp_ objects are also accepted.
---
When creating `cq.Vector`, call it as `cq.Vector(x, y, z)` with three numeric arguments or as `cq.Vector((x, y, z))` with a 3-tuple. CadQuery/OCC also accepts an OCC `gp_` object. If you see `TypeError: Expected three floats, OCC gp_, or 3-tuple`, convert your coordinates to one of those accepted forms before retrying.
