"""SAM3 open-set segmentation tool (lazy-loaded).

Corresponds to plan.md flow step 2 "SAM3 gives each object's mask". SAM3 uses a text prompt (e.g. "chair", "table") for open-set segmentation on the image, returning mask / box / score.

Dependency: ``pip install sam3`` (needs CUDA GPU, PyTorch). The checkpoint is loaded locally (modelscope already downloaded facebook/sam3; on HF it is gated and needs a token), so it does not go through HF download.
SAM3's fused op (addmm_act) forces bf16, so inference must be wrapped in a bf16 autocast.
"""

import json
import os
import sys
from pathlib import Path

import numpy as np
import torch

# --- in-repo third-party path (robust to repo renames/moves) -----------------
# Prefer the in-repo copy of SAM3 over any pip editable/regular install, so a
# rename or move of the project (e.g. layoutagent -> LayoutAgent) never breaks
# ``import sam3`` through a stale .pth path.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SAM3_SRC = _REPO_ROOT / "third_party" / "sam3"
if str(_SAM3_SRC) not in sys.path and _SAM3_SRC.is_dir():
    sys.path.insert(0, str(_SAM3_SRC))

# SAM3 checkpoint (downloaded to local via modelscope; facebook/sam3 is gated on HF).
# Override with the SAM3_CHECKPOINT env var; default to the modelscope cache under $HOME.
SAM3_CHECKPOINT = os.environ.get("SAM3_CHECKPOINT") or str(
    Path.home()
    / ".cache"
    / "modelscope"
    / "models"
    / "facebook--sam3"
    / "snapshots"
    / "master"
    / "sam3.pt"
)

SAM3_MODEL_KWARGS = {
    "checkpoint_path": SAM3_CHECKPOINT,
    "load_from_HF": False,
    "device": "cuda",
}

_DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


def sam3_available():
    """Check whether SAM3 is installed (without loading the model)."""
    try:
        import sam3  # noqa: F401
        return True
    except Exception:
        return False


class Segmenter:
    """SAM3 image segmenter. Each prompt returns a number of (mask, box, score)."""

    def __init__(self, **model_kwargs):
        self._model_kwargs = dict(SAM3_MODEL_KWARGS)
        self._model_kwargs.update(model_kwargs)
        self._processor = None

    def _load(self):
        if self._processor is not None:
            return
        try:
            from sam3.model_builder import build_sam3_image_model
            from sam3.model.sam3_image_processor import Sam3Processor
        except ImportError as e:
            raise ImportError(
                "SAM3 is not installed. Run `pip install sam3` and satisfy the CUDA/PyTorch dependencies, then retry."
            ) from e
        self._processor = Sam3Processor(build_sam3_image_model(**self._model_kwargs))

    def set_image(self, image):
        """Load an image and return the inference_state (reused across set_text_prompt calls)."""
        self._load()
        with torch.autocast(device_type=_DEVICE, dtype=torch.bfloat16):
            return self._processor.set_image(image)

    def segment(self, image, prompts, score_threshold=0.5):
        """Segment for each text prompt and return a list of results.

        Each result: ``{"prompt", "mask"(H,W bool), "box"(4,), "score"(float)}``.
        ``box`` is xyxy, in original-resolution pixel coordinates.
        """
        self._load()
        with torch.autocast(device_type=_DEVICE, dtype=torch.bfloat16):
            state = self._processor.set_image(image)
        results = []
        for p in prompts:
            with torch.autocast(device_type=_DEVICE, dtype=torch.bfloat16):
                out = self._processor.set_text_prompt(state=state, prompt=p)
            masks = out.get("masks", [])
            boxes = out.get("boxes", [])
            scores = out.get("scores", [])
            for mask, box, score in zip(masks, boxes, scores):
                s = float(_to_float(score))
                if s < score_threshold:
                    continue
                results.append({
                    "prompt": p,
                    "mask": _to_bool_array(mask),
                    "box": _to_float_array(box),
                    "score": s,
                })
        return results


def _to_float(t):
    """tensor(0-dim) -> python float (CUDA-tensor compatible)."""
    if hasattr(t, "detach"):
        t = t.detach().cpu()
    return float(t)


def _to_bool_array(mask):
    if hasattr(mask, "detach"):
        mask = mask.detach().cpu()
    a = np.asarray(mask)
    # SAM3 output has a batch dim (1, H, W); downstream unproject_masked expects (H, W)
    if a.ndim == 3 and a.shape[0] == 1:
        a = a[0]
    return a.astype(bool)


def _to_float_array(box):
    if hasattr(box, "detach"):
        box = box.detach().cpu()
    return [float(v) for v in np.asarray(box).reshape(-1)]


class Sam3SegmentTool:
    """LLM tool: open-set segmentation on the input image; masks are cached in the shared state for backproject_obb to reference, and boxes are cached in state.boxes for compile's image-consistency check."""

    def __init__(self, state):
        self.state = state
        self._segmenter = None

    def definition(self):
        return {
            "name": "sam3_segment",
            "description": (
                "This tool is used for task [Segmentation]. Run open-set segmentation for a text prompt (e.g. \"chair\") on the input image. "
                "Returns each found mask's box and score, and caches the mask under a name for "
                "backproject_obb."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "Object name / text prompt to segment (e.g. chair, table, wall)",
                    },
                    "score_threshold": {
                        "type": "number",
                        "description": "Minimum score to keep a mask (default 0.5)",
                    },
                },
                "required": ["prompt"],
            },
        }

    def execute(self, args):
        try:
            params = json.loads(args)
        except json.JSONDecodeError as e:
            return "Error: Arguments are not valid JSON: " + str(e)
        prompt = (params.get("prompt") or "").strip()
        if not prompt:
            return "Error: prompt is required"
        try:
            threshold = float(params.get("score_threshold", 0.5))
        except (TypeError, ValueError):
            return "Error: score_threshold must be a number"
        try:
            image = self.state.load_image()
        except Exception as e:
            return "Error: " + str(e)
        if self._segmenter is None:
            self._segmenter = Segmenter()
        try:
            results = self._segmenter.segment(image, [prompt], score_threshold=threshold)
        except Exception as e:
            return "Error: SAM3 segmentation failed: " + str(e)
        if not results:
            return f'[sam3_segment] "{prompt}" → no mask above score {threshold}.'
        lines = [f'[sam3_segment] "{prompt}" → {len(results)} mask(s):']
        for i, r in enumerate(results):
            key = prompt if len(results) == 1 else f"{prompt}_{i}"
            self.state.masks[key] = r["mask"]
            self.state.boxes[key] = r["box"]
            box = ", ".join(f"{v:.1f}" for v in r["box"])
            lines.append(f"  - {key}: box=[{box}], score={r['score']:.3f} (cached)")
        return "\n".join(lines)
