---
description: DEFINING REVOLUTE/CONTINUOUS JOINTS — set the parent to the part that stays fixed and the child to the part that moves, and name the articulation parent_to_child.
---
For any articulation, the parent part is the fixed anchor and the child is the moving part. Use model.articulation(name='<fixed>_to_<moving>', ArticulationType.CONTINUOUS, parent=<fixed_part>, child=<moving_part>, origin=..., axis=..., motion_limits=...). The joint axis passes through the parent, and the child rotates or translates relative to it. When a part must not move on its own (e.g., a cap held by fingers), make it the parent. To verify, assert the parent's world position is unchanged when the joint pose changes, while the child's bounding box or position changes.
