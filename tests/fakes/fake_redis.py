"""In-memory stand-in for the `redis.Redis` client used by
`app/services/historico_cache.py`. Supports only the commands that module
calls (`lrange`, and `rpush`/`ltrim`/`expire` via a pipeline) - enough to
exercise the cache-hit, cache-miss and Redis-outage paths without a real
Redis instance."""

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
        self.indisponivel = indisponivel

    def lrange(self, chave: str, start: int, end: int) -> list[str]:
        if self.indisponivel:
            raise redis.RedisError("Redis indisponível (fake)")
        valores = self.dados.get(chave, [])
        return valores[start:] if end == -1 else valores[start : end + 1]

    def pipeline(self) -> _FakePipeline:
        return _FakePipeline(self)
