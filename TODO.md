# TODO - próximas features (gamificação + chat do aluno)

Ordem sugerida, com dependências indicadas. Nada disto foi implementado ainda -
isto é só o plano.

## 1. Chat de tirar dúvidas para o aluno comum
- Decisão já tomada: **Q&A simples, sem tool-calling** (diferente do agente
  admin). A IA só enxerga (a) o conteúdo do módulo atual, quando o aluno abriu
  o chat estudando um módulo específico, e (b) o histórico da própria
  conversa. Sem acesso a ferramentas/outros dados.
- Provável: um novo método no `AIProvider` (ex.:
  `responder_pergunta_aluno(conteudo_modulo, historico, pergunta)`) + um novo
  router `POST /chat` (separado de `/admin/chat`).
- Reaproveitar os modelos `Conversa`/`Mensagem` já existentes, mas com um jeito
  de saber o contexto (ex.: `modulo_id` opcional na Conversa). Sem módulo
  associado, cai para um modo "tutor geral de ENEM".

## 2. Histórico de conversas do chat do aluno
- Depende do item 1.
- Espelha o que já existe no chat admin: `GET /chat` (lista as conversas do
  próprio aluno) e `GET /chat/{id}` (histórico completo) + sidebar no
  frontend para retomar uma conversa antiga.

## 3. Histórico de resumos
- Decisão já tomada: **um resumo por conversa** (não por módulo), gerado
  quando a conversa "termina"/fica inativa - não a cada mensagem.
- Precisa definir o gatilho exato (gerar/atualizar o resumo de forma
  preguiçosa quando o histórico é consultado e está desatualizado, ou uma ação
  explícita tipo "encerrar conversa" - evitar um job de background rodando
  sempre, não vale a pena para um projeto de faculdade).
- Novo método no `AIProvider` para resumir uma lista de mensagens. Campo
  `resumo` na Conversa (ou tabela própria, se quisermos manter o resumo mesmo
  que o chat completo seja limpo depois). Tela no frontend listando só os
  resumos.

## 4. Sistema de XP
- Pontos por ações do aluno (completar o questionário de um módulo, acertos,
  etc.).
- Precisa: total corrente por usuário **e por matéria** (o ranking do item 5
  depende disso), provavelmente um log de eventos de XP (não só um contador
  cru) para dar pra explicar "por que tenho esse tanto de XP".
- **Ainda em aberto: as regras de quanto XP cada ação vale** (XP base por
  módulo concluído, bônus por nota, XP reduzido/zero em retentativas etc.) -
  decidir antes de implementar.
- Ganchar em `grading_service.responder_tentativa` /
  `progresso_service.atualizar_progresso`, que já é onde a conclusão é
  detectada hoje.

## 5. Ranking / leaderboard
- Depende do item 4.
- Decisão já tomada: **ranking global E por matéria** (ex.: top alunos em
  Matemática especificamente) - não só um ranking único.
- Endpoints tipo `GET /ranking` e `GET /ranking?materia_id=...`, com
  paginação/top-N.
- **Ainda em aberto:** janela de tempo (só all-time, ou também
  semanal/mensal?) e privacidade (nome do aluno visível pros outros por
  padrão?).

## 6. Dificuldade das questões a partir de desempenho real
- Decisão já tomada: dificuldade **calculada a partir de dados reais de
  desempenho dos alunos** (% de erro), não atribuída pela IA na criação.
- Verificar se dá pra derivar isso dos registros de resposta já existentes
  (`Tentativa`/respostas) ou se precisa de uma tabela nova por questão.
- Pode ser calculado on-the-fly a partir de agregados, sem precisar de um job
  agendado (evita depender de cron num projeto de faculdade).
- **Ainda em aberto:** política de "cold start" - quantas tentativas uma
  questão precisa ter antes da dificuldade calculada ser confiável (até lá,
  tratar como "média"?).

## 7. Seleção adaptativa de questões
- Depende do item 6.
- Hoje `grading_service.iniciar_tentativa` amostra o pool de questões de
  forma uniforme (`random.sample`). Mudar para enviesar a amostra: aluno
  indo bem -> mais questões difíceis; aluno com dificuldade -> mais fáceis.
- **Ainda em aberto:** algoritmo exato de seleção (amostragem ponderada por
  dificuldade vs. abordagem por faixas) e contra o que medir "indo bem"
  (desempenho recente nesse módulo? XP/rank geral dos itens 4/5?).

## 8. Refazer quiz + histórico de tentativas do aluno
- Duas partes:
  1. **Confirmar** que o aluno já consegue refazer o quiz de um módulo já
     concluído (a trava atual só bloqueia módulo "bloqueado", então
     "concluído" já deveria permitir `POST /modulos/{id}/tentativas`) -
     auditar isso ponta a ponta e garantir que o frontend realmente oferece a
     opção "refazer quiz" em módulos concluídos, não só no primeiro acesso.
  2. **Capacidade nova de verdade:** um "minhas tentativas" - endpoint tipo
     `GET /tentativas` (do próprio usuário logado) listando as tentativas
     passadas (data, módulo, nota, aprovado/reprovado) + tela no frontend. Os
     registros de `Tentativa` já existem no banco, só falta um endpoint de
     listagem para o próprio aluno.

## 9. Progresso por matéria (revisão)
- Isso **já existe** via `GET /progresso`
  (`progresso_service.montar_progresso`) - % de conclusão por
  matéria/tema/módulo já é calculado e exibido na aba "Progresso" do
  frontend.
- Este item é só revisar se precisa estender depois que os itens 4/5 (XP +
  ranking) existirem, pra mostrar XP/rank por matéria ao lado do % de
  conclusão que já existe.

---

## Decisões já tomadas (não re-perguntar)
- Chat do aluno: Q&A simples, sem tool-calling.
- Resumos: um por conversa, não por módulo.
- Ranking: global E por matéria.
- Dificuldade: calculada por desempenho real, não atribuída pela IA.
