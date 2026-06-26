from __future__ import annotations
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

# Ensure HF downloads go to D: drive to avoid filling C:
os.environ.setdefault("HF_HOME", "D:\\hf_cache")
os.environ.setdefault("HF_HUB_CACHE", "D:\\hf_cache\\hub")
os.environ.setdefault("TRANSFORMERS_CACHE", "D:\\hf_cache\\hub")

logger = logging.getLogger("vision")

# ── Model configuration ────────────────────────────────────────────────────
# Backend: "auto" | "transformers" | "gguf"
VISION_BACKEND = os.environ.get("AGENTSHELL_VISION_BACKEND", "auto")
# HuggingFace model ID for transformers-based models (Florence-2, OWLViT, etc.)
VISION_MODEL_ID = os.environ.get(
    "AGENTSHELL_VISION_MODEL",
    "florence-community/Florence-2-base"
)
# GGUF model settings (for llama-cpp-python multimodal support)
VISION_GGUF_REPO = os.environ.get(
    "AGENTSHELL_VISION_REPO",
    ""
)
VISION_GGUF_FILE = os.environ.get(
    "AGENTSHELL_VISION_FILE",
    ""
)
VISION_GGUF_MMPROJ_FILE = os.environ.get(
    "AGENTSHELL_VISION_MMPROJ_FILE",
    ""
)
MODEL_DIR = Path(__file__).resolve().parent.parent / "data" / "models"
MIN_CONFIDENCE = float(os.environ.get("AGENTSHELL_VISION_CONFIDENCE", "0.3"))
GPU_LAYERS = int(os.environ.get("AGENTSHELL_VISION_GPU_LAYERS", "20"))

# ── Model state ────────────────────────────────────────────────────────────
_model_lock = threading.Lock()
_model_instance = None
_backend_used = None


def is_available() -> bool:
    """Check if a vision model backend is available."""
    try:
        if VISION_BACKEND == "gguf":
            return _is_gguf_available()
        elif VISION_BACKEND == "transformers":
            return _is_transformers_available()
        else:
            return _is_transformers_available() or _is_gguf_available()
    except Exception:
        return False


def _is_transformers_available() -> bool:
    try:
        import transformers  # noqa: F401
        import torch  # noqa: F401
        return True
    except ImportError:
        return False


def _is_gguf_available() -> bool:
    try:
        import llama_cpp
        return True
    except ImportError:
        return False


def _load_model():
    global _model_instance, _backend_used
    if _model_instance is not None:
        return _model_instance, _backend_used

    with _model_lock:
        if _model_instance is not None:
            return _model_instance, _backend_used

        backend = VISION_BACKEND

        if backend == "auto":
            if _is_transformers_available():
                backend = "transformers"
            elif _is_gguf_available():
                backend = "gguf"
            else:
                raise RuntimeError(
                    "No vision backend available. Install either:\n"
                    "  transformers + torch: pip install transformers torch\n"
                    "  llama-cpp-python: pip install llama-cpp-python"
                )

        if backend == "transformers":
            _model_instance, _backend_used = _load_transformers()
        elif backend == "gguf":
            _model_instance, _backend_used = _load_gguf()
        else:
            raise RuntimeError(f"Unknown vision backend: {backend}")

        logger.info(f"Vision model loaded (backend={_backend_used})")
        return _model_instance, _backend_used


def _load_transformers():
    """Load vision model via HuggingFace transformers."""
    from transformers import AutoProcessor, Florence2ForConditionalGeneration
    import torch

    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"Loading {VISION_MODEL_ID} on {device}...")

    model_id = VISION_MODEL_ID

    processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=False)

    if device == "cuda":
        model = Florence2ForConditionalGeneration.from_pretrained(
            model_id,
            torch_dtype=torch.float16,
            trust_remote_code=False,
            device_map="auto",
        )
    else:
        model = Florence2ForConditionalGeneration.from_pretrained(
            model_id,
            torch_dtype=torch.bfloat16,
            trust_remote_code=False,
        ).to(device)

    model.eval()

    return (processor, model, device), "transformers"


