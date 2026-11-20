import io
import json
from pathlib import Path
import runpy
from unittest.mock import patch

from tests.test_service import MockGenerationCase
from vlab import cli
from vlab.ai import AIError
from vlab.service import run_generation
from vlab.storage import StorageError


class CLITests(MockGenerationCase):
    def arguments(self, **changes):
        options = {
            "perfil": "ana", "ticket": "Wi-Fi não conecta", "tipo": "diagnosis",
            "versao": "v2", "storage-dir": str(self.directory),
        }
        options.update(changes)
        return [item for key, value in options.items() for item in (f"--{key}", value)]

    def invoke(self, args):
        with patch("sys.stdout", new_callable=io.StringIO) as output, patch(
            "sys.stderr", new_callable=io.StringIO
        ) as errors:
            code = cli.main(args)
        return code, output.getvalue(), errors.getvalue()

    def test_complete_cli_miss_hit_and_invalidation_use_same_service(self):
        with patch("vlab.cli.run_generation", wraps=run_generation) as service:
            code1, out1, err1 = self.invoke(self.arguments())
            self.assertEqual(self.create.call_count, 1)
            first = json.loads(out1)
            first_bytes = Path(first["history_path"]).read_bytes()
            code2, out2, err2 = self.invoke(self.arguments())
            self.assertEqual(self.create.call_count, 1)
            self.assertEqual(len(self.history()), 2)
            code3, out3, err3 = self.invoke(self.arguments(versao="v1"))
            self.assertEqual(self.create.call_count, 2)
            self.assertEqual(service.call_count, 3)
        second, changed = json.loads(out2), json.loads(out3)
        self.assertEqual((code1, code2, code3), (0, 0, 0))
        self.assertEqual((err1, err2, err3), ("", "", ""))
        self.assertEqual([r["cache_hit"] for r in (first, second, changed)], [False, True, False])
        self.assertEqual(first["conteudo"], second["conteudo"])
        self.assertEqual(first["cache_key"], second["cache_key"])
        self.assertNotEqual(first["cache_key"], changed["cache_key"])
        self.assertEqual(len(self.history()), 3)
        self.assertEqual(len(list((self.directory / "cache").glob("*.json"))), 2)
        self.assertEqual(Path(first["history_path"]).read_bytes(), first_bytes)
        self.assertNotEqual(first["history_path"], second["history_path"])
        for result in (first, second, changed):
            saved = json.loads(Path(result["history_path"]).read_text(encoding="utf-8"))
            self.assertEqual(saved["cache_hit"], result["cache_hit"])

    def test_all_four_profiles_are_accepted_and_loaded(self):
        for profile in ("ana", "bruno", "carla", "diego"):
            with self.subTest(profile=profile):
                code, output, errors = self.invoke(self.arguments(perfil=profile))
                self.assertEqual(code, 0)
                self.assertEqual(errors, "")
                self.assertEqual(json.loads(output)["cliente"]["id"], profile)
                self.assertEqual(json.loads(self.create.call_args.kwargs["input"])["perfil"]["id"], profile)
        self.assertEqual(self.create.call_count, 4)

    def test_all_types_and_versions_work_through_cli(self):
        for content_type in ("diagnosis", "resolution", "questions", "flow"):
            for version in ("v1", "v2"):
                with self.subTest(content_type=content_type, version=version):
                    code, output, errors = self.invoke(self.arguments(tipo=content_type, versao=version))
                    self.assertEqual(code, 0)
                    self.assertEqual(errors, "")
                    result = json.loads(output)
                    self.assertEqual(result["tipo_conteudo"], content_type)
                    self.assertEqual(result["versao_prompt"], version)
        self.assertEqual(self.create.call_count, 8)

    def test_default_type_version_and_environment_directory(self):
        import os

        with patch.dict(os.environ, {"VLAB_STORAGE_DIR": str(self.directory)}):
            code, output, _ = self.invoke(["--perfil", "ana", "--ticket", "Sem conexão"])
        self.assertEqual(code, 0)
        result = json.loads(output)
        self.assertEqual((result["tipo_conteudo"], result["versao_prompt"]), ("diagnosis", "v2"))
        self.assertEqual(Path(result["history_path"]).parent.parent, self.directory)

    def test_invalid_choices_missing_arguments_and_unknown_options_exit_two(self):
        invalid = [
            [], ["--perfil", "ana"], ["--ticket", "problema"],
            self.arguments(perfil="ausente"), self.arguments(tipo="other"),
            self.arguments(versao="v3"), self.arguments() + ["--unknown"],
        ]
        for args in invalid:
            with self.subTest(args=args), patch("sys.stderr", new_callable=io.StringIO) as errors:
                with self.assertRaises(SystemExit) as caught:
                    cli.main(args)
                self.assertEqual(caught.exception.code, 2)
                self.assertIn("error:", errors.getvalue())
        self.create.assert_not_called()

    def test_blank_ticket_is_reported_without_api(self):
        code, output, errors = self.invoke(self.arguments(ticket="  "))
        self.assertEqual(code, 1)
        self.assertEqual(output, "")
        self.assertIn("ticket deve ser um texto não vazio", errors)
        self.create.assert_not_called()

    def test_generation_validation_and_persistence_failures_exit_one(self):
        from vlab.prompt_engine import ResponseValidationError

        for error in (AIError("Falha de conexão."), StorageError("Falha no histórico."), ResponseValidationError("JSON inválido.")):
            with self.subTest(error=type(error).__name__), patch("vlab.cli.run_generation", side_effect=error):
                code, output, errors = self.invoke(self.arguments())
                self.assertEqual(code, 1)
                self.assertEqual(output, "")
                self.assertIn(str(error), errors)

    def test_real_storage_failure_has_nonzero_exit_and_no_success_output(self):
        with patch("vlab.storage.os.replace", side_effect=PermissionError("segredo")):
            code, output, errors = self.invoke(self.arguments())
        self.assertEqual(code, 1)
        self.assertEqual(output, "")
        self.assertIn("gravar cache", errors)
        self.assertNotIn("segredo", errors)

    def test_module_entrypoint_exits_zero_or_one(self):
        for raw, expected in ((None, 0), ("{}", 1)):
            with self.subTest(expected=expected):
                if raw is not None:
                    self.create.side_effect = None
                    self.create.return_value.output_text = raw
                args = self.arguments(ticket=f"Teste de saída {expected}")
                with patch("sys.argv", ["vlab.cli", *args]), patch("sys.stdout", new_callable=io.StringIO), patch("sys.stderr", new_callable=io.StringIO):
                    with self.assertRaises(SystemExit) as caught:
                        runpy.run_path(cli.__file__, run_name="__main__")
                self.assertEqual(caught.exception.code, expected)
