# Perfis definitivos

Este diretório contém exatamente os quatro perfis aprovados pelo responsável
pelo projeto, com um arquivo JSON por cliente:

| Arquivo / id | Nome | Nível técnico | Estilo de comunicação | Canal |
|---|---|---|---|---|
| `ana.json` / `ana` | Ana | leigo | didático | chat |
| `bruno.json` / `bruno` | Bruno | intermediário | detalhado | e-mail |
| `carla.json` / `carla` | Carla | avançado | direto | chat |
| `diego.json` / `diego` | Diego | leigo | direto | telefone |

Cada arquivo `<identificador>.json` deve conter um objeto com `nome` ou `id`
(texto não vazio), `nivel_tecnico`, `estilo_comunicacao` e `canal`.
Os valores devem seguir exatamente os acentos e a grafia do enunciado:

- `nivel_tecnico`: `leigo`, `intermediário` ou `avançado`.
- `estilo_comunicacao`: `direto`, `detalhado` ou `didático`.
- `canal`: `chat`, `e-mail` ou `telefone`.

Uso em Python: `load_profile("ana")`, de `vlab.profiles`.
O retorno é um dicionário validado; falhas levantam `ProfileError`.

Teste integrado real com Ana e um problema simples de Wi-Fi:
`python -m vlab.smoke --perfil ana`. Esse comando realiza uma chamada à OpenAI;
os testes automatizados continuam independentes da API real.

`tests/fixtures/perfil_teste.json` é exclusivamente uma fixture de teste e
não representa um dos quatro clientes definitivos.
