import { Search, X } from "lucide-react";
import type { DocumentStatus, Partition } from "../api/types";
import { partitionLabels } from "../constants/partitions";

const statusOptions: Array<{ value: DocumentStatus; label: string }> = [
  { value: "uploaded", label: "已上传" },
  { value: "parsing", label: "解析中" },
  { value: "pending_review", label: "待审核" },
  { value: "indexing", label: "入库中" },
  { value: "reindexing", label: "调整索引中" },
  { value: "deleting", label: "删除中" },
  { value: "ready", label: "已入库" },
  { value: "rejected", label: "已拒绝" },
  { value: "failed", label: "处理失败" },
];

interface KnowledgeFiltersProps {
  query: string;
  status: DocumentStatus | null;
  partition: Partition | null;
  onQueryChange: (value: string) => void;
  onStatusChange: (value: DocumentStatus | null) => void;
  onPartitionChange: (value: Partition | null) => void;
  onClear: () => void;
}

export function KnowledgeFilters({
  query,
  status,
  partition,
  onQueryChange,
  onStatusChange,
  onPartitionChange,
  onClear,
}: KnowledgeFiltersProps) {
  const filtered = Boolean(query || status || partition);

  return (
    <div className="knowledge-filters" aria-label="筛选知识库文档">
      <label className="knowledge-search">
        <Search aria-hidden="true" size={17} />
        <span className="sr-only">搜索标题或文件名</span>
        <input
          maxLength={200}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder="搜索标题或文件名"
          type="search"
          value={query}
        />
      </label>
      <label className="knowledge-select">
        <span>状态</span>
        <select
          aria-label="按状态筛选"
          onChange={(event) =>
            onStatusChange((event.target.value || null) as DocumentStatus | null)
          }
          value={status ?? ""}
        >
          <option value="">全部状态</option>
          {statusOptions.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>
      </label>
      <label className="knowledge-select">
        <span>分区</span>
        <select
          aria-label="按分区筛选"
          onChange={(event) =>
            onPartitionChange((event.target.value || null) as Partition | null)
          }
          value={partition ?? ""}
        >
          <option value="">全部分区</option>
          {(Object.keys(partitionLabels) as Partition[]).map((item) => (
            <option key={item} value={item}>
              {partitionLabels[item]}
            </option>
          ))}
        </select>
      </label>
      {filtered && (
        <button className="filter-clear-button" onClick={onClear} type="button">
          <X aria-hidden="true" size={15} />
          清除筛选
        </button>
      )}
    </div>
  );
}
