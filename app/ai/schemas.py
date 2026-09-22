"""Provider-agnostic result shapes returned by any AIProvider strategy.

Services depend on these, never on a concrete provider's SDK response objects -
that's what makes swapping the concrete strategy a no-op for callers.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from app.ai.base import AIProvider
    from app.repositories.materia_repository import MateriaRepository
    from app.repositories.modulo_repository import ModuloRepository
    from app.repositories.questionario_repository import QuestionarioRepository
    from app.repositories.tema_repository import TemaRepository

Letra = Literal["A", "B", "C", "D", "E"]


@dataclass(frozen=True)
class FonteEncontrada:
    titulo: str
    origem: str | None  # URL, when the provider's grounding exposes one
    conteudo: str  # extracted/synthesized text to feed into content generation


@dataclass(frozen=True)
class ConteudoGerado:
    """A módulo's own teaching material, generated from its tema's shared
    fontes plus the módulo's own focus - not shared across módulos."""

    conteudo: str
    modelo: str


@dataclass(frozen=True)
class AlternativaGerada:
    letra: Letra
    texto: str


@dataclass(frozen=True)
class QuestaoGerada:
    enunciado: str
    alternativas: list[AlternativaGerada]
    resposta_correta: Letra
    explicacao: str


@dataclass(frozen=True)
class QuestionarioGerado:
    questoes: list[QuestaoGerada]
    modelo: str


@dataclass(frozen=True)
class ErroQuestao:
    """One wrong answer of an attempt, fed to `AIProvider.gerar_feedback_erros`
    - only the data of the question the student missed, never the whole
    attempt or the correct answers of the ones they got right."""

    enunciado: str
    resposta_escolhida: Letra
    resposta_correta: Letra
    explicacao: str | None = None


@dataclass(frozen=True)
class ModuloPlanejado:
    titulo: str
    descricao: str


@dataclass(frozen=True)
class PlanoModulos:
    """An ordered outline for splitting a tema into módulos - each entry's
    `descricao` becomes that módulo's own focus, fed into its content
    generation exactly like an admin-authored one would be."""

    modulos: list[ModuloPlanejado]
    modelo: str


@dataclass(frozen=True)
class FerramentaDeclaracao:
    """One tool the agent may call - name, description, and a JSON-schema-shaped
    parameters dict, in the same vocabulary providers use for function calling."""

    nome: str
    descricao: str
    parametros: dict[str, Any]


@dataclass(frozen=True)
class ChamadaFerramenta:
    id: str
    nome: str
    argumentos: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RespostaAgente:
    """Either a final text reply, or one/more tool calls the agent wants
    executed before it can produce a final reply - never both populated."""

    texto: str | None
    chamadas_ferramentas: list[ChamadaFerramenta]


@dataclass(frozen=True)
class MensagemAgente:
    """Provider-agnostic chat turn, built from stored `Mensagem` rows and fed
    back into `conversar_com_ferramentas` as conversation history. A concrete
    provider translates this into its own message/content format."""

    papel: Literal["user", "assistant", "tool"]
    conteudo: str | None = None
    chamadas_ferramentas: list[ChamadaFerramenta] = field(default_factory=list)
    chamada_ferramenta_id: str | None = (
        None  # set on a "tool" message: which call this is the result of
    )
    nome_ferramenta: str | None = None  # set on a "tool" message


@dataclass
class FerramentaContexto:
    """Per-request context the admin agent's tools need to execute - repos,
    the AI provider itself (some tools trigger further AI generation, e.g.
    `criar_tema` kicking off `buscar_fontes`), the questionário pool size, and
    the id of the `Conversa` this turn belongs to. A provider that keeps its
    own persistent conversation session (e.g. `AdkProvider`'s ADK
    `SessionService`) keys that session off `conversa_id`."""

    materia_repo: "MateriaRepository"
    tema_repo: "TemaRepository"
    modulo_repo: "ModuloRepository"
    questionario_repo: "QuestionarioRepository"
    ai_provider: "AIProvider"
    pool_size: int
    conversa_id: uuid.UUID


@dataclass(frozen=True)
class MensagemHistorico:
    """One turn of a persisted conversation, read back out of wherever a
    provider actually keeps history - e.g. `AdkProvider` translates ADK
    `Event`s into these to serve the admin chat's history endpoint without
    that endpoint needing to know anything about the ADK's own types."""

    id: uuid.UUID
    papel: Literal["user", "assistant", "tool"]
    conteudo: str | None
    chamadas_ferramentas: list[dict[str, Any]] | None
    created_at: datetime
