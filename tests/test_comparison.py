"""BK-005: contratos reais do serviço com SDK simulado e persistência temporária."""

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from tests.test_prompt_engine import TICKET, VALID_CONTENT
from tests.test_service import MockGenerationCase
from vlab import comparison
from vlab.ai import AIError, get_generation_config
from vlab.storage import StorageError


def manual_fixture():
    """Notas fictícias para testes determinísticos; não avaliam saídas reais."""
    return {
        version: {
            criterion: {"score": score, "justification": f"Justificativa fictícia: {version}/{criterion}."}
            for criterion, score in zip(comparison.CRITERIA, scores)
        }
        for version, scores in (("v1", (1, 3, 5)), ("v2", (4, 2, 5)))
    }


class RubricTests(unittest.TestCase):
    def test_six_valid_scores_are_bound_to_version_and_totals_are_calculated(self):
        fixture = manual_fixture()
        evaluated = comparison.validate_rubric(fixture)
        self.assertEqual(evaluated["v1"]["total"], 9)
        self.assertEqual(evaluated["v2"]["total"], 11)
        for version in comparison.VERSIONS:
            self.assertEqual(evaluated[version]["criteria"], fixture[version])

    def test_all_six_scores_reject_out_of_range_noninteger_and_boolean_values(self):
        for version in comparison.VERSIONS:
            for criterion in comparison.CRITERIA:
                for score in (0, -1, 6, 1.5, 3.0, "3", None, True, False):
                    with self.subTest(version=version, criterion=criterion, score=score):
                        fixture = manual_fixture()
                        fixture[version][criterion]["score"] = score
                        with self.assertRaises(ValueError):
                            comparison.validate_rubric(fixture)

    def test_every_justification_is_required_and_cannot_be_blank(self):
        for version in comparison.VERSIONS:
            for criterion in comparison.CRITERIA:
                for justification in (None, "", " \n\t", 3):
                    with self.subTest(version=version, criterion=criterion, value=justification):
                        fixture = manual_fixture()
                        fixture[version][criterion]["justification"] = justification
                        with self.assertRaises(ValueError):
                            comparison.validate_rubric(fixture)
                fixture = manual_fixture()
                del fixture[version][criterion]["justification"]
                with self.assertRaises(ValueError):
                    comparison.validate_rubric(fixture)

    def test_both_versions_and_exact_three_criteria_are_required(self):
        for version in comparison.VERSIONS:
            fixture = manual_fixture()
            del fixture[version]
            with self.assertRaises(ValueError):
                comparison.validate_rubric(fixture)
            for criterion in comparison.CRITERIA:
                fixture = manual_fixture()
                del fixture[version][criterion]
                with self.assertRaises(ValueError):
                    comparison.validate_rubric(fixture)
        for fixture in (None, {}, {"v1": None, "v2": {}}, {**manual_fixture(), "v3": {}}):
            with self.assertRaises(ValueError):
                comparison.validate_rubric(fixture)

    def test_totals_cover_minimum_and_maximum_without_external_total(self):
        for score, total in ((1, 3), (5, 15)):
            fixture = manual_fixture()
            for criteria in fixture.values():
                for entry in criteria.values():
                    entry.update(score=score, total=999)
            evaluated = comparison.validate_rubric(fixture)
            self.assertEqual([evaluated[v]["total"] for v in comparison.VERSIONS], [total, total])


