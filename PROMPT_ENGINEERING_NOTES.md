# Notas de engenharia de prompt

## Construção dos prompts

`vlab.prompt_engine.build_prompt(perfil, ticket, tipo, versao)` valida a entrada e
retorna `instructions`, `input` e `schema`, que podem ser inspecionados sem chamar
a API. `generate_content` realiza a geração e a validação, sem persistir; o serviço
compartilhado adiciona cache e histórico.

A **persona** em `COMMON_INSTRUCTIONS` define um assistente de suporte técnico que
responde em português. O **context setting** fornece o perfil completo e o ticket
original como JSON em `input`, separados das instruções. As regras proíbem inventar
fatos/evidências, afirmar acesso a dispositivos ou seguir comandos inseridos no
perfil/ticket para substituir as instruções. Essa separação reduz ambiguidades,
mas não constitui garantia absoluta contra instruções maliciosas.

`CONTENT_STRATEGIES` adiciona o objetivo e o schema do tipo escolhido. As instruções
comuns de formato exigem somente JSON, sem Markdown ou campos extras, textos não
vazios e numeração consecutiva desde 1. Diagnóstico pede sínteses verificáveis,
sem raciocínio interno detalhado.

## Personalização e versões

As duas versões recebem o mesmo perfil e usam o mesmo contrato para um dado tipo.
A **v1**, baseline, pede que o modelo considere nível, estilo e canal, com resposta
simples e direta. A **v2**, chamada de otimizada na interface, explicita a separação
entre fatos, hipóteses e informações ausentes, a organização e a prioridade de
ações. Também acrescenta as instruções dos mapas abaixo, conforme o perfil:

| Campo | Valores e instruções acrescentadas na v2 |
|---|---|
| `nivel_tecnico` | `leigo`: linguagem cotidiana, termos explicados e uma ação por vez; `intermediário`: termos usuais e breve explicação de procedimentos menos comuns; `avançado`: precisão e profundidade sem conceitos básicos. |
| `estilo_comunicacao` | `didático`: progressão gradual e exemplos curtos; `detalhado`: detalhes relevantes e contexto suficiente; `direto`: concisão e prioridade da ação. |
| `canal` | `chat`: frases curtas; `e-mail`: frases completas e organização de leitura; `telefone`: orientações fáceis de falar/ouvir sem depender de recursos visuais. |

Essas regras vêm de `LEVEL_INSTRUCTIONS`, `STYLE_INSTRUCTIONS` e
`CHANNEL_INSTRUCTIONS`. Personalizam linguagem e apresentação; não autorizam
alterar fatos técnicos ou inventar contexto. A v1 também solicita adaptação ao
perfil, mas sem expandir esses mapas nas instruções.

A hipótese do experimento é que instruções mais específicas melhorem a resposta.
Isso precisa ser observado: mais instruções podem trazer redundância ou priorizar
uma ação menos adequada. A v1 pode superar a v2 em determinados cenários.

## Quatro estratégias de conteúdo

Todas compartilham construção, transporte e validação; o dispatch por configuração
seleciona objetivos e formatos distintos em `CONTENT_STRATEGIES`:

| Tipo | Finalidade | Campos de `conteudo` |
|---|---|---|
| `diagnosis` | Hipóteses, evidências do ticket, lacunas e conclusão provável ou impossibilidade de concluir. | `hipoteses: list[str]`, `evidencias: list[str]`, `informacoes_faltantes: list[str]`, `conclusao: str` |
| `resolution` | Passos ordenados aplicáveis ao cliente e verificação do resultado; prioriza ações reversíveis. | `passos: list[{ordem: int, instrucao: str}]`, `verificacao: str` |
| `questions` | Esclarecimentos prioritários que reduzam incertezas, sem repetir perguntas respondidas. | `perguntas: list[{prioridade: int, pergunta: str}]` |
| `flow` | Decisões ordenadas com condição verificável e próximos passos para cada alternativa. | `decisoes: list[{ordem: int, condicao: str, se_sim: str, se_nao: str}]` |

Somente `evidencias` e `informacoes_faltantes` permitem listas vazias. Os demais
arrays exigem pelo menos um item. Os objetos exigem todos os campos previstos e
rejeitam extras; textos devem ser não vazios e ordem/prioridade deve começar em 1,
sem lacunas. Exemplos estão em [samples/](samples/README.md).

## Structured Outputs e validação

`vlab.ai.generate_structured_text` usa `client.responses.create` com `instructions`
e `input` separados e `text.format` contendo `type="json_schema"`,
`name="support_content"`, o schema escolhido e `strict=True`. O modelo configurado
precisa oferecer suporte a Structured Outputs na Responses API.

Para conteúdo estruturado, a configuração envia `max_output_tokens=1600` e
`store=False`; o cliente usa timeout de 30 segundos e `max_retries=0`.
Não são enviados `temperature` ou `seed`. `modelo` registra o identificador
solicitado, não uma comprovação de revisão interna do modelo.

A geração pelo modelo e a aceitação pela aplicação são etapas distintas:

