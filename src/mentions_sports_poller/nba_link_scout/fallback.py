from __future__ import annotations

import importlib.util
import inspect
import logging
from pathlib import Path
from typing import Any

from .models import FallbackExtractorConfig


class FallbackExtractorAdapter:
    def __init__(
        self,
        *,
        config: FallbackExtractorConfig,
        logger: logging.Logger | None = None,
    ) -> None:
        self.config = config
        self.logger = logger or logging.getLogger(__name__)
        self._module: Any | None = None

    def extract(self, *, page_url: str, html: str) -> list[str]:
        module = self._load_module()
        func = getattr(module, self.config.function_name, None)
        if func is None:
            raise AttributeError(
                f"fallback function '{self.config.function_name}' not found in {self.config.module_path}"
            )

        args, kwargs = _build_call_arguments(
            func=func,
            page_url=page_url,
            html=html,
            base_kwargs=self.config.function_kwargs,
        )
        raw_result = func(*args, **kwargs)
        return _normalize_result(raw_result)

    def _load_module(self) -> Any:
        if self._module is not None:
            return self._module

        path = Path(self.config.module_path)
        if not path.exists():
            raise FileNotFoundError(f"fallback module path does not exist: {path}")
        module_name = f"fallback_extractor_{path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"unable to import fallback module from {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self._module = module
        return module


def _build_call_arguments(
    *,
    func: Any,
    page_url: str,
    html: str,
    base_kwargs: dict[str, Any],
) -> tuple[list[Any], dict[str, Any]]:
    signature = inspect.signature(func)
    params = signature.parameters
    kwargs = dict(base_kwargs)
    args: list[Any] = []

    if "page_url" in params:
        kwargs.setdefault("page_url", page_url)
    elif "url" in params:
        kwargs.setdefault("url", page_url)

    if "html" in params:
        kwargs.setdefault("html", html)

    if not kwargs:
        positional = [
            name
            for name, param in params.items()
            if param.kind
            in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
        ]
        if positional:
            args.append(page_url)
    return args, kwargs


def _normalize_result(raw_result: Any) -> list[str]:
    if raw_result is None:
        return []
    if isinstance(raw_result, str):
        return [raw_result]
    if isinstance(raw_result, (list, tuple, set)):
        return [value for value in raw_result if isinstance(value, str)]
    if isinstance(raw_result, dict):
        for key in ("found_links", "links", "urls", "results"):
            value = raw_result.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, str)]
        return []
    raise TypeError(f"unsupported fallback result type: {type(raw_result).__name__}")
