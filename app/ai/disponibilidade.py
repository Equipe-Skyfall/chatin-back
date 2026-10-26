"""Whether the AI provider is currently usable, judged by recent real calls.

No probe is sent to Gemini: after `FALHAS_SEGUIDAS` failed calls in a row the
provider is reported as unavailable for `JANELA_SEGUNDOS`, then reported as
available again so the next real call can find out. Any successful call clears
the count immediately. State is per process, which is enough for the single
Render instance this runs on.
"""

import threading
import time
from collections.abc import Callable

FALHAS_SEGUIDAS = 3
JANELA_SEGUNDOS = 60.0


class DisponibilidadeIA:
    def __init__(self, relogio: Callable[[], float] = time.monotonic):
        self._relogio = relogio
        self._trava = threading.Lock()
        self._falhas_seguidas = 0
        self._ultima_falha: float | None = None

    def registrar_sucesso(self) -> None:
        with self._trava:
            self._falhas_seguidas = 0
            self._ultima_falha = None

    def registrar_falha(self) -> None:
        with self._trava:
            self._falhas_seguidas += 1
            self._ultima_falha = self._relogio()

    def marcar_indisponivel(self) -> None:
        """For a failure that already says it all (the provider answered 5xx/429 or
        timed out on a long call): flips to unavailable now instead of waiting for
        `FALHAS_SEGUIDAS` repeats, so the app stops depending on the AI at once."""
        with self._trava:
            self._falhas_seguidas = FALHAS_SEGUIDAS
            self._ultima_falha = self._relogio()

    def segundos_ate_nova_tentativa(self) -> int:
        """0 when the provider is considered available."""
        with self._trava:
            if self._ultima_falha is None or self._falhas_seguidas < FALHAS_SEGUIDAS:
                return 0
            restante = JANELA_SEGUNDOS - (self._relogio() - self._ultima_falha)
            return max(0, int(restante + 0.999))

    def disponivel(self) -> bool:
        return self.segundos_ate_nova_tentativa() == 0


status_ia = DisponibilidadeIA()
