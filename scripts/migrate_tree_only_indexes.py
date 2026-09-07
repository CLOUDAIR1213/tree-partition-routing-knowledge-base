from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Callable
from hashlib import sha256
from pathlib import Path

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import Database
from app.db.tables import ChunkCandidateTable, DocumentTable
from app.models.enums import DocumentStatus, Partition
from app.services.hierarchical_index import (
    CHUNK_LEVEL,
    DOCUMENT_LEVEL,
    SECTION_LEVEL,
    HierarchicalIndexRegistry,
)
from app.services.hierarchy_builder import HierarchyIndexBuilder


class MigrationError(RuntimeError):
    pass


RegistryFactory = Callable[[Path, str], object]


def _resolved(path: Path) -> Path:
    return path.expanduser().resolve()


def _overlaps(left: Path, right: Path) -> bool:
    return left == right or left.is_relative_to(right) or right.is_relative_to(left)


def validate_paths(
    source_database: Path,
    target_root: Path,
    active_tree_root: Path,
    legacy_flat_root: Path,
) -> tuple[Path, Path, Path, Path]:
    source = _resolved(source_database)
    target = _resolved(target_root)
    active = _resolved(active_tree_root)
    legacy = _resolved(legacy_flat_root)
    if not source.is_file():
        raise MigrationError("source SQLite database does not exist")
    for protected, label in ((active, "active tree root"), (legacy, "legacy Flat root")):
        if _overlaps(target, protected):
            raise MigrationError(f"target overlaps {label}")
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise MigrationError("target directory must be absent or empty")
    return source, target, active, legacy


def _empty_stats() -> dict[str, object]:
    return {
        "documents": 0,
        "sections": 0,
        "chunks": 0,
        "checksum_sha256": sha256(b"").hexdigest(),
    }


async def build_and_verify(
    source_database: Path,
    target_root: Path,
    active_tree_root: Path,
    legacy_flat_root: Path,
    embedding_model: str,
    *,
    registry_factory: RegistryFactory = HierarchicalIndexRegistry,
) -> dict[str, object]:
    source, target, _active, _legacy = validate_paths(
        source_database,
        target_root,
        active_tree_root,
        legacy_flat_root,
    )
    database = Database(
        f"sqlite+aiosqlite:///file:{source.as_posix()}?mode=ro&uri=true"
    )
    registry = registry_factory(target, embedding_model)
    builder = HierarchyIndexBuilder(registry)
    stats = {partition.value: _empty_stats() for partition in Partition}
    checksum_inputs = {partition: [] for partition in Partition}
    failures: list[dict[str, str]] = []
    registry.load_all()
    health = registry.health()
    for partition in Partition:
        for level in (DOCUMENT_LEVEL, SECTION_LEVEL, CHUNK_LEVEL):
            if health.get(partition.value, {}).get(level) != "ready":
                failures.append(
                    {
                        "document_id": "",
                        "category": f"index_not_ready:{partition.value}/{level}",
                    }
                )
    try:
        async with database.session_factory() as session:
            documents = list(
                (
                    await session.scalars(
                        select(DocumentTable)
                        .where(DocumentTable.status == DocumentStatus.READY.value)
                        .order_by(DocumentTable.id)
                    )
                ).all()
            )
            for document in documents:
                if document.confirmed_partition is None:
                    failures.append(
                        {
                            "document_id": document.id,
                            "category": "missing_confirmed_partition",
                        }
                    )
                    continue
                try:
                    partition = Partition(document.confirmed_partition)
                except ValueError:
                    failures.append(
                        {
                            "document_id": document.id,
                            "category": "invalid_confirmed_partition",
                        }
                    )
                    continue
                chunks = list(
                    (
                        await session.scalars(
                            select(ChunkCandidateTable)
                            .where(ChunkCandidateTable.document_id == document.id)
                            .order_by(ChunkCandidateTable.chunk_index)
                        )
                    ).all()
                )
                if not chunks:
                    failures.append(
                        {"document_id": document.id, "category": "missing_chunks"}
                    )
                    continue
                nodes = builder.nodes_for_document(document, chunks, partition)
                chunk_rows = builder.chunk_rows_for_document(document, chunks, partition)
                try:
                    registry.upsert_chunks_and_save(partition, chunk_rows)
                    if not registry.verify_chunks(
                        partition, [chunk.id for chunk in chunks]
                    ):
                        raise MigrationError("chunk verification failed")
                    for level, level_nodes in builder.by_level(nodes).items():
                        registry.upsert_and_save(partition, level, level_nodes)
                        if not registry.verify(
                            partition,
                            level,
                            [node.id for node in level_nodes],
                        ):
                            raise MigrationError(f"{level} verification failed")
                    for other_partition in Partition:
                        if other_partition == partition:
                            continue
                        if not registry.verify_chunks_absent(
                            other_partition, [chunk.id for chunk in chunks]
                        ):
                            raise MigrationError("cross-partition chunk detected")
                        for level, level_nodes in builder.by_level(nodes).items():
                            if not registry.verify_absent(
                                other_partition,
                                level,
                                [node.id for node in level_nodes],
                            ):
                                raise MigrationError(
                                    f"cross-partition {level} node detected"
                                )
                except Exception as exc:  # noqa: BLE001
                    failures.append(
                        {
                            "document_id": document.id,
                            "category": (
                                str(exc)
                                if isinstance(exc, MigrationError)
                                else f"index_operation_failed:{type(exc).__name__}"
                            ),
                        }
                    )
                    continue

                partition_stats = stats[partition.value]
                partition_stats["documents"] += 1
                partition_stats["sections"] += sum(
                    node.level == SECTION_LEVEL for node in nodes
                )
                partition_stats["chunks"] += len(chunks)
                checksum_inputs[partition].extend(
                    [builder.node_checksum(node) for node in nodes]
                    + [chunk.checksum_sha256 for chunk in chunks]
                )
    except Exception as exc:  # noqa: BLE001
        failures.append(
            {
                "document_id": "",
                "category": f"database_read_failed:{type(exc).__name__}",
            }
        )
    finally:
        registry.close_all()
        await database.close()

    for partition in Partition:
        digest = sha256()
        for value in sorted(checksum_inputs[partition]):
            digest.update(value.encode("ascii"))
            digest.update(b"\n")
        stats[partition.value]["checksum_sha256"] = digest.hexdigest()

    return {
        "status": "verified" if not failures else "failed",
        "source_database": source.name,
        "target_root": target.name,
        "levels": [DOCUMENT_LEVEL, SECTION_LEVEL, CHUNK_LEVEL],
        "partitions": stats,
        "failure_count": len(failures),
        "failures": failures,
        "activated": False,
    }


