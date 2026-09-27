"""Minimal dotenv helper shared by the collectors (standard library only).

Credential resolution order used across this project:

1. environment variables
2. a dotenv file located by: ``$QUOTA_ENV_FILE`` -> ``./.env`` -> ``~/.hermes/.env``

Nothing here ever writes a secret to disk or to stdout.
"""
import os

DEFAULT_ENV_CANDIDATES = (
    os.environ.get("QUOTA_ENV_FILE", ""),
    os.path.join(os.getcwd(), ".env"),
    os.path.expanduser("~/.hermes/.env"),
)


def resolve_env_file(explicit=None):
    """Return the first existing dotenv path, or None."""
    for candidate in (explicit,) + DEFAULT_ENV_CANDIDATES:
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def load_env(explicit=None):
    """Parse ``KEY=VALUE`` lines. Returns ``(mapping, path_or_None)``."""
    env = {}
    path = resolve_env_file(explicit)
    if not path:
        return env, None
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip().strip('"').strip("'")
    return env, path


def first_env(env, *names):
    """Return the first non-empty value: ``os.environ`` wins over the dotenv file."""
    for name in names:
        value = os.environ.get(name) or env.get(name)
        if value:
            return value
    return None
