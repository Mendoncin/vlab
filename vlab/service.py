"""BK-003: fluxo reutilizável de motor, cache e histórico para CLI e futura UI."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from vlab import ai, prompt_engine
from vlab.storage import JSONStorage


def cache_key(data: dict) -> str:
    """SHA-256 de JSON canônico: a ordem das chaves não altera a identidade."""
    canonical = json.dumps(
        data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _cached_content(storage: JSONStorage, key: str, content_type: str) -> dict | None:
    entry = storage.read_cache(key)
    if (
        not isinstance(entry, dict)
        or entry.get("schema_version") != 1
        or entry.get("cache_key") != key
    ):
        return None
    try:
        return prompt_engine.validate_response(
            json.dumps(entry.get("conteudo"), ensure_ascii=False, allow_nan=False), content_type
        )
    except (ValueError, TypeError, RecursionError):
        return None


def run_generation(
    profile: dict, ticket: str, content_type: str, version: str, *,
    storage_dir: str | Path | None = None,
) -> dict:
    """Retorna conteúdo e metadados atuais somente após persistir o histórico.

    O diretório explícito prevalece sobre VLAB_STORAGE_DIR e sobre o padrão .vlab.
    Falhas da API/validação não são cacheadas; falhas de I/O geram StorageError.
    """
    prompt = prompt_engine.build_prompt(profile, ticket, content_type, version)
    configuration = ai.get_generation_config(
        schema=prompt["schema"], max_output_tokens=ai.STRUCTURED_MAX_OUTPUT_TOKENS
    )
    key = cache_key({
        "perfil": profile,
        "ticket": ticket,
        "tipo_conteudo": content_type,
        "versao_prompt": version,
        "prompt": prompt,
        "provedor": "openai",
        "configuracao_modelo": configuration,
    })
    storage = JSONStorage(storage_dir)
    content = _cached_content(storage, key, content_type)
    cache_hit = content is not None
    if not cache_hit:
        generated = prompt_engine.generate_content(
            profile, ticket, content_type, version,
            prepared_prompt=prompt, generation_config=configuration,
        )
        content = generated["conteudo"]
        storage.write_cache(key, content)

    record = {
        "schema_version": 1,
        "execution_id": uuid4().hex,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "status": "success",
        "cliente": {field: profile[field] for field in ("id", "nome") if field in profile},
        "ticket": ticket,
        "tipo_conteudo": content_type,
        "versao_prompt": version,
        "provedor": "openai",
        "modelo": configuration["model"],
        "configuracao_modelo": configuration,
        "conteudo": content,
        "origem": "cache" if cache_hit else "api",
        "cache_hit": cache_hit,
        "cache_key": key,
    }
    history_path = storage.write_history(record)
    return {**record, "history_path": str(history_path)}
