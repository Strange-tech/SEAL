# LayoutAgent × ArtiAgent 分层双智能体 执行方案

> 对应 `hierarchy_plan.md`。BaseAgent 长驻编排，LayoutAgent 管场景结构，ArtiAgent 管物体精细几何。

## 0. 现状与关键决策

### 现状
- `BaseAgent`（`/home/data/johnli/BaseAgent`）：一次性 CLI，无 `--image`，无编排。
- `LayoutAgent`（`/home/data/johnli/LayoutAgent`）：`--task --image` → `room.py`（`build_scene_graph()` 返回 `{"nodes":[{C,D,theta}], "edges":[...]}`），有 SAM3/DA3/compile/persistence。
- `ArtiAgent`（`/home/data/johnli/ArtiAgent`）：`--task [--image]` → 编辑 `model.py`（`build_object_model() -> ArticulatedObject`，URDF+mesh），有 structurer/compile_model/probe_model/review。**目前无 `--box`**。

### 关键决策（先定死，不返工）
1. **子进程编排（非 in-process import）**：两个 subagent 各自独立持有 system prompt/sdk/session/全部文件，天然对应子进程。BaseAgent 用 `subprocess` 调两个项目的 `main.py`，CLI 参数传任务、JSON 文件收结果。不复用 BaseAgent 现有的 `subagent.py`（那是单项目内工具 fan-out，不是跨项目调用）。
2. **机器可读交换（JSON）**：新增两个 emit —— LayoutAgent `--emit-scene-graph <path>`（dump `build_scene_graph()` 结果）；ArtiAgent `--emit-result <path>`（dump 产物目录 + 真实包围盒）。
3. **坐标系契约**：统一 y-up、物体正面=+z（朝向相机）、上方=+y，与 LayoutAgent 房间系一致。ArtiAgent 的 box 约束与真实包围盒都按此约定。

### SDK 核查结论（已核实）
- **真实包围盒**：SDK 无现成函数，但原语齐全 —— FK/姿态 `pose()`/`_world_tfs()`（`sdk/_core/v0/_testing/core.py:560,608`）、按关节限位采样（`fail_if_parts_overlap_in_sampled_poses`）、AABB 原语 `part_local_aabbs` / `_transform_aabb`（`_testing/common.py:371`）/ `_aabb_union`（`collision_helpers.py:59`）、关节限位 `articulation.motion_limits`（lower/upper）。→ 缺一个「遍历关节 range 并集所有 world AABB」的组装函数（见 Phase 4）。
- **差集/布尔**：SDK 已有布尔能力 —— `manifold3d`/`cadquery`/`trimesh`（`requirements.txt`），`sdk/_core/v0/_mesh/booleans.py` 已有 `_boolean_union_many` / `_manifold_from_geometry` / `_geometry_from_manifold`，`_mesh/controls.py` 有 `_cut_with_pattern`/`BezelCutout`。→ 差集在 ArtiAgent 做，基于 manifold3d 补一个 difference helper 即可（见 Phase 7）。

---

## Phase 1 — BaseAgent 长驻进程（REPL）

**目标**：一次性 CLI → 「输入一句 → 回复 → 等待下一句」常驻进程，session 跨轮延续。

**改动**：`BaseAgent/main.py`
- 加 `--repl`（或默认）模式：`while True: line = input(...)`，每轮 `agent.run(line)`，打印回复后继续等待。可以考虑用流式输出
- 同一 session 跨轮复用（不新建），上下文/记忆延续。
- 补 `--image` 参数（BaseAgent 现在没有，后面编排要用）。

**验收**：进程不退出；连续两轮能引用上一轮内容；`--help` 显示 `--image`。

---

## Phase 2 — 子进程编排层 + 子进程契约

**目标**：BaseAgent 能调用两个外部项目并拿到结构化结果。

**改动**
- 新增 `BaseAgent/subprocess_agent.py`：`run_layout_agent(...)` / `run_arti_agent(...)`，封装 `subprocess.run([python, <project>/main.py, ...args])` + 读 JSON 输出 + 超时/错误处理。
- 新增 `BaseAgent/tool_project.py`（可选）：把上面两个函数暴露成工具（`call_layout_agent` / `call_arti_agent`）给主 LLM 用。
- **LayoutAgent**：`main.py` 加 `--emit-scene-graph <path>`（跑完 dump `nodes/edges` JSON）。
- **ArtiAgent**：`main.py` 加 `--emit-result <path>`（先占位，Phase 3/4 填内容）。

**验收**：`run_layout_agent` 取回 `nodes/edges`；`run_arti_agent` 跑通取回占位 JSON。

---

## Phase 3 — ArtiAgent `--box` 约束 + 坐标系对齐

**目标**：ArtiAgent 支持 `--box`，物体约束在给定 box 的 scale+position 内；VLM 推正面=+z、上方=+y。

**改动**（`ArtiAgent/`）
- `main.py` 加 `--box '<cx,cy,cz>,<w,h,l>,<rx,ry,rz>'`（或 JSON），解析后传给 structurer + system prompt。
- `agent/structurer.py` / `agent/prompts.py`：box 作为**硬约束**写入 brief ——「物体必须落在该 box 内，正面沿 +z、上方沿 +y（与房间系一致）」。
- 几何层约束：除 prompt 外，让 `build_object_model` 的 root part 尺寸/朝向对齐 box。看 SDK 是否有「按外部 AABB/OBB 缩放+定位」入口；没有则加 `sdk` helper `fit_to_box(model, box)`，在 scaffold 中供 agent 调用。

**验收**：`--box "0,0.5,0,0.5,0.8,0.5,0,0,0"` 生成的物体 root 包围盒 ≈ 给定 box，z/y 朝向对齐。

