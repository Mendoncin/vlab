"""BK-004: controles reais do Streamlit com SDK simulado e armazenamento temporário."""

import json
import os
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from tests.test_prompt_engine import TICKET, VALID_CONTENT
from tests.test_service import MockGenerationCase
from vlab.ai import AIError
from vlab.profiles import ProfileError, load_profile
from vlab.prompt_engine import ResponseValidationError
from vlab.service import run_generation
from vlab.storage import StorageError


APP = Path(__file__).resolve().parent.parent / "app.py"


class AppTests(MockGenerationCase):
    def setUp(self):
        super().setUp()
        environment = patch.dict(os.environ, {"VLAB_STORAGE_DIR": str(self.directory)})
        environment.start()
        self.addCleanup(environment.stop)
        self.app = AppTest.from_file(str(APP), default_timeout=15)

    def submit(self, ticket=TICKET, profile="ana", content_type="diagnosis", version="v2"):
        self.app.selectbox(key="profile_id").select(profile)
        self.app.text_area(key="ticket").input(ticket)
        self.app.selectbox(key="content_type").select(content_type)
        self.app.selectbox(key="version").select(version)
        self.app.button[0].click().run()
        self.assertFalse(self.app.exception)

    def displayed(self):
        return "\n".join(element.value for element in self.app.markdown)

    def test_initialization_has_four_json_profiles_four_types_two_versions_and_no_generation(self):
        with patch("vlab.profiles.load_profile", wraps=load_profile) as loader:
            self.app.run()
        self.assertFalse(self.app.exception)
        self.assertEqual(self.app.title[0].value, "Vlab — Assistente de suporte")
        self.assertEqual([call.args[0] for call in loader.call_args_list], ["ana", "bruno", "carla", "diego"])
        self.assertEqual(self.app.selectbox(key="profile_id").options, [
            "Ana — Leigo, Didático, Chat", "Bruno — Intermediário, Detalhado, E-mail",
            "Carla — Avançado, Direto, Chat", "Diego — Leigo, Direto, Telefone",
        ])
        self.assertEqual(self.app.selectbox(key="content_type").options, [
            "Diagnóstico", "Resolução", "Perguntas de esclarecimento", "Fluxo de atendimento",
        ])
        self.assertEqual(self.app.selectbox(key="version").options, ["v1 — Baseline", "v2 — Otimizada"])
        self.assertEqual(self.app.button[0].label, "Gerar resposta")
        self.assertFalse(self.app.success)
        self.create.assert_not_called()

    def test_empty_or_whitespace_ticket_does_not_call_service(self):
        self.app.run()
        with patch("vlab.service.run_generation") as service:
            for ticket in ("", "  \n  "):
                with self.subTest(ticket=ticket):
                    self.submit(ticket=ticket)
                    self.assertIn("Informe o problema", self.app.error[0].value)
                    self.assertFalse(self.app.success)
            service.assert_not_called()
        self.create.assert_not_called()
        self.assertEqual(self.history(), [])

    def test_valid_submission_forwards_exact_profile_and_unmodified_ticket_to_service(self):
        self.app.run()
        ticket = f"  {TICKET}\n"
        with patch("vlab.service.run_generation", wraps=run_generation) as service:
            self.submit(ticket=ticket, profile="bruno", content_type="resolution", version="v1")
        service.assert_called_once_with(load_profile("bruno"), ticket, "resolution", "v1")
        self.create.assert_called_once()
        self.assertIn("Cliente: Bruno", self.displayed())
        self.assertIn("Tipo de conteúdo: Resolução", self.displayed())
        self.assertIn("Versão do prompt: v1", self.displayed())
        self.assertIn("Modelo: modelo-teste", self.displayed())
        self.assertTrue(self.app.success)

    def test_ana_diagnosis_v2_miss_then_hit_creates_two_current_history_records(self):
        self.app.run()
        self.submit()
        first_path = Path(self.app.code[0].value)
        first_bytes = first_path.read_bytes()
        first = json.loads(first_bytes)
        self.assertEqual(first["cliente"], {"id": "ana", "nome": "Ana"})
        self.assertEqual(first["ticket"], TICKET)
        self.assertEqual(first["tipo_conteudo"], "diagnosis")
        self.assertEqual(first["versao_prompt"], "v2")
        self.assertEqual(first["conteudo"], VALID_CONTENT["diagnosis"])
        self.assertFalse(first["cache_hit"])
        self.assertIn("Origem: API OpenAI (cache miss)", self.displayed())
        self.assertEqual(first_path.stem, first["execution_id"])
        self.assertEqual(len(self.history()), 1)
        self.create.assert_called_once()

        self.submit()
        second_path = Path(self.app.code[0].value)
        second = json.loads(second_path.read_text(encoding="utf-8"))
        self.assertTrue(second["cache_hit"])
        self.assertEqual(second["origem"], "cache")
        self.assertIn("Origem: cache (cache hit)", self.displayed())
        self.assertEqual(second_path.stem, second["execution_id"])
        self.assertNotEqual(first_path, second_path)
        self.assertEqual(first_path.read_bytes(), first_bytes)
        self.assertEqual(first["conteudo"], second["conteudo"])
        self.assertEqual(len(self.history()), 2)
        self.assertEqual(len(list((self.directory / "cache").glob("*.json"))), 1)
        self.create.assert_called_once()

    def test_all_types_and_versions_render_contract_fields(self):
        self.app.run()
        for content_type, content in VALID_CONTENT.items():
            for version in ("v1", "v2"):
                with self.subTest(content_type=content_type, version=version):
                    self.submit(content_type=content_type, version=version)
                    self.assertTrue(self.app.success)
                    self.assertFalse(self.app.error)
                    for value in self.text_values(content):
                        self.assertIn(value, self.displayed())
                    self.assertIn(f"Versão do prompt: {version}", self.displayed())
        self.assertEqual(self.create.call_count, 8)
        self.assertEqual(len(self.history()), 8)

    @staticmethod
    def text_values(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, list):
            for item in value:
                yield from AppTests.text_values(item)
        elif isinstance(value, dict):
            for item in value.values():
                yield from AppTests.text_values(item)

    def test_empty_optional_diagnosis_lists_render(self):
        self.create.side_effect = None
        self.create.return_value.status = "completed"
        self.create.return_value.output_text = json.dumps({
            **VALID_CONTENT["diagnosis"], "evidencias": [], "informacoes_faltantes": [],
        })
        self.app.run()
        self.submit()
        self.assertTrue(self.app.success)
        self.assertIn("Nenhuma informação indicada.", self.displayed())

    def test_all_profiles_can_be_submitted(self):
        self.app.run()
        for identifier in ("ana", "bruno", "carla", "diego"):
            with self.subTest(profile=identifier):
                self.submit(profile=identifier)
                saved = json.loads(Path(self.app.code[0].value).read_text(encoding="utf-8"))
                self.assertEqual(saved["cliente"]["id"], identifier)
        self.assertEqual(self.create.call_count, 4)

    def test_reruns_preserve_result_and_metadata_without_new_generation_or_history(self):
        self.app.run()
        with patch("vlab.service.run_generation", wraps=run_generation) as service:
            self.submit()
            history_path = self.app.code[0].value
            self.app.run()
            self.app.selectbox(key="profile_id").select("diego").run()
            self.app.selectbox(key="content_type").select("flow").run()
            self.app.selectbox(key="version").select("v1").run()
            self.app.text_area(key="ticket").input("Outro problema").run()
            service.assert_called_once()
        self.assertTrue(self.app.success)
        self.assertIn("Cliente: Ana", self.displayed())
        self.assertIn("Tipo de conteúdo: Diagnóstico", self.displayed())
        self.assertIn("Versão do prompt: v2", self.displayed())
        self.assertEqual(self.app.code[0].value, history_path)
        self.assertEqual(len(self.history()), 1)
        self.create.assert_called_once()

    def test_profile_loading_failure_is_safe_and_application_can_recover(self):
        with patch("vlab.profiles.load_profile", side_effect=ProfileError("segredo")):
            self.app.run()
        self.assertFalse(self.app.exception)
        self.assertIn("Não foi possível carregar os perfis", self.app.error[0].value)
        self.assertNotIn("segredo", self.app.error[0].value)
        self.create.assert_not_called()
        self.app.run()
        self.submit()
        self.assertTrue(self.app.success)

    def test_service_errors_are_safe_clear_previous_success_and_allow_retry(self):
        self.app.run()
        self.submit()
        errors = (
            (ProfileError("segredo"), "Perfil inválido ou indisponível"),
            (ValueError("segredo"), "Dados inválidos"),
            (ResponseValidationError("segredo"), "resposta inválida"),
            (AIError("segredo"), "OpenAI"),
            (StorageError("segredo"), "cache ou salvar o histórico"),
        )
        for error, expected in errors:
            with self.subTest(error=type(error).__name__):
                with patch("vlab.service.run_generation", side_effect=error):
                    self.submit()
                self.assertIn(expected, self.app.error[0].value)
                self.assertNotIn("segredo", self.app.error[0].value)
                self.assertFalse(self.app.success)
                self.assertFalse(self.app.code)
        self.assertEqual(len(self.history()), 1)
        self.submit()
        self.assertTrue(self.app.success)
        self.assertEqual(len(self.history()), 2)

    def test_invalid_engine_response_is_not_presented_or_persisted_as_success(self):
        self.create.side_effect = None
        self.create.return_value.status = "completed"
        self.create.return_value.output_text = "{}"
        self.app.run()
        self.submit()
        self.assertIn("resposta inválida", self.app.error[0].value)
        self.assertFalse(self.app.success)
        self.assertEqual(list(self.directory.rglob("*.json")), [])

    def test_cache_read_failure_prevents_api_and_success(self):
        self.app.run()
        with patch("vlab.storage.JSONStorage.read_cache", side_effect=StorageError("segredo")):
            self.submit()
        self.assertIn("cache ou salvar o histórico", self.app.error[0].value)
        self.assertFalse(self.app.success)
        self.create.assert_not_called()
        self.assertEqual(self.history(), [])

    def test_history_write_failure_never_reports_success_and_retry_uses_cache(self):
        self.app.run()
        with patch("vlab.storage.JSONStorage.write_history", side_effect=StorageError("segredo")):
            self.submit()
        self.assertIn("cache ou salvar o histórico", self.app.error[0].value)
        self.assertFalse(self.app.success)
        self.assertFalse(self.app.code)
        self.assertEqual(self.history(), [])
        self.submit()
        self.assertTrue(self.app.success)
        self.assertIn("Origem: cache (cache hit)", self.displayed())
        self.assertEqual(len(self.history()), 1)
        self.create.assert_called_once()

    def test_blank_submission_clears_previous_success(self):
        self.app.run()
        self.submit()
        self.submit(ticket=" ")
        self.assertTrue(self.app.error)
        self.assertFalse(self.app.success)
        self.assertFalse(self.app.code)
        self.create.assert_called_once()
        self.assertEqual(len(self.history()), 1)
