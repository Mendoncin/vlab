"""Geração de conteúdo com cache e histórico JSON (BK-003)."""

import argparse
import json
import sys

from vlab.ai import AIError
from vlab.profiles import load_profile
from vlab.prompt_engine import CONTENT_STRATEGIES
from vlab.service import run_generation
from vlab.storage import StorageError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--perfil", required=True, choices=("ana", "bruno", "carla", "diego"))
    parser.add_argument("--ticket", required=True, help="Texto original do ticket.")
    parser.add_argument("--tipo", default="diagnosis", choices=tuple(CONTENT_STRATEGIES))
    parser.add_argument("--versao", default="v2", choices=("v1", "v2"))
    parser.add_argument("--storage-dir", help="Diretório de cache e histórico (ou VLAB_STORAGE_DIR).")
    args = parser.parse_args(argv)
    try:
        result = run_generation(
            load_profile(args.perfil), args.ticket, args.tipo, args.versao,
            storage_dir=args.storage_dir,
        )
    except (ValueError, AIError, StorageError) as error:
        print(f"Falha na execução: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
