"""Concrete AIProvider strategy backed by Google Gemini (`google-genai`).

Grounding (`google_search`) and forced-schema JSON output are never combined
in one call - by construction they're used in separate methods here
(`buscar_fontes` vs `gerar_questionario`), which matches how the content
pipelines invoke this provider (`fonte_pipeline` calls `buscar_fontes` once on
tema creation; `conteudo_modulo_pipeline`/`questionario_pipeline` call
`gerar_conteudo_modulo`/`gerar_questionario` on each módulo's creation,
reusing the tema's already-found fontes).
"""

import json
import logging
import uuid
from typing import Any

from google import genai
from google.genai import types
from tenacity import retry, stop_after_attempt, wait_exponential

from app.ai.base import AIProvider
from app.ai.gemini_schemas import PLANO_MODULOS_RESPONSE_SCHEMA, QUESTIONARIO_RESPONSE_SCHEMA
from app.ai.prompts import (
    AGENTE_ADMIN_SYSTEM_INSTRUCTION,
    prompt_buscar_fontes,
    prompt_feedback_erros,
    prompt_gerar_conteudo_modulo,
    prompt_gerar_questionario,
    prompt_planejar_modulos,
    prompt_professor_aluno_system,
    prompt_resumir_conversa,
)
from app.ai.schemas import (
    AlternativaGerada,
    ChamadaFerramenta,
    ConteudoGerado,
    ErroQuestao,
    FerramentaContexto,
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
from app.core.exceptions import AgenteLimiteExcedidoException, ProvedorIAIndisponivelException

logger = logging.getLogger(__name__)

_retry_transient = retry(
    stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8), reraise=True
)

# The admin agent's function-calling call is, empirically, much flakier than
# our other Gemini calls: with ~19 tool declarations attached, it returns a
# fully empty response (finish_reason=STOP, no text, no function call, zero
# output tokens) roughly two-thirds of the time - a Gemini-side quirk with
# large tool lists, not something request-shape changes on our end fixed.
# Compensate with more attempts than `_retry_transient` gives.
_retry_agente = retry(
    stop=stop_after_attempt(10), wait=wait_exponential(multiplier=1, min=1, max=6), reraise=True
)


