import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import httpx
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    OpenAIError,
    RateLimitError,
)

from vlab.ai import AIError, DEFAULT_MODEL, MAX_OUTPUT_TOKENS, generate_text


class AITests(unittest.TestCase):
    def setUp(self):
        # Chave fictícia; .env real e rede nunca são utilizados nestes testes.
        environment = patch.dict(os.environ, {"OPENAI_API_KEY": "chave-ficticia"}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        dotenv = patch("vlab.ai.load_dotenv")
        self.load_dotenv = dotenv.start()
        self.addCleanup(dotenv.stop)
        sdk = patch("vlab.ai.OpenAI")
        self.sdk = sdk.start()
        self.addCleanup(sdk.stop)
        self.client = self.sdk.return_value.__enter__.return_value
        self.client.responses.create.return_value = SimpleNamespace(
            status="completed", output_text="  Olá!  "
        )

    def test_returns_text_and_limits_single_request(self):
        self.assertEqual(generate_text("Olá"), "Olá!")
        self.sdk.assert_called_once_with(
            api_key="chave-ficticia", timeout=30.0, max_retries=0
        )
        self.client.responses.create.assert_called_once_with(
            model=DEFAULT_MODEL, input="Olá", max_output_tokens=MAX_OUTPUT_TOKENS, store=False
        )
        self.assertFalse(self.load_dotenv.call_args.kwargs["override"])

    def test_uses_configured_model(self):
        os.environ["OPENAI_MODEL"] = "modelo-configurado"
        generate_text("Olá")
        self.assertEqual(self.client.responses.create.call_args.kwargs["model"], "modelo-configurado")

    def test_empty_model_uses_default(self):
        os.environ["OPENAI_MODEL"] = "  "
        generate_text("Olá")
        self.assertEqual(self.client.responses.create.call_args.kwargs["model"], DEFAULT_MODEL)

    def test_missing_or_blank_api_key_stops_before_client(self):
        for key in (None, "", "  "):
            with self.subTest(key=key):
                os.environ.pop("OPENAI_API_KEY", None)
                if key is not None:
                    os.environ["OPENAI_API_KEY"] = key
                with self.assertRaisesRegex(AIError, "Configure OPENAI_API_KEY"):
                    generate_text("Olá")
        self.sdk.assert_not_called()

    def test_loads_dotenv_and_preserves_environment_precedence(self):
        from dotenv import load_dotenv

        self.load_dotenv.side_effect = load_dotenv
        with TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text(
                "OPENAI_API_KEY=chave-do-arquivo\nOPENAI_MODEL=modelo-do-arquivo\n",
                encoding="utf-8",
            )
            os.environ.pop("OPENAI_API_KEY")
            with patch("vlab.ai.ENV_FILE", env_file):
                generate_text("Olá")
                self.assertEqual(self.sdk.call_args.kwargs["api_key"], "chave-do-arquivo")
                self.assertEqual(self.client.responses.create.call_args.kwargs["model"], "modelo-do-arquivo")
                os.environ["OPENAI_API_KEY"] = "chave-do-ambiente"
                os.environ["OPENAI_MODEL"] = "modelo-do-ambiente"
                generate_text("Olá")
                self.assertEqual(self.sdk.call_args.kwargs["api_key"], "chave-do-ambiente")
                self.assertEqual(self.client.responses.create.call_args.kwargs["model"], "modelo-do-ambiente")

    def test_rejects_invalid_input_without_client(self):
        for value in ("", "  ", None, 123):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    generate_text(value)
        self.sdk.assert_not_called()

    def test_rejects_empty_or_incomplete_response(self):
        for status, output in (("completed", "  "), ("incomplete", "Texto parcial")):
            with self.subTest(status=status):
                self.client.responses.create.return_value = SimpleNamespace(
                    status=status, output_text=output
                )
                with self.assertRaises(AIError):
                    generate_text("Olá")

    def test_sdk_errors_have_safe_messages(self):
        request = httpx.Request("POST", "https://api.openai.com/v1/responses")
        errors = (
            (AuthenticationError("dado-sensivel", response=httpx.Response(401, request=request), body=None), "Autenticação"),
            (RateLimitError("dado-sensivel", response=httpx.Response(429, request=request), body=None), "Limite ou saldo"),
            (APIConnectionError(message="dado-sensivel", request=request), "conexão"),
            (APITimeoutError(request=request), "tempo esgotado"),
            (APIStatusError("dado-sensivel", response=httpx.Response(400, request=request), body=None), "HTTP 400"),
            (APIStatusError("dado-sensivel", response=httpx.Response(403, request=request), body=None), "HTTP 403"),
            (APIStatusError("dado-sensivel", response=httpx.Response(404, request=request), body=None), "HTTP 404"),
            (APIStatusError("dado-sensivel", response=httpx.Response(500, request=request), body=None), "indisponível"),
            (OpenAIError("dado-sensivel"), "Não foi possível"),
        )
        for error, expected in errors:
            with self.subTest(error=type(error).__name__):
                self.client.responses.create.side_effect = error
                with self.assertRaisesRegex(AIError, expected) as caught:
                    generate_text("Olá")
                self.assertNotIn("dado-sensivel", str(caught.exception))
                self.assertNotIn("chave-ficticia", str(caught.exception))
                self.assertTrue(caught.exception.__suppress_context__)


if __name__ == "__main__":
    unittest.main()
