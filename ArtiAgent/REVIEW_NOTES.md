

## Review of session `20261103-204945-94247aea` (2026-11-03 22:10:33)
- **Degenerate boolean operations need a verified guard or workaround**: Human should verify how CadQuery/OCCT boolean calls should be guarded against degenerate or non-intersecting operands (e.g., shape validity/intersection checks or safe fallback patterns), since a prompt-only fix is not currently specified.

## Review of session `20261103-232024-0a9a765d` (2026-11-03 23:34:26)
- **Audit fillet edge selectors on named part stacks**: Human should audit the fillet selection code and document the correct selector string per target part or add a preflight guard that checks `selector.vals()` and the parent solid before applying fillet/chamfer. Also verify whether the intended edge selection should be something like `faces('>Z').edges()` rather than `edges('>Z')`.

## Review of session `20261104-193417-785e5867` (2026-11-04 19:38:12)
- **Improve overlap/floating-part error localization**: Enhance compiler-owned global QC to include part names, coordinates, or a minimal geometry snippet for overlapping/floating parts so agents can locate and fix issues in one round.