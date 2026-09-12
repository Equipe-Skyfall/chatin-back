"""Concrete `AIProvider` strategy backed by the Google Agent Development Kit
(`google-adk`) - Fase 1 of the ADK migration (see the migration plan).

Only `gerar_questionario` and `planejar_modulos` run through ADK so far, using
`LlmAgent(output_schema=<pydantic model>)` (`app/ai/adk_schemas.py`) in place
of Gemini's own uppercase-typed JSON schema dialect (`gemini_schemas.py`) and
the manual `json.loads` + retry-with-reinforcement-prompt parsing that lived
in `GeminiProvider`. The `output_schema` guarantees a well-formed result by
construction (including the "exactly 5 alternatives" constraint, via
Pydantic's `Field(min_length=5, max_length=5)`), so there is no retry-on-
malformed-output path here.

The remaining five `AIProvider` methods still delegate, by composition, to an
internal `GeminiProvider` instance - they migrate in later phases. This keeps
`AI_PROVIDER=adk` fully functional in production from Fase 1 onward, with
`AI_PROVIDER=gemini` remaining available as an instant rollback.
"""

import asyncio
import logging

from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.genai import types as genai_types
from pydantic import ValidationError
from tenacity import retry, stop_after_attempt, wait_exponential

from app.ai.adk_schemas import PlanoModulosSchema, QuestionarioSchema
from app.ai.base import AIProvider
from app.ai.gemini_provider import GeminiProvider
from app.ai.prompts import prompt_gerar_questionario, prompt_planejar_modulos
from app.ai.schemas import (
    AlternativaGerada,
    ConteudoGerado,
    FerramentaDeclaracao,
    FonteEncontrada,
    MensagemAgente,
    ModuloPlanejado,
    PlanoModulos,
    QuestaoGerada,
    QuestionarioGerado,
    RespostaAgente,
)
from app.config import Settings
from app.core.exceptions import ProvedorIAIndisponivelException

logger = logging.getLogger(__name__)

_retry_transient = retry(
    stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8), reraise=True
)

_APP_NAME = "chatin"
_USER_ID = "system"  # single-turn, stateless calls - no per-user session reuse yet (Fase 1)


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

    # --- single-turn ADK invocation helper ---

    @staticmethod
    def _run_single_turn(agent: LlmAgent, prompt: str) -> str:
        """Runs one single-turn invocation of `agent` against `prompt` in a
        throwaway in-memory session, and returns the final response text (the
        schema-validated JSON, when `agent.output_schema` is set)."""

        async def _run() -> str:
            runner = InMemoryRunner(agent=agent, app_name=_APP_NAME)
            session = await runner.session_service.create_session(
                app_name=_APP_NAME, user_id=_USER_ID
            )
            content = genai_types.Content(
                role="user", parts=[genai_types.Part.from_text(text=prompt)]
            )
            texto_final = ""
            async for event in runner.run_async(
                user_id=_USER_ID, session_id=session.id, new_message=content
            ):
                if event.error_message:
                    raise ProvedorIAIndisponivelException(
                        f"Falha no agente ADK '{agent.name}': {event.error_message}"
                    )
                if event.is_final_response() and event.content and event.content.parts:
                    texto_final = "".join(
                        part.text for part in event.content.parts if part.text
                    )
            return texto_final

        return asyncio.run(_run())

    # --- output-schema methods (Fase 1) ---

    @_retry_transient
    def gerar_questionario(
        self, conteudo_modulo: str, foco_modulo: str | None, quantidade: int
    ) -> QuestionarioGerado:
        prompt = prompt_gerar_questionario(conteudo_modulo, foco_modulo, quantidade)
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

    # --- not yet migrated: delegate to GeminiProvider (Fases 2-3) ---

    def buscar_fontes(
        self, tema_titulo: str, tema_descricao: str | None, direcionamento: str | None = None
    ) -> list[FonteEncontrada]:
        return self._gemini.buscar_fontes(tema_titulo, tema_descricao, direcionamento)

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
        return self._gemini.gerar_conteudo_modulo(
            tema_titulo,
            modulo_titulo,
            modulo_descricao,
            conteudos_fontes,
            direcionamento,
            conteudo_ja_coberto,
            instrucoes_regeneracao,
        )

    def conversar_com_ferramentas(
        self, mensagens: list[MensagemAgente], ferramentas: list[FerramentaDeclaracao]
    ) -> RespostaAgente:
        return self._gemini.conversar_com_ferramentas(mensagens, ferramentas)

    def responder_pergunta_aluno(
        self,
        historico: list[MensagemAgente],
        pergunta: str,
        conteudo_modulo: str | None = None,
    ) -> str:
        return self._gemini.responder_pergunta_aluno(historico, pergunta, conteudo_modulo)

    def resumir_conversa(self, mensagens: list[MensagemAgente]) -> str:
        return self._gemini.resumir_conversa(mensagens)