def activate_verified_target(
    target_root: Path,
    active_tree_root: Path,
    backup_root: Path,
    legacy_flat_root: Path,
) -> None:
    target = _resolved(target_root)
    active = _resolved(active_tree_root)
    backup = _resolved(backup_root)
    legacy = _resolved(legacy_flat_root)
    if not target.is_dir():
        raise MigrationError("verified target directory does not exist")
    if not active.is_dir():
        raise MigrationError("active tree root does not exist")
    if backup.exists():
        raise MigrationError("backup directory already exists")
    if len({target, active, backup, legacy}) != 4:
        raise MigrationError("target, active, backup and legacy roots must differ")
    if _overlaps(backup, legacy) or _overlaps(active, legacy):
        raise MigrationError("tree roots must not overlap legacy Flat root")
    if target.parent != active.parent or backup.parent != active.parent:
        raise MigrationError("target, active and backup must share one parent")

    active.rename(backup)
    try:
        target.rename(active)
    except Exception:
        backup.rename(active)
        raise


async def run_migration(
    source_database: Path,
    target_root: Path,
    report_path: Path,
    active_tree_root: Path,
    legacy_flat_root: Path,
    embedding_model: str,
    *,
    activate: bool = False,
    backup_root: Path | None = None,
    registry_factory: RegistryFactory = HierarchicalIndexRegistry,
) -> dict[str, object]:
    report_file = _resolved(report_path)
    for root, label in (
        (target_root, "target root"),
        (active_tree_root, "active tree root"),
        (legacy_flat_root, "legacy Flat root"),
    ):
        if report_file.is_relative_to(_resolved(root)):
            raise MigrationError(f"report path must be outside {label}")
    report = await build_and_verify(
        source_database,
        target_root,
        active_tree_root,
        legacy_flat_root,
        embedding_model,
        registry_factory=registry_factory,
    )
    _write_report(report_file, report)
    if activate:
        if report["status"] != "verified":
            report["activation_error"] = "verification_failed"
        elif backup_root is None:
            report["activation_error"] = "backup_root_required"
        else:
            activate_verified_target(
                target_root,
                active_tree_root,
                backup_root,
                legacy_flat_root,
            )
            report["activated"] = True
            report["backup_root"] = _resolved(backup_root).name
        _write_report(report_file, report)
    return report


def _write_report(report_file: Path, report: dict[str, object]) -> None:
    report_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="Build and verify tree-only indexes from a read-only SQLite source."
    )
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument(
        "--active-tree-root",
        type=Path,
        default=settings.hierarchical_index_root,
    )
    parser.add_argument(
        "--legacy-flat-root",
        type=Path,
        default=settings.data_root / "indexes",
    )
    parser.add_argument("--embedding-model", default=settings.embedding_model)
    parser.add_argument("--activate", action="store_true")
    parser.add_argument("--backup-root", type=Path)
    return parser.parse_args()


async def async_main() -> int:
    args = parse_args()
    try:
        report = await run_migration(
            args.database,
            args.target,
            args.report,
            args.active_tree_root,
            args.legacy_flat_root,
            args.embedding_model,
            activate=args.activate,
            backup_root=args.backup_root,
        )
    except MigrationError as exc:
        print(f"migration rejected: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "verified" and not report.get("activation_error") else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(async_main()))
