"""Smoke test BK-002: uma chamada real, sem salvar prompt ou resultado."""

import argparse

from vlab.ai import AIError
from vlab.profiles import load_profile
from vlab.prompt_engine import CONTENT_STRATEGIES, build_prompt, generate_content


TICKET = "Meu notebook não consegue se conectar ao Wi-Fi"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--perfil", default="ana", choices=("ana", "bruno", "carla", "diego"))
    parser.add_argument("--tipo", default="diagnosis", choices=tuple(CONTENT_STRATEGIES))
    parser.add_argument("--versao", default="v2", choices=("v1", "v2"))
    args = parser.parse_args()
    try:
        profile = load_profile(args.perfil)
        prompt = build_prompt(profile, TICKET, args.tipo, args.versao)
        print(f"Perfil definitivo carregado: {profile['nome']}.")
        print(f"Prompt montado: {args.tipo}/{args.versao}; {len(prompt['instructions'])} caracteres de instruções.")
        result = generate_content(profile, TICKET, args.tipo, args.versao)
    except (ValueError, AIError) as error:
        print(f"Falha no smoke test BK-002: {error}")
        return 1
    print(
        f"Sucesso: resposta real recebida e validada; "
        f"provedor={result['provedor']}; modelo={result['modelo']}; "
        f"cliente={result['cliente']['id']}; tipo={result['tipo_conteudo']}; "
        f"versão={result['versao_prompt']}; campos={', '.join(result['conteudo'])}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
