import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from vlab.profiles import ALLOWED_VALUES, PROFILES_DIR, ProfileError, load_profile, validate_profile


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


class DefinitiveProfileTests(unittest.TestCase):
    def test_profiles_match_approved_definitions(self):
        approved = (
            ("ana", "Ana", "leigo", "didático", "chat"),
            ("bruno", "Bruno", "intermediário", "detalhado", "e-mail"),
            ("carla", "Carla", "avançado", "direto", "chat"),
            ("diego", "Diego", "leigo", "direto", "telefone"),
        )
        for identifier, name, level, style, channel in approved:
            with self.subTest(profile=identifier):
                self.assertEqual(load_profile(identifier), {
                    "id": identifier,
                    "nome": name,
                    "nivel_tecnico": level,
                    "estilo_comunicacao": style,
                    "canal": channel,
                })

    def test_exactly_four_files_with_unique_matching_ids(self):
        files = sorted(PROFILES_DIR.glob("*.json"))
        expected_ids = {"ana", "bruno", "carla", "diego"}
        self.assertEqual({path.stem for path in files}, expected_ids)
        loaded_ids = [load_profile(path.stem)["id"] for path in files]
        self.assertEqual(len(loaded_ids), 4)
        self.assertEqual(len(set(loaded_ids)), 4)
        self.assertEqual(loaded_ids, [path.stem for path in files])


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.profile = load_profile("perfil_teste", FIXTURES_DIR)

    def test_loads_test_fixture(self):
        self.assertEqual(self.profile["id"], "fixture_teste_nao_definitiva")
        self.assertEqual(self.profile["nivel_tecnico"], "leigo")

    def test_accepts_all_allowed_values(self):
        for field, values in ALLOWED_VALUES.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    profile = dict(self.profile, **{field: value})
                    self.assertEqual(validate_profile(profile)[field], value)

    def test_accepts_name_or_id(self):
        for field in ("nome", "id"):
            with self.subTest(removed=field):
                profile = self.profile.copy()
                del profile[field]
                self.assertEqual(validate_profile(profile), profile)

    def test_rejects_missing_identity(self):
        profile = {k: v for k, v in self.profile.items() if k not in ("nome", "id")}
        with self.assertRaisesRegex(ProfileError, "nome ou id"):
            validate_profile(profile)

    def test_rejects_invalid_identity(self):
        for field in ("nome", "id"):
            for value in (None, 1, "", "  ", []):
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ProfileError):
                        validate_profile(dict(self.profile, **{field: value}))

    def test_rejects_missing_required_fields(self):
        for field in ALLOWED_VALUES:
            with self.subTest(field=field):
                profile = self.profile.copy()
                del profile[field]
                with self.assertRaisesRegex(ProfileError, "obrigatório ausente"):
                    validate_profile(profile)

    def test_rejects_invalid_values_and_types(self):
        for field in ALLOWED_VALUES:
            for value in ("inválido", "", None, 1, [], {}, True):
                with self.subTest(field=field, value=value):
                    with self.assertRaisesRegex(ProfileError, "Valor inválido"):
                        validate_profile(dict(self.profile, **{field: value}))

    def test_rejects_non_object_json(self):
        for value in ([], None, 1, "texto"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ProfileError, "objeto JSON"):
                    validate_profile(value)

    def test_file_errors(self):
        with TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ProfileError, "não encontrado"):
                load_profile("ausente", directory)
            path = Path(directory) / "invalido.json"
            for content in (b'{"nome":', b'\xff'):
                path.write_bytes(content)
                with self.assertRaisesRegex(ProfileError, "JSON UTF-8 válido"):
                    load_profile("invalido", directory)
            path.write_text(json.dumps({"nome": "Sem atributos"}), encoding="utf-8")
            with self.assertRaisesRegex(ProfileError, "obrigatório ausente"):
                load_profile("invalido", directory)

    def test_rejects_paths_in_identifier(self):
        for identifier in ("../perfil_teste", "a/b", "a\\b", "", ".", "..", None):
            with self.subTest(identifier=identifier):
                with self.assertRaisesRegex(ProfileError, "Identificador inválido"):
                    load_profile(identifier, FIXTURES_DIR)


if __name__ == "__main__":
    unittest.main()
