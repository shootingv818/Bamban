"""Configuration loader for the capture phase (config.yaml only, no secrets)."""
from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml


class ConfigError(RuntimeError):
    pass


class Config:
    def __init__(self, data: dict[str, Any], root: Path):
        self._data = data
        self.root = root

    @classmethod
    def load(cls, config_path: str | Path | None = None) -> "Config":
        path = Path(config_path) if config_path else _default_config_path()
        if not path.exists():
            raise ConfigError(f"Config file not found: {path}")
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls(data, path.resolve().parent)

    # -- dotted access ----------------------------------------------------
    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self._data
        for key in dotted.split("."):
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node

    def require(self, dotted: str) -> Any:
        sentinel = object()
        value = self.get(dotted, sentinel)
        if value is sentinel:
            raise ConfigError(f"Missing required config key: {dotted}")
        return value

    def path(self, dotted: str, default: str) -> Path:
        raw = Path(self.get(dotted, default))
        return raw if raw.is_absolute() else self.root / raw

    # -- convenience ------------------------------------------------------
    @property
    def base_url(self) -> str:
        return str(self.require("bank.base_url")).rstrip("/")

    @property
    def base_host(self) -> str:
        return urlsplit(self.base_url).netloc

    @property
    def login_url(self) -> str:
        return self.base_url + "/" + str(self.get("bank.login_path", "/")).lstrip("/")


def _default_config_path() -> Path:
    # repo_root/config.yaml  (this file lives in repo_root/bamban/)
    return Path(__file__).resolve().parent.parent / "config.yaml"
