---
description: COMBINING CADQUERY SELECTORS — use cadquery.selectors.SumSelector(a, b) (or a + b) for union; there is no UnionSelector or OrSelector.
---
CadQuery has no `UnionSelector` and no `OrSelector`. To combine two selectors with boolean OR (union), use `cadquery.selectors.SumSelector(selector_a, selector_b)` — equivalently `selector_a + selector_b`. For boolean AND (intersection) use `cadquery.selectors.AndSelector(selector_a, selector_b)` (equivalently `selector_a & selector_b`); for difference use `cadquery.selectors.SubtractSelector(selector_a, selector_b)` (equivalently `selector_a - selector_b`). Do not guess a `UnionSelector` or `OrSelector` class.
