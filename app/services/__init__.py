"""Business/service layer package.

Services encapsulate domain logic so route handlers stay thin:

    queue_service.py      -> queue ordering, next token, waiting-time estimates
    booking_service.py    -> booking validation, token generation
    slot_service.py       -> slot capacity validation
    notification_service  -> (lives in app/notifications)
    audit_service.py      -> audit log writing

Modules are added as their features are implemented.
"""