class GeminiProvider(AIProvider):
    def __init__(self, settings: Settings):
        self._settings = settings
        self._client = genai.Client(api_key=settings.GEMINI_API_KEY)

    @_retry_transient
    def buscar_fontes(
        self, tema_titulo: str, tema_descricao: str | None, direcionamento: str | None = None
    ) -> list[FonteEncontrada]:
        try:
            response = self._client.models.generate_content(
                model=self._settings.GEMINI_MODEL_SEARCH,
                contents=prompt_buscar_fontes(tema_titulo, tema_descricao, direcionamento),
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                ),
            )
        except Exception as exc:  # noqa: BLE001 - any SDK/network failure maps to one domain exception
            raise ProvedorIAIndisponivelException(f"Falha ao buscar fontes: {exc}") from exc

        return self._parse_fontes(response, tema_titulo)

    @staticmethod
    def _parse_fontes(response: Any, tema_titulo: str) -> list[FonteEncontrada]:
        texto = getattr(response, "text", None) or ""
        candidates = getattr(response, "candidates", None) or []
        grounding = getattr(candidates[0], "grounding_metadata", None) if candidates else None
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
        try:
            response = self._client.models.generate_content(
                model=self._settings.GEMINI_MODEL_CONTEUDO,
                contents=prompt_gerar_conteudo_modulo(
                    tema_titulo,
                    modulo_titulo,
                    modulo_descricao,
                    conteudos_fontes,
                    direcionamento,
                    conteudo_ja_coberto,
                    instrucoes_regeneracao,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            raise ProvedorIAIndisponivelException(f"Falha ao gerar conteúdo: {exc}") from exc

        conteudo = (getattr(response, "text", None) or "").strip()
        if not conteudo:
            raise ProvedorIAIndisponivelException("O provedor de IA retornou um conteúdo vazio.")
        return ConteudoGerado(conteudo=conteudo, modelo=self._settings.GEMINI_MODEL_CONTEUDO)

    def gerar_questionario(
        self,
        conteudo_modulo: str,
        foco_modulo: str | None,
        quantidade: int,
        contexto_conversa: str | None = None,
    ) -> QuestionarioGerado:
        raw = self._gerar_questionario_raw(
            conteudo_modulo, foco_modulo, quantidade, contexto_conversa=contexto_conversa
        )
        try:
            questoes = self._parse_questionario(raw, quantidade)
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            logger.warning("Questionário fora do formato esperado, tentando novamente: %s", exc)
            raw = self._gerar_questionario_raw(
                conteudo_modulo,
                foco_modulo,
                quantidade,
                contexto_conversa=contexto_conversa,
                reforco=(
                    "IMPORTANTE: responda estritamente no formato JSON solicitado, com exatamente "
                    f"{quantidade} questões e exatamente 5 alternativas em cada uma."
                ),
            )
            try:
                questoes = self._parse_questionario(raw, quantidade)
            except (ValueError, KeyError, json.JSONDecodeError) as exc2:
                raise ProvedorIAIndisponivelException(
                    f"O provedor de IA não retornou o questionário no formato esperado: {exc2}"
                ) from exc2

        return QuestionarioGerado(
            questoes=questoes, modelo=self._settings.GEMINI_MODEL_QUESTIONARIO
        )

    @_retry_transient
    def _gerar_questionario_raw(
        self,
        conteudo_modulo: str,
        foco_modulo: str | None,
        quantidade: int,
        contexto_conversa: str | None = None,
        reforco: str = "",
    ) -> str:
        prompt = prompt_gerar_questionario(
            conteudo_modulo, foco_modulo, quantidade, contexto_conversa
        )
        if reforco:
            prompt = f"{prompt}\n\n{reforco}"
        try:
            response = self._client.models.generate_content(
                model=self._settings.GEMINI_MODEL_QUESTIONARIO,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=QUESTIONARIO_RESPONSE_SCHEMA,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            raise ProvedorIAIndisponivelException(f"Falha ao gerar questionário: {exc}") from exc
        return getattr(response, "text", None) or ""

    @staticmethod
    def _linha_unica(texto: str) -> str:
        """Collapses stray newlines/repeated whitespace the model occasionally
        inserts mid-sentence (observed when it reaches for math notation it
        can't cleanly express as plain text) - these fields are meant to
        render as a single line, in the quiz UI and in QuestaoAdminOut."""
        return " ".join(texto.split())

    @staticmethod
    def _parse_questionario(raw: str, quantidade: int) -> list[QuestaoGerada]:
        data = json.loads(raw)
        if not isinstance(data, list) or len(data) != quantidade:
            got = len(data) if isinstance(data, list) else type(data).__name__
            raise ValueError(f"esperava {quantidade} questões, recebeu {got}")

        questoes: list[QuestaoGerada] = []
        for item in data:
            alternativas = item["alternativas"]
            if len(alternativas) != 5:
                raise ValueError("questão sem exatamente 5 alternativas")
            questoes.append(
                QuestaoGerada(
                    enunciado=GeminiProvider._linha_unica(item["enunciado"]),
                    alternativas=[
                        AlternativaGerada(
                            letra=a["letra"], texto=GeminiProvider._linha_unica(a["texto"])
                        )
                        for a in alternativas
                    ],
                    resposta_correta=item["resposta_correta"],
                    explicacao=GeminiProvider._linha_unica(item["explicacao"]),
                )
            )
        return questoes

    def planejar_modulos(
        self,
        tema_titulo: str,
        tema_descricao: str | None,
        conteudos_fontes: list[str],
        max_modulos: int,
        direcionamento: str | None = None,
    ) -> PlanoModulos:
        raw = self._planejar_modulos_raw(
            tema_titulo, tema_descricao, conteudos_fontes, max_modulos, direcionamento
        )
        try:
            modulos = self._parse_plano(raw, max_modulos)
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            logger.warning("Plano de módulos fora do formato esperado, tentando novamente: %s", exc)
            raw = self._planejar_modulos_raw(
                tema_titulo,
                tema_descricao,
                conteudos_fontes,
                max_modulos,
                direcionamento,
                reforco=(
                    "IMPORTANTE: responda estritamente no formato JSON solicitado, com no "
                    f"máximo {max_modulos} módulos, cada um com 'titulo' e 'descricao'."
                ),
            )
            try:
                modulos = self._parse_plano(raw, max_modulos)
            except (ValueError, KeyError, json.JSONDecodeError) as exc2:
                raise ProvedorIAIndisponivelException(
                    f"O provedor de IA não retornou o plano de módulos no formato esperado: {exc2}"
                ) from exc2

        return PlanoModulos(modulos=modulos, modelo=self._settings.GEMINI_MODEL_CONTEUDO)

    @_retry_transient
    def _planejar_modulos_raw(
        self,
        tema_titulo: str,
        tema_descricao: str | None,
        conteudos_fontes: list[str],
        max_modulos: int,
        direcionamento: str | None,
        reforco: str = "",
    ) -> str:
        prompt = prompt_planejar_modulos(
            tema_titulo, tema_descricao, conteudos_fontes, max_modulos, direcionamento
        )
        if reforco:
            prompt = f"{prompt}\n\n{reforco}"
        try:
            response = self._client.models.generate_content(
                model=self._settings.GEMINI_MODEL_CONTEUDO,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=PLANO_MODULOS_RESPONSE_SCHEMA,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            raise ProvedorIAIndisponivelException(f"Falha ao planejar módulos: {exc}") from exc
        return getattr(response, "text", None) or ""

    @staticmethod
    def _parse_plano(raw: str, max_modulos: int) -> list[ModuloPlanejado]:
        data = json.loads(raw)
        if not isinstance(data, list) or not data:
            raise ValueError("esperava uma lista não-vazia de módulos planejados")
        # Defensive cap even though the schema already limits maxItems - a model
        # could still ignore it.
        data = data[:max_modulos]
        return [
            ModuloPlanejado(titulo=item["titulo"], descricao=item["descricao"]) for item in data
        ]

    def conversar_com_ferramentas(
        self, mensagens: list[MensagemAgente], ctx: FerramentaContexto
    ) -> str:
        """Runs the admin agent's tool-calling loop manually - one
        `_conversar_um_turno` call per round trip, dispatching any requested
        tool calls via `agent_tools.executar_ferramenta` and feeding the
        result back in, until a final text reply comes back or
        `AGENTE_MAX_ITERACOES` round trips are used up. This is the loop that
        used to live in `app/services/agent_service.py` - it moved here
        because `AIProvider.conversar_com_ferramentas` now owns running the
        whole loop (so `AdkProvider` can hand it off to the ADK `Runner`
        instead), not just one round trip."""
        # Local import: `agent_tools` depends on `curriculo_service`, which in
        # turn touches most of the domain - importing it at module level here
        # would make `app.ai` depend on `app.services`, inverting the
        # intended dependency direction (services depend on `app.ai`, not the
        # other way around). This is the one place a concrete provider needs
        # the tool dispatcher itself, not just tool declarations.
        from app.services.agent_tools import TOOLS, executar_ferramenta

        historico = list(mensagens)
        for _ in range(self._settings.AGENTE_MAX_ITERACOES):
            resposta = self._conversar_um_turno(historico, TOOLS)

            if not resposta.chamadas_ferramentas:
                return resposta.texto or ""

            historico.append(
                MensagemAgente(
                    papel="assistant",
                    conteudo=resposta.texto,
                    chamadas_ferramentas=resposta.chamadas_ferramentas,
                )
            )
            for chamada in resposta.chamadas_ferramentas:
                resultado = executar_ferramenta(chamada.nome, chamada.argumentos, ctx)
                historico.append(
                    MensagemAgente(
                        papel="tool",
                        conteudo=resultado,
                        nome_ferramenta=chamada.nome,
                        chamada_ferramenta_id=chamada.id,
                    )
                )

        raise AgenteLimiteExcedidoException()

    @_retry_agente
    def _conversar_um_turno(
        self, mensagens: list[MensagemAgente], ferramentas: list[FerramentaDeclaracao]
    ) -> RespostaAgente:
        tool = types.Tool(
            function_declarations=[
                types.FunctionDeclaration(
                    name=f.nome, description=f.descricao, parameters=f.parametros
                )
                for f in ferramentas
            ]
        )
        # A cache-busting nonce in the system instruction: empirically, the empty
        # responses this call is retried for (see `_retry_agente`) come back with
        # `cached_content_token_count` set on the large tool-schema prefix, while
        # the one clean success in the same test run had no cache hit at all -
        # consistent with the server replaying the same bad cached completion on
        # a byte-identical retry rather than actually resampling. Varying the
        # instruction slightly per call forces a fresh cache key each attempt.
        instrucao = f"{AGENTE_ADMIN_SYSTEM_INSTRUCTION}\n\n<!-- {uuid.uuid4()} -->"
        try:
            response = self._client.models.generate_content(
                model=self._settings.GEMINI_MODEL_AGENTE,
                contents=[self._para_content(m) for m in mensagens],
                config=types.GenerateContentConfig(tools=[tool], system_instruction=instrucao),
            )
        except Exception as exc:  # noqa: BLE001
            raise ProvedorIAIndisponivelException(f"Falha na conversa com o agente: {exc}") from exc

        candidates = getattr(response, "candidates", None) or []
        content = getattr(candidates[0], "content", None) if candidates else None
        if not getattr(content, "parts", None):
            # Observed in practice: with a large tool list, Gemini sometimes returns
            # finish_reason=STOP with literally no content (no text, no function
            # call, zero output tokens) - a bad response, not a bad request. `@_retry_transient`
            # retries on any exception, so raising here re-runs the same call.
            raise ProvedorIAIndisponivelException(
                "O modelo retornou uma resposta vazia (sem texto e sem chamada de ferramenta)."
            )

        return self._parse_resposta_agente(response)

    @staticmethod
    def _para_content(mensagem: MensagemAgente) -> types.Content:
        if mensagem.papel == "user":
            return types.Content(
                role="user", parts=[types.Part.from_text(text=mensagem.conteudo or "")]
            )
        if mensagem.papel == "assistant":
            if mensagem.chamadas_ferramentas:
                parts = [
                    types.Part.from_function_call(name=c.nome, args=c.argumentos)
                    for c in mensagem.chamadas_ferramentas
                ]
                return types.Content(role="model", parts=parts)
            return types.Content(
                role="model", parts=[types.Part.from_text(text=mensagem.conteudo or "")]
            )
        # papel == "tool": the result of a previously executed function call
        return types.Content(
            role="user",
            parts=[
                types.Part.from_function_response(
                    name=mensagem.nome_ferramenta or "",
                    response={"resultado": mensagem.conteudo or ""},
                )
            ],
        )

    @staticmethod
    def _parse_resposta_agente(response: Any) -> RespostaAgente:
        candidates = getattr(response, "candidates", None) or []
        content = getattr(candidates[0], "content", None) if candidates else None
        parts = getattr(content, "parts", None) or []

        texto_partes: list[str] = []
        chamadas: list[ChamadaFerramenta] = []
        for part in parts:
            function_call = getattr(part, "function_call", None)
            if function_call is not None:
                chamadas.append(
                    ChamadaFerramenta(
                        id=str(uuid.uuid4()),
                        nome=function_call.name,
                        argumentos=dict(function_call.args or {}),
                    )
                )
                continue
            texto = getattr(part, "text", None)
            if texto:
                texto_partes.append(texto)

        return RespostaAgente(
            texto="\n".join(texto_partes) if texto_partes else None,
            chamadas_ferramentas=chamadas,
        )

    @_retry_transient
    def responder_pergunta_aluno(
        self,
        historico: list[MensagemAgente],
        pergunta: str,
        conteudo_modulo: str | None = None,
    ) -> str:
        contents = [self._para_content(m) for m in historico]
        contents.append(self._para_content(MensagemAgente(papel="user", conteudo=pergunta)))
        try:
            response = self._client.models.generate_content(
                model=self._settings.GEMINI_MODEL_PROFESSOR,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=prompt_professor_aluno_system(conteudo_modulo)
                ),
            )
        except Exception as exc:  # noqa: BLE001
            raise ProvedorIAIndisponivelException(
                f"Falha ao responder pergunta do aluno: {exc}"
            ) from exc

        texto = getattr(response, "text", None)
        if not texto:
            raise ProvedorIAIndisponivelException("O provedor de IA retornou uma resposta vazia.")
        return texto

    @_retry_transient
    def resumir_conversa(self, mensagens: list[MensagemAgente]) -> str:
        contents = [self._para_content(m) for m in mensagens]
        try:
            response = self._client.models.generate_content(
                model=self._settings.GEMINI_MODEL_PROFESSOR,
                contents=contents,
                config=types.GenerateContentConfig(system_instruction=prompt_resumir_conversa()),
            )
        except Exception as exc:  # noqa: BLE001
            raise ProvedorIAIndisponivelException(f"Falha ao resumir conversa: {exc}") from exc

        texto = (getattr(response, "text", None) or "").strip()
        if not texto:
            raise ProvedorIAIndisponivelException("O provedor de IA retornou um resumo vazio.")
        return texto

    @staticmethod
    def _formatar_erros(erros: list[ErroQuestao]) -> str:
        blocos: list[str] = []
        for erro in erros:
            bloco = (
                f"Questão: {erro.enunciado}\n"
                f"Resposta do aluno: {erro.resposta_escolhida}\n"
                f"Resposta correta: {erro.resposta_correta}"
            )
            if erro.explicacao:
                bloco += f"\nExplicação da correta: {erro.explicacao}"
            blocos.append(bloco)
        return "\n\n".join(blocos)

    @_retry_transient
    def gerar_feedback_erros(self, erros: list[ErroQuestao]) -> str:
        try:
            response = self._client.models.generate_content(
                model=self._settings.GEMINI_MODEL_PROFESSOR,
                contents=prompt_feedback_erros(self._formatar_erros(erros)),
            )
        except Exception as exc:  # noqa: BLE001
            raise ProvedorIAIndisponivelException(f"Falha ao gerar feedback: {exc}") from exc

        texto = (getattr(response, "text", None) or "").strip()
        if not texto:
            raise ProvedorIAIndisponivelException("O provedor de IA retornou um feedback vazio.")
        return texto
