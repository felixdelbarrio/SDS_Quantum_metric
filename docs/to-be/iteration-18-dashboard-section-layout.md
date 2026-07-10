# Jerarquía y layout del dashboard

La estructura es Dashboard → Tab → Section → Widget. Discovery conserva `section_id`, `section_name`, `section_index` y layout `x/y/width/height`. Si no hay tab demostrable, se usa la resolución técnica `unassigned`; nunca Summary.

Home usa `DashboardSectionGrid` y `WidgetRenderer`. El orden contractual se resuelve por section/widget order y coordenadas. El ancho/alto se transmiten como variables CSS; `compact-kpi`, `chart-card` y `table-card` son variantes centrales, sin estilos por título o widget.
