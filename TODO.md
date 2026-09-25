# TODO / status - gamificação, chat do aluno, quizzes por tema

Última atualização: 2026-09-12. Backend e frontend de teste (`ChatIn-Front`)
implementados e verificados ao vivo contra o banco real para tudo marcado ✅.

## 1. Chat de tirar dúvidas para o aluno comum ✅
- `POST /chat` (Q&A simples, sem tool-calling - só vê o conteúdo do módulo
  quando `modulo_id` é passado, mais o próprio histórico da conversa).
- `AIProvider.responder_pergunta_aluno` (modelo `GEMINI_MODEL_PROFESSOR`).
- Reaproveita `Conversa`/`Mensagem` (migration `0004`): campo `tipo`
  ("admin"/"aluno") separa as conversas do agente admin das do aluno, e
  `modulo_id` guarda o contexto.
- Frontend: botão "tirar dúvidas" no header, e "💬 tirar dúvida sobre este
  módulo" na tela do módulo (abre já contextualizado).

## 2. Histórico de conversas do chat do aluno ✅
- `GET /chat` (lista) e `GET /chat/{id}` (histórico completo), simétrico ao
  chat admin. Frontend: sidebar de conversas na tela de chat do aluno.

## 3. Histórico de resumos ✅
- Um resumo por conversa, gerado sob demanda (lazy) em `GET /chat/resumos` -
  só chama a IA se o resumo estiver ausente ou desatualizado
  (`resumo_gerado_em < updated_at`), nunca a cada mensagem. Verificado ao
  vivo: segunda chamada não gera custo de IA (resposta em ~0.5s, mesmo
  timestamp).
- `AIProvider.resumir_conversa` + campos `resumo`/`resumo_gerado_em` em
  `Conversa` (migration `0004`). Frontend: tela "resumos".

## 4. Sistema de XP ✅ (regras revisadas em 2026-09-12)
- Append-only: `xp_eventos` (migration `0005`) - totais são sempre somados
  (nunca um contador cru), mesmo princípio do `progresso_usuario`.
- Regras atuais, por faixa de nota, só na PRIMEIRA tentativa de um módulo
  (`app/services/xp_service.py`):
  - Abaixo do limite de aprovação → **20 XP**
  - Do limite até 79% → **80 XP**
  - 80% a 99% → **100 XP**
  - 100% (perfeito) → **200 XP**
- Retentativa que bate a melhor nota anterior: XP = pontos de melhoria.
  Retentativa que não melhora: 0 XP.
- Ganchado em `progresso_service.atualizar_progresso` (chamado por
  `POST /tentativas/{id}/responder`). Migration `0007` renomeou o motivo de
  auditoria de `modulo_concluido_primeira_vez` para `primeira_tentativa`,
  já que agora dispara em qualquer resultado da primeira tentativa, não só
  quando aprova.

## 5. Sistema de nível ✅
- `xp_service.calcular_nivel`: nível 1 = 500 XP, cada nível seguinte exige
  20% a mais que o anterior (500, 600, 720, 864, ...) - puramente calculado
  a partir do XP total, nunca armazenado.
- `GET /xp/meu` retorna `nivel`, `xp_proximo_nivel`, `xp_faltando_proximo_nivel`.
- Frontend: badge "Nível N · X XP" no header, atualiza no login e após cada
  quiz.

## 6. Ranking / leaderboard ✅
- `GET /ranking` (global) e `GET /ranking/materias/{materia_id}`.
- Nomes de exibição resolvidos: `perfis_usuario` (migration `0006`) espelha
  localmente `user_id -> nome/email` a partir das claims do próprio JWT
  (`username`/`email`), atualizado a cada request autenticado
  (`app.deps._sincronizar_perfil` + `PerfilRepository.upsert`, um UPSERT só,
  sem custo perceptível). `RankingEntradaOut.nome` vem de lá - `None` só para
  um usuário que nunca fez nenhuma chamada autenticada ainda.
- Ainda em aberto (não bloqueia uso): janela de tempo (só all-time por
  enquanto) e privacidade/opt-out.
- Frontend: tela de ranking com abas (Global + uma por matéria).

## 7. Dificuldade das questões a partir de desempenho real ✅
- Calculada on-the-fly (sem job/cron) a partir de `respostas_tentativa` já
  existente - `QuestionarioRepository.estatisticas_por_questao`.
- Cold-start: menos de 10 respostas registradas = tratada como "média"
  (`app/services/dificuldade_service.py::MINIMO_RESPOSTAS_PARA_CONFIAR`).

## 8. Seleção adaptativa de questões ✅
- `grading_service.iniciar_tentativa`/`iniciar_tentativa_tema` amostram por
  peso (algoritmo de Efraimidis-Spirakis, sem dependência nova) em vez de
  `random.sample` puro.
