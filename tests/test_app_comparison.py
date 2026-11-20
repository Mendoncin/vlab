"""Smoke e interação da comparação via Streamlit AppTest, sem chamadas reais."""

import json
import os
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from tests import test_app
from tests.test_comparison import manual_fixture
from tests.test_prompt_engine import TICKET, VALID_CONTENT
from tests.test_service import MockGenerationCase
from vlab import comparison
from vlab.ai import AIError
from vlab.storage import StorageError


class ComparisonAppTests(MockGenerationCase):
    def setUp(self):
        super().setUp()
        environment = patch.dict(os.environ, {"VLAB_STORAGE_DIR": str(self.directory)})
        environment.start()
        self.addCleanup(environment.stop)
        self.app = AppTest.from_file(str(test_app.APP), default_timeout=15).run()

    def start(self, content_type="diagnosis"):
        self.app.text_area(key="comparison_ticket").input(TICKET)
        self.app.selectbox(key="comparison_type").select(content_type)
        self.app.button(key="compare_prompts").click().run()
        self.assertFalse(self.app.exception)
        return self.app.session_state["comparison"]

    def fill(self):
        identifier = self.app.session_state["comparison"]["comparison_id"]
        for version, criteria in manual_fixture().items():
            for criterion, entry in criteria.items():
                prefix = f"{identifier}_{version}_{criterion}"
                self.app.number_input(key=prefix + "_score").set_value(entry["score"])
                self.app.text_area(key=prefix + "_justification").input(entry["justification"])

    def displayed(self):
        return "\n".join(element.value for element in self.app.markdown)

    def test_initial_comparison_controls_and_empty_ticket_do_not_generate(self):
        self.assertEqual(len(self.app.selectbox(key="comparison_profile").options), 4)
        self.assertEqual(len(self.app.selectbox(key="comparison_type").options), 4)
        self.app.button(key="compare_prompts").click().run()
        self.assertFalse(self.app.exception)
        self.assertIn("antes de comparar", self.app.error[0].value)
        self.assertFalse(self.app.number_input)
        self.create.assert_not_called()

    def test_complete_smoke_generate_rubric_save_json_and_repeat_with_cache(self):
        active = self.start()
        self.assertEqual(self.create.call_count, 2)
        self.assertEqual(len(self.history()), 2)
        self.assertIn("Prompt v1 — Baseline", [item.value for item in self.app.subheader])
        self.assertIn("Prompt v2 — Otimizada", [item.value for item in self.app.subheader])
        self.assertEqual(len(self.app.columns[0].markdown) > 0, True)
        self.assertIn(VALID_CONTENT["diagnosis"]["conclusao"], self.displayed())
        self.assertEqual(len(self.app.number_input), 6)
        for version in comparison.VERSIONS:
            for label, _ in comparison.CRITERIA.values():
                self.assertIn(f"Nota de {label} ({version})", [item.label for item in self.app.number_input])
                self.assertIn(f"Justificativa de {label} ({version})", [item.label for item in self.app.text_area])
        self.fill()
        self.app.button(key="save_comparison").click().run()
        self.assertFalse(self.app.exception)
        self.assertTrue(self.app.success)
        saved = self.app.session_state["saved_comparison"]
        path = Path(saved["comparison_path"])
        self.assertIn(str(path), [element.value for element in self.app.code])
        record = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(record["comparison_id"], active["comparison_id"])
        self.assertEqual(record["cenario"]["ticket"], TICKET)
        self.assertEqual(record["totais"], {"v1": 9, "v2": 11, "delta_v2_v1": 2})
        self.assertIn("Total v1: 9/15 · Total v2: 11/15", self.displayed())
        self.assertTrue(self.app.button(key="save_comparison").disabled)
        self.assertFalse(self.app.number_input)
        self.assertIn(manual_fixture()["v2"]["clarity"]["justification"], self.displayed())
        original_bytes = path.read_bytes()
        self.app.run()
        self.assertEqual(path.read_bytes(), original_bytes)
        self.assertEqual(len(list(path.parent.glob("*.json"))), 1)
        self.assertEqual(self.create.call_count, 2)
        second = self.start()
        self.assertNotEqual(active["comparison_id"], second["comparison_id"])
        self.assertTrue(all(result["cache_hit"] for result in second["resultados"].values()))
        self.assertEqual(len(self.history()), 4)
        self.assertEqual(self.create.call_count, 2)
        self.assertFalse(self.app.success)
        self.assertTrue(all(widget.value == "" for widget in self.app.text_area if "Justificativa" in widget.label))

    def test_editing_scores_justifications_and_reruns_never_regenerates(self):
        active = self.start()
        identifier = active["comparison_id"]
        self.app.number_input(key=f"{identifier}_v1_clarity_score").set_value(5).run()
        self.app.text_area(key=f"{identifier}_v2_customer_fit_justification").input("Comentário de teste").run()
        self.app.run()
        self.assertFalse(self.app.exception)
        self.assertEqual(self.app.session_state["comparison"], active)
        self.assertEqual(self.create.call_count, 2)
        self.assertEqual(len(self.history()), 2)

    def test_missing_or_whitespace_justifications_are_not_saved(self):
        self.start()
        self.app.button(key="save_comparison").click().run()
        self.assertIn("justificativa", self.app.error[0].value)
        self.assertFalse(self.app.success)
        self.fill()
        identifier = self.app.session_state["comparison"]["comparison_id"]
        self.app.text_area(key=f"{identifier}_v2_actionability_justification").input(" \n ")
        self.app.button(key="save_comparison").click().run()
        self.assertIn("justificativa", self.app.error[0].value)
        self.assertEqual(list((self.directory / "comparisons").glob("*.json")), [])
        self.assertEqual(self.create.call_count, 2)

    def test_each_scenario_edit_invalidates_old_results_and_evaluation(self):
        for field, value in (("comparison_profile", "bruno"), ("comparison_ticket", "Outro ticket"),
                             ("comparison_type", "flow")):
            with self.subTest(field=field):
                self.app.selectbox(key="comparison_profile").select("ana")
                self.start()
                self.fill()
                if field == "comparison_ticket":
                    self.app.text_area(key=field).input(value).run()
                else:
                    self.app.selectbox(key=field).select(value).run()
                self.assertFalse(self.app.exception)
                self.assertFalse(self.app.number_input)
                self.assertFalse([button for button in self.app.button if button.key == "save_comparison"])
                self.assertNotIn("comparison", self.app.session_state)
                self.assertEqual(list((self.directory / "comparisons").glob("*.json")), [])

    def test_generating_new_comparison_resets_rubric_and_saved_path(self):
        first = self.start()
        self.fill()
        self.app.button(key="save_comparison").click().run()
        path = self.app.session_state["saved_comparison"]["comparison_path"]
        self.app.selectbox(key="comparison_profile").select("diego").run()
        self.assertFalse(self.app.success)
        self.assertNotIn(path, [element.value for element in self.app.code])
        second = self.start()
        self.assertNotEqual(first["comparison_id"], second["comparison_id"])
        self.assertEqual(second["cliente"]["id"], "diego")
        self.assertTrue(all(widget.value == 3 for widget in self.app.number_input))
        self.assertTrue(Path(path).is_file())

    def test_first_or_second_generation_failure_cannot_be_evaluated_or_saved(self):
        # Falha da segunda geração ocorre depois de gravar o histórico da primeira.
        def respond(**kwargs):
            if "Versão do prompt: v2" in kwargs["instructions"]:
                raise AIError("segredo de teste")
            return self.respond(**kwargs)
        self.create.side_effect = respond
        self.app.text_area(key="comparison_ticket").input(TICKET)
        self.app.button(key="compare_prompts").click().run()
        self.assertFalse(self.app.exception)
        self.assertIn("Comparação incompleta", self.app.error[0].value)
        self.assertNotIn("segredo de teste", self.app.error[0].value)
        self.assertEqual(len(self.history()), 1)
        self.assertFalse(self.app.number_input)
        self.assertFalse(self.app.success)
        self.create.side_effect = self.respond
        self.start()
        with patch("vlab.service.run_generation", side_effect=StorageError("segredo")):
            self.app.button(key="compare_prompts").click().run()
        self.assertIn("Comparação incompleta", self.app.error[0].value)
        self.assertFalse(self.app.number_input)
        self.assertFalse(self.app.success)

    def test_write_failure_is_not_success_and_retry_does_not_generate_again(self):
        self.start()
        self.fill()
        with patch("vlab.storage.os.replace", side_effect=OSError("segredo")):
            self.app.button(key="save_comparison").click().run()
        self.assertFalse(self.app.exception)
        self.assertIn("Não foi possível salvar", self.app.error[0].value)
        self.assertFalse(self.app.success)
        self.assertFalse(self.app.button(key="save_comparison").disabled)
        self.assertEqual(list((self.directory / "comparisons").glob("*.json")), [])
        self.app.button(key="save_comparison").click().run()
        self.assertTrue(self.app.success)
        self.assertEqual(self.create.call_count, 2)

    def test_all_four_contents_render_in_both_columns(self):
        for content_type, content in VALID_CONTENT.items():
            with self.subTest(content_type=content_type):
                self.start(content_type=content_type)
                for value in test_app.AppTests.text_values(content):
                    self.assertEqual(self.displayed().count(value), 2)
        self.assertEqual(self.create.call_count, 8)

    def test_individual_result_and_comparison_coexist_without_overwriting(self):
        self.app.text_area(key="ticket").input("Ticket individual")
        self.app.button[0].click().run()
        individual = self.app.session_state["last_result"]
        self.start()
        self.fill()
        self.app.button(key="save_comparison").click().run()
        self.assertEqual(self.app.session_state["last_result"], individual)
        self.assertIn(individual["history_path"], [element.value for element in self.app.code])
        self.assertEqual(len(self.history()), 3)
