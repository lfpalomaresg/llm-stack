#!/usr/bin/env python3
"""Genera el bloque `provider.llm-stack.models` de opencode.json desde el catálogo.

Fuente de verdad de DOS capas:
  - ~/llm-stack/litellm.config.yaml   -> qué alias existen y a qué modelo sirven
  - ~/llm-stack/opencode-models.yaml  -> cómo se presenta cada alias en opencode

Uso:
  gen-opencode-models.py            regenera ~/.config/opencode/opencode.json
  gen-opencode-models.py --check    exit 1 si hay drift (no escribe nada)
  gen-opencode-models.py --diff     muestra el diff y no escribe

Por qué existe: hasta 2026-11-01 los alias vivían en dos catálogos sincronizados a mano
(20 en LiteLLM, 13 en opencode.json) y ya había drift (cloud-megacontext anunciaba V4-Pro
sirviendo V4.1-Flash). Ahora un alias nuevo en LiteLLM sin entrada en el catálogo es un
error visible, no un hueco silencioso.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

STACK = Path.home() / "llm-stack"
LITELLM = STACK / "litellm.config.yaml"
CATALOG = STACK / "opencode-models.yaml"
OPENCODE = Path.home() / ".config" / "opencode" / "opencode.json"

REQUIRED = ("name",)


def load_aliases() -> list[str]:
    data = yaml.safe_load(LITELLM.read_text(encoding="utf-8"))
    return [m["model_name"] for m in data["model_list"]]


def load_catalog() -> dict:
    return yaml.safe_load(CATALOG.read_text(encoding="utf-8")) or {}


def build(aliases: list[str], catalog: dict) -> tuple[dict, list[str]]:
    """Devuelve (bloque models, lista de avisos)."""
    warns: list[str] = []
    models: dict[str, dict] = {}

    for alias in aliases:
        entry = catalog.get(alias)
        if entry is None:
            warns.append(f"alias sin entrada en el catálogo: {alias}")
            continue
        if entry.get("expose") is False:
            continue
        for field in REQUIRED:
            if field not in entry:
                warns.append(f"{alias}: falta el campo obligatorio '{field}'")
                continue
        model: dict = {"name": entry["name"]}
        if "tool_call" in entry:
            model["tool_call"] = bool(entry["tool_call"])
        if "reasoning" in entry:
            model["reasoning"] = bool(entry["reasoning"])
        if "limit" in entry:
            lim = entry["limit"]
            model["limit"] = {"context": int(lim["context"]), "output": int(lim["output"])}
        models[alias] = model

    for alias in catalog:
        if alias not in aliases:
            warns.append(f"entrada huérfana en el catálogo (no existe en LiteLLM): {alias}")

    return models, warns


def main() -> int:
    check = "--check" in sys.argv
    show_diff = "--diff" in sys.argv

    aliases = load_aliases()
    catalog = load_catalog()
    models, warns = build(aliases, catalog)

    cfg = json.loads(OPENCODE.read_text(encoding="utf-8"))
    provider = cfg.setdefault("provider", {}).setdefault("llm-stack", {})
    current = provider.get("models", {})

    drift = current != models
    if warns:
        print("AVISOS:", file=sys.stderr)
        for w in warns:
            print(f"  - {w}", file=sys.stderr)

    if check:
        if drift:
            added = sorted(set(models) - set(current))
            removed = sorted(set(current) - set(models))
            changed = sorted(
                k for k in set(models) & set(current) if models[k] != current[k]
            )
            print("DRIFT en opencode.json:", file=sys.stderr)
            for label, items in (("nuevos", added), ("sobrantes", removed), ("cambiados", changed)):
                if items:
                    print(f"  {label}: {', '.join(items)}", file=sys.stderr)
            print("  arreglo: gen-opencode-models.py", file=sys.stderr)
            return 1
        if warns:
            print("DRIFT en el catálogo (ver avisos)", file=sys.stderr)
            return 1
        print(f"ok: {len(models)} alias en opencode, catálogo y LiteLLM en sincronía")
        return 0

    if drift:
        provider["models"] = models
        out = json.dumps(cfg, indent=2, ensure_ascii=False) + "\n"
        if show_diff:
            import difflib

            old = OPENCODE.read_text(encoding="utf-8").splitlines()
            new = out.splitlines()
            diff = difflib.unified_diff(old, new, "antes", "despues", lineterm="")
            print("\n".join(diff))
        else:
            OPENCODE.write_text(out, encoding="utf-8")
            print(f"escrito {OPENCODE} ({len(models)} alias)")
    else:
        print(f"sin cambios ({len(models)} alias)")

    return 1 if warns else 0


if __name__ == "__main__":
    sys.exit(main())
