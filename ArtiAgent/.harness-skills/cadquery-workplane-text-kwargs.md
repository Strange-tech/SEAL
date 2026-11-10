---
description: ENGRAVING TEXT — correct cq.Workplane.text kwargs: fontsize (lowercase), distance, combine.
---
cq.Workplane.text signature is:
(self: ~T, txt: str, fontsize: float, distance: float, combine: Union[bool, Literal['cut', 'a', 's']] = 'cut', clean: bool = True, font: str = 'Arial', fontPath: Optional[str] = None, kind: Literal['regular', 'bold', 'italic'] = 'regular', halign: Literal['center', 'left', 'right'] = 'center', valign: Literal['center', 'top', 'bottom'] = 'center') -> ~T
Use `fontsize` (not `fontSize`) for text size, `distance` for extrusion depth, and `combine` for how the text is combined with the workplane. Valid combine values are `True`, `False`, or one of the strings 'cut', 'a', 's'.
