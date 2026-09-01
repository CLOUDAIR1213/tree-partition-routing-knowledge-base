import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import type { RouteMode } from "../api/types";
import { PartitionSelector } from "./PartitionSelector";

function Harness() {
  const [value, setValue] = useState<RouteMode>(null);
  return (
    <>
      <PartitionSelector includeAuto onChange={setValue} value={value} />
      <output>{value ?? "auto"}</output>
    </>
  );
}

describe("PartitionSelector", () => {
  it("maps auto mode to null and selects exactly one partition", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    expect(screen.getByRole("radio", { name: "自动路由" })).toBeChecked();
    expect(screen.getByText("auto", { selector: "output" })).toBeInTheDocument();

    await user.click(screen.getByRole("radio", { name: "财务" }));

    expect(screen.getByRole("radio", { name: "财务" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "自动路由" })).not.toBeChecked();
    expect(screen.getByText("finance", { selector: "output" })).toBeInTheDocument();
  });
});
