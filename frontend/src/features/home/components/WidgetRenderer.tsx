import type { KpiWidget as KpiWidgetContract } from "../types";
import { KpiWidget } from "./KpiWidget";

export function WidgetRenderer({ widget }: { widget: KpiWidgetContract }) {
  return <KpiWidget widget={widget} />;
}
