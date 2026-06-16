# Ingestion Chronological Model

## API Shape

`GET /api/ingestions` returns:

```json
{
  "active": [],
  "history": []
}
```

Jobs include:

- `is_active`
- `started_at`
- `finished_at`
- `sort_index`
- `current_chunk_index`
- `planned_chunks`
- `completed_chunks`
- `chunks`

## Ordering

- Active jobs are shown first.
- Historical jobs are sorted by `started_at DESC`.
- Chunks inside each job are sorted by chunk start ascending.

## UI

The Ingesta screen renders active jobs in a dedicated section and completed jobs in a separate Historico section. This prevents old completed jobs from looking like the current process.
