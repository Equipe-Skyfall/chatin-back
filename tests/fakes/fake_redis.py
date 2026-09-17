"""In-memory stand-in for the `redis.Redis` client used by
`app/services/historico_cache.py`. Supports only the commands that module
calls (`lrange`, `rpush`/`ltrim`/`expire` via a pipeline, and `set`/`delete`
for the per-conversa lock) - enough to exercise the cache-hit, cache-miss,
lock and Redis-outage paths without a real Redis instance."""

import redis


class _FakePipeline:
    def __init__(self, cliente: "FakeRedisCliente"):
        self._cliente = cliente
        self._comandos: list[tuple] = []

    def rpush(self, chave: str, *valores: str) -> "_FakePipeline":
        self._comandos.append(("rpush", chave, valores))
        return self

    def ltrim(self, chave: str, start: int, end: int) -> "_FakePipeline":
        self._comandos.append(("ltrim", chave, start, end))
        return self

    def expire(self, chave: str, ttl: int) -> "_FakePipeline":
        self._comandos.append(("expire", chave, ttl))
        return self

    def execute(self) -> None:
        if self._cliente.indisponivel:
            raise redis.RedisError("Redis indisponível (fake)")
        for comando, chave, *args in self._comandos:
            if comando == "rpush":
                self._cliente.dados.setdefault(chave, []).extend(args[0])
            elif comando == "ltrim":
                start, _end = args
                self._cliente.dados[chave] = self._cliente.dados.get(chave, [])[start:]
            elif comando == "expire":
                self._cliente.ttls[chave] = args[0]


class FakeRedisCliente:
    def __init__(self, indisponivel: bool = False):
        self.dados: dict[str, list[str]] = {}
        self.ttls: dict[str, int] = {}
        self.chaves_simples: dict[str, str] = {}
        self.indisponivel = indisponivel

    def lrange(self, chave: str, start: int, end: int) -> list[str]:
        if self.indisponivel:
            raise redis.RedisError("Redis indisponível (fake)")
        valores = self.dados.get(chave, [])
        return valores[start:] if end == -1 else valores[start : end + 1]

    def pipeline(self) -> _FakePipeline:
        return _FakePipeline(self)

    def set(self, chave: str, valor: str, nx: bool = False, ex: int | None = None) -> bool:
        if self.indisponivel:
            raise redis.RedisError("Redis indisponível (fake)")
        if nx and chave in self.chaves_simples:
            return False
        self.chaves_simples[chave] = valor
        if ex is not None:
            self.ttls[chave] = ex
        return True

    def delete(self, chave: str) -> None:
        if self.indisponivel:
            raise redis.RedisError("Redis indisponível (fake)")
        self.chaves_simples.pop(chave, None)
