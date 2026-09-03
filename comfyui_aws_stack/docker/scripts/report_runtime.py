#!/usr/bin/env python3
"""Log the pinned GPU runtime versions before ComfyUI starts."""

import importlib
import importlib.metadata


def module_version(name):
    try:
        module = importlib.import_module(name)
        return getattr(module, "__version__", "unknown")
    except Exception as error:  # noqa: BLE001 - diagnostics must not block startup
        return f"unavailable ({error})"


def distribution_version(name):
    try:
        return importlib.metadata.version(name)
    except Exception as error:  # noqa: BLE001 - diagnostics must not block startup
        return f"unavailable ({error})"


def runtime_summary():
    try:
        torch = importlib.import_module("torch")
        torch_version = getattr(torch, "__version__", "unknown")
        cuda_version = getattr(getattr(torch, "version", None), "cuda", None)
        cuda_available = torch.cuda.is_available()
    except Exception as error:  # noqa: BLE001 - diagnostics must not block startup
        torch_version = f"unavailable ({error})"
        cuda_version = None
        cuda_available = False

    return {
        "torch": torch_version,
        "torchvision": module_version("torchvision"),
        "torchaudio": module_version("torchaudio"),
        "comfy_kitchen": distribution_version("comfy-kitchen"),
        "triton": distribution_version("triton"),
        "torch_cuda": cuda_version,
        "cuda_available": cuda_available,
    }


def main():
    summary = runtime_summary()
    formatted = " ".join(f"{key}={value}" for key, value in summary.items())
    print(f"[runtime] {formatted}", flush=True)
    if summary["torch_cuda"] != "13.0":
        print(
            "[runtime] WARNING: expected the PyTorch cu130 runtime",
            flush=True,
        )


if __name__ == "__main__":
    main()
