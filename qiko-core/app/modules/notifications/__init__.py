"""Generic in-app notification module (app.modules.notifications).

A tenant-scoped inbox reusable across verticals -- Sales Intelligence wires its triggers now,
Pre-Sales will reuse the same store/endpoints. Faithful port of the qiko-backend
origin/idg-sales generic `notifications` table + NotificationService, adapted to qiko-core's
Protocol-based store injection (in-memory dev default, Postgres-backed store behind the same
Protocol -- see app/db/stores.py). In-product only (no email/FCM push -- the Queries sheet says
in-product first)."""
