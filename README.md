# Vlab — Assistente de suporte técnico

Vlab é uma aplicação Python com Streamlit desenvolvida para um desafio técnico de
Estágio em IA e Engenharia de Prompt. Transforma um ticket em conteúdo de suporte
com a OpenAI, considerando o nível técnico, o estilo de comunicação e o canal do
cliente. O experimento v1/v2 compara instruções simples com instruções mais
específicas de personalização e precisão, sem presumir qual versão será melhor.

## Funcionalidades

- Quatro perfis JSON: Ana, Bruno, Carla e Diego, descritos em [profiles/README.md](profiles/README.md).
- Diagnóstico, resolução, perguntas de esclarecimento e fluxo de atendimento.
- Prompts v1 (baseline) e v2 (otimizada), com contratos de saída compartilhados.
- Interface Streamlit e CLI sobre o mesmo serviço de geração.
- Cache determinístico e histórico JSON por execução bem-sucedida.
- Comparação lado a lado com três critérios de avaliação manual, notas e justificativas.

## Aplicação pública

Publicada no Railway: [abrir Vlab](https://vlab-production-52dd11c2.up.railway.app).
O endereço foi validado pelo responsável pelo projeto; esta atualização de
documentação não inclui uma nova verificação pública.

## Instalação local

Utilize **Python 3.12**, conforme `.python-version`, e execute os comandos na raiz
do repositório. As dependências estão fixadas em `requirements.txt`.

Linux/WSL:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Windows/PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

No Ubuntu/WSL, se faltar `ensurepip`, instale o pacote de suporte a `venv` da
versão de Python utilizada. Se ainda não houver `.env`, copie o modelo:

```bash
# Linux/WSL
cp -n .env.example .env
```

```powershell
# Windows/PowerShell
if (!(Test-Path .env)) { Copy-Item .env.example .env }
```

Edite `.env` localmente, preservando um arquivo já configurado:

| Variável | Uso |
|---|---|
| `OPENAI_API_KEY` | Chave válida da OpenAI, necessária para novas gerações. |
| `OPENAI_MODEL` | Opcional; vazio utiliza `gpt-4o-mini`. O modelo deve aceitar Structured Outputs na Responses API. |
| `VLAB_STORAGE_DIR` | Opcional; vazio utiliza `.vlab/` na raiz do projeto. No Railway, `/data`. |

O `.env` é localizado pela raiz do projeto, independentemente do diretório
corrente. Variáveis já exportadas prevalecem sobre o arquivo. Não versione `.env`
nem coloque credenciais em tickets ou perfis.

## Execução

### Interface Streamlit

Com o ambiente virtual ativado:

```bash
python -m streamlit run app.py
```

Abra o endereço local informado pelo Streamlit (normalmente
`http://localhost:8501`). Selecione perfil, informe o ticket, escolha tipo e versão
e clique em **Gerar resposta**. A página apresenta o conteúdo, o modelo solicitado,
a origem API/cache e o caminho do histórico JSON. Rerenderizações mantêm o resultado
em sessão sem gerar novamente; uma nova submissão cria outra execução.

### CLI

```bash
python -m vlab.cli --perfil ana --ticket "Meu notebook não consegue se conectar ao Wi-Fi" --tipo diagnosis --versao v2
python -m vlab.cli --help
```

| Argumento | Valores |
|---|---|
| `--perfil` | Obrigatório: `ana`, `bruno`, `carla`, `diego`. |
| `--ticket` | Texto obrigatório e não vazio. |
| `--tipo` | `diagnosis` (padrão), `resolution`, `questions`, `flow`. |
| `--versao` | `v1` ou `v2` (padrão). |
| `--storage-dir` | Diretório opcional; prevalece sobre `VLAB_STORAGE_DIR`. |

A saída de sucesso é JSON com conteúdo e metadados, incluindo `history_path`.
Códigos de saída: 0 em sucesso, 1 em falha de entrada/geração/persistência e 2 em
erros de argumentos do `argparse`.

### Comparação v1/v2

Na interface, acesse **Comparação de prompts e rubrica**, selecione perfil, ticket
e tipo e clique em **Comparar v1 e v2**. O serviço fixa o mesmo cenário e snapshot
de modelo/configuração para as duas versões. Cada resultado informa se veio da
API ou do cache.

Avalie manualmente cada versão em **Clareza**, **Adequação ao nível do cliente** e
**Acionabilidade**: nota inteira de 1 a 5 e justificativa não vazia por critério.
Clique em **Salvar avaliação** para persistir o registro completo. A soma vai de
3 a 15 por versão; o delta é v2 menos v1. A avaliação não é feita por outro LLM.
Editar o cenário invalida a comparação em sessão; editar a rubrica não regenera
respostas. Após salvar, a avaliação fica somente para leitura nessa sessão.

### Histórico e cache

O diretório padrão é `.vlab/` na raiz do projeto:

| Subpasta | Conteúdo |
|---|---|
| `cache/<sha256>.json` | Conteúdo validado, chave e versão do schema. |
| `history/<execution_id>.json` | Um registro por geração bem-sucedida, inclusive cache hits. |
| `comparisons/<comparison_id>.json` | Cenário, respostas v1/v2, prompts, metadados, rubricas e totais salvos. |

Abra o JSON no caminho exibido pela interface ou CLI. O histórico contém
`schema_version`, ID, timestamp UTC, status, cliente, ticket original, tipo, versão,
provedor, modelo, configuração, conteúdo, origem, indicador/chave de cache e prompt
efetivo. `history_path` é acrescentado ao retorno do serviço; não ao próprio JSON
de histórico. Os resultados da comparação incluem esses caminhos.

`VLAB_STORAGE_DIR` altera a base; caminhos relativos personalizados são relativos
ao diretório corrente. Repita exatamente uma solicitação já cacheada para
reutilizar seu conteúdo sem nova chamada à API, mantendo outro ID e histórico.
O SHA-256 considera perfil completo, ticket original, tipo, versão, prompt efetivo,
schema, provedor e configuração do modelo. Ordenar chaves JSON não muda a
identidade; diferenças de espaços ou redação do ticket mudam.

Somente conteúdo validado entra no cache. Cache corrompido permite nova geração;
falhas de API/validação não criam histórico de sucesso. Erros de armazenamento
impedem confirmar sucesso; se o cache já foi escrito, uma tentativa posterior
pode reutilizá-lo. A escrita usa temporário e substituição atômica. Os diretórios
de dados são ignorados pelo Git; não são uma interface de consulta de histórico.

## Testes

```bash
python -m unittest discover -v
```

A suíte usa `unittest`, mocks do SDK, diretórios temporários e Streamlit `AppTest`.
Não exige chave real nem chamadas à OpenAI. Abrange integração simulada, perfis,
prompts, validação, cache, histórico, CLI, interface, comparação e falhas.

Os smoke tests externos abaixo são opcionais: cada comando faz uma chamada real,
pode gerar cobrança e exige chave/modelo válidos. Não integram a descoberta da
suíte nem persistem resultados:

```bash
python -m vlab.smoke --perfil ana
python -m vlab.smoke --fixture
python -m vlab.smoke_engine
python -m vlab.smoke_engine --perfil diego --tipo flow --versao v1
```

O primeiro módulo verifica transporte de texto; o segundo exercita o motor e a
validação estruturada. A fixture não representa um dos quatro clientes definitivos.

## Arquitetura resumida

```text
Perfil + Ticket + Tipo + Versão
  → Motor de prompts → Cache / OpenAI → Validação
  → Histórico JSON → Interface / CLI
```

O serviço valida entradas e prepara prompt/configuração antes de consultar o
cache; tanto conteúdo cacheado quanto conteúdo novo passam por validação.

| Componente | Responsabilidade |
|---|---|
| `vlab/profiles.py` e `profiles/` | Carregar e validar os quatro perfis. |
| `vlab/prompt_engine.py` | Montar instruções/contexto/schema e validar os quatro contratos. |
| `vlab/ai.py` | Configuração, Responses API com Structured Outputs e tratamento de falhas externas. |
| `vlab/service.py` | Coordenar geração, chave de cache e histórico. |
| `vlab/storage.py` | Leitura e escrita atômica dos JSONs locais. |
| `vlab/comparison.py` | Executar cenário controlado, validar rubrica e persistir comparação. |
| `app.py` / `vlab/cli.py` | Interação web / terminal usando o serviço compartilhado. |

## Deploy Railway

A aplicação publicada utiliza **Railpack**, Python **3.12** definido em
`.python-version` e as dependências de `requirements.txt`. O comando atual de
`deploy.startCommand` em `railpack.json` é:

```sh
python -m streamlit run app.py --server.address 0.0.0.0 --server.port ${PORT:-8501} --server.headless true
```

Na configuração publicada, a porta de destino no Railway é **8080**; o ambiente
deve fornecer **`PORT=8080`**, para o Streamlit escutar na mesma porta.
`${PORT:-8501}` usa o valor de `PORT`; 8501 é apenas o fallback quando a variável
está ausente ou vazia. O endereço `0.0.0.0` permite receber conexões do contêiner.
O comando de inicialização permanece o definido no arquivo, sem sobrescrita.

As variáveis da aplicação são `OPENAI_API_KEY`, `OPENAI_MODEL` (opcional) e
**`VLAB_STORAGE_DIR=/data`**. O serviço utiliza um **volume persistente montado em
`/data`**, onde grava `cache/`, `history/` e `comparisons/`. Definir a variável não
cria o volume: ele precisa estar anexado com esse ponto de montagem. Arquivos
fora do volume podem se perder ao substituir o contêiner. Não envie `.env` ao
repositório; configure a chave no ambiente Railway.

Esta documentação descreve a configuração fornecida pelo responsável e os
arquivos locais; não executa deploy, inspeção remota ou teste de persistência
após redeploy.

## Exemplos e engenharia de prompt

- [samples/README.md](samples/README.md): quatro contratos de conteúdo e duas
  comparações reais avaliadas, com origem e sanitização documentadas.
- [PROMPT_ENGINEERING_NOTES.md](PROMPT_ENGINEERING_NOTES.md): construção dos
  prompts, personalização, Structured Outputs, rubrica e resultados observados.

## Limitações

A geração depende da disponibilidade/acesso à API externa. Respostas podem variar
mesmo com configurações equivalentes; validação estrutural não comprova correção
técnica. A rubrica depende do julgamento humano e poucos cenários não demonstram
superioridade geral de uma versão. O cache compara entradas exatas, sem reconhecer
equivalência semântica; não há TTL, limpeza automática ou coordenação entre
processos para evitar gerações simultâneas da mesma entrada.
