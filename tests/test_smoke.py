import io
import json
import unittest
from unittest.mock import patch

from vlab.ai import AIError
from vlab.profiles import load_profile
from vlab.smoke import FIXTURES_DIR, main


class SmokeTests(unittest.TestCase):
    def test_ana_context_and_technical_problem_reach_ai(self):
        with patch("sys.argv", ["smoke", "--perfil", "ana"]), patch(
            "vlab.smoke.generate_text", return_value="Ana, verifique se o Wi-Fi está ativado."
        ) as generate, patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(main(), 0)
            profile = load_profile("ana")
            self.assertIn(json.dumps(profile, ensure_ascii=False), generate.call_args.args[0])
            self.assertIn(
                "Meu notebook não consegue se conectar ao Wi-Fi",
                generate.call_args.args[0],
            )
            generate.assert_called_once()
            self.assertIn("Perfil definitivo carregado e validado", output.getvalue())

    def test_fixture_context_reaches_ai(self):
        with patch("sys.argv", ["smoke", "--fixture"]), patch(
            "vlab.smoke.generate_text", return_value="Olá, cliente de teste!"
        ) as generate, patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(main(), 0)
            profile = load_profile("perfil_teste", FIXTURES_DIR)
            self.assertIn(json.dumps(profile, ensure_ascii=False), generate.call_args.args[0])
            generate.assert_called_once()
            self.assertIn("não é um dos quatro clientes definitivos", output.getvalue())

    def test_api_failure_has_nonzero_exit_code(self):
        with patch("sys.argv", ["smoke", "--fixture"]), patch(
            "vlab.smoke.generate_text", side_effect=AIError("Falha de conexão.")
        ), patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(main(), 1)
            self.assertIn("Falha de conexão", output.getvalue())

    def test_missing_profile_does_not_call_ai(self):
        with patch("sys.argv", ["smoke", "--perfil", "ausente"]), patch(
            "vlab.smoke.generate_text"
        ) as generate, patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(main(), 1)
            generate.assert_not_called()

    def test_requires_explicit_profile_source(self):
        with patch("sys.argv", ["smoke"]), patch("sys.stderr", new_callable=io.StringIO):
            with self.assertRaises(SystemExit) as caught:
                main()
            self.assertEqual(caught.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
