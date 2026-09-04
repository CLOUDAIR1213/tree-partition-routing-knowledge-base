from collections import Counter

from app.models.enums import Partition
from app.models.schemas import PartitionSuggestion

PARTITION_KEYWORDS: dict[Partition, tuple[str, ...]] = {
    Partition.FINANCE: (
        "报销", "发票", "预算", "付款", "采购", "费用", "成本中心", "资产", "会计", "税务", "差旅",
    ),
    Partition.HR: (
        "员工", "入职", "转正", "离职", "考勤", "休假", "薪酬", "福利", "劳动合同", "培训", "绩效", "人事",
    ),
    Partition.TECH: (
        "系统", "部署", "发布", "代码", "git", "vpn", "账号", "权限", "数据库", "服务器", "容器", "docker", "故障", "日志", "索引", "rag", "txtai", "api",
    ),
}


class KeywordPartitionSuggester:
    def suggest(self, text: str) -> PartitionSuggestion:
        normalized = text.lower()
        counts: dict[Partition, Counter[str]] = {}
        totals: dict[Partition, int] = {}
        for partition, keywords in PARTITION_KEYWORDS.items():
            matches = Counter({keyword: normalized.count(keyword) for keyword in keywords})
            matches = Counter({keyword: count for keyword, count in matches.items() if count})
            counts[partition] = matches
            totals[partition] = sum(matches.values())

        ranked = sorted(totals, key=lambda partition: totals[partition], reverse=True)
        top = ranked[0]
        top_total = totals[top]
        runner_up = totals[ranked[1]]
        all_total = sum(totals.values())
        if top_total == 0 or top_total == runner_up:
            return PartitionSuggestion(
                partition=None,
                confidence=0,
                reasons=["内容没有形成唯一的分区关键词优势"],
            )

        evidence = "、".join(
            f"{keyword}（{count}）" for keyword, count in counts[top].most_common(3)
        )
        confidence = round(top_total / all_total, 2) if all_total else 0
        return PartitionSuggestion(
            partition=top,
            confidence=confidence,
            reasons=[f"命中{top.value}关键词：{evidence}"],
        )
