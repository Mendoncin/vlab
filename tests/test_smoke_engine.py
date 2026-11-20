import io
import unittest
from unittest.mock import patch

from vlab.ai import AIError
from vlab.prompt_engine import ResponseValidationError
from vlab.smoke_engine import TICKET, main


class EngineSmokeTests(unittest.TestCase):
    def test_default_smoke_loads_ana_and_checks_structured_result(self):
        result = {
            "cliente": {"id": "ana"}, "provedor": "openai", "modelo": "modelo-teste",
            "tipo_conteudo": "diagnosis", "versao_prompt": "v2", "conteudo": {"hipoteses": []},
        }
        with patch("sys.argv", ["smoke_engine"]), patch(
            "vlab.smoke_engine.generate_content", return_value=result
        ) as generate, patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(main(), 0)
            profile, ticket, content_type, version = generate.call_args.args
            self.assertEqual(profile["id"], "ana")
            self.assertEqual((ticket, content_type, version), (TICKET, "diagnosis", "v2"))
            self.assertIn("resposta real recebida e validada", output.getvalue())
            self.assertIn("modelo=modelo-teste", output.getvalue())
            generate.assert_called_once()

    def test_failure_returns_nonzero(self):
        for error in (AIError("Falha de conexão."), ResponseValidationError("JSON inválido.")):
            with self.subTest(error=type(error).__name__):
                with patch("sys.argv", ["smoke_engine"]), patch(
                    "vlab.smoke_engine.generate_content", side_effect=error
                ), patch("sys.stdout", new_callable=io.StringIO) as output:
                    self.assertEqual(main(), 1)
                    self.assertIn("Falha no smoke test BK-002", output.getvalue())


if __name__ == "__main__":
    unittest.main()
