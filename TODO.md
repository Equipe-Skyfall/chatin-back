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

---

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
