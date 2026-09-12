"""The tool-calling loop for the admin content-creation chat.

Each turn: persist the user's message, ask the AI provider for a reply, and if
it requests tool calls, dispatch them via `agent_tools.executar_ferramenta`,
persist both the assistant's tool-call message and each tool's result, and
loop - until the provider returns a final text reply (or a safety cap on
round-trips is hit).
"""

from app.ai.base import AIProvider
from app.ai.schemas import ChamadaFerramenta, MensagemAgente
from app.core.exceptions import AgenteLimiteExcedidoException
from app.models.conversa import (
    PAPEL_ASSISTENTE,
    PAPEL_FERRAMENTA,
    PAPEL_USUARIO,
    Conversa,
    Mensagem,
)
from app.repositories.conversa_repository import ConversaRepository
from app.services.agent_tools import TOOLS, FerramentaContexto, executar_ferramenta


def _mensagem_para_agente(mensagem: Mensagem) -> MensagemAgente:
    if mensagem.papel == PAPEL_ASSISTENTE:
        chamadas = [
            ChamadaFerramenta(id=c["id"], nome=c["nome"], argumentos=c.get("argumentos", {}))
            for c in (mensagem.chamadas_ferramentas or [])
        ]
        return MensagemAgente(
            papel=PAPEL_ASSISTENTE, conteudo=mensagem.conteudo, chamadas_ferramentas=chamadas
        )
    if mensagem.papel == PAPEL_FERRAMENTA:
        info = (mensagem.chamadas_ferramentas or [{}])[0]
        return MensagemAgente(
            papel=PAPEL_FERRAMENTA,
            conteudo=mensagem.conteudo,
            nome_ferramenta=info.get("nome"),
            chamada_ferramenta_id=info.get("id"),
        )
    return MensagemAgente(papel=PAPEL_USUARIO, conteudo=mensagem.conteudo)


def processar_mensagem(
    conversa: Conversa,
    texto_usuario: str,
    conversa_repo: ConversaRepository,
    ctx: FerramentaContexto,
    ai_provider: AIProvider,
    max_iteracoes: int,
) -> str:
    """Persists the user's message, runs the tool-calling loop (persisting
    every assistant/tool turn along the way), and returns the final reply."""

    def _salvar(papel: str, conteudo: str | None, chamadas: list[dict] | None) -> None:
        ordem = conversa_repo.proxima_ordem(conversa.id)
        conversa_repo.add_mensagem(
            Mensagem(
                conversa_id=conversa.id,
                papel=papel,
                conteudo=conteudo,
                chamadas_ferramentas=chamadas,
                ordem=ordem,
            )
        )
        conversa_repo.commit()

    _salvar(PAPEL_USUARIO, texto_usuario, None)
    recarregada = conversa_repo.get_with_mensagens(conversa.id)
    historico = [_mensagem_para_agente(m) for m in recarregada.mensagens]

    for _ in range(max_iteracoes):
        resposta = ai_provider.conversar_com_ferramentas(historico, TOOLS)

        if resposta.chamadas_ferramentas:
            chamadas_serializadas = [
                {"id": c.id, "nome": c.nome, "argumentos": c.argumentos}
                for c in resposta.chamadas_ferramentas
            ]
            _salvar(PAPEL_ASSISTENTE, resposta.texto, chamadas_serializadas)
            historico.append(
                MensagemAgente(
                    papel=PAPEL_ASSISTENTE,
                    conteudo=resposta.texto,
                    chamadas_ferramentas=resposta.chamadas_ferramentas,
                )
            )

            for chamada in resposta.chamadas_ferramentas:
                resultado = executar_ferramenta(chamada.nome, chamada.argumentos, ctx)
                _salvar(PAPEL_FERRAMENTA, resultado, [{"id": chamada.id, "nome": chamada.nome}])
                historico.append(
                    MensagemAgente(
                        papel=PAPEL_FERRAMENTA,
                        conteudo=resultado,
                        nome_ferramenta=chamada.nome,
                        chamada_ferramenta_id=chamada.id,
                    )
                )
            continue

        _salvar(PAPEL_ASSISTENTE, resposta.texto, None)
        conversa_repo.tocar(conversa.id)
        conversa_repo.commit()
        return resposta.texto or ""

    raise AgenteLimiteExcedidoException()
