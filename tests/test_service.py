from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import httpx
from openai import APIConnectionError

from tests.test_prompt_engine import TICKET, VALID_CONTENT
from vlab.ai import AIError
from vlab.profiles import load_profile
from vlab.prompt_engine import ResponseValidationError, VERSION_INSTRUCTIONS, generate_content
from vlab.service import cache_key, run_generation
from vlab.storage import JSONStorage, StorageError


class MockGenerationCase(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        # Canonicaliza também nomes curtos de diretórios temporários no Windows.
        self.directory = Path(temporary.name).resolve()
        self.profile = load_profile("ana")
        environment = patch.dict(os.environ, {
            "OPENAI_API_KEY": "chave-ficticia-secreta", "OPENAI_MODEL": "modelo-teste",
            # Permite ao Streamlit localizar um home isolado no Windows.
            "USERPROFILE": str(self.directory),
        }, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        dotenv = patch("vlab.ai.load_dotenv")
        dotenv.start()
        self.addCleanup(dotenv.stop)
        sdk = patch("vlab.ai.OpenAI")
        self.sdk = sdk.start()
        self.addCleanup(sdk.stop)
        self.create = self.sdk.return_value.__enter__.return_value.responses.create
        self.create.side_effect = self.respond

    @staticmethod
    def respond(**kwargs):
        # Identifica o contrato efetivamente enviado ao SDK, sem repetir o motor.
        fields = set(kwargs["text"]["format"]["schema"]["required"])
        content = next(content for content in VALID_CONTENT.values() if set(content) == fields)
        return SimpleNamespace(status="completed", output_text=json.dumps(content))

    def run_request(self, **changes):
        arguments = {
            "profile": self.profile, "ticket": TICKET,
            "content_type": "diagnosis", "version": "v2", "storage_dir": self.directory,
        }
        arguments.update(changes)
        return run_generation(**arguments)

    def history(self):
        return sorted((self.directory / "history").glob("*.json"))


class ServiceTests(MockGenerationCase):
    def test_first_execution_persists_required_metadata_and_exact_configuration(self):
        result = self.run_request(ticket=f"  {TICKET}\n")
        self.create.assert_called_once()
        record = json.loads(Path(result["history_path"]).read_text(encoding="utf-8"))
        self.assertEqual(record, {k: v for k, v in result.items() if k != "history_path"})
        self.assertEqual(record["cliente"], {"id": "ana", "nome": "Ana"})
        self.assertEqual(record["ticket"], f"  {TICKET}\n")
        self.assertEqual(record["tipo_conteudo"], "diagnosis")
        self.assertEqual(record["versao_prompt"], "v2")
        self.assertEqual(record["provedor"], "openai")
        self.assertEqual(record["modelo"], "modelo-teste")
        self.assertEqual(record["status"], "success")
        self.assertEqual(record["origem"], "api")
        self.assertFalse(record["cache_hit"])
        self.assertEqual(record["conteudo"], VALID_CONTENT["diagnosis"])
        self.assertEqual(datetime.fromisoformat(record["timestamp_utc"]).tzinfo, timezone.utc)
        self.assertEqual(len(record["cache_key"]), 64)
        actual_config = dict(self.create.call_args.kwargs)
        actual_config.pop("input")
        actual_config.pop("instructions")
        self.assertEqual(record["configuracao_modelo"], actual_config)
        self.assertEqual(len(list((self.directory / "cache").glob("*.json"))), 1)

    def test_identical_request_skips_generator_and_creates_own_history(self):
        with patch("vlab.service.prompt_engine.generate_content", wraps=generate_content) as generate:
            first = self.run_request()
            first_bytes = Path(first["history_path"]).read_bytes()
            second = self.run_request()
            generate.assert_called_once()
        self.create.assert_called_once()
        self.assertFalse(first["cache_hit"])
        self.assertTrue(second["cache_hit"])
        self.assertEqual(second["origem"], "cache")
        self.assertEqual(first["conteudo"], second["conteudo"])
        self.assertEqual(first["cache_key"], second["cache_key"])
        self.assertNotEqual(first["execution_id"], second["execution_id"])
        self.assertNotEqual(first["timestamp_utc"], second["timestamp_utc"])
        self.assertEqual(len(self.history()), 2)
        self.assertEqual(Path(first["history_path"]).read_bytes(), first_bytes)
        saved = json.loads(Path(second["history_path"]).read_text(encoding="utf-8"))
        self.assertTrue(saved["cache_hit"])
        self.assertEqual(saved["timestamp_utc"], second["timestamp_utc"])

    def test_ticket_type_version_and_every_profile_field_invalidate_cache(self):
        original = self.run_request()
        variants = [
            {"ticket": TICKET + "!"}, {"content_type": "resolution"},
            {"version": "v1"},
        ]
        for field, value in {
            "id": "outra-ana", "nome": "Ana Silva", "nivel_tecnico": "avançado",
            "estilo_comunicacao": "direto", "canal": "e-mail", "extra": {"contexto": ["novo"]},
        }.items():
            variants.append({"profile": dict(self.profile, **{field: value})})
        for variant in variants:
            with self.subTest(variant=variant):
                result = self.run_request(**variant)
                self.assertFalse(result["cache_hit"])
                self.assertNotEqual(result["cache_key"], original["cache_key"])
        self.assertEqual(self.create.call_count, 1 + len(variants))
        self.assertEqual(len(self.history()), 1 + len(variants))

    def test_effective_instructions_change_with_same_version_invalidates_cache(self):
        original = self.run_request()
        with patch.dict(VERSION_INSTRUCTIONS, {"v2": VERSION_INSTRUCTIONS["v2"] + " Nova regra."}):
            changed = self.run_request()
            repeated = self.run_request()
        self.assertNotEqual(original["cache_key"], changed["cache_key"])
        self.assertFalse(changed["cache_hit"])
        self.assertTrue(repeated["cache_hit"])
        self.assertIn("Nova regra.", self.create.call_args.kwargs["instructions"])
        self.assertEqual(self.create.call_count, 2)

    def test_model_and_output_limit_changes_reach_api_and_invalidate_cache(self):
        original = self.run_request()
        with patch.dict(os.environ, {"OPENAI_MODEL": "outro-modelo"}):
            changed_model = self.run_request()
            self.assertEqual(self.create.call_args.kwargs["model"], "outro-modelo")
        with patch("vlab.ai.STRUCTURED_MAX_OUTPUT_TOKENS", 1700):
            changed_limit = self.run_request()
            self.assertEqual(self.create.call_args.kwargs["max_output_tokens"], 1700)
            self.assertTrue(self.run_request()["cache_hit"])
        self.assertEqual(len({r["cache_key"] for r in (original, changed_model, changed_limit)}), 3)
        self.assertEqual(self.create.call_count, 3)

    def test_schema_change_invalidates_cache_and_is_sent_to_api(self):
        from vlab.prompt_engine import CONTENT_STRATEGIES

        original = self.run_request()
        strategies = deepcopy(CONTENT_STRATEGIES)
        strategies["diagnosis"]["schema"]["properties"]["conclusao"]["description"] = "Síntese."
        with patch.dict(CONTENT_STRATEGIES, strategies):
            changed = self.run_request()
        self.assertFalse(changed["cache_hit"])
        self.assertNotEqual(original["cache_key"], changed["cache_key"])
        self.assertIn("description", self.create.call_args.kwargs["text"]["format"]["schema"]["properties"]["conclusao"])
        self.assertEqual(self.create.call_count, 2)

    def test_prompt_is_built_once_and_model_snapshot_survives_environment_change(self):
        from vlab.prompt_engine import build_prompt

        def generate_after_environment_change(*args, **kwargs):
            os.environ["OPENAI_MODEL"] = "modelo-alterado-depois-da-chave"
            return generate_content(*args, **kwargs)

        with patch("vlab.service.prompt_engine.build_prompt", wraps=build_prompt) as build, patch(
            "vlab.service.prompt_engine.generate_content", side_effect=generate_after_environment_change
        ):
            result = self.run_request()
        build.assert_called_once()
        self.assertEqual(result["modelo"], "modelo-teste")
        self.assertEqual(self.create.call_args.kwargs["model"], "modelo-teste")

    def test_reordered_nested_json_keys_preserve_identity_and_cache_hit(self):
        profile = dict(self.profile, extra={"a": {"x": 1, "y": 2}, "b": [1, 2]})
        reordered = dict(reversed(list(profile.items())))
        reordered["extra"] = {"b": [1, 2], "a": {"y": 2, "x": 1}}
        first = self.run_request(profile=profile)
        second = self.run_request(profile=reordered)
        self.assertEqual(first["cache_key"], second["cache_key"])
        self.assertTrue(second["cache_hit"])
        self.create.assert_called_once()
        self.assertEqual(cache_key({"b": 2, "a": 1}), cache_key({"a": 1, "b": 2}))

    def test_credentials_are_never_persisted_or_used_in_key(self):
        first = self.run_request()
        with patch.dict(os.environ, {"OPENAI_API_KEY": "outra-chave-secreta", "AUTH_TOKEN": "token-secreto"}):
            second = self.run_request()
        self.assertTrue(second["cache_hit"])
        self.assertEqual(first["cache_key"], second["cache_key"])
        for path in self.directory.rglob("*.json"):
            saved = path.read_text(encoding="utf-8")
            for secret in ("chave-ficticia-secreta", "outra-chave-secreta", "token-secreto", "OPENAI_API_KEY"):
                self.assertNotIn(secret, saved)

    def test_cache_hit_does_not_require_api_credentials(self):
        first = self.run_request()
        os.environ.pop("OPENAI_API_KEY")
        second = self.run_request()
        self.assertEqual(first["conteudo"], second["conteudo"])
        self.assertTrue(second["cache_hit"])
        self.create.assert_called_once()

    def test_environment_directory_and_explicit_override_are_respected(self):
        with patch.dict(os.environ, {"VLAB_STORAGE_DIR": str(self.directory / "environment")}):
            environment = self.run_request(storage_dir=None)
            explicit = self.run_request(storage_dir=self.directory / "explicit")
        self.assertEqual(Path(environment["history_path"]).parent.parent, self.directory / "environment")
        self.assertEqual(Path(explicit["history_path"]).parent.parent, self.directory / "explicit")
        self.assertEqual(environment["cache_key"], explicit["cache_key"])
        self.assertEqual(self.create.call_count, 2)

    def test_default_directory_is_local_project_directory(self):
        from vlab.storage import DEFAULT_STORAGE_DIR

        self.assertEqual(JSONStorage().directory, DEFAULT_STORAGE_DIR)
        self.assertEqual(DEFAULT_STORAGE_DIR.name, ".vlab")

    def test_empty_invalid_and_incomplete_responses_are_not_cached_and_can_retry(self):
        for status, raw in (("completed", ""), ("completed", "{"), ("completed", "{}"), ("incomplete", "{}")):
            with self.subTest(status=status, raw=raw), TemporaryDirectory() as directory:
                self.create.side_effect = None
                self.create.return_value = SimpleNamespace(status=status, output_text=raw)
                before = self.create.call_count
                with self.assertRaises((AIError, ResponseValidationError)):
                    self.run_request(storage_dir=directory)
                self.assertEqual(list(Path(directory).rglob("*.json")), [])
                self.create.side_effect = self.respond
                result = self.run_request(storage_dir=directory)
                self.assertFalse(result["cache_hit"])
                self.assertEqual(self.create.call_count, before + 2)

    def test_api_failure_is_not_cached_and_retry_calls_api_again(self):
        self.create.side_effect = APIConnectionError(
            message="dado-sensivel", request=httpx.Request("POST", "https://api.openai.com")
        )
        with self.assertRaises(AIError) as caught:
            self.run_request()
        self.assertNotIn("dado-sensivel", str(caught.exception))
        self.assertEqual(list(self.directory.rglob("*.json")), [])
        self.create.side_effect = self.respond
        self.assertFalse(self.run_request()["cache_hit"])
        self.assertEqual(self.create.call_count, 2)

    def test_corrupt_cache_is_replaced_only_after_valid_generation(self):
        first = self.run_request()
        cache_path = self.directory / "cache" / f"{first['cache_key']}.json"
        invalid_entries = [
            b"{", b"\xff", b"null", b"[]", b"{}",
            json.dumps({"schema_version": 99, "cache_key": first["cache_key"], "conteudo": VALID_CONTENT["diagnosis"]}).encode(),
            json.dumps({"schema_version": 1, "cache_key": "outro", "conteudo": VALID_CONTENT["diagnosis"]}).encode(),
            json.dumps({"schema_version": 1, "cache_key": first["cache_key"], "conteudo": {}}).encode(),
            json.dumps({"schema_version": 1, "cache_key": first["cache_key"], "conteudo": VALID_CONTENT["flow"]}).encode(),
        ]
        for invalid in invalid_entries:
            with self.subTest(invalid=invalid):
                cache_path.write_bytes(invalid)
                self.assertFalse(self.run_request()["cache_hit"])
                self.assertEqual(json.loads(cache_path.read_text(encoding="utf-8"))["conteudo"], VALID_CONTENT["diagnosis"])
        self.assertEqual(self.create.call_count, 1 + len(invalid_entries))

    def test_read_error_is_reported_before_api(self):
        with patch("pathlib.Path.open", side_effect=PermissionError("dado-sensivel")):
            with self.assertRaisesRegex(StorageError, "ler o cache") as caught:
                self.run_request()
        self.assertNotIn("dado-sensivel", str(caught.exception))
        self.create.assert_not_called()

    def test_cache_write_error_is_not_reported_as_success(self):
        with patch("vlab.storage.os.replace", side_effect=OSError("dado-sensivel")):
            with self.assertRaisesRegex(StorageError, "gravar cache") as caught:
                self.run_request()
        self.assertNotIn("dado-sensivel", str(caught.exception))
        self.assertEqual(list(self.directory.rglob("*.json")), [])
        self.assertEqual(list(self.directory.rglob("*.tmp")), [])
        self.assertFalse(self.run_request()["cache_hit"])
        self.assertEqual(self.create.call_count, 2)

    def test_history_write_error_propagates_and_retry_can_use_valid_cache(self):
        with patch.object(JSONStorage, "write_history", side_effect=StorageError("Falha no histórico.")):
            with self.assertRaisesRegex(StorageError, "histórico"):
                self.run_request()
        self.assertEqual(self.history(), [])
        retry = self.run_request()
        self.assertTrue(retry["cache_hit"])
        self.assertEqual(len(self.history()), 1)
        self.create.assert_called_once()

    def test_blocked_storage_directory_reports_write_failure(self):
        blocked = self.directory / "blocked"
        blocked.write_text("arquivo", encoding="utf-8")
        with self.assertRaisesRegex(StorageError, "ler o cache"):
            self.run_request(storage_dir=blocked)
        self.create.assert_not_called()


class AtomicStorageTests(unittest.TestCase):
    def test_storage_path_resolution_failure_has_safe_error(self):
        with patch("pathlib.Path.resolve", side_effect=PermissionError("segredo")):
            with self.assertRaisesRegex(StorageError, "diretório de armazenamento") as caught:
                JSONStorage("local")
        self.assertNotIn("segredo", str(caught.exception))

    def test_interrupted_replacement_preserves_previous_json_and_cleans_temporary(self):
        with TemporaryDirectory() as directory:
            storage = JSONStorage(directory)
            path = storage.write_cache("key", {"original": "válido"})
            previous = path.read_bytes()
            with patch("vlab.storage.os.replace", side_effect=OSError("interrompido")):
                with self.assertRaises(StorageError):
                    storage.write_cache("key", {"novo": "conteúdo"})
            self.assertEqual(path.read_bytes(), previous)
            self.assertEqual(list(Path(directory).rglob("*.tmp")), [])

    def test_directory_creation_failure_has_safe_error(self):
        with TemporaryDirectory() as directory, patch("pathlib.Path.mkdir", side_effect=PermissionError("segredo")):
            with self.assertRaisesRegex(StorageError, "gravar cache") as caught:
                JSONStorage(directory).write_cache("key", {})
            self.assertNotIn("segredo", str(caught.exception))

    def test_non_json_data_never_leaves_partial_record(self):
        with TemporaryDirectory() as directory:
            with self.assertRaises(StorageError):
                JSONStorage(directory).write_cache("key", {"valor": float("nan")})
            self.assertEqual(list(Path(directory).rglob("*.json")), [])
            self.assertEqual(list(Path(directory).rglob("*.tmp")), [])

    def test_custom_storage_subdirectories_protect_untracked_runtime_files(self):
        with TemporaryDirectory() as directory:
            storage = JSONStorage(directory)
            path = storage.write_cache("key", {})
            self.assertEqual((path.parent / ".gitignore").read_text(encoding="utf-8"), "*\n")


if __name__ == "__main__":
    unittest.main()
