"""Smoke test explícito: carrega um perfil e faz exatamente uma chamada real."""

import argparse
import json
from pathlib import Path

from vlab.ai import AIError, generate_text
from vlab.profiles import ProfileError, load_profile


FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--perfil", help="Identificador de um JSON definitivo em profiles/.")
    source.add_argument(
        "--fixture", action="store_true", help="Usa apenas a fixture de teste, não definitiva."
    )
    args = parser.parse_args()

    try:
        if args.fixture:
            profile = load_profile("perfil_teste", FIXTURES_DIR)
            print("Perfil: fixture de teste; não é um dos quatro clientes definitivos.")
        else:
            profile = load_profile(args.perfil)
            print("Perfil definitivo carregado e validado.")

        # Somente demonstra transporte de contexto; o motor de prompts é do BK-002.
        message = (
            f"Dados do cliente: {json.dumps(profile, ensure_ascii=False)}\n"
            "Problema técnico: Meu notebook não consegue se conectar ao Wi-Fi.\n"
            "Sugira um primeiro passo simples em uma frase curta em português, "
            "considerando os dados do cliente."
        )
        answer = generate_text(message)
    except (ProfileError, AIError) as error:
        print(f"Falha no smoke test: {error}")
        return 1

    # A resposta é validada por generate_text; não há persistência de resultados.
    print(f"Sucesso: resposta real concluída e não vazia ({len(answer)} caracteres).")
    print(answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
