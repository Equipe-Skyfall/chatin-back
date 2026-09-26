# CHATin Back-end

Serviço de estudos do CHATin: um currículo (matérias → temas → módulos) montado por administradores ou pelos
próprios alunos, com conteúdo e questionários gerados por IA, quizzes com progresso desbloqueável, chat de dúvidas,
resumos de estudo em PDF e um agente de IA para administrar o currículo.

Stack: **Python 3.11 · FastAPI · SQLAlchemy 2 + Alembic · PostgreSQL (Supabase) · Google Gemini (`google-genai` /
`google-adk`) · fpdf2**.

> Convenções do projeto (commits, PR, review): [`docs/AGENTS.md`](./docs/AGENTS.md) (backend) e
> `../docs/AGENTS.md` (raiz do monorepo `chatin`).

## Sumário

1. [Arquitetura](#1-arquitetura)
2. [Casos de uso](#2-casos-de-uso)
3. [Modelo de dados (ER)](#3-modelo-de-dados-er)
4. [API](#4-api)
5. [Autenticação e IA](#5-autenticação-e-ia)
6. [Configuração](#6-configuração)
7. [Como rodar e testar](#7-como-rodar-e-testar)
8. [Estrutura do projeto](#8-estrutura-do-projeto)

---

## 1. Arquitetura

O serviço **não emite tokens**: o front-end faz login no `authSys`, recebe um JWT e o envia ao `chatin-back`, que só
o **valida** com o segredo compartilhado.

```mermaid
flowchart TB
    Client([Front-end])
    Auth([authSys])
    Gemini([Google Gemini])

    Client -->|1. login| Auth
    Auth -->|2. JWT| Client
    Client -->|3. HTTP + Bearer JWT| Routers

    subgraph Back[chatin-back]
        Routers[Routers<br/>valida o JWT e recebe a requisição]
        Services[Services<br/>regras de negócio]
        Repos[Repositories<br/>acesso a dados]
        AI[AIProvider<br/>ADK ou Gemini]
        Routers --> Services
        Services --> Repos
        Services --> AI
    end

    Repos --> DB[(PostgreSQL)]
    AI --> Gemini
```

- **Routers → Services → Repositories:** os services dependem de repositórios e do `AIProvider`, nunca de `Session` ou
  do SDK da IA. Por isso os testes unitários rodam sem banco e sem rede.
- **`AIProvider`** é uma estratégia com duas implementações (`AdkProvider`, o padrão, e `GeminiProvider`, rollback
  imediato), escolhidas por `AI_PROVIDER`.
- **Erros:** exceções de domínio (`AppException`) carregam o status HTTP e um único handler as converte em JSON.
- **Segundo plano:** a pesquisa de fontes ao criar um tema e a divisão automática em módulos rodam em
  `BackgroundTasks`.

---

## 2. Casos de uso

```mermaid
flowchart LR
    Aluno([Aluno])
    Admin([Administrador])

    subgraph Sistema[chatin-back]
        direction TB
        A1((Navegar no currículo<br/>e ver progresso))
        A2((Estudar um módulo))
        A3((Fazer quiz do módulo))
        A4((Praticar e revisar tema))
        A5((Tirar dúvidas no chat))
        A6((Gerar resumo e baixar PDF))
        A7((Criar trilha própria<br/>e votar em trilhas))
        B1((Gerir matérias, temas<br/>e módulos))
        B2((Gerar conteúdo e<br/>questionários com IA))
        B3((Editar conteúdo e questões))
        B4((Administrar pelo chat<br/>com agente))
    end

    Aluno --> A1
    Aluno --> A2
    Aluno --> A3
    Aluno --> A4
    Aluno --> A5
    Aluno --> A6
    Aluno --> A7
    Admin --> B1
    Admin --> B2
    Admin --> B3
    Admin --> B4
```

| Caso de uso | Ator | Endpoints principais |
|---|---|---|
| Navegar no currículo e ver progresso | Aluno | `GET /materias`, `GET /trilha`, `GET /progresso`, `GET /temas/{id}`, `GET /modulos/{id}` |
| Fazer o quiz do módulo | Aluno | `POST /modulos/{id}/tentativas`, `POST /tentativas/{id}/responder` |
| Praticar e revisar um tema | Aluno | `POST /modulos/{id}/questionario-personalizado`, `POST /temas/{id}/tentativas` |
| Tirar dúvidas no chat | Aluno | `POST /chat`, `GET /chat`, `GET /chat/{id}` |
| Gerar resumo e baixar PDF | Aluno | `POST /resumos`, `GET /resumos`, `GET /resumos/{id}/pdf` |
| Criar trilha própria e votar | Aluno | `POST /materias`, `POST /materias/{id}/temas`, `POST`/`DELETE /materias/{id}/votar` |
| Gerir matérias, temas e módulos | Admin (global) ou dono (trilha própria) | `/materias…`, `/temas…`, `/modulos…` |
| Gerar conteúdo e questionários | Admin ou dono | `…/gerar-automaticamente`, `…/regenerar` |
| Administrar pelo chat com agente | Admin | `POST /admin/chat`, `GET /admin/chat` |

---

## 3. Modelo de dados (ER)

`user_id` vem da claim `userId` do JWT (string tipo `cuid`); **não há tabela de usuários** neste serviço.

```mermaid
erDiagram
    MATERIAS ||--o{ TEMAS : "tem"
    TEMAS ||--o{ FONTES : "pesquisa gera"
    TEMAS ||--o{ MODULOS : "divide em"
    MODULOS ||--|| QUESTIONARIOS : "tem 1"
    QUESTIONARIOS ||--o{ QUESTOES : "pool"
    QUESTOES ||--|| GABARITOS : "resposta correta"
    QUESTIONARIOS |o--o{ TENTATIVAS : "escopo módulo"
    TEMAS |o--o{ TENTATIVAS : "escopo revisão"
    TENTATIVAS ||--o{ TENTATIVA_QUESTOES : "amostra fixa"
    QUESTOES ||--o{ TENTATIVA_QUESTOES : "sorteada em"
    TENTATIVAS ||--o{ RESPOSTAS_TENTATIVA : "respostas"
    QUESTOES ||--o{ RESPOSTAS_TENTATIVA : "respondida em"
    MODULOS ||--o{ PROGRESSO_USUARIO : "por aluno"
    MATERIAS ||--o{ VOTOS_MATERIA : "recebe"
    MODULOS |o--o{ CONVERSAS : "contexto (opcional)"
    CONVERSAS ||--o{ MENSAGENS : "contém"
    MODULOS ||--o{ RESUMOS_ESTUDO : "1 por aluno"
    CONVERSAS |o--o{ RESUMOS_ESTUDO : "origem (opcional)"

    MATERIAS {
        uuid id PK
        string nome
        string descricao
        string owner_user_id "nulo = currículo global"
    }
    TEMAS {
        uuid id PK
        uuid materia_id FK
        string titulo
        int ordem
        string status "gerando | pronto | erro"
        text direcionamento
    }
    FONTES {
        uuid id PK
        uuid tema_id FK
        string origem
        string conteudo_extraido
        jsonb metadata
    }
    MODULOS {
        uuid id PK
        uuid tema_id FK
        string titulo
        int ordem
        string status "gerando | pronto | erro"
        text conteudo
    }
    QUESTIONARIOS {
        uuid id PK
        uuid modulo_id FK "1 por módulo"
    }
    QUESTOES {
        uuid id PK
        uuid questionario_id FK
        int ordem
        text enunciado
        jsonb alternativas
        text explicacao
        bool personalizada
    }
    GABARITOS {
        uuid questao_id PK, FK
        string resposta_correta "A a E"
    }
    TENTATIVAS {
        uuid id PK
        uuid questionario_id FK "ou tema_id, nunca os dois"
        uuid tema_id FK
        string user_id
        string status "em_andamento | concluida"
        bool pratica
        numeric pontuacao
    }
    TENTATIVA_QUESTOES {
        uuid id PK
        uuid tentativa_id FK
        uuid questao_id FK
        int ordem
    }
    RESPOSTAS_TENTATIVA {
        uuid id PK
        uuid tentativa_id FK
        uuid questao_id FK
        string resposta_escolhida
        bool correta
    }
    PROGRESSO_USUARIO {
        uuid id PK
        string user_id
        uuid modulo_id FK
        string status "disponivel | concluido"
        numeric melhor_pontuacao
    }
    VOTOS_MATERIA {
        uuid id PK
        string user_id
        uuid materia_id FK
        int valor "1 ou -1"
    }
    CONVERSAS {
        uuid id PK
        string user_id
        string tipo "admin | aluno"
        uuid modulo_id FK
        string titulo
    }
    MENSAGENS {
        uuid id PK
        uuid conversa_id FK
        string papel
        text conteudo
        int ordem
    }
    RESUMOS_ESTUDO {
        uuid id PK
        string user_id
        uuid modulo_id FK
        uuid conversa_id FK
        jsonb conteudo "template estruturado"
    }
```

- `tentativas`: pertence a um módulo **ou** a um tema; só pode haver **uma** com `status = 'em_andamento'` por aluno
  (índice único parcial).
- `questoes.personalizada`: questões geradas no "Praticar"; ficam no pool do módulo, mas fora do pool que vale nota.
- `progresso_usuario`, `resumos_estudo`: únicos por (`user_id`, `modulo_id`); `votos_materia`: por (`user_id`,
  `materia_id`).
- Apagar uma matéria, tema ou módulo remove em cascata o que está abaixo. Migrations em `migrations/versions`.

---

## 4. API

Documentação interativa: `GET /docs` e `GET /openapi.json`. **Auth:** *Autenticado* = qualquer JWT válido; *Admin* =
`role = ADMIN`; *Dono/Admin* = admin para conteúdo global, dono para uma trilha própria.

| Grupo | Rotas | Auth |
|---|---|---|
| Saúde | `GET /healthz`, `GET`/`HEAD /` | — |
| Matérias | `POST`/`GET /materias`, `GET`/`PUT`/`DELETE /materias/{id}` | Autenticado (escrita: Dono/Admin) |
| Votos | `POST`/`DELETE /materias/{id}/votar` | Autenticado |
| Temas | `POST`/`GET /materias/{id}/temas`, `PUT`/`DELETE /materias/{id}/temas/{tema_id}`, `POST …/{tema_id}/regenerar`, `GET /temas/{id}`, `GET /temas/{id}/status`, `GET /trilha` | Autenticado (escrita: Dono/Admin) |
| Módulos | `POST`/`GET /temas/{id}/modulos`, `POST …/gerar-automaticamente`, `PUT`/`DELETE …/{modulo_id}`, `POST …/{modulo_id}/regenerar`, `POST …/questionario/regenerar`, `POST /temas/{id}/questionarios/regenerar`, `GET /modulos/{id}` | Autenticado (escrita: Dono/Admin) |
| Conteúdo e questões | `GET`/`PUT /modulos/{id}/conteudo`, `GET /modulos/{id}/questoes`, `PUT …/questoes/{questao_id}` | Dono/Admin |
| Quizzes | `POST /modulos/{id}/tentativas`, `POST /modulos/{id}/questionario-personalizado`, `POST /temas/{id}/tentativas`, `POST /tentativas/{id}/responder`, `GET /tentativas` | Autenticado (dono da tentativa) |
| Progresso | `GET /progresso` | Autenticado |
| Chat do aluno | `POST`/`GET /chat`, `GET /chat/{id}`, `GET /chat/resumos` | Autenticado (dono) |
| Chat admin | `POST`/`GET /admin/chat`, `GET /admin/chat/{id}` | Admin |
| Resumos | `POST`/`GET /resumos`, `GET /resumos/{id}`, `GET /resumos/{id}/pdf` | Autenticado (dono) |

### Resumos de estudo + Biblioteca

Um resumo de estudo por **módulo** por aluno (template estruturado + export em PDF).

| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/resumos` | Gera/regera o resumo de estudo do módulo da conversa (`{"conversa_id": "..."}`). Upsert por (`user_id`, `modulo_id`). A conversa precisa estar ligada a um módulo |
| `GET` | `/resumos` | Lista os resumos **do próprio usuário** (filtrado pelo JWT), paginado: `limit` (1–100, padrão 20), `offset`, e opcional `materia_id` |
| `GET` | `/resumos/{id}` | Detalhe de um resumo (só do dono) |
| `GET` | `/resumos/{id}/pdf` | PDF gerado on-demand a partir do template salvo (só do dono) |

Todas exigem `Authorization: Bearer <jwt>`; o `user_id` vem da claim `userId`. Detalhes de implementação em
[`TODO.md`](./TODO.md) (item 13).

### Erros

Respostas de erro têm o formato `{"detail": "mensagem"}`.

| Status | Quando |
|---|---|
| `400` | Requisição inválida ou estado que não permite a ação |
| `401` | Token ausente, inválido ou expirado |
| `403` | Sem permissão, ou tema/módulo bloqueado |
| `404` | Não encontrado, ou de outro usuário |
| `409` / `422` | Conflito (ordem duplicada, conversa ocupada) / submissão de quiz incompleta |
| `502` | Falha ou indisponibilidade da IA |
| `500` | Erro inesperado |

---

## 5. Autenticação e IA

**Autenticação.** O JWT (HS256, segredo `JWT_SECRET`) vem do `authSys` com o payload
`{ userId, email, username, role }` (**`userId`, não `sub`**; `role` é `ADMIN` ou `USER`). Toda escrita no currículo
passa por `verificar_acesso_escrita` (`app/core/autorizacao.py`), que exige admin para conteúdo global e o dono para
uma trilha própria. Conversas, tentativas, resumos e progresso são sempre filtrados por `user_id`.

**IA.** Toda chamada trata a indisponibilidade do Gemini com uma exceção de domínio e tenta de novo em falhas
transitórias, então uma falha da IA não derruba a aplicação.

- `AI_PROVIDER=adk` (padrão): saída estruturada validada, busca de fontes com `google_search` e sessões persistentes
  para o agente admin. `gemini`: caminho legado, para rollback.
- **Agente admin:** ferramentas para gerir matérias, temas, módulos e questões. **Agente do aluno:**
  `buscar_conteudo`, `meu_desempenho`, `criar_minha_trilha`.
- Prompts em `app/ai/prompts.py`; a busca de fontes em `app/ai/grounding.py`.

---

## 6. Configuração

Copie `.env.example` para `.env` (nunca o commite). **Segredos ficam só em variáveis de ambiente.**

| Variável | Padrão | Descrição |
|---|---|---|
| `SUPABASE_DB_URL` | — | URL do Postgres (`postgresql+psycopg://…`) |
| `JWT_SECRET`, `JWT_ALGORITHM` | —, `HS256` | Segredo compartilhado com o `authSys` |
| `AI_PROVIDER` | `adk` | `adk` ou `gemini` |
| `GEMINI_API_KEY` | — | Chave da API do Gemini |
| `GEMINI_MODEL_*` | `gemini-2.5-flash` | Modelo por finalidade (`CONTEUDO`, `QUESTIONARIO`, `SEARCH`, `AGENTE`, `PROFESSOR`) |
| `QUESTIONARIO_POOL_SIZE` | `12` | Questões no pool de cada módulo |
| `TENTATIVA_NUM_QUESTOES` | `5` | Questões sorteadas por tentativa |
| `PONTUACAO_MINIMA_APROVACAO` | `60` | Nota (%) para concluir um módulo |
| `CORS_ORIGINS` | `http://localhost:3000` | Origens permitidas, separadas por vírgula |
| `ENV`, `LOG_LEVEL` | `local`, `INFO` | Ambiente e nível de log |

Há outras variáveis opcionais (limite de iterações do agente, janela de mensagens do chat); veja `.env.example`.

> **ADK:** ele lê a chave de `GOOGLE_API_KEY`/`GEMINI_API_KEY` **do ambiente do processo**. Com `docker compose`
> (`env_file`) funciona; rodando `uvicorn` direto só com um `.env` e `AI_PROVIDER=adk`, exporte a chave no shell.

---

## 7. Como rodar e testar

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env            # preencha as variáveis
alembic upgrade head            # aplica as migrations
uvicorn app.main:app --reload   # http://localhost:8000  (docs em /docs)
```

Com Docker: `docker compose up --build` sobe um Postgres 16 local (usuário e senha `postgres`, banco `chatin`) e a API
em `http://localhost:8000`; aponte `SUPABASE_DB_URL` para
`postgresql+psycopg://postgres:postgres@postgres:5432/chatin` e rode `docker compose exec app alembic upgrade head`.

```bash
pytest tests/unit          # rápido, sem banco e sem rede
ruff check app tests       # lint
```

Os testes unitários usam repositórios em memória e um `FakeAIProvider` (`tests/fakes`). Os de integração
(`tests/integration`) exigem um Postgres **descartável** em `TEST_DATABASE_URL` e terminam com `drop_all`:
**nunca** aponte essa variável para o banco real.

---

## 8. Estrutura do projeto

```
app/
├── main.py         # FastAPI, CORS, routers, /healthz
├── config.py       # variáveis de ambiente
├── deps.py         # JWT e injeção de repositórios e do AIProvider
├── routers/        # camada HTTP
├── services/       # regras de negócio
├── repositories/   # acesso a dados
├── models/         # SQLAlchemy
├── schemas/        # Pydantic (entrada/saída da API)
├── ai/             # AIProvider, providers ADK/Gemini, prompts, ferramentas dos agentes
└── core/           # segurança, autorização, exceções, logging
migrations/         # Alembic
tests/              # unit, integration, builders, fakes
docs/               # AGENTS.md e documentação adicional
```

Mais documentação: [`TODO.md`](./TODO.md) (status das funcionalidades e pontos de performance).
