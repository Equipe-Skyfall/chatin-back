"""Concrete `AIProvider` strategy backed by the Google Agent Development Kit
(`google-adk`) - Fases 1-3 of the ADK migration (see the migration plan).

Fase 1: `gerar_questionario` and `planejar_modulos` run through ADK using
`LlmAgent(output_schema=<pydantic model>)` (`app/ai/adk_schemas.py`) in place
of Gemini's own uppercase-typed JSON schema dialect (`gemini_schemas.py`) and
the manual `json.loads` + retry-with-reinforcement-prompt parsing that lived
in `GeminiProvider`. The `output_schema` guarantees a well-formed result by
construction (including the "exactly 5 alternatives" constraint, via
Pydantic's `Field(min_length=5, max_length=5)`), so there is no retry-on-
malformed-output path here.

Fase 2: `gerar_conteudo_modulo` (plain text) and `buscar_fontes` (grounded via
the ADK's builtin `google_search` tool) also run through ADK now - both are
still single-turn (one prompt, one response), so they reuse the same
throwaway-session helper as Fase 1, just without an `output_schema`.

Fase 3: `conversar_com_ferramentas` (the admin tool-calling agent) also runs
through ADK now, the native way - a fresh `LlmAgent(tools=...)` per call
(tools are closures over that call's `FerramentaContexto`, see
`app/ai/adk_tools.py`) handed to a `Runner` backed by a persistent
`DatabaseSessionService`, so the ADK's own `Session`/`Event`s (keyed by
`conversa_id`) are the source of truth for this conversation's history - the
`Runner` auto-invokes tools and manages the whole model<->tool loop
internally (capped via `RunConfig(max_llm_calls=...)`), which is what makes
`AIProvider.conversar_com_ferramentas` return one final string instead of one
round trip at a time.

`conversar_com_agente_aluno` (the student agent, `app/services/
agent_tools_aluno.py`) runs the same way, on the same `Runner`/
`DatabaseSessionService` - conversas are globally unique ids regardless of
`tipo`, so there's no collision reusing the one session service for both
audiences.

The remaining `AIProvider` method (`resumir_conversa`, the student chat's
summary generation) still delegates, by composition, to an internal
`GeminiProvider` instance - migrating it to the same persistent
`SessionService` is a follow-up, not required by this phase. This keeps
`AI_PROVIDER=adk` fully functional in production from Fase 1 onward, with
`AI_PROVIDER=gemini` remaining available as an instant rollback.
"""

import asyncio
import logging
import threading
import uuid
from datetime import UTC, datetime

from google.adk.agents import LlmAgent, RunConfig
from google.adk.agents.invocation_context import LlmCallsLimitExceededError
from google.adk.runners import InMemoryRunner, Runner
from google.adk.sessions import DatabaseSessionService
from google.adk.tools import google_search
from google.genai import types as genai_types
from pydantic import ValidationError
from tenacity import retry, stop_after_attempt, wait_exponential

from app.ai.adk_schemas import PlanoModulosSchema, QuestionarioSchema, ResumoEstudoSchema
from app.ai.adk_tools import construir_tools, construir_tools_aluno
from app.ai.base import AIProvider
from app.ai.gemini_provider import GeminiProvider
from app.ai.prompts import (
    AGENTE_ADMIN_SYSTEM_INSTRUCTION,
    prompt_agente_aluno_system,
    prompt_buscar_fontes,
    prompt_gerar_conteudo_modulo,
    prompt_gerar_questionario,
    prompt_planejar_modulos,
    prompt_resumo_estudo,
)
from app.ai.schemas import (
    AlternativaGerada,
    ConceitoChave,
    ConteudoGerado,
    DuvidaResolvida,
    ErroQuestao,
    FerramentaContexto,
    FonteEncontrada,
    MensagemAgente,
    MensagemHistorico,
    ModuloPlanejado,
    PlanoModulos,
    QuestaoGerada,
    QuestionarioGerado,
    ResumoEstudoGerado,
)
from app.config import Settings
from app.core.exceptions import AgenteLimiteExcedidoException, ProvedorIAIndisponivelException

logger = logging.getLogger(__name__)

_retry_transient = retry(
    stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8), reraise=True
)

_APP_NAME = "chatin"
_USER_ID = "system"  # sessions are keyed by conversa_id (already globally
# unique) - a constant user_id is enough, ADK's per-user semantics aren't
# needed here.


