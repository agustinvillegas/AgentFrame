from __future__ import annotations
import ctypes
import logging
import os
import sys
from typing import Any

logger = logging.getLogger("mtmd")

_MTMD_LIB: ctypes.CDLL | None = None
_LLAMA_LIB: ctypes.CDLL | None = None


def _load_mtmd() -> ctypes.CDLL:
    global _MTMD_LIB
    if _MTMD_LIB is not None:
        return _MTMD_LIB
    lib_dir = os.path.join(sys.prefix, "Lib", "site-packages", "llama_cpp", "lib")
    path = os.path.join(lib_dir, "mtmd.dll")
    _MTMD_LIB = ctypes.CDLL(path)
    return _MTMD_LIB


def _load_llama() -> ctypes.CDLL:
    global _LLAMA_LIB
    if _LLAMA_LIB is not None:
        return _LLAMA_LIB
    lib_dir = os.path.join(sys.prefix, "Lib", "site-packages", "llama_cpp", "lib")
    path = os.path.join(lib_dir, "llama.dll")
    _LLAMA_LIB = ctypes.CDLL(path)
    return _LLAMA_LIB


# ── Struct definitions ─────────────────────────────────────────────────────

class MtmdContextParams(ctypes.Structure):
    _fields_ = [
        ("use_gpu", ctypes.c_bool),
        ("print_timings", ctypes.c_bool),
        ("n_threads", ctypes.c_int),
        ("image_marker", ctypes.c_char_p),
        ("media_marker", ctypes.c_char_p),
        ("flash_attn_type", ctypes.c_int),
        ("warmup", ctypes.c_bool),
        ("image_min_tokens", ctypes.c_int),
        ("image_max_tokens", ctypes.c_int),
        ("cb_eval", ctypes.c_void_p),
        ("cb_eval_user_data", ctypes.c_void_p),
        ("batch_max_tokens", ctypes.c_int32),
        ("progress_callback", ctypes.c_void_p),
        ("progress_callback_user_data", ctypes.c_void_p),
    ]


class MtmdInputText(ctypes.Structure):
    _fields_ = [
        ("text", ctypes.c_char_p),
        ("add_special", ctypes.c_bool),
        ("parse_special", ctypes.c_bool),
    ]


class MtmdHelperBitmapWrapper(ctypes.Structure):
    _fields_ = [
        ("bitmap", ctypes.c_void_p),
        ("video_ctx", ctypes.c_void_p),
    ]


