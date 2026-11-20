# Vlab — BK-001 e BK-002

Base Python para carregar perfis de clientes e gerar conteúdos de suporte com a OpenAI.
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

# Smoke test REAL do motor BK-002: Ana, Wi-Fi, diagnosis/v2; uma chamada paga.
python -m vlab.smoke_engine

# Opcional: exercitar outro contrato/versão (uma chamada paga por execução).
python -m vlab.smoke_engine --perfil diego --tipo flow --versao v1

# Alternativa de teste com fixture não definitiva (também faz chamada real).
python -m vlab.smoke --fixture
```

O smoke test do BK-001 carrega e valida um JSON, inclui todos os seus dados e um problema
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
- `vlab/prompt_engine.py`: montagem de prompts, estratégias e validação do BK-002.
- `vlab/smoke_engine.py`: smoke test real do motor com validação e metadados.
- `profiles/`: destino dos quatro JSONs definitivos e descrição do formato.
- `tests/`: testes com `unittest` e fixture explicitamente não definitiva.

A integração utiliza `client.responses.create(...)` e `response.output_text`,
conforme o [SDK oficial](https://github.com/openai/openai-python).
O [modelo padrão](https://developers.openai.com/api/docs/models/gpt-4o-mini)
foi escolhido pelo custo reduzido e suporte à Responses API.
O motor reutiliza configuração, cliente e tratamento de erros do BK-001.

## Motor de prompts — BK-002

```python
from vlab.profiles import load_profile
from vlab.prompt_engine import build_prompt, generate_content

perfil = load_profile("ana")
ticket = "Meu notebook não consegue se conectar ao Wi-Fi"
prompt = build_prompt(perfil, ticket, "diagnosis", "v2")  # Inspeção local, sem API.
resultado = generate_content(perfil, ticket, "diagnosis", "v2")  # Uma chamada real.
```

As duas funções recebem um perfil JSON já convertido em `dict`, ticket não vazio,
tipo (`diagnosis`, `resolution`, `questions` ou `flow`) e versão (`v1` ou `v2`).
`build_prompt` retorna `instructions`, `input` e `schema`: os dados são separados
das instruções e tratados como contexto não confiável. A persona delimita o papel
de suporte, proíbe inventar fatos e não solicita raciocínio interno detalhado.

- **v1:** orientações simples, perfil, problema, objetivo e formato obrigatório.
- **v2:** adapta explicitamente linguagem e profundidade ao nível técnico, estilo
  e canal; separa fatos de hipóteses, prioriza ações e solicita dados ausentes.

Para comparar, altere apenas a versão e preserve perfil, ticket e tipo, mantendo
`OPENAI_MODEL` e o ambiente iguais. Ambas usam o mesmo contrato, modelo configurado,
limite de 1600 tokens, timeout de 30 segundos, `store=False` e zero retentativas.
Não são enviados parâmetros de amostragem diferentes entre versões. A v2 torna
a metodologia mais explícita; não garante maior qualidade em todos os casos.

Cada tipo usa um contrato JSON próprio, compartilhado entre v1 e v2:

| Tipo | Campos de `conteudo` |
|---|---|
| `diagnosis` | `hipoteses: list[str]`, `evidencias: list[str]`, `informacoes_faltantes: list[str]`, `conclusao: str` |
| `resolution` | `passos: list[{ordem: int, instrucao: str}]`, `verificacao: str` |
| `questions` | `perguntas: list[{prioridade: int, pergunta: str}]` |
| `flow` | `decisoes: list[{ordem: int, condicao: str, se_sim: str, se_nao: str}]` |

`generate_content` retorna um `dict` serializável com `cliente` (id e/ou nome
disponíveis), `ticket` original, `tipo_conteudo`, `versao_prompt`, `provedor`,
`modelo` (identificador solicitado na chamada) e `conteudo` validado.
Não salva arquivos, IDs, timestamps, histórico ou cache.

A API recebe [Structured Outputs com JSON Schema estrito](https://developers.openai.com/api/docs/guides/structured-outputs).
O modelo configurado deve suportar esse recurso na Responses API.
A validação local usa a biblioteca padrão e verifica campos obrigatórios,
ausência de campos extras, tipos, textos não vazios, listas mínimas e numeração
consecutiva a partir de 1. Somente `evidencias` e `informacoes_faltantes` podem ser
listas vazias. A validação é estrutural: não comprova a veracidade das hipóteses
nem a qualidade do conteúdo.

Entradas inválidas geram `ValueError` (incluindo `ProfileError`); saída inválida
gera `ResponseValidationError`; falhas da API, saída sem texto ou incompleta
geram `AIError`. As mensagens não incluem o corpo bruto retornado pela API.
Não há correção automática de JSON nem novas tentativas.

`python -m unittest discover -v` executa os testes BK-001 e BK-002 com mocks do
SDK, sem rede ou chave real: matriz dos oito pares tipo/versão para Ana e o
mesmo ticket, geração com os quatro perfis, montagem, contratos e falhas.
`python -m vlab.smoke_engine` carrega o perfil definitivo, monta o prompt,
chama a OpenAI e só informa sucesso após a validação estrutural. Exibe metadados
e campos recebidos, sem persistir conteúdo; retorna código 1 em caso de falha.

Validação desta implementação: 47 testes automatizados aprovados (incluindo os
25 originais do BK-001). Quatro chamadas reais aprovadas com Ana, o mesmo ticket
de Wi-Fi e `gpt-4o-mini`: `diagnosis/v2`, `resolution/v2`, `questions/v2` e
`flow/v2`. A matriz completa v1/v2 e os outros perfis foram exercitados com mocks;
não foi realizada avaliação comparativa de qualidade.

`.env`, ambientes virtuais e caches Python permanecem ignorados pelo Git.
Nunca inclua chaves nos JSONs, testes ou mensagens enviadas ao modelo.
