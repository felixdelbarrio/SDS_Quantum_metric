import type { DynamicDashboardResponse } from "./types";

const PICTOGRAPH = /\p{Extended_Pictographic}|\uFE0F|\u200D/gu;

export function normalizeDashboardDisplayText(
  dashboard: DynamicDashboardResponse,
): DynamicDashboardResponse {
  return {
    ...dashboard,
    dashboard_name: cleanDisplayText(dashboard.dashboard_name),
    dashboard_title: cleanDisplayText(dashboard.dashboard_title),
    tabs: dashboard.tabs.map((tab) => ({
      ...tab,
      tab_name: cleanDisplayText(tab.tab_name) || tab.tab_name,
      sections: tab.sections.map((section) => ({
        ...section,
        section_name: cleanDisplayText(section.section_name),
        widgets: section.widgets.map((widget) => ({
          ...widget,
          title: cleanDisplayText(widget.title) || widget.title,
        })),
      })),
    })),
  };
}

export function cleanDisplayText<T extends string | null | undefined>(
  value: T,
): T | string {
  return typeof value === "string"
    ? value.replace(PICTOGRAPH, "").replace(/\s+/g, " ").trim()
    : value;
}
