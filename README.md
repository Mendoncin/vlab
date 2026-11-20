# Vlab — BK-001

Base Python para carregar perfis de clientes e enviar texto à OpenAI.
Os quatro perfis definitivos estão em `profiles/`: Ana (`ana`), Bruno (`bruno`),
Carla (`carla`) e Diego (`diego`). As combinações aprovadas estão descritas em
[profiles/README.md](profiles/README.md). A fixture em `tests/fixtures/` continua
restrita aos testes.

## Instalação

Requer Python 3.10 ou superior (validado com Python 3.12).
Na raiz do repositório:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

No Windows/PowerShell, crie com `py -m venv .venv` e ative com
`.venv\Scripts\Activate.ps1`. No Ubuntu/WSL, se faltar `ensurepip`,
instale o pacote `python3-venv` antes de criar o ambiente.

Se ainda não existir `.env`, copie `.env.example` para `.env` e preencha
`OPENAI_API_KEY` localmente. Preserve um `.env` já configurado.
`OPENAI_MODEL` é opcional: o padrão é `gpt-4o-mini`.
Variáveis já exportadas no ambiente têm prioridade sobre o arquivo `.env`.
O caminho do `.env` é sempre relativo à raiz deste projeto.

## Execução e testes

Com o ambiente ativado e na raiz do repositório:

```bash
# Testes automatizados: não acessam a API nem precisam de chave real.
python -m unittest discover -v

# Teste integrado REAL: uma chamada paga com o perfil definitivo Ana.
python -m vlab.smoke --perfil ana

# Alternativa de teste com fixture não definitiva (também faz chamada real).
python -m vlab.smoke --fixture
```

O smoke test carrega e valida um JSON, inclui todos os seus dados e um problema
simples de conexão Wi-Fi na mensagem e verifica se a resposta real foi concluída
e contém texto. Retorna código 1
em caso de falha. Execute-o somente quando quiser validar a integração externa;
ele não faz parte da descoberta de testes. Há timeout de 30 segundos, limite
de 120 tokens de saída e nenhuma retentativa automática. O modelo configurado
deve aceitar a Responses API e esses parâmetros.

## Organização e uso

- `vlab/profiles.py`: `load_profile(id)` retorna um dicionário validado;
  `ProfileError` informa arquivo ausente, JSON inválido ou campos incorretos.
- `vlab/ai.py`: `generate_text(texto)` lê a configuração, valida a chave,
  usa o SDK oficial e retorna texto; falhas externas geram `AIError` sem
  reproduzir o erro bruto da API.
- `vlab/smoke.py`: demonstra o fluxo completo com um perfil, sem motor de prompts.
- `profiles/`: destino dos quatro JSONs definitivos e descrição do formato.
- `tests/`: testes com `unittest` e fixture explicitamente não definitiva.

A integração utiliza `client.responses.create(...)` e `response.output_text`,
conforme o [SDK oficial](https://github.com/openai/openai-python).
O [modelo padrão](https://developers.openai.com/api/docs/models/gpt-4o-mini)
foi escolhido pelo custo reduzido e suporte à Responses API.
Não há histórico, persistência de resultados, interface ou estratégias v1/v2.
O BK-002 poderá montar mensagens com os perfis e reutilizar `generate_text`.

`.env`, ambientes virtuais e caches Python permanecem ignorados pelo Git.
Nunca inclua chaves nos JSONs, testes ou mensagens enviadas ao modelo.
