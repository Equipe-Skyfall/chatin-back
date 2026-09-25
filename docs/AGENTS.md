# AGENTS.md — chatin-back

Convenções específicas deste repositório (backend). Convenções comuns aos dois repos (padrão de commit, PR, review, arquitetura geral) vivem em `../docs/AGENTS.md` (raiz do monorepo `chatin`) — leia aquele primeiro.

## Stack

Python, FastAPI, SQLAlchemy + Alembic (migrations), PostgreSQL (+ pgvector), Gemini (IA/PLN, via `google-genai`/`google-adk`), Redis (cache/lock de concorrência do chat).

Não adicione uma nova biblioteca sem antes verificar se uma das já escolhidas resolve o problema. Se for realmente necessária, justifique no PR.

## Ambiente e segurança

- Segredos (chaves de API, credenciais de banco) ficam **somente** em variáveis de ambiente (`.env`, não commitado). Nunca hardcode uma chave no código, mesmo "temporariamente". `.env.example` documenta cada variável.
- Ao gerar código que chama a IA (Gemini), sempre trate o caso de falha/indisponibilidade sem quebrar o restante da aplicação (ver RNF6 no DoR) — nunca deixe uma chamada de IA sem `try/except` propagando pra fora do endpoint sem uma exceção de domínio tratada.
- Toda chamada à IA deve poder ser contabilizada (RNF7) — não crie chamadas "soltas" fora do mecanismo de registro de consumo.
- `ENV` (`app/config.py`) controla comportamento sensível a ambiente (ex.: fallback de verificação de JWT em `app/core/security.py`) — default é sempre o mais restrito (`"production"`), nunca assuma que uma env var ausente significa "modo dev".
- Endpoints que leem/escrevem conteúdo do currículo (`Materia`/`Tema`/`Modulo`) devem checar autorização antes de tocar nos dados — ver o padrão em `app/routers/modulos.py`/`temas.py`.

## Padrão de testes (backend)

`pytest`. Todo teste deve poder rodar localmente sem depender de uma chave de API real — use os fakes em `tests/fakes/` (`FakeAIProvider`, repositórios em memória) em vez de mockar `google-genai` diretamente.
