# Testing and Validation

`compile` validates the scene graph produced by `build_scene_graph()` and
reports three diagnostic tiers. The goal is to drive all three to zero:

- `failure`: must be fixed (structure errors, unexempted collisions, floating).
- `warning`: should be fixed (a relation contradicts the geometry).
- `note`: informational (nothing to fix, but worth knowing).

## Structure Errors

These are `failure` and must be fixed first. `compile` stops before geometry
checks until the structure is valid.

- a node is not a dict;
- `id` is missing, empty, not a string, or duplicated;
- `type` is not one of `wall`, `floor`, `door`, `window`, `object`;
- `C`, `D`, or `theta` is not a length-3 list;
- any entry in `D` is negative;
- an edge is not a dict; its `type` is not one of the four edge types; or
  `src`/`dst` references an unknown node id.

## Collision

Two OBBs that intersect (SAT test) are a `failure` unless an `embedded_in` or
`overlaps_ok` edge is declared between them.

- `floor` never participates in collision.
- Two walls meeting at a corner do overlap; declare `overlaps_ok` if that
  overlap is intentional.
- A door/window embedded in a wall is covered by `embedded_in`.

## Floating

A `wall` or `object` whose bottom `C[1] - D[1]/2` is above the floor top
`floor.C[1] + floor.D[1]/2` by more than the tolerance (0.05) is a `failure`.

Exempt from the floating check:

- `floor` itself;
- `door` and `window` (they are embedded in walls);
- the `src` of an `abuts` edge (it is supported by `dst`).

If a scene has no `floor`, the floating check is skipped and a `note` is
reported instead.

## Warning

An `overlaps_ok` edge whose two OBBs do not actually intersect produces a
`warning`: the relation says "overlap is fine" but the geometry says "they do
not overlap". Fix either the geometry or the relation.

## Exemptions

| relation | exempts |
|----------|---------|
| `embedded_in` | collision between the door/window and its wall |
| `overlaps_ok` | collision between the two nodes |
| `abuts` | floating check for the `src` node |

By type, `floor` never collides, and `door`/`window` never float.

## Compile Loop

After every code change:

1. Run `compile`.
2. Read the reported `failure`/`warning`/`note`.
3. Fix `failure` first, then `warning`.
4. Compile again until all three tiers are empty.

## Worked Examples

A collision:

```
[failure] collision: chair vs table
```

`chair` and `table` intersect with no `embedded_in`/`overlaps_ok` edge between
them. If the overlap is legitimate (a chair under a table), add an
`overlaps_ok` edge; otherwise move one of them.

A floating object:

```
[failure] floating: table bottom=0.120 above floor top=0.000
```

The table bottom is `C[1] - D[1]/2 = 0.120`, but the floor top is `0.000`.
Lower the table so its bottom reaches `0` (`C[1] = D[1]/2`), or add an `abuts`
edge from `table` to the object that actually supports it.

A contradictory relation:

```
[warning] overlaps_ok but no overlap: chair vs table
```

The `overlaps_ok` edge is declared, but the two OBBs do not intersect. Either
place them so they overlap, or remove the edge.
