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
    FerramentaDeclaracao,
    FonteEncontrada,
    MensagemAgente,
    PlanoModulos,
    QuestionarioGerado,
    RespostaAgente,
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
        self, conteudo_modulo: str, foco_modulo: str | None, quantidade: int
    ) -> QuestionarioGerado:
        """Generate a pool of multiple-choice questions (5 alternatives, 1 correct each)."""

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
        self, mensagens: list[MensagemAgente], ferramentas: list[FerramentaDeclaracao]
    ) -> RespostaAgente:
        """One turn of a tool-calling chat: given the conversation so far and
        the tools available, return either a final text reply or the tool
        call(s) the agent wants executed next."""
