"""Histórico e cache em JSON local; escrita temporária seguida de replace atômico."""

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile


DEFAULT_STORAGE_DIR = Path(__file__).resolve().parent.parent / ".vlab"


class StorageError(RuntimeError):
    """Não foi possível ler ou persistir os dados da execução."""


class JSONStorage:
    def __init__(self, directory: str | Path | None = None):
        configured = directory if directory is not None else os.getenv("VLAB_STORAGE_DIR")
        try:
            self.directory = Path(configured or DEFAULT_STORAGE_DIR).expanduser().resolve()
        except (OSError, RuntimeError):
            raise StorageError("Não foi possível acessar o diretório de armazenamento.") from None

    def read_cache(self, key: str) -> object:
        try:
            with (self.directory / "cache" / f"{key}.json").open(encoding="utf-8") as file:
                return json.load(file)
        except FileNotFoundError:
            return None
        except (ValueError, UnicodeError, RecursionError):
            # Arquivo incompleto ou corrompido: permite outra geração.
            return None
        except OSError:
            raise StorageError("Não foi possível ler o cache local.") from None

    def write_cache(self, key: str, content: dict) -> Path:
        return self._write("cache", key, {
            "schema_version": 1, "cache_key": key, "conteudo": content,
        })

    def write_history(self, record: dict) -> Path:
        return self._write("history", record["execution_id"], record)

    def _write(self, folder: str, identifier: str, data: dict) -> Path:
        directory = self.directory / folder
        temporary = None
        try:
            directory.mkdir(parents=True, exist_ok=True)
            # Protege também diretórios personalizados dentro de um repositório.
            # Não altera um .gitignore que já exista nesse diretório.
            try:
                with (directory / ".gitignore").open("x", encoding="utf-8") as file:
                    file.write("*\n")
            except FileExistsError:
                pass
            destination = directory / f"{identifier}.json"
            with NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=directory, suffix=".tmp", delete=False
            ) as file:
                temporary = Path(file.name)
                json.dump(data, file, ensure_ascii=False, indent=2, allow_nan=False)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, destination)
            return destination
        except (OSError, TypeError, ValueError, RecursionError):
            raise StorageError(f"Não foi possível gravar {folder} em JSON local.") from None
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    raise StorageError("Não foi possível remover o arquivo temporário local.") from None