1. O transporte exige status `completed` e `output_text` não vazio; erros do SDK,
   saída incompleta ou sem texto geram `AIError` com mensagem controlada.
2. `validate_response` converte JSON, rejeita constantes não JSON, confere campos,
   tipos, textos, listas mínimas e sequência de ordem/prioridade. O validador cobre
   os recursos utilizados nesses contratos, não todo o padrão JSON Schema.
3. Conteúdo incompatível gera `ResponseValidationError`. Não há reparo automático
   de JSON nem novas tentativas automáticas. O serviço valida novamente conteúdo
   recuperado do cache; entrada inválida no cache permite nova geração.

A validação local acrescenta exigências como textos não vazios e sequência
consecutiva, além das restrições do schema enviado. Ela não avalia veracidade,
segurança técnica, relevância ou qualidade linguística. Falhas da API/validação
não são persistidas como sucesso; falhas de I/O geram `StorageError`.

## Comparação controlada e rubrica manual

`vlab.comparison.run_comparison` preserva perfil completo, ticket original, tipo,
provedor e um snapshot de modelo/configuração nas duas execuções. A variável de
interesse é a versão do prompt e suas instruções. O serviço salva prompt efetivo,
schema, configuração, IDs, timestamps e origem API/cache, permitindo inspecionar o
que foi comparado. Não há parâmetros de amostragem diferentes entre versões.

`validate_comparison` verifica conteúdo, vínculo ao cenário, configurações, chaves
de cache e IDs distintos. `validate_rubric` exige os dois conjuntos completos:

| Critério | Pergunta orientadora |
|---|---|
| Clareza (`clarity`) | A resposta é compreensível, organizada e sem ambiguidades desnecessárias? |
| Adequação ao nível do cliente (`customer_fit`) | Vocabulário, profundidade e explicações combinam com o perfil? |
| Acionabilidade (`actionability`) | Cliente ou atendente identifica o que fazer a seguir? |

Cada critério recebe **nota inteira de 1 a 5 e justificativa manual não vazia**:
1 insuficiente, 2 fraco, 3 adequado, 4 bom, 5 excelente. A soma sem pesos vai de
3 a **15 pontos por versão**. `save_comparison` recalcula totais e delta v2 − v1 e
persiste um snapshot com respostas e avaliações vinculadas à versão correta.
Não existe avaliação por outro LLM.

### Avaliações reais disponíveis

Foram encontrados dois registros locais com rubrica preenchida, distintos da
fixture fictícia dos testes. Suas respostas, prompts, notas, justificativas e
metadados foram preservados nos [samples](samples/README.md). Foram conferidos os
validadores, as somas e o vínculo de cada resultado ao seu histórico original.

Os dois cenários usam Ana (leigo, didático, chat), o ticket
"Meu notebook não consegue se conectar ao Wi-Fi" e `gpt-4o-mini`:

| Tipo | v1: clareza / adequação / ação | Total v1 | v2: clareza / adequação / ação | Total v2 | Delta |
|---|---|---:|---|---:|---:|
| Diagnóstico | 4 / 3 / 3 | 10 | 4 / 3 / 3 | 10 | 0 |
| Resolução | 4 / 4 / 4 | 12 | 4 / 4 / 3 | 11 | −1 |

No diagnóstico, as justificativas apontam falta de didatismo/orientações em ambas.
Na resolução, a avaliação de acionabilidade da v2 observa que ela começa pelo
reinício e não verifica outros dispositivos; a v1 recebeu nota maior nesse
critério. São observações desses registros, sem generalização de superioridade.
Houve uso de cache: diagnóstico tem dois hits; resolução tem hit em v1 e miss em
v2. As notas se referem aos textos preservados, não a novas gerações nesta task.

## Limitações e decisões

- Instruções mais específicas não garantem uma resposta melhor. Formato válido
  também não comprova fatos ou adequação da orientação.
- Configurações equivalentes não eliminam variação do modelo. Duas avaliações do
  mesmo perfil/ticket não cobrem outros clientes, problemas ou repetições.
- A rubrica é subjetiva, usa pesos iguais e não mede concordância entre avaliadores.
  O registro não identifica o avaliador; não se infere quem atribuiu as notas.
- Fixar o cenário/configuração e preservar os prompts facilita atribuir diferenças
  às versões, mas os resultados continuam sujeitos à variabilidade e ao julgamento.
- O cache SHA-256 usa JSON canônico com perfil, ticket exato, tipo, versão, prompt,
  provedor e configuração. Ganha rastreabilidade/reuso sem reconhecer equivalência
  semântica. Cache hits congelam o texto observado, não são novas amostras do modelo.
- JSON Schema estrito e validação local favorecem contratos verificáveis; o limite
  de saída e a ausência de reparos/retentativas mantêm o fluxo simples, mas saídas
  incompletas precisam de nova solicitação do usuário.
- Persistência em arquivos JSON com escrita atômica mantém a solução pequena e
  inspecionável; não há banco, TTL ou coordenação entre processos. No Railway,
  os arquivos dependem do volume em `/data` para persistir entre deployments.
