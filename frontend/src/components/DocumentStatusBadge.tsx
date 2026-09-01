import {
  CheckCircle2,
  Clock3,
  LoaderCircle,
  UploadCloud,
  XCircle,
} from "lucide-react";
import type { DocumentStatus } from "../api/types";

const statusConfig = {
  uploaded: { label: "已上传", Icon: UploadCloud },
  parsing: { label: "解析中", Icon: LoaderCircle },
  pending_review: { label: "待审核", Icon: Clock3 },
  indexing: { label: "入库中", Icon: LoaderCircle },
  ready: { label: "已入库", Icon: CheckCircle2 },
  rejected: { label: "已拒绝", Icon: XCircle },
  failed: { label: "处理失败", Icon: XCircle },
} satisfies Record<DocumentStatus, { label: string; Icon: typeof Clock3 }>;

export function DocumentStatusBadge({ status }: { status: DocumentStatus }) {
  const { label, Icon } = statusConfig[status];
  const loading = status === "parsing" || status === "indexing";
  return (
    <span className="document-status" data-status={status}>
      <Icon aria-hidden="true" className={loading ? "spin" : undefined} size={15} />
      {label}
    </span>
  );
}
