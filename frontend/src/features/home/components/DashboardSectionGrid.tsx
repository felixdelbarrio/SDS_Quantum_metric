import type { CSSProperties } from "react";
import type { DynamicDashboardSection } from "../types";
import { WidgetRenderer } from "./WidgetRenderer";

type LayoutProperties = CSSProperties & {
  "--widget-column-start"?: number;
  "--widget-column-span"?: number;
  "--widget-row-span"?: number;
};

export function DashboardSectionGrid({
  section,
  sectionIndex,
}: {
  section: DynamicDashboardSection;
  sectionIndex: number;
}) {
  return (
    <section
      className="dashboard-section"
      data-section-id={section.section_id ?? `section-${sectionIndex}`}
    >
      {section.section_name ? <h2>{section.section_name}</h2> : null}
      <div className="dashboard-widget-grid dashboard-widget-layout-grid">
        {section.widgets.map((widget) => {
          const style: LayoutProperties = {
            "--widget-column-start":
              widget.layout_x !== null && widget.layout_x !== undefined
                ? Math.max(1, Math.min(16, widget.layout_x + 1))
                : undefined,
            "--widget-column-span": widget.layout_width
              ? Math.min(16, widget.layout_width)
              : undefined,
            "--widget-row-span": widget.layout_height
              ? Math.max(1, widget.layout_height)
              : undefined,
          };
          return (
            <div
              className="dashboard-widget-layout-item"
              key={widget.widget_id ?? widget.role ?? widget.id}
              style={style}
            >
              <WidgetRenderer widget={widget} />
            </div>
          );
        })}
      </div>
    </section>
  );
}
