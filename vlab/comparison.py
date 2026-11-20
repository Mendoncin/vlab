"""BK-005: um cenário, duas gerações existentes e rubrica exclusivamente manual."""

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

from vlab import ai, prompt_engine, service
from vlab.storage import JSONStorage


CRITERIA = {
    "clarity": ("Clareza", "A resposta é compreensível, organizada e evita ambiguidades desnecessárias?"),
    "customer_fit": (
        "Adequação ao nível do cliente",
        "O vocabulário, a profundidade e as explicações combinam com o perfil selecionado?",
    ),
    "actionability": (
        "Acionabilidade", "O cliente ou atendente consegue identificar o que fazer a seguir?",
    ),
}
VERSIONS = ("v1", "v2")


def validate_rubric(evaluations: dict) -> dict:
    """Valida seis notas/justificativas e calcula totais; não recebe totais prontos."""
    if not isinstance(evaluations, dict) or set(evaluations) != set(VERSIONS):
        raise ValueError("Preencha a avaliação de v1 e v2.")
    validated = {}
    for version in VERSIONS:
        criteria = evaluations[version]
        if not isinstance(criteria, dict) or set(criteria) != set(CRITERIA):
            raise ValueError(f"Preencha os três critérios obrigatórios de {version}.")
        clean = {}
        for criterion, (label, _) in CRITERIA.items():
            entry = criteria[criterion]
            if not isinstance(entry, dict):
                raise ValueError(f"Preencha nota e justificativa de {label} ({version}).")
            score = entry.get("score")
            if type(score) is not int or not 1 <= score <= 5:
                raise ValueError(f"A nota de {label} ({version}) deve ser inteira entre 1 e 5.")
            justification = entry.get("justification")
            if not isinstance(justification, str) or not justification.strip():
                raise ValueError(f"Preencha a justificativa de {label} ({version}).")
            clean[criterion] = {"score": score, "justification": justification.strip()}
        validated[version] = {
            "criteria": clean, "total": sum(entry["score"] for entry in clean.values()),
        }
    return validated


def run_comparison(
    profile: dict, ticket: str, content_type: str, *, storage_dir: str | Path | None = None,
) -> dict:
    """Só retorna uma comparação completa; falhas preservam cache/históricos já gravados."""
    profile = deepcopy(profile)
    prompt = prompt_engine.build_prompt(profile, ticket, content_type, "v1")
    configuration = ai.get_generation_config(
        schema=prompt["schema"], max_output_tokens=ai.STRUCTURED_MAX_OUTPUT_TOKENS,
    )
    # Resolve após carregar o .env e fixa o mesmo diretório para ambas as execuções.
    directory = JSONStorage(storage_dir).directory
    results = {}
    for version in VERSIONS:
        results[version] = service.run_generation(
            profile, ticket, content_type, version,
            storage_dir=directory, generation_config=configuration,
        )
    comparison = {
        "schema_version": 1,
        "comparison_id": uuid4().hex,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "cliente": results["v1"]["cliente"],
        "cenario": {
            "perfil": profile, "ticket": ticket, "tipo_conteudo": content_type,
            "provedor": results["v1"]["provedor"], "modelo": configuration["model"],
            "configuracao_modelo": configuration,
        },
        "resultados": results,
    }
    validate_comparison(comparison)
    return comparison


def validate_comparison(comparison: dict) -> None:
    """Confere conteúdo, equivalência e vínculo dos resultados com o cenário salvo."""
    try:
        scenario = comparison["cenario"]
        results = comparison["resultados"]
        if set(results) != set(VERSIONS):
            raise ValueError
        for version in VERSIONS:
            result = results[version]
            prompt = result["prompt"]
            configuration = result["configuracao_modelo"]
            expected_customer = {
                field: scenario["perfil"][field] for field in ("id", "nome")
                if field in scenario["perfil"]
            }
            if (
                result["status"] != "success"
                or result["versao_prompt"] != version
                or result["ticket"] != scenario["ticket"]
                or result["tipo_conteudo"] != scenario["tipo_conteudo"]
                or result["cliente"] != expected_customer
                or comparison["cliente"] != expected_customer
                or result["provedor"] != scenario["provedor"]
                or result["modelo"] != scenario["modelo"]
                or configuration != scenario["configuracao_modelo"]
                or configuration["model"] != result["modelo"]
                or json.loads(prompt["input"]) != {
                    "perfil": scenario["perfil"], "ticket": scenario["ticket"],
                }
            ):
                raise ValueError
            expected_key = service.cache_key({
                "perfil": scenario["perfil"], "ticket": scenario["ticket"],
                "tipo_conteudo": scenario["tipo_conteudo"], "versao_prompt": version,
                "prompt": prompt, "provedor": result["provedor"],
                "configuracao_modelo": configuration,
            })
            if result["cache_key"] != expected_key:
                raise ValueError
            prompt_engine.validate_response(
                json.dumps(result["conteudo"], ensure_ascii=False, allow_nan=False),
                scenario["tipo_conteudo"],
            )
        if results["v1"]["execution_id"] == results["v2"]["execution_id"]:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise ValueError("A comparação precisa de duas respostas válidas vinculadas ao mesmo cenário.") from None


def save_comparison(
    comparison: dict, evaluations: dict, *, storage_dir: str | Path | None = None,
) -> dict:
    """Persiste um snapshot completo; só devolve o caminho após a gravação confirmada."""
    validate_comparison(comparison)
    rubric = validate_rubric(evaluations)
    record = deepcopy(comparison)
    record["evaluated_at_utc"] = datetime.now(timezone.utc).isoformat()
    for version in VERSIONS:
        record["resultados"][version]["avaliacao"] = rubric[version]
    record["totais"] = {
        "v1": rubric["v1"]["total"], "v2": rubric["v2"]["total"],
        "delta_v2_v1": rubric["v2"]["total"] - rubric["v1"]["total"],
    }
    path = JSONStorage(storage_dir).write_comparison(record)
    return {**record, "comparison_path": str(path)}