- Sinal de nível do aluno: média de pontuação em todas as tentativas
  concluídas (`TentativaRepository.media_pontuacao_concluidas`) - ≥80 puxa
  pra questões difíceis, <50 puxa pra fáceis, entre isso fica neutro.

## 9. Refazer quiz + histórico de tentativas do aluno ✅
- Confirmado ao vivo: `POST /modulos/{id}/tentativas` já permite refazer um
  módulo concluído (só bloqueia "bloqueado", não "concluído").
- `GET /tentativas` (histórico do próprio aluno: módulo ou tema, nota,
  status, data). Frontend: tela "minhas tentativas".

## 10. Progresso por matéria (extensão) ✅
- `GET /progresso` inclui `xp` por matéria em `ProgressoMateriaOut`, ao lado
  do `percentual_completo` que já existia. Exibido na aba "Progresso".

## 11. Criar módulo sem IA (conteúdo manual) ✅
- `ModuloCreate.conteudo` opcional: se informado, `criar_modulo` pula a
  geração de conteúdo por IA e usa o texto fornecido direto
  (`conteudo_modelo_ia="manual"`) - só o questionário continua sendo gerado
  por IA a partir desse texto. Disponível na REST API, no agente admin
  (`criar_modulo` tool) e no painel admin (campo "conteúdo manual" no
  formulário de novo módulo).

## 12. Quiz de revisão por tema + regeneração de questionário sob demanda ✅
- `POST /temas/{tema_id}/tentativas`: quiz de revisão que mistura questões
  de todos os módulos prontos de um tema (mesma seleção adaptativa) - **não**
  atualiza progresso nem XP, é só treino (migration `0008` tornou
  `tentativas.questionario_id` opcional e adicionou `tentativas.tema_id`,
  exatamente um dos dois preenchido). Frontend: tela "quiz" onde o aluno
  escolhe o tema.
- Admin: `POST /temas/{tema_id}/modulos/{modulo_id}/questionario/regenerar`
  (só o questionário, conteúdo intocado) e
  `POST /temas/{tema_id}/questionarios/regenerar` (em lote, todos os módulos
  do tema) - disponíveis via REST, agente admin e painel admin.

## 13. Resumo de estudo + Biblioteca + PDF ✅
- Um resumo de estudo por **módulo** por aluno: `resumos_estudo` (migration
  `0014`), com `UniqueConstraint (user_id, modulo_id)` - regenerar faz upsert
  no mesmo registro, nunca duplica ("um resumo por módulo", a Biblioteca como
  um livro dos resumos).
- `POST /resumos {conversa_id}` gera/regera a partir do **conteúdo do módulo**
  (contexto) + **todas as conversas do aluno naquele módulo** (não só a que
  disparou - ver `resumo_estudo_service._historico`, com o mesmo cap de chars
  do `questionario_personalizado_service`). Rejeita conversa sem `modulo_id`
  (400) e módulo sem conteúdo (400).
- Template estruturado (`conteudo` JSONB): visão geral, conceitos-chave,
  pontos importantes, exemplos, dúvidas do aluno, revisão rápida e fontes.
  Novo método `AIProvider.gerar_resumo_estudo` nos dois providers (Gemini com
  `response_schema`, ADK com `output_schema`).
- `GET /resumos?limit=&offset=&materia_id=` lista **só os resumos do próprio
  usuário do JWT** (`CurrentUserId`), paginado; `GET /resumos/{id}` abre o
  detalhe; `GET /resumos/{id}/pdf` devolve o PDF.
- PDF gerado **on-demand** com `fpdf2` (pure-Python, sem deps de sistema) a
  partir do template salvo - nenhum byte de PDF é armazenado. Fontes core do
  fpdf são latin-1, então `resumo_pdf_service._sanitizar` dobra travessões,
  aspas curvas e bullets antes de escrever.
- Frontend: `/biblioteca` deixa de ser `EmptyPage` e renderiza os resumos
  agrupados por matéria -> tema -> módulo, com viewer e "Baixar PDF"; botão
  "Gerar resumo de estudo" no chat (só em conversa vinculada a módulo). O
  proxy `/api/study/[...path]` ganhou `resumos` na allowlist e passthrough
  binário para `application/pdf`.

---

## Performance - revisar antes de escalar (2026-09-12)

Nada disto é urgente hoje - a filosofia "sempre computado, nunca cacheado"
(XP, progresso, dificuldade) é deliberada e correta para consistência a este
volume. Mas cada item abaixo cresce em custo com uso real, em graus
diferentes. Em ordem de prioridade:

1. **Regeneração em lote trava a requisição HTTP por minutos.**
   `dividir_tema_em_modulos` e `regenerar_questionarios_tema` fazem várias
   chamadas de IA sequenciais dentro de uma única request. Já observamos
   2m38s ao vivo para regenerar 5 módulos. A maioria de gateways/load
   balancers (inclusive o que ficaria na frente de um serviço no Render) tem
   timeout de request bem menor que isso - mais alguns módulos, ou uma
   resposta mais lenta da Gemini, e a requisição falha mesmo com o backend
   ainda processando. **Fix**: mover para um job em background (mínimo:
   `BackgroundTasks` do FastAPI; ideal: uma fila de verdade tipo Arq/Celery
   que sobrevive a um restart) com um endpoint de status para o admin
   consultar, em vez de bloquear a request.

