"""Strategy pattern: the AIProvider interface.

`fonte_pipeline`/`conteudo_modulo_pipeline`/`questionario_pipeline`/`agent_service`
depend only on this interface, so swapping providers later (or A/B testing
one) means writing one new class here - zero changes to business logic.
`GeminiProvider` is today's concrete strategy; `tests/fakes/fake_ai_provider.py`
is the test double.
"""

from abc import ABC, abstractmethod

from app.ai.schemas import (
    ConteudoGerado,
    FerramentaContexto,
    FonteEncontrada,
    MensagemAgente,
    PlanoModulos,
    QuestionarioGerado,
)


class AIProvider(ABC):
    @abstractmethod
    def buscar_fontes(
        self, tema_titulo: str, tema_descricao: str | None, direcionamento: str | None = None
    ) -> list[FonteEncontrada]:
        """Find a handful of relevant sources for a tema (grounded web search) -
        called once per tema, reused by every módulo underneath it."""

    @abstractmethod
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
        """Synthesize one módulo's own teaching material from the tema's
        shared source texts plus this módulo's own focus. `conteudo_ja_coberto`
        is the actual content of earlier módulos (by ordem) under the same
        tema, so this módulo continues rather than repeating them.
        `instrucoes_regeneracao` is admin feedback on what to change (only set
        when regenerating, e.g. "deixe mais curto", "adicione mais exemplos")."""

    @abstractmethod
    def gerar_questionario(
        self,
        conteudo_modulo: str,
        foco_modulo: str | None,
        quantidade: int,
        contexto_conversa: str | None = None,
    ) -> QuestionarioGerado:
        """Generate a pool of multiple-choice questions (5 alternatives, 1
        correct each). `contexto_conversa` is optional grounding from a
        student's own chat about this módulo - set only by the on-demand
        personalized quiz (`questionario_personalizado_service`), never by
        the admin's own pool generation."""

    @abstractmethod
    def planejar_modulos(
        self,
        tema_titulo: str,
        tema_descricao: str | None,
        conteudos_fontes: list[str],
        max_modulos: int,
        direcionamento: str | None = None,
    ) -> PlanoModulos:
        """Propose an ordered, non-overlapping breakdown of a tema's content
        into at most `max_modulos` módulos - used by the auto-split action."""

    @abstractmethod
    def conversar_com_ferramentas(
        self, mensagens: list[MensagemAgente], ctx: FerramentaContexto
    ) -> str:
        """Runs the admin agent's full tool-calling loop - as many
        model<->tool round trips as needed, up to the provider's own
        iteration cap - and returns the final text reply. `ctx` carries what
        the tools need to actually execute (repos, the AI provider, the
        questionário pool size, the conversation id); the provider owns
        building/invoking the tools now, not just declaring them."""

    @abstractmethod
    def responder_pergunta_aluno(
        self,
        historico: list[MensagemAgente],
        pergunta: str,
        conteudo_modulo: str | None = None,
    ) -> str:
        """Grounded Q&A for a student - deliberately NOT tool-calling (unlike
        `conversar_com_ferramentas`): the model sees only `conteudo_modulo`
        (the módulo the student is currently studying, if any) plus the
        conversation history, and returns its reply text directly. No agent
        loop, no function calls, no access to any other data."""

    @abstractmethod
    def resumir_conversa(self, mensagens: list[MensagemAgente]) -> str:
        """Summarizes a student/teacher conversation into a short digest for
        the student's conversation-summary history."""