class ComparisonTests(MockGenerationCase):
    def compare(self, **overrides):
        options = {
            "profile": self.profile, "ticket": TICKET,
            "content_type": "diagnosis", "storage_dir": self.directory,
        }
        options.update(overrides)
        return comparison.run_comparison(**options)

    def test_same_complete_profile_original_ticket_type_config_only_instructions_change(self):
        profile = {**self.profile, "contexto_extra": {"preferencia": "passos curtos"}}
        original = deepcopy(profile)
        ticket = f"  {TICKET}\n"
        result = self.compare(profile=profile, ticket=ticket)
        first, second = [call.kwargs for call in self.create.call_args_list]
        self.assertEqual(json.loads(first["input"]), {"perfil": profile, "ticket": ticket})
        self.assertEqual(first["input"], second["input"])
        self.assertNotEqual(first["instructions"], second["instructions"])
        self.assertIn("Versão do prompt: v1", first["instructions"])
        self.assertIn("Versão do prompt: v2", second["instructions"])
        self.assertEqual(
            {k: v for k, v in first.items() if k != "instructions"},
            {k: v for k, v in second.items() if k != "instructions"},
        )
        self.assertEqual(profile, original)
        self.assertEqual(result["cenario"]["perfil"], original)
        profile["contexto_extra"]["preferencia"] = "alterado"
        self.assertEqual(result["cenario"]["perfil"], original)
        self.assertEqual(result["cenario"]["tipo_conteudo"], "diagnosis")

    def test_one_configuration_snapshot_even_if_environment_changes_between_calls(self):
        def respond(**kwargs):
            os.environ["OPENAI_MODEL"] = "outro-modelo"
            return self.respond(**kwargs)
        self.create.side_effect = respond
        with patch("vlab.ai.get_generation_config", wraps=get_generation_config) as get_config:
            result = self.compare()
        get_config.assert_called_once()
        self.assertEqual(result["resultados"]["v1"]["configuracao_modelo"],
                         result["resultados"]["v2"]["configuracao_modelo"])
        self.assertEqual([call.kwargs["model"] for call in self.create.call_args_list],
                         ["modelo-teste", "modelo-teste"])

    def test_distinct_contents_metadata_and_history_are_preserved_without_overwriting(self):
        def respond(**kwargs):
            response = self.respond(**kwargs)
            content = json.loads(response.output_text)
            content["conclusao"] = kwargs["instructions"].split("Versão do prompt: ")[1].split(".")[0]
            response.output_text = json.dumps(content)
            return response
        self.create.side_effect = respond
        result = self.compare()
        for version in comparison.VERSIONS:
            execution = result["resultados"][version]
            self.assertEqual(execution["conteudo"]["conclusao"], version)
            self.assertEqual(execution["versao_prompt"], version)
            self.assertEqual(json.loads(Path(execution["history_path"]).read_text())["execution_id"],
                             execution["execution_id"])
            self.assertIn("instructions", execution["prompt"])
        self.assertNotEqual(result["resultados"]["v1"]["execution_id"],
                            result["resultados"]["v2"]["execution_id"])

    def test_cache_is_independent_per_prompt_and_hits_still_write_two_new_histories(self):
        first = self.compare()
        original_history = {path: path.read_bytes() for path in self.history()}
        second = self.compare()
        self.assertNotEqual(first["comparison_id"], second["comparison_id"])
        self.assertEqual(len(self.history()), 4)
        self.assertEqual(len(list((self.directory / "cache").glob("*.json"))), 2)
        self.assertEqual(self.create.call_count, 2)
        self.assertNotEqual(first["resultados"]["v1"]["cache_key"], first["resultados"]["v2"]["cache_key"])
        for version in comparison.VERSIONS:
            self.assertFalse(first["resultados"][version]["cache_hit"])
            self.assertTrue(second["resultados"][version]["cache_hit"])
        for path, content in original_history.items():
            self.assertEqual(path.read_bytes(), content)

    def test_each_of_four_content_types_uses_existing_contract(self):
        for content_type, content in VALID_CONTENT.items():
            with self.subTest(content_type=content_type):
                result = self.compare(content_type=content_type)
                for execution in result["resultados"].values():
                    self.assertEqual(execution["conteudo"], content)
        self.assertEqual(self.create.call_count, 8)

    def test_failure_in_second_generation_preserves_first_execution_and_cache(self):
        self.create.side_effect = [self.respond(**{
            "text": {"format": {"schema": {"required": list(VALID_CONTENT["diagnosis"])}}},
        }), AIError("erro simulado")]
        with self.assertRaises(AIError):
            self.compare()
        self.assertEqual(len(self.history()), 1)
        self.assertEqual(len(list((self.directory / "cache").glob("*.json"))), 1)
        self.assertEqual(list((self.directory / "comparisons").glob("*.json")), [])
        self.create.side_effect = self.respond
        retry = self.compare()
        self.assertTrue(retry["resultados"]["v1"]["cache_hit"])
        self.assertFalse(retry["resultados"]["v2"]["cache_hit"])
        self.assertEqual(len(self.history()), 3)

    def test_complete_json_contains_scenario_effective_prompts_metadata_rubric_and_totals(self):
        active = self.compare()
        original = deepcopy(active)
        saved = comparison.save_comparison(active, manual_fixture(), storage_dir=self.directory)
        path = Path(saved["comparison_path"])
        self.assertEqual(path.parent, self.directory / "comparisons")
        self.assertEqual(path.stem, active["comparison_id"])
        raw = path.read_text(encoding="utf-8")
        record = json.loads(raw)
        self.assertEqual(record, {k: v for k, v in saved.items() if k != "comparison_path"})
        self.assertEqual(active, original)
        self.assertEqual(record["cenario"]["perfil"], self.profile)
        self.assertEqual(record["cenario"]["ticket"], TICKET)
        self.assertEqual(record["cenario"]["modelo"], "modelo-teste")
        self.assertEqual(record["cliente"], {"id": "ana", "nome": "Ana"})
        self.assertEqual(record["totais"], {"v1": 9, "v2": 11, "delta_v2_v1": 2})
        self.assertEqual(datetime.fromisoformat(record["timestamp_utc"]).tzinfo, timezone.utc)
        for version in comparison.VERSIONS:
            execution = record["resultados"][version]
            self.assertEqual(execution["avaliacao"]["criteria"], manual_fixture()[version])
            self.assertEqual(execution["avaliacao"]["total"], record["totais"][version])
            self.assertEqual(execution["configuracao_modelo"], record["cenario"]["configuracao_modelo"])
            self.assertEqual(execution["prompt"], active["resultados"][version]["prompt"])
            self.assertTrue(Path(execution["history_path"]).is_file())
        self.assertNotIn("chave-ficticia-secreta", raw)
        self.assertIn('\n  "schema_version"', raw)

    def test_new_comparisons_preserve_previous_files_and_environment_storage_is_respected(self):
        with patch.dict(os.environ, {"VLAB_STORAGE_DIR": str(self.directory)}):
            first = comparison.save_comparison(self.compare(), manual_fixture())
            previous = Path(first["comparison_path"]).read_bytes()
            second = comparison.save_comparison(self.compare(), manual_fixture())
        self.assertNotEqual(first["comparison_path"], second["comparison_path"])
        self.assertEqual(Path(first["comparison_path"]).read_bytes(), previous)
        self.assertEqual(len(list((self.directory / "comparisons").glob("*.json"))), 2)

    def test_invalid_evaluations_do_not_create_comparison_files(self):
        active = self.compare()
        with self.assertRaises(ValueError):
            comparison.save_comparison(active, {}, storage_dir=self.directory)
        self.assertEqual(list((self.directory / "comparisons").glob("*.json")), [])

    def test_incomplete_invalid_misbound_or_swapped_results_cannot_be_saved(self):
        active = self.compare()
        invalid = []
        missing = deepcopy(active)
        del missing["resultados"]["v2"]
        invalid.append(missing)
        for field, value in (
            ("conteudo", {}), ("ticket", "Outro problema"), ("versao_prompt", "v2"),
            ("modelo", "outro-modelo"), ("cache_key", "x"), ("status", "failed"),
            ("configuracao_modelo", {}),
        ):
            changed = deepcopy(active)
            changed["resultados"]["v1"][field] = value
            invalid.append(changed)
        changed = deepcopy(active)
        changed["cenario"]["perfil"]["canal"] = "telefone"
        invalid.append(changed)
        changed = deepcopy(active)
        changed["resultados"]["v1"], changed["resultados"]["v2"] = (
            changed["resultados"]["v2"], changed["resultados"]["v1"],
        )
        invalid.append(changed)
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    comparison.save_comparison(value, manual_fixture(), storage_dir=self.directory)
        self.assertEqual(list((self.directory / "comparisons").glob("*.json")), [])

    def test_atomic_persistence_failure_propagates_and_leaves_no_partial_file(self):
        active = self.compare()
        with patch("vlab.storage.os.replace", side_effect=OSError("erro simulado")):
            with self.assertRaises(StorageError):
                comparison.save_comparison(active, manual_fixture(), storage_dir=self.directory)
        self.assertEqual(list((self.directory / "comparisons").glob("*.json")), [])
        self.assertEqual(list(self.directory.rglob("*.tmp")), [])
        self.assertEqual(len(self.history()), 2)
        saved = comparison.save_comparison(active, manual_fixture(), storage_dir=self.directory)
        self.assertTrue(Path(saved["comparison_path"]).is_file())
