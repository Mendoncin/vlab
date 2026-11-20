# Vlab — BK-001, BK-002, BK-003 e BK-004

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
- `vlab/service.py`: fluxo compartilhado de geração, cache e histórico.
- `vlab/storage.py`: leitura e escrita atômica de JSON local.
- `vlab/cli.py`: argumentos e apresentação do resultado do serviço.
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

## CLI, histórico e cache — BK-003

Com o ambiente ativado, execute na raiz do projeto (uma chamada real em cache miss):

```bash
python -m vlab.cli --perfil ana --ticket "Meu notebook não consegue se conectar ao Wi-Fi" --tipo diagnosis --versao v2
```

Argumentos: `--perfil` (obrigatório: `ana`, `bruno`, `carla`, `diego`), `--ticket`
(texto obrigatório), `--tipo` (`diagnosis`, `resolution`, `questions`, `flow`;
padrão `diagnosis`), `--versao` (`v1`, `v2`; padrão `v2`) e `--storage-dir`
(opcional). Consulte também `python -m vlab.cli --help`.
A saída é JSON com conteúdo estruturado, `cache_hit`, `origem`, `cache_key`,
timestamp UTC, metadados e `history_path`, o caminho do registro salvo.
Códigos de saída: 0 em sucesso, 1 em falha de entrada/geração/persistência,
2 em argumentos ausentes ou inválidos no argparse.

O padrão é `.vlab/` na raiz do projeto, independentemente do diretório corrente:

- `cache/<sha256>.json`: conteúdo validado reutilizável.
- `history/<execution_id>.json`: um registro independente por atendimento bem-sucedido,
  inclusive cache hits; o identificador usa UUID para evitar sobrescritas.

O diretório pode ser alterado por `VLAB_STORAGE_DIR` (ambiente ou `.env`) ou por
`--storage-dir /caminho/dados` (tem prioridade). Caminhos relativos personalizados
são relativos ao diretório corrente. O serviço também aceita `storage_dir`:

```python
from vlab.profiles import load_profile
from vlab.service import run_generation

resultado = run_generation(
    load_profile("ana"), "Wi-Fi não conecta", "diagnosis", "v2",
    storage_dir=".vlab",
)
```

O serviço reutiliza o motor BK-002. Monta o prompt uma vez, obtém um snapshot
da configuração efetiva e usa ambos na chave e na chamada. Os parâmetros
opcionais `prepared_prompt` e `generation_config` integram esse snapshot ao motor;
as chamadas existentes de quatro argumentos e seu retorno permanecem compatíveis.
O SHA-256 considera JSON canônico (chaves ordenadas), perfil completo, ticket
original, tipo, versão, prompt efetivo (instruções, contexto e schema), provedor,
modelo e parâmetros enviados, incluindo formato estrito e limite de saída.
Credenciais do ambiente não entram na chave ou nos arquivos.

Para verificar o cache, repita exatamente o comando: o primeiro atendimento
mostra `cache_hit: false`; o segundo, `true`, sem chamar a OpenAI, com outro
`history_path` e novo timestamp. Alterar ticket, perfil, tipo, versão, instruções,
schema, modelo ou parâmetros relevantes gera outra chave.
Os registros podem ser consultados abrindo os JSONs de `history/` e relacionados
por `cache_key`; `schema_version: 1` permite evolução futura do formato.

Somente respostas válidas são cacheadas. Cache inválido/corrompido provoca nova
geração e passa novamente pela validação do motor. Falhas de API ou validação
não criam cache nem histórico de sucesso; podem ser tentadas novamente.
Erros de I/O são reportados como `StorageError`, sem indicar persistência concluída.
Se o cache for gravado e o histórico falhar, a execução falha; uma nova tentativa
pode usar o cache válido e registrar seu próprio atendimento.
As gravações usam temporário no mesmo diretório, flush/fsync e substituição
atômica. `.vlab/` é ignorado pelo Git; as subpastas geradas também recebem
`.gitignore` para proteger dados em diretórios personalizados.

