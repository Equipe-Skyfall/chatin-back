"""Domain exception hierarchy.

Routers and services raise these instead of building `HTTPException` by hand.
`core.exception_handlers` maps the base class to an HTTP response in one place.
"""

from datetime import datetime
from uuid import UUID

from app.core.falha_ia import TipoFalhaIA, classificar_falha


class AppException(Exception):
    status_code: int = 500
    detail: str = "Erro interno."
    # Stable, machine-readable identifier the frontend can branch on (the
    # `detail` text is for people and may change). `None` when there is nothing
    # specific to branch on.
    code: str | None = None
    # Extra fields merged into the JSON body next to `detail`/`code`.
    extra: dict | None = None

    def __init__(self, detail: str | None = None):
        if detail is not None:
            self.detail = detail
        super().__init__(self.detail)


# --- 404s ---


class RecursoNaoEncontradoException(AppException):
    status_code = 404
    detail = "Recurso não encontrado."


class MateriaNaoEncontradaException(RecursoNaoEncontradoException):
    def __init__(self, materia_id: UUID):
        super().__init__(f"Matéria '{materia_id}' não encontrada.")


class TemaNaoEncontradoException(RecursoNaoEncontradoException):
    def __init__(self, tema_id: UUID):
        super().__init__(f"Tema '{tema_id}' não encontrado.")


class ModuloNaoEncontradoException(RecursoNaoEncontradoException):
    def __init__(self, modulo_id: UUID):
        super().__init__(f"Módulo '{modulo_id}' não encontrado.")


class QuestionarioNaoEncontradoException(RecursoNaoEncontradoException):
    def __init__(self, questionario_id: UUID):
        super().__init__(f"Questionário '{questionario_id}' não encontrado.")


class TentativaNaoEncontradaException(RecursoNaoEncontradoException):
    def __init__(self, tentativa_id: UUID):
        super().__init__(f"Tentativa '{tentativa_id}' não encontrada.")


class QuestaoNaoEncontradaException(RecursoNaoEncontradoException):
    def __init__(self, questao_id: UUID):
        super().__init__(f"Questão '{questao_id}' não encontrada.")


class ConteudoModuloNaoEncontradoException(RecursoNaoEncontradoException):
    detail = "Este módulo ainda não possui conteúdo gerado."


class ConversaNaoEncontradaException(RecursoNaoEncontradoException):
    def __init__(self, conversa_id: UUID):
        super().__init__(f"Conversa '{conversa_id}' não encontrada.")


class ResumoEstudoNaoEncontradoException(RecursoNaoEncontradoException):
    def __init__(self, resumo_id: UUID):
        super().__init__(f"Resumo de estudo '{resumo_id}' não encontrado.")


# --- 400s / 422s (bad request / invalid state) ---


class TemaNaoProntoException(AppException):
    status_code = 400
    detail = "O tema ainda não está pronto (fontes não encontradas)."


class ConteudoIndisponivelException(AppException):
    status_code = 400
    detail = "Conteúdo ainda não disponível para este recurso."


class ResumoEstudoSemModuloException(AppException):
    status_code = 400
    detail = "Só é possível gerar um resumo de estudo para conversas vinculadas a um módulo."


class RespostaInvalidaException(AppException):
    status_code = 400
    detail = "Resposta inválida para esta tentativa."


class SubmissaoIncompletaException(AppException):
    status_code = 422
    detail = "Todas as questões da tentativa devem ser respondidas."


class TentativaJaFinalizadaException(AppException):
    status_code = 400
    detail = "Esta tentativa já foi respondida."


class ModulosJaExistemException(AppException):
    status_code = 400
    detail = (
        "Este tema já possui módulos - a divisão automática só é permitida quando o tema "
        "ainda não tem nenhum módulo criado."
    )


class OrdemDuplicadaException(AppException):
    status_code = 409

    def __init__(self, ordem: int):
        super().__init__(
            f"Já existe um item com ordem={ordem} neste mesmo nível - escolha outra ordem "
            "ou omita o campo para adicionar ao final."
        )


