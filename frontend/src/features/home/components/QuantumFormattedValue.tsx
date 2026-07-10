import type { DisplayNumberContract } from "../types";

export function QuantumFormattedValue({
  display,
}: {
  display: DisplayNumberContract;
}) {
  if (display.formatted) return <>{display.formatted}</>;
  if (display.display_value === null || display.display_value === undefined)
    return <>-</>;
  const value = display.display_value.toLocaleString(undefined, {
    minimumFractionDigits: display.precision,
    maximumFractionDigits: display.precision,
    useGrouping: display.formatter !== "plain",
  });
  return <>{`${display.prefix ?? ""}${value}${display.suffix ?? ""}`}</>;
}
