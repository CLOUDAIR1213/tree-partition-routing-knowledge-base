import { AlertTriangle, Table2 } from "lucide-react";
import type { ParseQualityReport } from "../api/types";
import { partitionLabels } from "../constants/partitions";

interface ParseQualitySummaryProps {
  quality: ParseQualityReport | null | undefined;
}

function formatPercent(value: number) {
  return `${Math.round(value * 100)}%`;
}

export function ParseQualitySummary({ quality }: ParseQualitySummaryProps) {
  if (!quality) {
    return (
      <section className="parse-quality-section" aria-labelledby="parse-quality-heading">
        <div className="section-heading-row">
          <div>
            <h2 id="parse-quality-heading">解析质量</h2>
            <p>此历史文档没有可用的解析质量报告。</p>
          </div>
        </div>
      </section>
    );
  }

  const suggestion = quality.partition_suggestion;
  const suggestionLabel = suggestion.partition
    ? partitionLabels[suggestion.partition]
    : "未形成唯一建议";

  return (
    <section className="parse-quality-section" aria-labelledby="parse-quality-heading">
      <div className="section-heading-row">
        <div>
          <h2 id="parse-quality-heading">解析质量</h2>
          <p>基于当前文件的结构、Chunk 和内容关键词生成，仅供审核参考。</p>
        </div>
      </div>

      <dl className="parse-quality-metrics">
        <div><dt>章节</dt><dd>{quality.section_count}</dd></div>
        <div><dt>标题识别率</dt><dd>{formatPercent(quality.heading_recognition_rate)}</dd></div>
        <div><dt>Chunk</dt><dd>{quality.chunk_count}</dd></div>
        <div><dt>Chunk 长度</dt><dd>{quality.min_chunk_tokens}-{quality.max_chunk_tokens}</dd></div>
        <div><dt>空白页</dt><dd>{quality.blank_page_numbers.length}</dd></div>
        <div><dt>表格</dt><dd>{quality.table_count}</dd></div>
      </dl>

      <div className="partition-suggestion" data-suggested={Boolean(suggestion.partition)}>
        <strong>内容建议 · {suggestionLabel}</strong>
        <span>置信度 {formatPercent(suggestion.confidence)}</span>
        {suggestion.reasons.map((reason) => <p key={reason}>{reason}</p>)}
      </div>

      {quality.warnings.length > 0 && (
        <ul className="parse-quality-warnings">
          {quality.warnings.map((warning) => (
            <li key={warning}>
              <AlertTriangle aria-hidden="true" size={15} />
              {warning}
            </li>
          ))}
        </ul>
      )}

      {quality.table_count > 0 && (
        <p className="parse-quality-note"><Table2 aria-hidden="true" size={15} />表格内容已按文件原始顺序纳入相邻章节。</p>
      )}
    </section>
  );
}