class AdkProvider(AIProvider):
    def __init__(self, settings: Settings):
        self._settings = settings
        # Composition, not inheritance: methods not yet migrated to ADK delegate
        # here so `AI_PROVIDER=adk` covers 100% of `AIProvider` from Fase 1 on.
        self._gemini = GeminiProvider(settings)

        self._questionario_agent = LlmAgent(
            name="questionario_agent",
            model=settings.GEMINI_MODEL_QUESTIONARIO,
            instruction="Você gera questionários de múltipla escolha no estilo ENEM.",
            output_schema=QuestionarioSchema,
        )
        self._planejamento_agent = LlmAgent(
            name="planejamento_agent",
            model=settings.GEMINI_MODEL_CONTEUDO,
            instruction="Você planeja trilhas de estudo dividindo temas em módulos.",
            output_schema=PlanoModulosSchema,
        )
        self._conteudo_agent = LlmAgent(
            name="conteudo_agent",
            model=settings.GEMINI_MODEL_CONTEUDO,
            instruction="Você é um professor gerando material didático.",
        )
        self._fontes_agent = LlmAgent(
            name="fontes_agent",
            model=settings.GEMINI_MODEL_SEARCH,
            instruction="Você é um assistente de pesquisa educacional.",
            tools=[google_search],
        )
        self._resumo_estudo_agent = LlmAgent(
            name="resumo_estudo_agent",
            model=settings.GEMINI_MODEL_PROFESSOR,
            instruction="Você monta resumos de estudos preparatórios para alunos do ENEM.",
            output_schema=ResumoEstudoSchema,
        )
        # The admin agent's own session store - persistent, unlike the
        # throwaway sessions the other methods above use, since its history
        # (tool calls included) needs to survive across HTTP requests. Its
        # async engine (asyncpg) binds its connection pool to whichever event
        # loop is running the first time it's actually used - `asyncio.run()`
        # tears its loop down after every call, so a *second* call from a
        # different `asyncio.run()` would hand the pool a dead loop
        # ("attached to a different loop"). A single background thread
        # running one event loop for this provider's whole lifetime is what
        # lets the engine be used safely across many HTTP requests.
        self._agente_session_service = DatabaseSessionService(db_url=settings.adk_session_db_url)
        self._agente_loop = asyncio.new_event_loop()
        self._agente_loop_thread = threading.Thread(
            target=self._agente_loop.run_forever, daemon=True
        )
        self._agente_loop_thread.start()

    def _run_no_loop_do_agente(self, coro):
        """Runs `coro` on the dedicated background loop (see `__init__`) and
        blocks the calling (sync) thread until it's done - the only safe way
        to drive `self._agente_session_service`'s async engine from more than
        one request."""
        return asyncio.run_coroutine_threadsafe(coro, self._agente_loop).result()

    # --- single-turn ADK invocation helper ---

    @staticmethod
    def _run_single_turn_full(
        agent: LlmAgent, prompt: str
    ) -> tuple[str, genai_types.GroundingMetadata | None]:
        """Runs one single-turn invocation of `agent` against `prompt` in a
        throwaway in-memory session, and returns the final response text (the
        schema-validated JSON, when `agent.output_schema` is set) along with
        any grounding metadata attached to that final event (set when `agent`
        has the `google_search` tool, `None` otherwise)."""

        async def _run() -> tuple[str, genai_types.GroundingMetadata | None]:
            runner = InMemoryRunner(agent=agent, app_name=_APP_NAME)
            session = await runner.session_service.create_session(
                app_name=_APP_NAME, user_id=_USER_ID
            )
            content = genai_types.Content(
                role="user", parts=[genai_types.Part.from_text(text=prompt)]
            )
            texto_final = ""
            grounding: genai_types.GroundingMetadata | None = None
            async for event in runner.run_async(
                user_id=_USER_ID, session_id=session.id, new_message=content
            ):
                if event.error_message:
                    raise ProvedorIAIndisponivelException(
                        f"Falha no agente ADK '{agent.name}': {event.error_message}"
                    )
                if event.grounding_metadata is not None:
                    grounding = event.grounding_metadata
                if event.is_final_response() and event.content and event.content.parts:
                    texto_final = "".join(part.text for part in event.content.parts if part.text)
            return texto_final, grounding

        return asyncio.run(_run())

    @staticmethod
    def _run_single_turn(agent: LlmAgent, prompt: str) -> str:
        texto, _grounding = AdkProvider._run_single_turn_full(agent, prompt)
        return texto

    # --- output-schema methods (Fase 1) ---

    @_retry_transient
    def gerar_questionario(
        self,
        conteudo_modulo: str,
        foco_modulo: str | None,
        quantidade: int,
        contexto_conversa: str | None = None,
    ) -> QuestionarioGerado:
        prompt = prompt_gerar_questionario(
            conteudo_modulo, foco_modulo, quantidade, contexto_conversa
        )
        try:
            raw = self._run_single_turn(self._questionario_agent, prompt)
        except ProvedorIAIndisponivelException:
            raise
        except Exception as exc:  # noqa: BLE001 - any ADK/SDK/network failure maps to one domain exception
            raise ProvedorIAIndisponivelException(f"Falha ao gerar questionário: {exc}") from exc

        try:
            schema = QuestionarioSchema.model_validate_json(raw)
        except ValidationError as exc:
            raise ProvedorIAIndisponivelException(
                f"O provedor de IA não retornou o questionário no formato esperado: {exc}"
            ) from exc

        if len(schema.questoes) != quantidade:
            raise ProvedorIAIndisponivelException(
                f"esperava {quantidade} questões, recebeu {len(schema.questoes)}"
            )

        questoes = [
            QuestaoGerada(
                enunciado=self._linha_unica(q.enunciado),
                alternativas=[
                    AlternativaGerada(letra=a.letra, texto=self._linha_unica(a.texto))
                    for a in q.alternativas
                ],
                resposta_correta=q.resposta_correta,
                explicacao=self._linha_unica(q.explicacao),
            )
            for q in schema.questoes
        ]
        return QuestionarioGerado(
            questoes=questoes, modelo=self._settings.GEMINI_MODEL_QUESTIONARIO
        )

    @_retry_transient
    def planejar_modulos(
        self,
        tema_titulo: str,
        tema_descricao: str | None,
        conteudos_fontes: list[str],
        max_modulos: int,
        direcionamento: str | None = None,
    ) -> PlanoModulos:
        prompt = prompt_planejar_modulos(
            tema_titulo, tema_descricao, conteudos_fontes, max_modulos, direcionamento
        )
        try:
            raw = self._run_single_turn(self._planejamento_agent, prompt)
        except ProvedorIAIndisponivelException:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ProvedorIAIndisponivelException(f"Falha ao planejar módulos: {exc}") from exc

        try:
            schema = PlanoModulosSchema.model_validate_json(raw)
        except ValidationError as exc:
            raise ProvedorIAIndisponivelException(
                f"O provedor de IA não retornou o plano de módulos no formato esperado: {exc}"
            ) from exc

        # Defensive cap even though the schema doesn't enforce an upper bound -
        # the model could still ignore the instruction to respect `max_modulos`.
        modulos = [
            ModuloPlanejado(titulo=m.titulo, descricao=m.descricao)
            for m in schema.modulos[:max_modulos]
        ]
        return PlanoModulos(modulos=modulos, modelo=self._settings.GEMINI_MODEL_CONTEUDO)

    @staticmethod
    def _linha_unica(texto: str) -> str:
        """Collapses stray newlines/repeated whitespace - mirrors
        `GeminiProvider._linha_unica`, same rendering requirement downstream."""
        return " ".join(texto.split())

    # --- text-generation methods (Fase 2) ---

    @_retry_transient
    def buscar_fontes(
        self, tema_titulo: str, tema_descricao: str | None, direcionamento: str | None = None
    ) -> list[FonteEncontrada]:
        prompt = prompt_buscar_fontes(tema_titulo, tema_descricao, direcionamento)
        try:
            texto, grounding = self._run_single_turn_full(self._fontes_agent, prompt)
        except ProvedorIAIndisponivelException:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ProvedorIAIndisponivelException(f"Falha ao buscar fontes: {exc}") from exc
        return self._parse_fontes(texto, grounding, tema_titulo)

    @staticmethod
    def _parse_fontes(
        texto: str, grounding: genai_types.GroundingMetadata | None, tema_titulo: str
    ) -> list[FonteEncontrada]:
        chunks = getattr(grounding, "grounding_chunks", None) or []

        fontes: list[FonteEncontrada] = []
        for chunk in chunks:
            web = getattr(chunk, "web", None)
            titulo = getattr(web, "title", None) or f"Fonte sobre {tema_titulo}"
            uri = getattr(web, "uri", None)
            fontes.append(FonteEncontrada(titulo=titulo, origem=uri, conteudo=texto))

        if not fontes:
            # No grounding chunks came back - keep the model's synthesized text as a single
            # source rather than failing the whole pipeline over an empty citations list.
            fontes.append(
                FonteEncontrada(
                    titulo=f"Busca automática: {tema_titulo}", origem=None, conteudo=texto
                )
            )
        return fontes

    @_retry_transient
    def gerar_conteudo_modulo(
        self,
        tema_titulo: str,
        modulo_titulo: str,
        modulo_descricao: str | None,
        conteudos_fontes: list[str],
        direcionamento: str | None = None,
        conteudo_ja_coberto: list[str] | None = None,
        instrucoes_regeneracao: str | None = None,
    ) -> ConteudoGerado:
        prompt = prompt_gerar_conteudo_modulo(
            tema_titulo,
            modulo_titulo,
            modulo_descricao,
            conteudos_fontes,
            direcionamento,
            conteudo_ja_coberto,
            instrucoes_regeneracao,
        )
        try:
            conteudo = self._run_single_turn(self._conteudo_agent, prompt)
        except ProvedorIAIndisponivelException:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ProvedorIAIndisponivelException(f"Falha ao gerar conteúdo: {exc}") from exc

        conteudo = conteudo.strip()
        if not conteudo:
            raise ProvedorIAIndisponivelException("O provedor de IA retornou um conteúdo vazio.")
        return ConteudoGerado(conteudo=conteudo, modelo=self._settings.GEMINI_MODEL_CONTEUDO)

    @_retry_transient
    def gerar_resumo_estudo(
        self,
        historico: list[MensagemAgente],
        materia_nome: str | None,
        tema_titulo: str | None,
        modulo_titulo: str,
        conteudo_modulo: str | None,
    ) -> ResumoEstudoGerado:
        conversa_texto = "\n".join(m.conteudo for m in historico if m.conteudo) or None
        prompt = prompt_resumo_estudo(
            materia_nome, tema_titulo, modulo_titulo, conteudo_modulo, conversa_texto
        )
        try:
            raw = self._run_single_turn(self._resumo_estudo_agent, prompt)
        except ProvedorIAIndisponivelException:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ProvedorIAIndisponivelException(
                f"Falha ao gerar resumo de estudo: {exc}"
            ) from exc

        try:
            schema = ResumoEstudoSchema.model_validate_json(raw)
        except ValidationError as exc:
            raise ProvedorIAIndisponivelException(
                f"O provedor de IA não retornou o resumo no formato esperado: {exc}"
            ) from exc

        return ResumoEstudoGerado(
            visao_geral=self._linha_unica(schema.visao_geral),
            conceitos_chave=[
                ConceitoChave(termo=c.termo, explicacao=self._linha_unica(c.explicacao))
                for c in schema.conceitos_chave
            ],
            pontos_importantes=[self._linha_unica(p) for p in schema.pontos_importantes],
            exemplos=[self._linha_unica(e) for e in schema.exemplos],
            duvidas_do_aluno=[
                DuvidaResolvida(pergunta=d.pergunta, resposta=self._linha_unica(d.resposta))
                for d in schema.duvidas_do_aluno
            ],
            revisao_rapida=[self._linha_unica(r) for r in schema.revisao_rapida],
            fontes=[str(f) for f in schema.fontes],
            modelo=self._settings.GEMINI_MODEL_PROFESSOR,
        )

    # --- admin tool-calling agent (Fase 3) ---

    def conversar_com_ferramentas(
        self, mensagens: list[MensagemAgente], ctx: FerramentaContexto
    ) -> str:
        """Runs the admin agent's full tool-calling loop the native ADK way -
        see `_executar_agente`."""
        agente = LlmAgent(
            name="agente_admin_agent",
            model=self._settings.GEMINI_MODEL_AGENTE,
            instruction=AGENTE_ADMIN_SYSTEM_INSTRUCTION,
            tools=construir_tools(ctx),
        )
        return self._executar_agente(mensagens, ctx.conversa_id, agente)

    def conversar_com_agente_aluno(
        self,
        mensagens: list[MensagemAgente],
        conteudo_modulo: str | None,
        ctx: FerramentaContexto,
    ) -> str:
        """Same as `conversar_com_ferramentas`, the student agent's much
        smaller tool set (`adk_tools.construir_tools_aluno`) and system
        instruction - see `_executar_agente`."""
        agente = LlmAgent(
            name="agente_aluno_agent",
            model=self._settings.GEMINI_MODEL_AGENTE,
            instruction=prompt_agente_aluno_system(conteudo_modulo),
            tools=construir_tools_aluno(ctx),
        )
        return self._executar_agente(mensagens, ctx.conversa_id, agente)

    def _executar_agente(
        self, mensagens: list[MensagemAgente], conversa_id: uuid.UUID, agente: LlmAgent
    ) -> str:
        """A fresh `LlmAgent` (tools closed over that call's `ctx`, see
        `adk_tools.py`) handed to a `Runner` backed by the persistent
        `DatabaseSessionService`, keyed by `conversa_id` - the `Runner`
        auto-invokes tools and manages the whole model<->tool loop
        internally, capped by `RunConfig(max_llm_calls=...)`. Shared by the
        admin and student agents - they differ only in which `LlmAgent`
        (tools + instruction) the caller built."""
        pergunta = mensagens[-1].conteudo or "" if mensagens else ""
        session_id = str(conversa_id)

        runner = Runner(
            app_name=_APP_NAME, agent=agente, session_service=self._agente_session_service
        )

        async def _run() -> str:
            session = await self._agente_session_service.get_session(
                app_name=_APP_NAME, user_id=_USER_ID, session_id=session_id
            )
            if session is None:
                await self._agente_session_service.create_session(
                    app_name=_APP_NAME, user_id=_USER_ID, session_id=session_id
                )
            content = genai_types.Content(
                role="user", parts=[genai_types.Part.from_text(text=pergunta)]
            )
            run_config = RunConfig(max_llm_calls=self._settings.AGENTE_MAX_ITERACOES)
            texto_final = ""
            async for event in runner.run_async(
                user_id=_USER_ID,
                session_id=session_id,
                new_message=content,
                run_config=run_config,
            ):
                if event.error_message:
                    raise ProvedorIAIndisponivelException(
                        f"Falha na conversa com o agente: {event.error_message}"
                    )
                if event.is_final_response() and event.content and event.content.parts:
                    texto_final = "".join(part.text for part in event.content.parts if part.text)
            return texto_final

        try:
            return self._run_no_loop_do_agente(_run())
        except LlmCallsLimitExceededError as exc:
            raise AgenteLimiteExcedidoException() from exc
        except ProvedorIAIndisponivelException:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ProvedorIAIndisponivelException(f"Falha na conversa com o agente: {exc}") from exc

    def obter_historico_sessao(self, conversa_id: uuid.UUID) -> list[MensagemHistorico] | None:
        """Reads the admin agent's ADK session for `conversa_id` and
        translates its `Event`s into `MensagemHistorico` - `None` when no
        session exists yet (e.g. a conversation never sent through
        `AI_PROVIDER=adk`), so the caller can fall back to another source."""

        async def _run() -> list[MensagemHistorico] | None:
            session = await self._agente_session_service.get_session(
                app_name=_APP_NAME, user_id=_USER_ID, session_id=str(conversa_id)
            )
            if session is None:
                return None
            mensagens = []
            for event in session.events:
                mensagem = self._event_para_mensagem_historico(event)
                if mensagem is not None:
                    mensagens.append(mensagem)
            return mensagens

        return self._run_no_loop_do_agente(_run())

    @staticmethod
    def _event_para_mensagem_historico(event) -> MensagemHistorico | None:  # noqa: ANN001
        texto = None
        if event.content and event.content.parts:
            texto = "".join(part.text for part in event.content.parts if part.text) or None

        chamadas = event.get_function_calls()
        respostas = event.get_function_responses()
        chamadas_ferramentas: list[dict] | None = None
        if chamadas:
            chamadas_ferramentas = [
                {"id": c.id, "nome": c.name, "argumentos": dict(c.args or {})} for c in chamadas
            ]
        elif respostas:
            chamadas_ferramentas = [{"id": r.id, "nome": r.name} for r in respostas]

        if texto is None and not chamadas_ferramentas:
            return None

        if event.author == "user":
            papel = "user"
        elif respostas:
            papel = "tool"
        else:
            papel = "assistant"

        return MensagemHistorico(
            id=uuid.uuid5(uuid.NAMESPACE_OID, event.id),
            papel=papel,
            conteudo=texto,
            chamadas_ferramentas=chamadas_ferramentas,
            created_at=datetime.fromtimestamp(event.timestamp, tz=UTC),
        )

    def resumir_conversa(self, mensagens: list[MensagemAgente]) -> str:
        return self._gemini.resumir_conversa(mensagens)

    def gerar_feedback_erros(self, erros: list[ErroQuestao]) -> str:
        return self._gemini.gerar_feedback_erros(erros)
