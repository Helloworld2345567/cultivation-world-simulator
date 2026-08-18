# Public Spectator and Admin Deployment

## Goal

Deploy the simulator at `https://world.ym0v0.com` through Cloudflare while keeping world observation public and restricting every state-changing or sensitive operation to one administrator.

## Access model

1. Public visitors may load the application and use read-only world queries.
2. A single administrator authenticates with a deployment-provided password.
3. Authentication is enforced by the backend. Hiding frontend controls is only a usability measure.
4. The administrator session uses a signed, HTTP-only cookie with an expiry.
5. Protected browser requests require a per-session CSRF token.
6. Repeated failed logins are rate-limited.
7. Local development keeps the existing unauthenticated workflow when admin authentication is not configured.
8. Spectator WebSocket connections must not pause or resume the world in the public deployment, including when the last spectator disconnects.

## Protected surfaces

The following require an authenticated administrator when authentication is enabled:

- every `/api/v1/command/*` endpoint;
- settings mutations and LLM configuration access;
- save-file listing;
- server shutdown;
- any future non-read-only endpoint added beneath those namespaces.

The regular `/api/v1/query/*` world-observation endpoints remain public unless they expose administrator-only data.

## Frontend behavior

1. A global administrator entry is available on both the splash and game scenes.
2. It shows whether the current browser is a visitor or administrator.
3. It supports login and logout without exposing the configured password.
4. Visitors see a read-only experience; primary mutation controls are hidden or disabled.
5. The HTTP client automatically includes the current CSRF token on protected writes.
6. Backend authorization remains authoritative if a visitor calls an endpoint directly.

## Deployment boundary

1. The backend port is not published to the host or internet.
2. The frontend container may bind to `127.0.0.1:8123` for local health checks only.
3. An official `cloudflared` sidecar is the only public ingress and targets the frontend service over the private Compose network.
4. The public hostname is `world.ym0v0.com`.
5. Administrator password, session signing secret, and Cloudflare tunnel credentials are runtime secrets and are never committed.
6. WebSocket traffic must continue to work through the tunnel.
7. Deployment documentation covers setup, verification, rotation, backup, and rollback.
8. Credentialed CORS accepts only the configured public origin in production.
9. Docker build context excludes runtime data and populated Cloudflare credential files.

## Verification

- Public queries succeed without a session.
- Public mutation attempts return `401`.
- A wrong password fails without creating a session.
- A correct password creates a session and returns a CSRF token.
- An authenticated write without the CSRF token returns `403`.
- An authenticated write with the token reaches the existing command handler.
- Logout invalidates the browser session.
- Connecting or disconnecting as a spectator does not change the pause state.
- Frontend type checking, unit tests, and production build pass.
- Backend targeted tests and the non-Docker suite pass.
- The deployed hostname serves HTTPS, loads the world, and supports WebSockets.
