from pathlib import Path
from threading import RLock

from app.models.enums import Partition


class IndexRegistry:
    def __init__(self, root: Path, embedding_model: str) -> None:
        from txtai import Embeddings

        self.root = root
        self.embedding_model = embedding_model
        self._embeddings_type = Embeddings
        self._indexes: dict[Partition, object] = {}
        self._locks = {partition: RLock() for partition in Partition}
        self._populated = {partition: False for partition in Partition}
        self._errors: dict[Partition, str] = {}

    def load_all(self) -> None:
        for partition in Partition:
            path = self.root / partition.value
            path.mkdir(parents=True, exist_ok=True)
            try:
                index = self._embeddings_type(
                    {"path": self.embedding_model, "content": True}
                )
                persisted = any(item.name != ".gitkeep" for item in path.iterdir())
                if persisted:
                    index.load(str(path))
                self._indexes[partition] = index
                self._populated[partition] = persisted
                self._errors.pop(partition, None)
            except Exception as exc:  # noqa: BLE001
                self._errors[partition] = type(exc).__name__

    def get(self, partition: Partition):
        if not isinstance(partition, Partition):
            raise TypeError("partition must be a Partition enum")
        if partition not in self._indexes:
            raise RuntimeError(f"index is not ready: {partition.value}")
        return self._indexes[partition]

    def upsert_and_save(self, partition: Partition, rows: list[dict]) -> None:
        with self._locks[partition]:
            index = self.get(partition)
            documents = [
                (
                    row["id"],
                    {key: value for key, value in row.items() if key != "id"},
                    None,
                )
                for row in rows
            ]
            if self._populated[partition]:
                index.upsert(documents)
            else:
                index.index(documents)
                self._populated[partition] = True
            index.save(str(self.root / partition.value))

    def delete_and_save(self, partition: Partition, chunk_ids: list[str]) -> None:
        with self._locks[partition]:
            if not chunk_ids:
                return
            index = self.get(partition)
            if not self._populated[partition]:
                return
            index.delete(chunk_ids)
            index.save(str(self.root / partition.value))

    def verify(self, partition: Partition, chunk_ids: list[str]) -> bool:
        with self._locks[partition]:
            if not chunk_ids:
                return True
            index = self.get(partition)
            return all(self._contains(index, chunk_id) for chunk_id in chunk_ids)

    def verify_absent(self, partition: Partition, chunk_ids: list[str]) -> bool:
        with self._locks[partition]:
            if not chunk_ids:
                return True
            index = self.get(partition)
            if not self._populated[partition]:
                return True
            return not any(self._contains(index, chunk_id) for chunk_id in chunk_ids)

    @staticmethod
    def _contains(index, chunk_id: str) -> bool:
        wanted = chunk_id.replace("'", "''")
        rows = index.search(f"select id from txtai where id = '{wanted}'")
        return any(str(row.get("id")) == chunk_id for row in rows)

    def search(self, partition: Partition, query: str, limit: int = 5) -> list[dict]:
        if not self._populated[partition]:
            return []
        return self.get(partition).search(query, limit)

    def health(self) -> dict[str, str]:
        return {
            partition.value: "ready" if partition in self._indexes else "error"
            for partition in Partition
        }

    def close_all(self) -> None:
        self._indexes.clear()