def _setup_functions():
    mtmd = _load_mtmd()
    llama = _load_llama()

    # ── mtmd ───────────────────────────────────────────────────────────────
    mtmd.mtmd_context_params_default.argtypes = []
    mtmd.mtmd_context_params_default.restype = MtmdContextParams

    mtmd.mtmd_init_from_file.argtypes = [
        ctypes.c_char_p,             # mmproj_fname
        ctypes.c_void_p,             # text_model (llama_model*)
        MtmdContextParams,           # ctx_params (by value)
    ]
    mtmd.mtmd_init_from_file.restype = ctypes.c_void_p

    mtmd.mtmd_free.argtypes = [ctypes.c_void_p]
    mtmd.mtmd_free.restype = None

    mtmd.mtmd_support_vision.argtypes = [ctypes.c_void_p]
    mtmd.mtmd_support_vision.restype = ctypes.c_bool

    mtmd.mtmd_default_marker.argtypes = []
    mtmd.mtmd_default_marker.restype = ctypes.c_char_p

    # bitmap
    mtmd.mtmd_bitmap_init.argtypes = [
        ctypes.c_uint32,             # nx
        ctypes.c_uint32,             # ny
        ctypes.POINTER(ctypes.c_ubyte),  # data
    ]
    mtmd.mtmd_bitmap_init.restype = ctypes.c_void_p

    mtmd.mtmd_bitmap_get_nx.argtypes = [ctypes.c_void_p]
    mtmd.mtmd_bitmap_get_nx.restype = ctypes.c_uint32

    mtmd.mtmd_bitmap_get_ny.argtypes = [ctypes.c_void_p]
    mtmd.mtmd_bitmap_get_ny.restype = ctypes.c_uint32

    mtmd.mtmd_bitmap_get_data.argtypes = [ctypes.c_void_p]
    mtmd.mtmd_bitmap_get_data.restype = ctypes.POINTER(ctypes.c_ubyte)

    mtmd.mtmd_bitmap_get_n_bytes.argtypes = [ctypes.c_void_p]
    mtmd.mtmd_bitmap_get_n_bytes.restype = ctypes.c_size_t

    mtmd.mtmd_bitmap_free.argtypes = [ctypes.c_void_p]
    mtmd.mtmd_bitmap_free.restype = None

    # bitmap helper (from buffer)
    mtmd.mtmd_helper_bitmap_init_from_buf.argtypes = [
        ctypes.c_void_p,             # ctx
        ctypes.POINTER(ctypes.c_ubyte),  # buf
        ctypes.c_size_t,             # len
        ctypes.c_bool,               # placeholder
    ]
    mtmd.mtmd_helper_bitmap_init_from_buf.restype = MtmdHelperBitmapWrapper

    # input chunks
    mtmd.mtmd_input_chunks_init.argtypes = []
    mtmd.mtmd_input_chunks_init.restype = ctypes.c_void_p

    mtmd.mtmd_input_chunks_free.argtypes = [ctypes.c_void_p]
    mtmd.mtmd_input_chunks_free.restype = None

    mtmd.mtmd_input_chunks_size.argtypes = [ctypes.c_void_p]
    mtmd.mtmd_input_chunks_size.restype = ctypes.c_size_t

    mtmd.mtmd_input_chunks_get.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    mtmd.mtmd_input_chunks_get.restype = ctypes.c_void_p

    # input chunk
    mtmd.mtmd_input_chunk_get_type.argtypes = [ctypes.c_void_p]
    mtmd.mtmd_input_chunk_get_type.restype = ctypes.c_int

    mtmd.mtmd_input_chunk_get_n_tokens.argtypes = [ctypes.c_void_p]
    mtmd.mtmd_input_chunk_get_n_tokens.restype = ctypes.c_size_t

    mtmd.mtmd_input_chunk_get_tokens_text.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    mtmd.mtmd_input_chunk_get_tokens_text.restype = ctypes.POINTER(ctypes.c_int32)

    # tokenize
    mtmd.mtmd_tokenize.argtypes = [
        ctypes.c_void_p,             # ctx
        ctypes.c_void_p,             # output chunks
        ctypes.POINTER(MtmdInputText),  # text
        ctypes.POINTER(ctypes.c_void_p),  # bitmaps (array of pointers)
        ctypes.c_size_t,             # n_bitmaps
    ]
    mtmd.mtmd_tokenize.restype = ctypes.c_int32

    # encode chunk
    mtmd.mtmd_encode_chunk.argtypes = [
        ctypes.c_void_p,             # ctx
        ctypes.c_void_p,             # chunk
    ]
    mtmd.mtmd_encode_chunk.restype = ctypes.c_int32

    # get output embeddings
    mtmd.mtmd_get_output_embd.argtypes = [ctypes.c_void_p]
    mtmd.mtmd_get_output_embd.restype = ctypes.POINTER(ctypes.c_float)

    # helper eval chunks
    mtmd.mtmd_helper_eval_chunks.argtypes = [
        ctypes.c_void_p,             # mtmd_ctx
        ctypes.c_void_p,             # llama_ctx
        ctypes.c_void_p,             # chunks
        ctypes.c_int32,              # n_past
        ctypes.c_int32,              # seq_id
        ctypes.c_int32,              # n_batch
        ctypes.c_bool,               # logits_last
        ctypes.POINTER(ctypes.c_int32),  # new_n_past (output)
    ]
    mtmd.mtmd_helper_eval_chunks.restype = ctypes.c_int32

    # decode image chunk (for custom pipeline)
    mtmd.mtmd_helper_decode_image_chunk.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_float),
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_int32),
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    mtmd.mtmd_helper_decode_image_chunk.restype = ctypes.c_int32

    # ── llama ──────────────────────────────────────────────────────────────
    llama.llama_get_logits.argtypes = [ctypes.c_void_p]
    llama.llama_get_logits.restype = ctypes.POINTER(ctypes.c_float)

    llama.llama_n_vocab.restype = ctypes.c_int32

    llama.llama_token_get_text.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int32,
    ]
    llama.llama_token_get_text.restype = ctypes.c_char_p


