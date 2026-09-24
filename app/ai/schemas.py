"""Provider-agnostic result shapes returned by any AIProvider strategy.

Services depend on these, never on a concrete provider's SDK response objects -
that's what makes swapping the concrete strategy a no-op for callers.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from fastapi import BackgroundTasks

if TYPE_CHECKING:
    from app.ai.base import AIProvider
    from app.repositories.materia_repository import MateriaRepository
    from app.repositories.modulo_repository import ModuloRepository
    from app.repositories.progresso_repository import ProgressoRepository
    from app.repositories.questionario_repository import QuestionarioRepository
    from app.repositories.tema_repository import TemaRepository
    from app.repositories.voto_repository import VotoRepository
    from app.repositories.xp_repository import XpRepository

Letra = Literal["A", "B", "C", "D", "E"]


@dataclass(frozen=True)
class ReferenciaFonte:
    """One web page a grounded search cited. `titulo` is what a student should
    see (the grounding API only exposes the site's domain, e.g. `ufpel.edu.br`);
    `origem` is the provider's link, kept for traceability but not shown - for
    Gemini it is a short-lived Google redirect, not the page's real address."""

    titulo: str
    origem: str | None


@dataclass(frozen=True)
class FonteEncontrada:
    titulo: str
    origem: str | None  # URL, when the provider's grounding exposes one
    conteudo: str  # extracted/synthesized text to feed into content generation
    # The pages the search cited. The grounded search yields ONE synthesized
    # text for all of them, so it is stored once, with these alongside.
    referencias: tuple[ReferenciaFonte, ...] = ()


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
class ConceitoChave:
    termo: str
    explicacao: str


@dataclass(frozen=True)
class DuvidaResolvida:
    pergunta: str
    resposta: str


@dataclass(frozen=True)
class ResumoEstudoGerado:
    """A módulo-scoped study summary, filled into the fixed template the
    Biblioteca renders and the PDF export is built from. Provider-agnostic -
    each provider maps its own structured-output schema into this shape."""

    visao_geral: str
    conceitos_chave: list[ConceitoChave]
    pontos_importantes: list[str]
    exemplos: list[str]
    duvidas_do_aluno: list[DuvidaResolvida]
    revisao_rapida: list[str]
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
    """Per-request context an agent's tools need to execute - repos, the AI
    provider itself (some tools trigger further AI generation, e.g.
    `criar_tema` kicking off `buscar_fontes`), the questionário pool size,
    the calling user's id, and the id of the `Conversa` this turn belongs
    to. A provider that keeps its own persistent conversation session (e.g.
    `AdkProvider`'s ADK `SessionService`) keys that session off
    `conversa_id`. Shared by both the admin agent (`agent_tools.py`) and the
    student agent (`agent_tools_aluno.py`) - `xp_repo`/`progresso_repo`/
    `voto_repo`/`background_tasks` exist for the latter's tools
    (`meu_desempenho`, `criar_minha_trilha`) and are simply unused by the
    admin's; splitting into two context types wasn't worth it for the size
    of the difference."""

    materia_repo: "MateriaRepository"
    tema_repo: "TemaRepository"
    modulo_repo: "ModuloRepository"
    questionario_repo: "QuestionarioRepository"
    xp_repo: "XpRepository"
    progresso_repo: "ProgressoRepository"
    voto_repo: "VotoRepository"
    ai_provider: "AIProvider"
    pool_size: int
    user_id: str
    conversa_id: uuid.UUID
    background_tasks: BackgroundTasks | None = None
    # Output, not input: `criar_minha_trilha` (agent_tools_aluno.py) writes
    # these when it actually creates something, so the router can hand the
    # ids back to the frontend (`ChatRespostaOut`) without the client having
    # to parse them out of the model's free-text reply. `ctx` is the same
    # object instance the whole way down the tool-calling loop, so a tool
    # writing to it is visible to the router after the call returns -
    # no AIProvider interface change needed for this. Never set by any
    # admin tool; stays `None` on the admin chat's response.
    materia_criada_id: uuid.UUID | None = None
    tema_criado_id: uuid.UUID | None = None


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
