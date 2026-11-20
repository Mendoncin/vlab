"""Uma entrada textual, uma chamada à OpenAI, uma resposta textual."""

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import (
    APIConnectionError,
    APIStatusError,
    AuthenticationError,
    OpenAI,
    OpenAIError,
    RateLimitError,
)


ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
DEFAULT_MODEL = "gpt-4o-mini"
MAX_OUTPUT_TOKENS = 120


class AIError(RuntimeError):
    """Falha de configuração, comunicação ou resposta da IA."""


def generate_text(text: str) -> str:
    """Gera texto com saída limitada e sem tentativas automáticas adicionais."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("A entrada deve ser um texto não vazio.")

    load_dotenv(ENV_FILE, override=False)
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise AIError("Configure OPENAI_API_KEY no .env ou no ambiente.")
    model = os.getenv("OPENAI_MODEL", "").strip() or DEFAULT_MODEL

    try:
        with OpenAI(api_key=api_key, timeout=30.0, max_retries=0) as client:
            response = client.responses.create(
                model=model,
                input=text,
                max_output_tokens=MAX_OUTPUT_TOKENS,
                store=False,
            )
    except AuthenticationError:
        raise AIError("Autenticação recusada. Verifique a chave da OpenAI.") from None
    except RateLimitError:
        raise AIError("Limite ou saldo da conta atingido. Verifique a conta OpenAI.") from None
    except APIConnectionError:
        raise AIError("Falha de conexão ou tempo esgotado ao acessar a OpenAI.") from None
    except APIStatusError as error:
        if error.status_code == 400:
            raise AIError(
                "A OpenAI rejeitou os parâmetros da solicitação (HTTP 400). "
                "Verifique o modelo e o suporte à Responses API."
            ) from None
        if error.status_code == 403:
            raise AIError(
                "Acesso negado pela OpenAI (HTTP 403). "
                "Verifique as permissões da conta, do projeto e da chave."
            ) from None
        if error.status_code == 404:
            raise AIError(
                "Modelo ou recurso não encontrado na OpenAI (HTTP 404). "
                "Verifique OPENAI_MODEL e o acesso da conta ao modelo."
            ) from None
        raise AIError(
            f"A OpenAI recusou a solicitação ou está indisponível (HTTP {error.status_code}). "
            "Verifique o modelo configurado e o acesso da conta."
        ) from None
    except OpenAIError:
        raise AIError("Não foi possível concluir a solicitação à OpenAI.") from None

    if response.status != "completed":
        raise AIError("A OpenAI não concluiu a resposta; verifique o limite de saída e o modelo.")
    output = response.output_text.strip()
    if not output:
        raise AIError("A OpenAI retornou uma resposta sem texto.")
    return output
