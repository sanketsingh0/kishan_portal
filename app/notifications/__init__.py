"""Notification engine package (designed to be channel-agnostic).

Planned architecture:

    Notification Engine
    ├── In-App                 (stored in DB, shown in dashboard/UI)
    ├── Push                   (Web Push / FCM - free channels)
    └── Optional WhatsApp/SMS  (external channels, added later, never required)

Internal events (e.g. "queue_updated", "centre_delayed") are produced by the
booking/queue services and fanned out to every configured channel, so new
channels can be added without rewriting business logic.

No notifications are implemented yet - this module ships as an empty package.
"""