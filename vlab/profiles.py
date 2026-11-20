"""Leitura e validação dos dados de clientes, sem dependência da API."""

import json
import re
from pathlib import Path


PROFILES_DIR = Path(__file__).resolve().parent.parent / "profiles"
ALLOWED_VALUES = {
    "nivel_tecnico": ("leigo", "intermediário", "avançado"),
    "estilo_comunicacao": ("direto", "detalhado", "didático"),
    "canal": ("chat", "e-mail", "telefone"),
}


class ProfileError(ValueError):
    """Perfil ausente, ilegível ou fora do formato esperado."""


def validate_profile(profile: object) -> dict:
    """Exige nome ou id textual e os três atributos definidos no enunciado."""
    if not isinstance(profile, dict):
        raise ProfileError("O perfil deve ser um objeto JSON.")

    if not any(field in profile for field in ("nome", "id")):
        raise ProfileError("O perfil deve conter nome ou id.")
    for field in ("nome", "id"):
        if field in profile and (
            not isinstance(profile[field], str) or not profile[field].strip()
        ):
            raise ProfileError(f"O campo {field} deve ser um texto não vazio.")

    for field, allowed in ALLOWED_VALUES.items():
        if field not in profile:
            raise ProfileError(f"Campo obrigatório ausente: {field}.")
        if profile[field] not in allowed:
            raise ProfileError(
                f"Valor inválido para {field}. Permitidos: {', '.join(allowed)}."
            )
    return profile


def load_profile(profile_id: str, profiles_dir: str | Path = PROFILES_DIR) -> dict:
    """Carrega <profile_id>.json de um diretório; não aceita caminhos no id."""
    if not isinstance(profile_id, str) or not re.fullmatch(r"[\w-]+", profile_id):
        raise ProfileError("Identificador inválido: use letras, números, _ ou -.")

    path = Path(profiles_dir) / f"{profile_id}.json"
    try:
        with path.open(encoding="utf-8") as file:
            profile = json.load(file)
    except FileNotFoundError:
        raise ProfileError("Perfil não encontrado no diretório informado.") from None
    except (json.JSONDecodeError, UnicodeError):
        raise ProfileError("O arquivo do perfil não contém JSON UTF-8 válido.") from None
    except OSError:
        raise ProfileError("Não foi possível ler o arquivo do perfil.") from None

    return validate_profile(profile)
