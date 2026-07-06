# Iteration 14 WoW Configuration

Configuration is now driven by one selected country. The country selector controls base URL, global default, session status, dashboard list, dashboard metadata and widget structure.

## Layout

- Country panel: selected country, base URL, default global state, test country and dashboard refresh.
- Dashboard panel: dashboard selector, source, internal ID, visible name, type, team ID and default state.
- Manual panel: URL or dashboard ID plus visible name, validated against Quantum before it can be persisted.
- Structure panel: one group per real Quantum tab.

## Data rules

- The dashboard combo uses `dashboard_id` as value.
- The visible option text uses `name`.
- Empty names render as `Dashboard sin nombre`; IDs are only shown in the technical ID field.
- The screen renders only the selected country's dashboard and widgets.
- `Actualizar dashboards` is the only UI action that forces a new Quantum resourcesList fetch.
- Cache is used when the app is offline or unauthenticated.

## Components

The current implementation keeps the page in `frontend/src/features/quantum-config/QuantumPage.tsx` but splits the experience into reusable internal render helpers and shared design-system classes. Tokens live in `frontend/src/shared/design-system/tokens.css`.