_setup_functions()


class MtmdHelper:
    def __init__(self, llama_model_ptr: int, mmproj_path: str):
        mtmd = _load_mtmd()
        self._mtmd = mtmd

        params = mtmd.mtmd_context_params_default()
        params.warmup = False
        params.batch_max_tokens = 4096

        self._ctx = mtmd.mtmd_init_from_file(
            mmproj_path.encode("utf-8"),
            ctypes.c_void_p(llama_model_ptr),
            params,
        )
        if self._ctx is None:
            raise RuntimeError(f"mtmd_init_from_file failed for {mmproj_path}")

        logger.info("mtmd context initialized")

    @property
    def ctx(self):
        return self._ctx

    def close(self):
        if self._ctx is not None:
            self._mtmd.mtmd_free(self._ctx)
            self._ctx = None

    def __del__(self):
        self.close()

    def bitmap_from_buf(self, data: bytes) -> tuple[ctypes.c_void_p, int, int]:
        buf = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        result = self._mtmd.mtmd_helper_bitmap_init_from_buf(
            self._ctx, buf, len(data), False
        )
        if result.bitmap is None:
            raise RuntimeError("mtmd_helper_bitmap_init_from_buf failed")

        nx = self._mtmd.mtmd_bitmap_get_nx(result.bitmap)
        ny = self._mtmd.mtmd_bitmap_get_ny(result.bitmap)
        return result.bitmap, nx, ny

    def bitmap_free(self, bitmap_ptr: ctypes.c_void_p):
        self._mtmd.mtmd_bitmap_free(bitmap_ptr)

    def tokenize(
        self, text: str, bitmaps: list[ctypes.c_void_p]
    ) -> ctypes.c_void_p:
        chunks = self._mtmd.mtmd_input_chunks_init()
        if chunks is None:
            raise RuntimeError("mtmd_input_chunks_init failed")

        input_text = MtmdInputText(
            text=text.encode("utf-8"),
            add_special=True,
            parse_special=True,
        )

        n = len(bitmaps)
        bitmap_arr = (ctypes.c_void_p * n)(*bitmaps) if n > 0 else None

        ret = self._mtmd.mtmd_tokenize(
            self._ctx, chunks,
            ctypes.byref(input_text),
            bitmap_arr, n,
        )
        if ret != 0:
            self._mtmd.mtmd_input_chunks_free(chunks)
            raise RuntimeError(f"mtmd_tokenize failed with code {ret}")

        return chunks

    def chunks_free(self, chunks_ptr: ctypes.c_void_p):
        self._mtmd.mtmd_input_chunks_free(chunks_ptr)

    def eval_chunks(
        self, chunks_ptr: ctypes.c_void_p,
        llama_ctx_ptr: int,
        n_past: int = 0,
        seq_id: int = 0,
        n_batch: int = 512,
    ) -> int:
        new_n_past = ctypes.c_int32(0)
        ret = self._mtmd.mtmd_helper_eval_chunks(
            self._ctx,
            ctypes.c_void_p(llama_ctx_ptr),
            chunks_ptr,
            ctypes.c_int32(n_past),
            ctypes.c_int32(seq_id),
            ctypes.c_int32(n_batch),
            True,  # logits_last
            ctypes.byref(new_n_past),
        )
        if ret != 0:
            raise RuntimeError(f"mtmd_helper_eval_chunks failed with code {ret}")
        return new_n_past.value

    def get_output_embd(self) -> ctypes.pointer:
        return self._mtmd.mtmd_get_output_embd(self._ctx)
