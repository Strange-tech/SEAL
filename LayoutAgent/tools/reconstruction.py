"""Depth Anything 3 reconstruction tool (lazy-loaded).

Corresponds to plan.md flow step 3 "DA3 gives the scene points + camera pose + frame depth".
DA3 single-frame inference returns ``depth / intrinsics / extrinsics / conf``; the point cloud is obtained by backprojection (see ``sdk.projection``), and an object OBB is fitted from mask + point cloud (see ``sdk.fitting``).

The ``DA3NESTED`` series outputs metric depth (real scale); the ``Monocular`` series is relative depth.
Dependency: ``pip install depth-anything-3`` (needs CUDA GPU, PyTorch); model weights are loaded from a local directory (default ``~/models/DA3NESTED-GIANT-LARGE/``, overridable via the ``DA3_MODEL`` env var).
"""

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from sdk.projection import unproject_masked
from sdk.fitting import mask_to_obb

# --- in-repo third-party path (robust to repo renames/moves) -----------------
# Prefer the in-repo copy of depth_anything_3 (src layout) over any pip install,
# so a rename or move of the project never breaks ``import depth_anything_3``.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_DA3_SRC = _REPO_ROOT / "third_party" / "depth-anything-3" / "src"
if str(_DA3_SRC) not in sys.path and _DA3_SRC.is_dir():
    sys.path.insert(0, str(_DA3_SRC))

# DA3 model weights (DA3NESTED series = metric depth). Override with the DA3_MODEL
# env var; default to the local weights dir under $HOME/models.
DEFAULT_MODEL = os.environ.get("DA3_MODEL") or str(
    Path.home() / "models" / "DA3NESTED-GIANT-LARGE"
)
# Longest-side processing resolution for DA3. The library default is 504; 1008
# (2x) stays well within 48 GB and gives a finer depth map. Override with the
# DA3_PROCESS_RES environment variable if needed.
DEFAULT_PROCESS_RES = 1008


def da3_available():
    """Check whether DA3 is installed (without loading the model)."""
    try:
        import depth_anything_3  # noqa: F401
        return True
    except Exception:
        return False


@dataclass
class Reconstruction:
    """Single-frame reconstruction result: depth/intrinsics/extrinsics/conf, plus backprojection and OBB fitting."""

    depth: np.ndarray                      # (H, W) float32
    intrinsics: np.ndarray                 # (3, 3) float32
    extrinsics: np.ndarray                 # (3, 4) float32 (w2c)
    conf: np.ndarray = None                # (H, W) float32 optional
    width: int = 0
    height: int = 0

    def _resize_mask(self, mask):
        """Resize an external mask (SAM3 output, original resolution) to the depth resolution.

        DA3 internally resizes the input to (height, width) before inference, so its depth / intrinsics correspond to that resolution; SAM3's mask is at the original resolution. Directly broadcasting the two would mismatch shapes, so here the mask is nearest-neighbor resized to the depth resolution before backprojection.
        """
        mask = np.asarray(mask)
        if mask.shape[:2] == (self.height, self.width):
            return mask.astype(bool)
        from PIL import Image
        img = Image.fromarray(mask.astype(np.uint8) * 255)
        img = img.resize((self.width, self.height), Image.NEAREST)
        return np.asarray(img).astype(bool)

    def world_points(self, mask=None):
        """Backproject the whole (or masked) depth into a world point cloud (N,3)."""
        if mask is not None:
            mask = self._resize_mask(mask)
        return unproject_masked(self.depth, self.intrinsics, self.extrinsics, mask)

    def object_obb(self, mask, min_points=50):
        """mask region -> world point cloud -> upright OBB. Returns (center, dims, theta) or None."""
        mask = self._resize_mask(mask)
        return mask_to_obb(self.depth, self.intrinsics, self.extrinsics, mask,
                           min_points=min_points)


class Reconstructor:
    """DA3 single-frame reconstructor (``process_res`` = longest-side input resolution)."""

    def __init__(self, model_name=DEFAULT_MODEL, process_res=None, **model_kwargs):
        self.model_name = model_name
        self.process_res = int(
            process_res or os.environ.get("DA3_PROCESS_RES", "") or DEFAULT_PROCESS_RES
        )
        self._model_kwargs = model_kwargs
        self._model = None

    def _load(self):
        if self._model is not None:
            return
        try:
            from depth_anything_3.api import DepthAnything3
        except ImportError as e:
            raise ImportError(
                "Depth Anything 3 is not installed. Run `pip install depth-anything-3` "
                "and satisfy the CUDA/PyTorch dependencies, then retry."
            ) from e
        self._model = DepthAnything3.from_pretrained(self.model_name, **self._model_kwargs)

    def reconstruct(self, image):
        """Run inference on a single image and return a :class:`Reconstruction`."""
        self._load()
        pred = self._model.inference([image], process_res=self.process_res)
        return Reconstruction(
            depth=np.asarray(pred.depth[0], dtype=np.float32),
            intrinsics=np.asarray(pred.intrinsics[0], dtype=np.float32),
            extrinsics=np.asarray(pred.extrinsics[0], dtype=np.float32),
            conf=np.asarray(pred.conf[0], dtype=np.float32) if getattr(pred, "conf", None) is not None else None,
            width=int(np.asarray(pred.depth[0]).shape[1]),
            height=int(np.asarray(pred.depth[0]).shape[0]),
        )