def _find_mmproj() -> Path | None:
    """Search for mmproj file in MODEL_DIR or via env var."""
    if VISION_GGUF_MMPROJ_FILE:
        explicit = MODEL_DIR / VISION_GGUF_MMPROJ_FILE
        if explicit.exists():
            return explicit
        # Search recursively
        candidates = list(MODEL_DIR.rglob(VISION_GGUF_MMPROJ_FILE))
        if candidates:
            return candidates[0]
        # Try downloading explicit mmproj from HF
        if VISION_GGUF_REPO:
            from huggingface_hub import hf_hub_download
            MODEL_DIR.mkdir(parents=True, exist_ok=True)
            try:
                path = hf_hub_download(
                    repo_id=VISION_GGUF_REPO,
                    filename=VISION_GGUF_MMPROJ_FILE,
                    local_dir=MODEL_DIR,
                )
                return Path(path)
            except Exception:
                pass

    # Auto-detect: glob for files containing "mmproj" in MODEL_DIR
    if MODEL_DIR.exists():
        for pattern in ("mmproj*", "*mmproj*"):
            candidates = sorted(MODEL_DIR.rglob(pattern))
            if candidates:
                return candidates[0]

    return None


def _load_gguf():
    """Load vision model via llama-cpp-python (GGUF multimodal)."""
    from llama_cpp import Llama

    if not VISION_GGUF_REPO or not VISION_GGUF_FILE:
        raise RuntimeError(
            "GGUF backend requires AGENTSHELL_VISION_REPO and AGENTSHELL_VISION_FILE "
            "environment variables pointing to a multimodal GGUF model on HuggingFace."
        )

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODEL_DIR / VISION_GGUF_FILE

    if not model_path.exists():
        # Search recursively in subdirectories
        candidates = list(MODEL_DIR.rglob(VISION_GGUF_FILE))
        if candidates:
            model_path = candidates[0]
        else:
            from huggingface_hub import hf_hub_download
            logger.info(f"Downloading {VISION_GGUF_REPO}/{VISION_GGUF_FILE}...")
            path = hf_hub_download(
                repo_id=VISION_GGUF_REPO,
                filename=VISION_GGUF_FILE,
                local_dir=MODEL_DIR,
            )
            model_path = Path(path)

    mmproj_path = _find_mmproj()
    kwargs = dict(
        model_path=str(model_path),
        n_ctx=2048,
        n_gpu_layers=GPU_LAYERS,
        verbose=False,
    )
    if mmproj_path:
        kwargs["mmproj"] = str(mmproj_path)
        logger.info(f"Using mmproj: {mmproj_path}")

    model = Llama(**kwargs)
    return model, "gguf"


def detect_ui_elements(
    image_bytes: bytes,
    prompt: str,
    threshold: float | None = None,
) -> list[dict[str, Any]]:
    """
    Detect UI elements in an image matching a text prompt.

    Args:
        image_bytes: PNG/JPEG screenshot bytes.
        prompt: Natural language query (e.g. "play button", "search field").
        threshold: Confidence threshold 0-1, defaults to AGENTSHELL_VISION_CONFIDENCE.

    Returns:
        [{"label": str, "confidence": float,
          "bounds": {"left", "top", "right", "bottom"},
          "center": [x, y]}, ...]
    """
    conf = threshold if threshold is not None else MIN_CONFIDENCE

    try:
        model, backend = _load_model()

        if backend == "transformers":
            return _run_transformers(model, image_bytes, prompt, conf)
        elif backend == "gguf":
            return _run_gguf(model, image_bytes, prompt, conf)
        else:
            return []

    except Exception as e:
        logger.warning(f"Vision detection failed: {e}")
        return []


def _run_transformers(
    model_tuple: tuple, image_bytes: bytes, prompt: str, threshold: float
) -> list[dict[str, Any]]:
    from PIL import Image
    import torch
    import io as _io

    processor, model, device = model_tuple
    image = Image.open(_io.BytesIO(io_to_bytes(image_bytes))).convert("RGB")
    img_width, img_height = image.size

    task_prompt = f"<OPEN_VOCABULARY_DETECTION>\n{prompt}"

    inputs = processor(
        text=[task_prompt],
        images=[image],
        return_tensors="pt",
    )
    inputs = {k: v.to(device) for k, v in inputs.items()}
    if "pixel_values" in inputs:
        inputs["pixel_values"] = inputs["pixel_values"].to(model.dtype)

    with torch.no_grad():
        generated_ids = model.generate(
            input_ids=inputs["input_ids"],
            pixel_values=inputs["pixel_values"],
            max_new_tokens=1024,
            num_beams=1,
            do_sample=False,
        )

    generated_text = processor.batch_decode(
        generated_ids, skip_special_tokens=False
    )[0]

    parsed = processor.post_process_generation(
        generated_text,
        task="<OPEN_VOCABULARY_DETECTION>",
        image_size=(img_width, img_height),
    )

    return _parse_florence_ovd(parsed, threshold, prompt)


