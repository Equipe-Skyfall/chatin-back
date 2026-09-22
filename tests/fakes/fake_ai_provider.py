from app.ai.base import AIProvider
from app.ai.schemas import (
    AlternativaGerada,
    ConceitoChave,
    ConteudoGerado,
    DuvidaResolvida,
    FerramentaContexto,
    FonteEncontrada,
    MensagemAgente,
    ModuloPlanejado,
    PlanoModulos,
    QuestaoGerada,
    QuestionarioGerado,
    ResumoEstudoGerado,
)


class FakeAIProvider(AIProvider):
    """No network, canned data, with call counters - used to assert that a
    pipeline calls the AI provider exactly the number of times it should
    (e.g. once per módulo, never again per attempt).
    """

    def __init__(self):
        self.buscar_fontes_calls = 0
        self.gerar_conteudo_modulo_calls = 0
        self.gerar_questionario_calls = 0
        self.planejar_modulos_calls = 0
        self.conversar_com_ferramentas_calls = 0
        self.falhar_buscar_fontes = False
        self.falhar_gerar_conteudo_modulo = False
        self.falhar_gerar_questionario = False
        self.falhar_planejar_modulos = False
        self.direcionamentos_recebidos: list[str | None] = []
        self.contextos_conversa_recebidos: list[str | None] = []
        self.conteudo_ja_coberto_recebido: list[list[str] | None] = []
        self.instrucoes_regeneracao_recebidas: list[str | None] = []
        self.plano_fixo: PlanoModulos | None = None
        self.resposta_agente_fixa: str | None = None
        self.falhar_conversar_com_ferramentas = False
        self.ctx_recebido: FerramentaContexto | None = None
        self.conversar_com_agente_aluno_calls = 0
        self.resumir_conversa_calls = 0
        self.conteudos_modulo_recebidos: list[str | None] = []
        self.historicos_recebidos: list[list[MensagemAgente]] = []
        self.falhar_conversar_com_agente_aluno = False
        self.falhar_resumir_conversa = False
        self.resposta_agente_aluno_fixa: str | None = None
        self.gerar_resumo_estudo_calls = 0
        self.falhar_gerar_resumo_estudo = False
        self.resumos_estudo_recebidos: list[dict] = []

    def buscar_fontes(
        self, tema_titulo: str, tema_descricao: str | None, direcionamento: str | None = None
    ) -> list[FonteEncontrada]:
        self.buscar_fontes_calls += 1
        self.direcionamentos_recebidos.append(direcionamento)
        if self.falhar_buscar_fontes:
            raise RuntimeError("falha simulada na busca de fontes")
        return [
            FonteEncontrada(
                titulo=f"Fonte sobre {tema_titulo}",
                origem="https://example.org",
                conteudo="Conteúdo de teste.",
            )
        ]

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
        self.gerar_conteudo_modulo_calls += 1
        self.direcionamentos_recebidos.append(direcionamento)
        self.conteudo_ja_coberto_recebido.append(conteudo_ja_coberto)
        self.instrucoes_regeneracao_recebidas.append(instrucoes_regeneracao)
        if self.falhar_gerar_conteudo_modulo:
            raise RuntimeError("falha simulada na geração de conteúdo")
        conteudo = f"Conteúdo de teste do módulo '{modulo_titulo}' (tema: {tema_titulo})."
        if instrucoes_regeneracao:
            conteudo += f" [ajustado: {instrucoes_regeneracao}]"
        return ConteudoGerado(conteudo=conteudo, modelo="fake-model")

    def gerar_questionario(
        self,
        conteudo_modulo: str,
        foco_modulo: str | None,
        quantidade: int,
        contexto_conversa: str | None = None,
    ) -> QuestionarioGerado:
        self.gerar_questionario_calls += 1
        self.contextos_conversa_recebidos.append(contexto_conversa)
        if self.falhar_gerar_questionario:
            raise RuntimeError("falha simulada na geração do questionário")
        questoes = [
            QuestaoGerada(
                enunciado=f"Questão de teste {i}",
                alternativas=[
                    AlternativaGerada(letra=letra, texto=f"Alternativa {letra}")
                    for letra in "ABCDE"
                ],
                resposta_correta="A",
                explicacao="Explicação de teste.",
            )
            for i in range(quantidade)
        ]
        return QuestionarioGerado(questoes=questoes, modelo="fake-model")

    def planejar_modulos(
        self,
        tema_titulo: str,
        tema_descricao: str | None,
        conteudos_fontes: list[str],
        max_modulos: int,
        direcionamento: str | None = None,
    ) -> PlanoModulos:
        self.planejar_modulos_calls += 1
        self.direcionamentos_recebidos.append(direcionamento)
        if self.falhar_planejar_modulos:
            raise RuntimeError("falha simulada no planejamento de módulos")
        if self.plano_fixo is not None:
            return self.plano_fixo
        modulos = [
            ModuloPlanejado(titulo=f"Parte {i + 1}", descricao=f"Foco da parte {i + 1}")
            for i in range(min(3, max_modulos))
        ]
        return PlanoModulos(modulos=modulos, modelo="fake-model")

    def conversar_com_ferramentas(
        self, mensagens: list[MensagemAgente], ctx: FerramentaContexto
    ) -> str:
        self.conversar_com_ferramentas_calls += 1
        self.ctx_recebido = ctx
        if self.falhar_conversar_com_ferramentas:
            raise RuntimeError("falha simulada na conversa com ferramentas")
        if self.resposta_agente_fixa is not None:
            return self.resposta_agente_fixa
        return "Resposta de teste."

    def conversar_com_agente_aluno(
        self,
        mensagens: list[MensagemAgente],
        conteudo_modulo: str | None,
        ctx: FerramentaContexto,
    ) -> str:
        self.conversar_com_agente_aluno_calls += 1
        self.conteudos_modulo_recebidos.append(conteudo_modulo)
        self.historicos_recebidos.append(list(mensagens))
        self.ctx_recebido = ctx
        if self.falhar_conversar_com_agente_aluno:
            raise RuntimeError("falha simulada na conversa com o agente do aluno")
        if self.resposta_agente_aluno_fixa is not None:
            return self.resposta_agente_aluno_fixa
        pergunta = mensagens[-1].conteudo if mensagens else ""
        return f"Resposta de teste para: {pergunta}"

    def resumir_conversa(self, mensagens: list[MensagemAgente]) -> str:
        self.resumir_conversa_calls += 1
        if self.falhar_resumir_conversa:
            raise RuntimeError("falha simulada ao resumir conversa")
        return "Resumo de teste da conversa."

    def gerar_resumo_estudo(
        self,
        historico: list[MensagemAgente],
        materia_nome: str | None,
        tema_titulo: str | None,
        modulo_titulo: str,
        conteudo_modulo: str | None,
    ) -> ResumoEstudoGerado:
        self.gerar_resumo_estudo_calls += 1
        self.resumos_estudo_recebidos.append(
            {
                "historico": list(historico),
                "materia_nome": materia_nome,
                "tema_titulo": tema_titulo,
                "modulo_titulo": modulo_titulo,
                "conteudo_modulo": conteudo_modulo,
            }
        )
        if self.falhar_gerar_resumo_estudo:
            raise RuntimeError("falha simulada ao gerar resumo de estudo")
        return ResumoEstudoGerado(
            visao_geral=f"Visão geral de {modulo_titulo}.",
            conceitos_chave=[ConceitoChave(termo="Conceito", explicacao="Explicação de teste.")],
            pontos_importantes=["Ponto importante de teste."],
            exemplos=["Exemplo de teste."],
            duvidas_do_aluno=[DuvidaResolvida(pergunta="Dúvida?", resposta="Resposta de teste.")],
            revisao_rapida=["Revisar conceito."],
            fontes=["https://example.org"],
            modelo="fake-model",
        )
