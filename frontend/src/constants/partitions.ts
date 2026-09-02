import { Code2, Landmark, Route, Users } from "lucide-react";
import type { ComponentType } from "react";
import type { LucideProps } from "lucide-react";
import type { Partition, RouteMode } from "../api/types";

export interface PartitionOption {
  value: RouteMode;
  label: string;
  description?: string;
  Icon: ComponentType<LucideProps>;
}

export const routeOptions: PartitionOption[] = [
  { value: null, label: "自动路由", Icon: Route },
  {
    value: "finance",
    label: "财务",
    description: "报销、发票、预算、付款和会计处理",
    Icon: Landmark,
  },
  {
    value: "hr",
    label: "人事",
    description: "入职、合同、考勤、绩效和福利",
    Icon: Users,
  },
  {
    value: "tech",
    label: "技术",
    description: "研发、部署、数据库、运维和故障处理",
    Icon: Code2,
  },
];

export const partitionLabels: Record<Partition, string> = {
  finance: "财务",
  hr: "人事",
  tech: "技术",
};

export function getRouteLabel(value: RouteMode | "composite" | "clarify") {
  if (value === null) return "自动路由";
  if (value === "composite") return "复合";
  if (value === "clarify") return "待确认";
  return partitionLabels[value];
}
