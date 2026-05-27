"""RECORDING_CONFIG-driven YAML loader.

Selects between `config/recording.local.yaml` and `config/recording.aws.yaml`
based on the `RECORDING_CONFIG` env var. Default is `local`. Used by both the
collector tier and the lab-tier pipeline so the same config drives both ends.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml


_VALID_ENVS = ("local", "aws")
_REPO_ROOT = Path(__file__).resolve().parent.parent


def load_config() -> dict:
    env = os.environ.get("RECORDING_CONFIG", "local")
    if env not in _VALID_ENVS:
        raise ValueError(
            f"RECORDING_CONFIG must be one of {_VALID_ENVS}, got: {env!r}"
        )

    config_path = _REPO_ROOT / "config" / f"recording.{env}.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")

    with open(config_path) as f:
        return yaml.safe_load(f)


def load_exchanges() -> dict:
    path = _REPO_ROOT / "config" / "exchanges.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Exchanges config not found: {path}")
    with open(path) as f:
        return yaml.safe_load(f)
