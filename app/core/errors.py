from typing import Any


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


class PartitionIsolationError(AppError):
    def __init__(self, partition: str) -> None:
        super().__init__(
            "PARTITION_ISOLATION_VIOLATION",
            "索引返回了其他分区的数据",
            500,
            {"requested_partition": partition},
        )

