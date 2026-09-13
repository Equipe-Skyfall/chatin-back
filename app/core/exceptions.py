"""Domain exception hierarchy.

Routers and services raise these instead of building `HTTPException` by hand.
`core.exception_handlers` maps the base class to an HTTP response in one place.
"""

from uuid import UUID


class AppException(Exception):
    status_code: int = 500
    detail: str = "Erro interno."

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


# --- 400s / 422s (bad request / invalid state) ---


class TemaNaoProntoException(AppException):
    status_code = 400
    detail = "O tema ainda não está pronto (fontes não encontradas)."


class ConteudoIndisponivelException(AppException):
    status_code = 400
    detail = "Conteúdo ainda não disponível para este recurso."


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


# --- 401 (auth) ---


class NaoAutenticadoException(AppException):
    status_code = 401
    detail = "Credenciais inválidas ou ausentes."


# --- 502 (upstream AI provider failures) ---


class ProvedorIAIndisponivelException(AppException):
    status_code = 502
    detail = "O provedor de IA falhou ao gerar o conteúdo."


class GeracaoConteudoFalhouException(AppException):
    status_code = 502

    def __init__(self, motivo: str):
        super().__init__(f"Falha ao gerar conteúdo: {motivo}")


class AgenteLimiteExcedidoException(AppException):
    status_code = 502
    detail = "O agente excedeu o número máximo de chamadas de ferramentas para esta mensagem."
