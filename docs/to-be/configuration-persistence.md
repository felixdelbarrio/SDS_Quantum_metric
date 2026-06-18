# Configuration Persistence

Configuration persists in:

`config/quantum_config.json`

The file is written atomically and contains schema version `2`.

Persisted fields:

- browser;
- session mode;
- theme preference;
- ingestion depth;
- countries;
- default country;
- base URL by country;
- dashboards by country;
- default dashboard by country;
- widget IDs;
- widget types;
- widget enabled flags;
- validation timestamps/status.

Not persisted:

- cookies;
- Authorization headers;
- manual cookie values;
- tokens.

`.env` synchronization is best-effort and limited to non-secret operational values.
