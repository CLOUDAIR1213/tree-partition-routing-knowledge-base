import { ChevronRight, FileText } from "lucide-react";
import { Link } from "react-router-dom";
import type { DocumentSummaryResponse, Partition } from "../api/types";
import { partitionLabels } from "../constants/partitions";
import { DocumentStatusBadge } from "./DocumentStatusBadge";

function formatDate(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function effectivePartition(document: DocumentSummaryResponse): Partition {
  return document.confirmed_partition ?? document.selected_partition;
}

export function KnowledgeDocumentTable({
  documents,
}: {
  documents: DocumentSummaryResponse[];
}) {
  return (
    <div className="knowledge-table-wrap">
      <table className="knowledge-table">
        <thead>
          <tr>
            <th scope="col">文档</th>
            <th scope="col">状态</th>
            <th scope="col">分区</th>
            <th scope="col">Chunk</th>
            <th scope="col">更新时间</th>
            <th scope="col"><span className="sr-only">查看详情</span></th>
          </tr>
        </thead>
        <tbody>
          {documents.map((document) => {
            const partition = effectivePartition(document);
            const pendingConfirmation = document.confirmed_partition === null;
            return (
              <tr key={document.document_id}>
                <td>
                  <Link
                    className="knowledge-document-link"
                    to={`/knowledge/documents/${document.document_id}`}
                  >
                    <FileText aria-hidden="true" size={17} />
                    <span>
                      <strong>{document.title || document.original_filename}</strong>
                      <small>{document.original_filename}</small>
                    </span>
                  </Link>
                </td>
                <td><DocumentStatusBadge status={document.status} /></td>
                <td>
                  <span className="knowledge-partition">
                    {partitionLabels[partition]}
                    {pendingConfirmation && <small>待确认</small>}
                  </span>
                </td>
                <td>{document.chunk_count}</td>
                <td><time dateTime={document.updated_at}>{formatDate(document.updated_at)}</time></td>
                <td>
                  <Link
                    aria-label={`查看 ${document.title || document.original_filename} 详情`}
                    className="knowledge-row-action"
                    to={`/knowledge/documents/${document.document_id}`}
                  >
                    <ChevronRight aria-hidden="true" size={17} />
                  </Link>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