2. **Dificuldade das questões: recomputada toda vez, e sem índice adequado.**
   `QuestionarioRepository.estatisticas_por_questao` roda a cada início de
   tentativa. Além de ser recalculada sempre (como você já apontou),
   confirmei que `respostas_tentativa.questao_id` **não tem índice próprio**
   - só existe um índice composto `(tentativa_id, questao_id)` com
   `tentativa_id` como coluna líder, que não ajuda uma busca filtrando só por
   `questao_id`. Conforme a tabela cresce, essa query tende a scan completo.
   **Fix**: adicionar índice em `questao_id`, e mover o cálculo para um job
   periódico (cron) que grava um valor de dificuldade já pronto para leitura
   - exatamente a ideia que você propôs.

3. **`GET /progresso` tem um N+1 e recarrega o currículo inteiro sempre.**
   Duas coisas na mesma rota: (a) um loop Python chama
   `xp_repo.total_por_usuario_e_materia` uma vez PARA CADA matéria do
   sistema - uma query separada por matéria, clássico N+1, devia ser uma
   única query `GROUP BY materia_id`; (b) a rota sempre carrega a árvore
   inteira do currículo (toda matéria → tema → módulo) pra calcular o
   progresso de um único usuário, mesmo que ele só tenha tocado uma fração
   dela. Conforme o currículo cresce, a rota fica mais lenta pra todo mundo,
   até pra quem mal começou.

4. **Ranking global é o problema clássico de leaderboard.**
   `GET /ranking` faz `GROUP BY user_id ORDER BY SUM(xp) DESC LIMIT N` sobre
   a tabela inteira de `xp_eventos` - o `LIMIT` não reduz o custo de
   agregação, só o tamanho do resultado. Tranquilo no volume atual; em escala
   real, leaderboards normalmente viram um snapshot materializado
   periodicamente (recalculado a cada alguns minutos) em vez de agregado ao
   vivo a cada request - mesmo tipo de solução do item 2.

5. **`GET /chat/resumos` chama a IA em loop, sequencialmente.**
   Mesmo formato do item 1, em escala menor: se várias conversas do aluno
   ficaram desatualizadas ao mesmo tempo, o endpoint chama a Gemini uma vez
   por conversa, uma atrás da outra, dentro da mesma request.

6. **Escala horizontal (múltiplas instâncias) - não é urgente, só ficar de olho.**
   Cada processo/instância tem seu próprio pool de conexões do SQLAlchemy
   (`pool_size` padrão = 5). Ok pra uma instância no Render; se algum dia
   escalar para várias, vale checar contra o limite de conexões do Supabase.

7. **Cota da API do Gemini - fora do nosso controle.**
   Com uso real, o limite passa a ser o rate limit do Google, não o nosso
   código. O retry (`_retry_transient`/`_retry_agente`) já lida bem com
   falhas transitórias; volume alto sustentado é conversa de aumentar cota
   com o Google, não fix de código.

## Limitações conhecidas (decisões conscientes, não bugs)
- **Sem teste de nivelamento/diagnóstico**: todo aluno entra numa matéria no
  mesmo ponto fixo (primeiro tema/módulo por `ordem`); não há como pular
  conteúdo que o aluno já sabe. Foi levantado como pergunta do cliente sobre
  "ponto de partida" - resposta honesta foi que isso não existe hoje.
- **Sem streak/hábito diário**: nada rastreia "o aluno voltou hoje" -
  reforço é só sobre profundidade/personalização de conteúdo ao longo do
  tempo, não sobre retenção dia-a-dia. Também levantado com o cliente como
  gap honesto, não implementado.
- Regras de XP são um segundo palpite (o primeiro, 100 base + 1/ponto, foi
  substituído pelo esquema de faixas acima a pedido do cliente) - ainda não
  validado com uso real; fácil de ajustar em `xp_service.py` já que XP é
  sempre recomputado, nunca cacheado.
- `percentual_completo` por matéria é binário-ish (só conta um tema como
  concluído se todos os módulos dele estiverem concluídos) - comportamento
  pré-existente, não mexido nesta rodada.
- Ranking usa só all-time, sem opt-out de privacidade.

## Diagramas
Esquema do banco + casos de uso (Aluno/Administrador) documentados em
diagrama publicado: ver link compartilhado na conversa (`Diagramas ChatIn`).

## Próximo passo natural
Nada bloqueado no momento - os itens "ainda em aberto" acima (janela de
tempo do ranking, teste de nivelamento, streak) são features novas a
discutir com o cliente antes de implementar, não bugs a corrigir.