class QuestionarioJaExisteException(AppException):
    status_code = 409
    detail = (
        "Este módulo já possui um questionário - adicione questões a ele "
        "ou remova-o antes de criar outro."
    )


class QuestionarioSemQuestoesException(AppException):
    status_code = 409
    detail = (
        "Um questionário precisa ter ao menos uma questão - para removê-las todas, "
        "remova o questionário."
    )


class LimiteQuestoesExcedidoException(AppException):
    status_code = 400

    def __init__(self, limite: int):
        super().__init__(f"Um questionário pode ter no máximo {limite} questões.")


class ConversaOcupadaException(AppException):
    status_code = 409
    detail = "Já existe uma mensagem sendo processada nesta conversa - aguarde a resposta anterior."


# --- 403s (access / lock state) ---


class AcessoNegadoException(AppException):
    status_code = 403
    detail = "Acesso negado."


class TemaBloqueadoException(AppException):
    status_code = 403
    detail = "Este tema ainda está bloqueado."


class ModuloBloqueadoException(AppException):
    status_code = 403
    detail = "Este módulo ainda está bloqueado."


class LicaoNaoIniciadaException(AppException):
    status_code = 403
    detail = "Comece a lição deste módulo no chat antes de fazer o questionário."
    code = "LICAO_NAO_INICIADA"

    def __init__(self, modulo_id: UUID):
        super().__init__()
        self.extra = {"modulo_id": str(modulo_id)}


class VotoEmConteudoGlobalException(AppException):
    status_code = 400
    detail = (
        "Não é possível votar no currículo oficial - votos só existem em trilhas criadas "
        "por alunos."
    )


# --- 401 (auth) ---


class NaoAutenticadoException(AppException):
    status_code = 401
    detail = "Credenciais inválidas ou ausentes."


# --- 502 (upstream AI provider failures) ---


class ProvedorIAIndisponivelException(AppException):
    """The AI provider failed. What the student sees (`detail`) is always a
    friendly sentence; the technical reason passed to the constructor stays in
    `motivo` for the logs and is never sent to the client. Status and `code`
    depend on what went wrong, read from the original error (`__cause__`)."""

    def __init__(self, motivo: str | None = None):
        self.motivo = motivo
        Exception.__init__(self, motivo or self.detail)

    @property
    def tipo(self) -> TipoFalhaIA:
        return classificar_falha(self.__cause__)

    @property
    def status_code(self) -> int:  # type: ignore[override]
        return 504 if self.tipo is TipoFalhaIA.TIMEOUT else 503

    @property
    def code(self) -> str:  # type: ignore[override]
        return "ia_timeout" if self.tipo is TipoFalhaIA.TIMEOUT else "ia_indisponivel"

    @property
    def detail(self) -> str:  # type: ignore[override]
        if self.tipo is TipoFalhaIA.TIMEOUT:
            return "O assistente de IA demorou demais para responder. Tente novamente em instantes."
        return (
            "O assistente de IA está indisponível no momento. "
            "O restante da plataforma continua funcionando; tente novamente em instantes."
        )


class GeracaoConteudoFalhouException(AppException):
    status_code = 502

    def __init__(self, motivo: str):
        super().__init__(f"Falha ao gerar conteúdo: {motivo}")


class AgenteLimiteExcedidoException(AppException):
    status_code = 502
    detail = "O agente excedeu o número máximo de chamadas de ferramentas para esta mensagem."


class LimiteTrilhasMensalExcedidoException(AppException):
    status_code = 403
    code = "LIMITE_TRILHAS_MENSAL"

    def __init__(self, limite: int, reseta_em: datetime):
        super().__init__(
            f"Você já criou {limite} trilhas neste mês. O limite renova em "
            f"{reseta_em.strftime('%d/%m/%Y')}."
        )
        self.extra = {"limite": limite, "usadas": limite, "reseta_em": reseta_em.isoformat()}


class NaoPodePararDeEstudarException(AppException):
    status_code = 409
    detail = "Currículo verificado e trilhas criadas por você não saem da sua lista de estudos."
