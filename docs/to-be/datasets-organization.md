# Datasets Organization

Datasets are organized for discrepancy analysis:

```text
Pais
  Dashboard
    Widgets
      RAW
      Derived
      Chart Payload
      Regression
    Config
    Manifest
```

Entity metadata now includes:

- category;
- dashboard ID;
- widget role;
- rows;
- files;
- bytes;
- update timestamp.

Export includes:

- `manifest.json`;
- `config/quantum_config.json`;
- `parquet/country=*/...`.

Import validates the manifest, rejects unsafe paths and rejects secret-looking config payloads.
