# Auth Session Model

## Browser mode

Default mode must be `Browser` with Chrome as default browser.

Observed cookie sources:

- `.bbvamx.quantummetric.com`: `session`, `session.sig`
- `bbvamx.quantummetric.com`: `accessToken`, `refreshToken`
- `.iam.quantummetric.com`: `qm:iam:session`, `qm:iam:session:marker`
- `.quantummetric.com`: non-auth product cookies such as pivot/beamer/suppression cookies

Only cookie names and counts were logged. Values were kept in memory only.

## Token flow

1. Read encrypted browser cookies on explicit user action only.
2. Decrypt in memory using OS keychain.
3. Call `GET /data/init` to validate app session and discover `qmServicesEndpoint`.
4. Call `GET /auth-token` to obtain an access token in memory.
5. Use `Authorization: Bearer <accessToken>` for `https://api.quantummetric.com/query` and worker analytics calls.
6. Clear references when the process ends.

## Security constraints for implementation

- Never persist cookie values, access tokens, refresh tokens or Authorization headers.
- Never log cookie values or tokens.
- Sanitize exceptions because request libraries may include headers in debug details.
- Do not read browser cookies on app startup.
- Trigger cookie access only from `Test de conexion` or `Ingesta`.
- Use an ephemeral Playwright context; do not call `storage_state()` and do not use a persistent browser profile for injected cookies.
- Add tests that scan config, logs, manifests and exports for cookie/token names and value-shaped secrets.

## macOS considerations

- Reading Chrome cookies may require Keychain access.
- The local app should show an explanation before running browser-cookie access.
- Manual session mode is required as fallback when Keychain or browser permissions fail.