class PerceptionState:
    """Shared state between the SAM3/DA3 tools: input image + DA3 reconstruction + SAM3 mask cache.

    mask / depth / point cloud are large numpy arrays that cannot round-trip through the LLM's JSON tool protocol, so this object caches them in-process and tools refer to them by object name.
    """

    def __init__(self, image_path=None):
        self.image_path = image_path          # str | None
        self.image = None                     # PIL.Image (RGB)
        self.reconstruction = None            # Reconstruction | None
        self.masks = {}                       # name -> (H,W) bool ndarray
        self.boxes = {}                       # name -> [x1,y1,x2,y2] (SAM3 box, original resolution)

    def load_image(self):
        """Lazily load the input image and return a PIL.Image (RGB)."""
        if self.image is None:
            if not self.image_path:
                raise RuntimeError("no input image provided: pass --image <path> at startup")
            from PIL import Image
            self.image = Image.open(self.image_path).convert("RGB")
        return self.image


class Da3ReconstructTool:
    """LLM tool: run DA3 on the input image; the reconstruction is cached in the shared state."""

    def __init__(self, state):
        self.state = state
        self._reconstructor = None

    def definition(self):
        return {
            "name": "da3_reconstruct",
            "description": (
                "This tool is used for task [Reconstruction]. Run Depth Anything 3 on the input image to get metric depth plus camera "
                "intrinsics/extrinsics. Caches the reconstruction for backproject_obb."
            ),
            "parameters": {"type": "object", "properties": {}},
        }

    def execute(self, args):
        try:
            image = self.state.load_image()
        except Exception as e:
            return "Error: " + str(e)
        if self._reconstructor is None:
            self._reconstructor = Reconstructor()
        try:
            recon = self._reconstructor.reconstruct(image)
        except Exception as e:
            return "Error: DA3 reconstruction failed: " + str(e)
        self.state.reconstruction = recon
        d = recon.depth
        dmin = float(np.nanmin(d)) if d.size else 0.0
        dmax = float(np.nanmax(d)) if d.size else 0.0
        return (
            f"[da3_reconstruct] done. depth={recon.height}x{recon.width} "
            f"(process_res={self._reconstructor.process_res}, range {dmin:.3f}..{dmax:.3f} m), "
            f"K={list(recon.intrinsics.shape)}, [R|t]={list(recon.extrinsics.shape)}. "
            f"Cached for backproject_obb."
        )


class BackprojectObbTool:
    """LLM tool: backproject a cached mask with the reconstruction and fit an upright OBB."""

    def __init__(self, state):
        self.state = state

    def definition(self):
        return {
            "name": "backproject_obb",
            "description": (
                "Backproject a cached segmentation mask with the DA3 reconstruction and fit an "
                "upright oriented bounding box. Returns (center, dims, theta). Requires "
                "da3_reconstruct first, and sam3_segment for the mask name."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "mask_id": {
                        "type": "string",
                        "description": "Mask name returned by sam3_segment (e.g. \"chair\" or \"chair_0\")",
                    },
                    "min_points": {
                        "type": "integer",
                        "description": "Minimum points to fit an OBB (default 50)",
                    },
                },
                "required": ["mask_id"],
            },
        }

    def execute(self, args):
        try:
            params = json.loads(args)
        except json.JSONDecodeError as e:
            return "Error: Arguments are not valid JSON: " + str(e)
        mask_id = (params.get("mask_id") or "").strip()
        if not mask_id:
            return "Error: mask_id is required"
        if self.state.reconstruction is None:
            return "Error: no reconstruction yet; run da3_reconstruct first"
        mask = self.state.masks.get(mask_id)
        if mask is None:
            known = ", ".join(sorted(self.state.masks)) or "(none)"
            return f"Error: unknown mask_id {mask_id!r}; known masks: {known}"
        min_points = int(params.get("min_points", 50))
        obb = self.state.reconstruction.object_obb(mask, min_points=min_points)
        if obb is None:
            return f"[backproject_obb] {mask_id}: not enough points (< {min_points}) to fit an OBB."

        def fmt(v):
            return "[" + ", ".join(f"{x:.3f}" for x in v) + "]"

        center, dims, theta = obb
        return (
            f"[backproject_obb] {mask_id}: center={fmt(center)}, "
            f"dims={fmt(dims)}, theta={fmt(theta)}"
        )
