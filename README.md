# CHATin Back-end

Serviço de estudos do CHATin (FastAPI + PostgreSQL). Convenções do projeto em
[`docs/AGENTS.md`](../docs/AGENTS.md); identidade visual em [`docs/DESIGN.md`](../docs/DESIGN.md).

## Endpoints principais

### Resumos de estudo + Biblioteca

Um resumo de estudo por **módulo** por aluno (template estruturado + export em PDF).

| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/resumos` | Gera/regera o resumo de estudo do módulo da conversa (`{"conversa_id": "..."}`). Upsert por (`user_id`, `modulo_id`). |
| `GET` | `/resumos` | Lista os resumos **do próprio usuário** (filtrado pelo JWT), paginado: `limit` (1–100, padrão 20), `offset`, e opcional `materia_id`. |
| `GET` | `/resumos/{id}` | Detalhe de um resumo (só do dono). |
| `GET` | `/resumos/{id}/pdf` | PDF gerado on-demand a partir do template salvo (só do dono). |

Todas exigem `Authorization: Bearer <jwt>`; o `user_id` vem da claim `userId`.
Detalhes de implementação em [`TODO.md`](./TODO.md) (item 13).
