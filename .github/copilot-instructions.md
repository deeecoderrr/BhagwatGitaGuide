You are helping build a full-stack backend project that serves APIs for a premium Expo React Native mobile app and also serves/supports a web app frontend built in the same project.

The mobile app frontend is maintained in a separate Expo React Native project/repository. The web app frontend exists inside this same backend/full-stack project. Therefore, this project must support both: secure, reliable, scalable backend APIs and high-quality web app frontend integration.

Always think like a senior full-stack engineer building a world-class product. Prioritize clean API design, strong authentication and authorization, strict input validation, consistent JSON responses, stable error codes, efficient database access, secure session/token handling, logging, monitoring, performance, security, and easy integration for both the mobile app and web app.

For backend work, build secure, scalable, production-ready APIs. For web app work inside this project, build polished, responsive, accessible, production-ready frontend experiences using the project’s existing frontend stack and conventions.

Do not create Expo or React Native mobile app code in this project. Do not add mobile screens, mobile navigation, or Expo-specific code here. The mobile app is separate. This project may include web frontend code only if it belongs to the existing web app in this repository.

For every API endpoint, use the existing project conventions. Validate request body, query params, route params, headers, uploaded files, and webhook payloads. Protect private routes. Verify user ownership and permissions. Never trust client-provided user IDs without checking authorization. Return proper HTTP status codes. Use safe error messages. Never expose stack traces, database errors, secrets, tokens, or internal implementation details to clients.

Use consistent API response shapes unless the project already has a different standard. Prefer predictable responses like success/data/message for successful requests and success/error/code/message/details for failed requests. Use stable error codes such as VALIDATION_ERROR, UNAUTHORIZED, FORBIDDEN, NOT_FOUND, CONFLICT, RATE_LIMITED, and INTERNAL_ERROR so both mobile and web clients can handle errors cleanly.

Because one client is a mobile app, always consider slow networks, retries, offline states, token expiration, refresh-token flows, small payload sizes, pagination, filtering, sorting, search, media upload limits, push notifications if relevant, app version compatibility, and backward-compatible API changes.

Because this project also serves a web app frontend, always consider responsive layouts, accessibility, SEO where relevant, fast page loads, secure browser sessions/cookies if used, CSRF protection where applicable, safe CORS configuration, form validation, loading states, empty states, error states, and polished UI/UX.

Avoid breaking existing clients. Prefer additive API changes, backward-compatible response changes, and documented migrations. If a breaking change is necessary, make it explicit and update both API documentation and affected web frontend code where appropriate.

Keep backend route handlers thin. Prefer a clean structure with routes/controllers for HTTP handling, services for business logic, repositories or data-access layers for database work, validators or schemas for input validation, middleware for authentication, authorization, logging, rate limiting, and error handling, and utilities for shared helpers.

Use the project’s existing database and ORM conventions. Write efficient queries, avoid N+1 problems, select only required fields, use transactions for multi-step writes, add indexes where needed, and avoid destructive migrations unless explicitly requested. Never leak raw database errors to API clients.

Security is critical. Hash passwords securely if passwords exist. Never log passwords, access tokens, refresh tokens, OTPs, API keys, payment data, or private secrets. Apply rate limits to sensitive endpoints such as login, OTP, password reset, payments, webhooks, and admin actions. Validate webhook signatures and make webhook handlers idempotent.

Use environment variables for all secrets and environment-specific configuration, including database URLs, JWT/session secrets, API keys, storage credentials, payment credentials, email/SMS credentials, CORS origins, web app URLs, and mobile app URLs. Never hardcode or commit secrets.

If the backend handles images or videos, validate file type and size, store media securely, use signed or protected URLs where needed, generate thumbnails or optimized URLs where useful, avoid large binary payloads in JSON, and clean up failed uploads when possible.

For third-party integrations, handle timeouts, retries, webhook verification, idempotency, and safe logging. Do not expose raw third-party errors directly to mobile or web clients.

For web frontend work in this project, do not create basic developer-looking UI. Build clean, modern, polished, responsive, accessible interfaces. Prioritize clear visual hierarchy, consistent spacing, strong typography, theme consistency, loading states, empty states, error states, form validation, useful animations, and high-quality image/video presentation where relevant. Follow the existing design system and component conventions.

Add or update documentation when creating or changing endpoints, including route path, method, auth requirement, request body, query params, response shape, error codes, and example request/response when useful. Add or update tests for authentication, authorization, validation, business-critical flows, database writes, webhooks, API contracts, and important web UI behavior where practical.

The final product should feel secure, stable, fast, scalable, maintainable, well-documented, visually polished on web, and easy for the separate Expo mobile app to integrate with. Do not write quick hacks or fragile code. Always produce clean, maintainable, production-ready full-stack code.