def _parse_florence_ovd(
    parsed: dict, threshold: float, prompt: str
) -> list[dict[str, Any]]:
    """
    Parse Florence-2 OVD output.

    Expected format (pixel coordinates):
        {"<OPEN_VOCABULARY_DETECTION>": {"bboxes": [[x1,y1,x2,y2], ...],
                                         "bboxes_labels": ["label", ...]}}
    """
    elements = []

    # Find the data dict (nested under task key or flat)
    data = parsed
    for key in ("<OPEN_VOCABULARY_DETECTION>", "<OD>"):
        if key in parsed and isinstance(parsed[key], dict):
            data = parsed[key]
            break

    bboxes = data.get("bboxes", [])
    labels = data.get("bboxes_labels", data.get("labels", [prompt] * len(bboxes)))
    for bbox, lbl in zip(bboxes, labels):
        if len(bbox) != 4:
            continue
        x1, y1, x2, y2 = map(int, bbox)
        elements.append({
            "label":      str(lbl or prompt).strip(),
            "confidence": 0.9,
            "bounds":     {"left": x1, "top": y1, "right": x2, "bottom": y2},
            "center":     [(x1 + x2) // 2, (y1 + y2) // 2],
        })

    return elements


def _run_gguf(
    model, image_bytes: bytes, prompt: str, threshold: float
) -> list[dict[str, Any]]:
    import base64 as _base64

    b64 = _base64.b64encode(image_bytes).decode("utf-8")

    # Try chat completion with image (multimodal)
    user_content = f"data:image/png;base64,{b64}\n\nReturn a JSON array of objects matching '{prompt}'. Each object must have: label (str), confidence (float 0-1), bbox (object with left, top, right, bottom as integers). Return ONLY the JSON array, no markdown."

    for attempt in range(2):
        try:
            if attempt == 0:
                result = model.create_chat_completion(
                    messages=[{"role": "user", "content": user_content}],
                    temperature=0.1,
                    max_tokens=1024,
                )
            else:
                result = model.create_completion(
                    prompt=user_content,
                    temperature=0.1,
                    max_tokens=1024,
                )
            break
        except Exception as e:
            if attempt == 0:
                logger.warning(f"Chat completion failed, trying completion API: {e}")
                continue
            raise

    if attempt == 0:
        raw = result["choices"][0]["message"]["content"]
    else:
        raw = result["choices"][0]["text"]

    parsed = json.loads(raw)
    items = parsed if isinstance(parsed, list) else parsed.get("elements", parsed.get("objects", []))

    elements = []
    for el in items:
        conf = el.get("confidence", 0.0)
        if conf < threshold:
            continue
        bbox = el.get("bbox", el.get("bounds", {}))
        label = el.get("label", el.get("name", prompt))
        left   = bbox.get("left", bbox.get("x", 0))
        top    = bbox.get("top", bbox.get("y", 0))
        right  = bbox.get("right", left + bbox.get("width", 0))
        bottom = bbox.get("bottom", top + bbox.get("height", 0))
        elements.append({
            "label":      str(label).strip(),
            "confidence": round(conf, 2),
            "bounds":     {"left": left, "top": top, "right": right, "bottom": bottom},
            "center":     [(left + right) // 2, (top + bottom) // 2],
        })
    return elements


def _ensure_bytes(image_bytes: bytes | bytearray) -> bytes:
    return bytes(image_bytes) if isinstance(image_bytes, bytearray) else image_bytes


def io_to_bytes(data: Any) -> bytes:
    """Convert various image input formats to bytes."""
    if isinstance(data, (bytes, bytearray)):
        return _ensure_bytes(data)
    if hasattr(data, "read"):
        return data.read()
    if hasattr(data, "tobytes"):
        return data.tobytes()
    return bytes(data)


def pipeline_fallback(
    image_bytes: bytes,
    prompt: str,
    ocr_result: dict | None = None,
    threshold: float | None = None,
) -> dict:
    """
    Run Locate Anything as a fallback layer between OCR and raw capture.
    Called automatically when OCR is incomplete.

    Returns:
        {"detections": [...], "count": int, "note": str}
    """
    try:
        detections = detect_ui_elements(image_bytes, prompt, threshold)
        if detections:
            return {
                "detections": detections,
                "count":      len(detections),
                "model":      VISION_MODEL_ID,
                "note":       f"Located {len(detections)} element(s) matching prompt via vision model.",
            }
        return {
            "detections": [],
            "count":      0,
            "model":      VISION_MODEL_ID,
            "note":       "Vision model found no elements matching the prompt.",
        }
    except Exception as e:
        return {
            "detections": [],
            "count":      0,
            "error":      str(e),
            "note":       f"Vision model unavailable: {e}. Falling back to raw capture.",
        }