---

## Phase 4 — ArtiAgent「真实包围盒」工具（补 SDK 函数）

**目标**：ArtiAgent 返回铰链物体**所有关节全活动范围**覆盖的包围盒（非当前姿态）。

**改动**（`ArtiAgent/`）
- SDK 加 `sdk/_core/v0/real_bounding_box.py`（或并入现有模块）：
  `joint_range_bounding_box(model, samples=None) -> (center, dims)`。
  实现：枚举关节限位采样（复用 `fail_if_parts_overlap_in_sampled_poses` 的采样逻辑）→ 每姿态取各 part 的 `part_local_aabbs` → `_transform_aabb` 到 world（用 `_world_tfs()`）→ `_aabb_union` 求并集 → 返回 root 帧下的 (center, dims)。这是一个组装函数，不涉及新运动学。
- 新增工具 `real_bbox`（放 `tool_layer.py` 或新 `tools/bbox.py`），调上述 SDK 函数。
- `--emit-result` 写 `{asset_dir, real_bbox}`。

**验收**：对开盖箱子，`real_bbox` 范围 ≥ 盖子全开 + 闭合两姿态并集。

---

## Phase 5 — BaseAgent 编排主流程（layout 先行 → 每 box 并行 ArtiAgent）

**目标**：`--image input/xx.png --task "reconstruct xxx"` 走通「Layout → 逐 box 并行 ArtiAgent」。

**改动**（`BaseAgent/`）
- `subprocess_agent.py` 加 `orchestrate_reconstruct(image, task)`：
  1. 调 LayoutAgent → 取 `nodes/edges`。
  2. 筛出需精细化的 `object` 节点（每节点一个 box）。
  3. 对每 box 并行调 ArtiAgent（`ThreadPoolExecutor`；`--image`=该物体 SAM3 mask、`--task`=VLM 语义描述、`--box`=该 box）。
  4. 汇总 `{asset_dir, real_bbox}`。
- 主 agent 用工具 `reconstruct_scene` 触发此流程。

**验收**：一张图 → room.py 布局 + 每物体独立 ArtiAgent 产物；并行 N 时总耗时 ≈ 单物体耗时而非 N×。

---

## Phase 6 — 双向迭代优化循环

**目标**：ArtiAgent 真实包围盒回传 LayoutAgent，布局自适应铰链形变，消除碰撞与悬空。

**改动**（`BaseAgent/` + `LayoutAgent/`）
- LayoutAgent 加 `--apply-bboxes <json>`：读入各物体真实包围盒，覆盖 room.py 对应节点的 `D`（必要时 `C`），再 `compile` 重校验。
- `orchestrate_reconstruct` 改为循环：
  `layout → per-box ArtiAgent → real_bbox → apply-bboxes → compile → 仍有碰撞/悬空则再迭代`，直到 stable 或达上限。

**验收**：开盖物体从「闭盖 box」被修正为「全开真实 box」，邻近物体间距/支撑不再冲突。

---

## Phase 7 — 跨物体互适应（差集在 ArtiAgent，OBB 不变）

> 差集**不做在 LayoutAgent**。host 物体的几何在 ArtiAgent 里被 guest 挖去，但其 OBB 保持不变。

**目标**：`embedded_in` 关系改变 host 物体几何 —— 如窗户嵌入墙 → 墙 mesh 被挖洞，但墙的 OBB 仍是完整墙 box。

**改动**（`ArtiAgent/`）
- ArtiAgent 加 `--subtract '<box1>;<box2>...'`（要挖掉的 guest 体积盒，房间系），由 BaseAgent 从 `embedded_in` 边解析后传入。
- 几何层：用现有 manifold3d 布尔做差集。`sdk/_core/v0/_mesh/booleans.py` 若只有 union，补 `_boolean_subtract(...)`（manifold3d `Manifold - Manifold`）。
- host 物体的 root OBB **不变**（仍是墙 box），只有 mesh 带孔；`real_bbox` 也仍按 OBB 报，不因挖洞而变。

**验收**：窗户嵌入墙后，墙 mesh 有对应开孔，窗与墙不重叠；墙的 `D`/`C` 不变。

---

## Phase 8 — subagent session 压缩共享

**目标**：两个 subagent 的 session 记录被压缩后汇入 BaseAgent 的 session。

**改动**（`BaseAgent/`）
- `subprocess_agent.py` 跑完后读对应项目 `.sessions/<id>.jsonl`。
- 复用 BaseAgent `compression.compact` 压成一段摘要，append 到 BaseAgent 自己的 session（作为跨 agent 上下文记忆）。

**验收**：跑完一次 reconstruct，BaseAgent 会话出现「LayoutAgent 摘要 + 各 ArtiAgent 摘要」；下一轮能据此回答「上一步某物体为何这样摆」。

---

## 建议执行顺序与依赖

```
Phase 1 (REPL)      ──┐
Phase 2 (编排层)     ──┼── 可先做，互不阻塞
Phase 3 (--box)      ──┤
Phase 4 (real bbox)  ──┤
                       ↓
Phase 5 (主流程，依赖 2+3)
Phase 6 (迭代循环，依赖 4+5)
Phase 7 (差集/挖洞，依赖 5)
Phase 8 (session 共享，依赖 2，可与 3–7 并行)
```

## 风险 / 待确认
1. 关节限位字段名需在 Phase 4 确认（`motion_limits` vs `limit`，见 `_urdf_export.py:215` 与 `expectations.py:708` 两处写法）。回答：用 motion_limits
2. `_mesh/booleans.py` 当前是否只有 union、是否需要补 `subtract`（Phase 7 开工前确认）。需要补subtract
