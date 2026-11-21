# Exemplos JSON

Os quatro arquivos de conteúdo representam **somente o objeto `conteudo`**
retornado pelo motor e armazenado no histórico, sem o envelope de metadados.
Não são históricos completos. Respeitam os contratos de `CONTENT_STRATEGIES` e
podem ser verificados com `vlab.prompt_engine.validate_response`.

| Arquivo | Origem |
|---|---|
| [diagnosis.json](diagnosis.json) | Saída real de `gpt-4o-mini`, v2, extraída da comparação de diagnóstico abaixo. |
| [resolution.json](resolution.json) | Saída real de `gpt-4o-mini`, v1, extraída da comparação de resolução abaixo. |
| [questions.json](questions.json) | **Sintético e ilustrativo**, elaborado sem chamada à API para o cenário Ana + Wi-Fi. |
| [flow.json](flow.json) | **Sintético e ilustrativo**, elaborado sem chamada à API para o mesmo cenário. |

Nos exemplos reais, o perfil é Ana (`leigo`, `didático`, `chat`) e o ticket é
"Meu notebook não consegue se conectar ao Wi-Fi". Os exemplos ilustrativos
mostram o formato, sem representar uma execução nem avaliação experimental.
Não foram acrescentados campos de identificação ao JSON: a origem está nesta
legenda para preservar o contrato.

## Comparações reais avaliadas

| Arquivo | Registro local de origem | v1 | v2 | Delta v2 − v1 |
|---|---|---:|---:|---:|
| [comparison-diagnosis-evaluated.json](comparison-diagnosis-evaluated.json) | `1b25ef69198a45058bec801483d6dbcd.json` | 10 | 10 | 0 |
| [comparison-resolution-evaluated.json](comparison-resolution-evaluated.json) | `cb04a42cc7f2427799d25b33267ec6ae.json` | 12 | 11 | −1 |

Os originais foram encontrados em
`.vlab/bk005-real-smoke-data/comparisons/`, com notas e justificativas humanas já
preenchidas. Não são a fixture fictícia de `bk005-mock-smoke-data`, nem o snapshot
antigo `comparison-awaiting-manual-review.json`. Nenhuma nota ou justificativa foi
atribuída ou alterada nesta task; a identidade do avaliador não consta do contrato.

Foram conferidos `validate_comparison`, `validate_rubric`, os totais/deltas e a
correspondência de cada execução ao JSON original em `history/`. O prompt
armazenado também foi comparado ao produzido por `build_prompt` para o cenário e
a versão correspondentes. As configurações são equivalentes entre versões.

As cópias preservam respostas, instruções, configurações, IDs, timestamps,
indicadores de cache, notas e justificativas. A única sanitização de valores foi
trocar os quatro `history_path` absolutos por caminhos relativos à raiz do
repositório, removendo o diretório pessoal da máquina. Esses caminhos documentam
a origem; os históricos locais ignorados pelo Git não acompanham os samples.
O cache key permanece válido porque não inclui `history_path`.

No diagnóstico, ambos os resultados avaliados vieram do cache. Na resolução,
v1 veio do cache e v2 da API. As notas avaliam os textos registrados; não medem
latência nem novas gerações. O empate e a vantagem da v1 na resolução não
estabelecem superioridade geral de qualquer versão. Veja a análise e as limitações
em [PROMPT_ENGINEERING_NOTES.md](../PROMPT_ENGINEERING_NOTES.md).

## Validação local, sem API

Na raiz do projeto, com o ambiente virtual ativado:

```bash
python -c "import json; from pathlib import Path; from vlab.prompt_engine import validate_response; from vlab.comparison import validate_comparison, validate_rubric; [validate_response(Path('samples', t + '.json').read_text(encoding='utf-8'), t) for t in ('diagnosis', 'resolution', 'questions', 'flow')]; records = [json.loads(p.read_text(encoding='utf-8')) for p in Path('samples').glob('comparison-*-evaluated.json')]; [(validate_comparison(r), validate_rubric({v: x['avaliacao']['criteria'] for v, x in r['resultados'].items()})) for r in records]; print('6 exemplos validados')"
```