O armazenamento local não tem TTL, limpeza automática nem coordenação entre
processos: chamadas simultâneas ainda podem gerar respostas equivalentes.
O diretório configurável permitirá usar um volume persistente no futuro;
nenhum armazenamento remoto ou deploy foi adicionado.

```bash
# Suíte completa BK-001/BK-002/BK-003: mocks, sem rede e sem chave real.
python -m unittest discover -v

# Inclui cenário integrado CLI: miss → hit → mudança de versão → miss.
python -m unittest tests.test_service tests.test_cli -v
```

Os testes usam diretórios temporários e contadores do SDK simulado para verificar
cache, histórico, invalidações, recuperação de corrupção, falhas e códigos da CLI.

## Interface web — BK-004

O `requirements.txt` inclui Streamlit 1.65, compatível com Python 3.10 ou superior.
Com o ambiente virtual ativado, instale
as dependências e execute a página única na raiz do projeto:

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

Abra o endereço local informado pelo Streamlit (normalmente
`http://localhost:8501`). Selecione Ana, Bruno, Carla ou Diego, informe o ticket,
escolha um dos quatro conteúdos e a versão v1 ou v2, e clique em **Gerar resposta**.
Os nomes e atributos dos perfis são carregados dos JSONs existentes.

O formulário `st.form` envia as escolhas em conjunto; somente a submissão chama
`vlab.service.run_generation`, o mesmo serviço da CLI BK-003. Ele reutiliza o motor
BK-002, a configuração OpenAI e o `.env` do BK-001. Há indicador de carregamento
e mensagens de erro sem credenciais ou stack traces. A última resposta fica em
`st.session_state`, para que rerenderizações não disparem outra geração.

A resposta estruturada aparece em seções de diagnóstico, passos de resolução,
perguntas por prioridade ou decisões de fluxo, conforme o contrato do motor.
Abaixo são exibidos cliente, tipo, versão, modelo, origem API/cache e o caminho
do JSON correspondente à execução. Cache e histórico são integralmente os do
BK-003, em `.vlab/` ou `VLAB_STORAGE_DIR`. Repetir exatamente a solicitação pode
reutilizar o cache sem chamar a API, mas sempre cria outro registro de histórico.

```bash
# Suíte completa, incluindo interface; sem chamadas reais à OpenAI.
python -m unittest discover -v

# Controles, submissão, apresentação, falhas e integração cache/histórico da UI.
python -m unittest tests.test_app -v
```

Os testes da interface usam `streamlit.testing.v1.AppTest`, os perfis reais,
armazenamento temporário e mocks do SDK. O cenário Ana +
"Meu notebook não consegue se conectar ao Wi-Fi" + diagnóstico/v2 comprova
miss → hit, uma única chamada ao SDK e dois históricos distintos. Também
verificam que rerenderizações preservam o resultado sem gerar outra execução.

Para demonstrar no navegador, execute o servidor, preencha esse mesmo cenário
e submeta duas vezes. Com cache inicialmente vazio e chave válida, a primeira
execução usa a OpenAI e a segunda usa o cache; cada uma exibe seu próprio JSON.

Validação do BK-004 em Python 3.12: **94 testes aprovados**, incluindo 14 da
interface, e `pip check` sem conflitos. O servidor local e o formulário foram
exercitados em Chrome headless via automação do navegador, com apresentação
da resposta e do caminho do histórico. O cenário Ana + Wi-Fi + diagnóstico/v2
realizou uma chamada real à OpenAI (`gpt-4o-mini`), seguida de três repetições
atendidas pelo cache: um arquivo de cache e quatro históricos distintos, com
conteúdo idêntico. Não houve teste manual no navegador. Evidências locais,
ignoradas pelo Git: `.vlab/bk004-tests.log`, `.vlab/bk004-browser-smoke.log`,
`.vlab/bk004-browser-smoke.png` e `.vlab/bk004-browser-smoke-data/history/`.
