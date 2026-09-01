import type { Partition, RouteMode } from "../api/types";
import { routeOptions } from "../constants/partitions";

interface PartitionSelectorProps {
  value: RouteMode;
  onChange: (value: RouteMode) => void;
  includeAuto?: boolean;
  disabled?: boolean;
  layout?: "segmented" | "list";
  legend?: string;
}

export function PartitionSelector({
  value,
  onChange,
  includeAuto = false,
  disabled = false,
  layout = "segmented",
  legend = "选择知识分区",
}: PartitionSelectorProps) {
  const options = includeAuto
    ? routeOptions
    : routeOptions.filter((option) => option.value !== null);

  return (
    <fieldset className={`partition-selector partition-selector--${layout}`}>
      <legend className="sr-only">{legend}</legend>
      {options.map(({ value: optionValue, label, description, Icon }) => {
        const id = `partition-${layout}-${optionValue ?? "auto"}`;
        return (
          <label
            className="partition-option"
            data-selected={value === optionValue}
            htmlFor={id}
            key={optionValue ?? "auto"}
          >
            <input
              checked={value === optionValue}
              disabled={disabled}
              id={id}
              name={`partition-${layout}`}
              onChange={() => onChange(optionValue as Partition | null)}
              type="radio"
              value={optionValue ?? "auto"}
            />
            <span className="partition-option-icon">
              <Icon aria-hidden="true" size={15} strokeWidth={1.8} />
            </span>
            <span className="partition-option-copy">
              <strong>{label}</strong>
              {layout === "list" && description && <small>{description}</small>}
            </span>
          </label>
        );
      })}
    </fieldset>
  );
}
