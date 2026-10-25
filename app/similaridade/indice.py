"""In-memory sqlite-vec index of the trilhas' embeddings (cosine distance).

Postgres stays the source of truth: the index lives only in this process and is
reconciled with the matérias before each search (`sincronizar`), so it needs no
hook on create/edit/delete and survives restarts and multiple workers.
"""

import sqlite3
import threading
from functools import lru_cache
from uuid import UUID

import sqlite_vec


class IndiceTrilhas:
    def __init__(self, dim: int) -> None:
        self._dim = dim
        self._lock = threading.Lock()
        self._db = sqlite3.connect(":memory:", check_same_thread=False)
        self._db.enable_load_extension(True)
        sqlite_vec.load(self._db)
        self._db.enable_load_extension(False)
        self._db.execute(
            "create virtual table trilhas using "
            f"vec0(embedding float[{dim}] distance_metric=cosine)"
        )
        self._rowid_por_id: dict[UUID, int] = {}
        self._id_por_rowid: dict[int, UUID] = {}
        self._texto_por_id: dict[UUID, str] = {}
        self._proximo = 1

    @property
    def dim(self) -> int:
        return self._dim

    def _remover(self, materia_id: UUID) -> None:
        rowid = self._rowid_por_id.pop(materia_id, None)
        if rowid is not None:
            self._id_por_rowid.pop(rowid, None)
            self._db.execute("delete from trilhas where rowid = ?", (rowid,))
        self._texto_por_id.pop(materia_id, None)

    def sincronizar(self, textos: dict[UUID, str], embedder) -> None:
        """Makes the index hold exactly `textos` (id -> text), embedding only
        what is new or whose text changed."""
        with self._lock:
            for materia_id in set(self._texto_por_id) - set(textos):
                self._remover(materia_id)
            for materia_id, texto in textos.items():
                if self._texto_por_id.get(materia_id) == texto:
                    continue
                self._remover(materia_id)
                # Remembered even without a vector, so it isn't re-embedded every time.
                self._texto_por_id[materia_id] = texto
                vetor = embedder.vetor(texto)
                if vetor is None:
                    continue
                rowid, self._proximo = self._proximo, self._proximo + 1
                self._db.execute(
                    "insert into trilhas(rowid, embedding) values (?, ?)",
                    (rowid, sqlite_vec.serialize_float32(vetor)),
                )
                self._rowid_por_id[materia_id] = rowid
                self._id_por_rowid[rowid] = materia_id

    def buscar(self, vetor: list[float], k: int) -> list[tuple[UUID, float]]:
        """The `k` nearest trilhas as (id, cosine similarity), most similar first."""
        with self._lock:
            if not self._id_por_rowid:
                return []
            linhas = self._db.execute(
                "select rowid, distance from trilhas where embedding match ? and k = ? "
                "order by distance",
                (sqlite_vec.serialize_float32(vetor), k),
            ).fetchall()
        return [(self._id_por_rowid[rowid], 1.0 - distancia) for rowid, distancia in linhas]


@lru_cache
def get_indice(dim: int) -> IndiceTrilhas:
    return IndiceTrilhas(dim)
