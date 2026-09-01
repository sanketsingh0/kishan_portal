"""Database models package.

Modules will be added here, one per domain, as they are implemented:

    users, farmers, staff, centres, crops,       # phase 1
    slots, bookings, queue_entries,              # phase 2
    procurements, payments,                      # phase 3
    notifications, push_subscriptions, audit_logs  # phase 4
"""

# Importing models here makes them visible to Flask-Migrate (autogenerate) and
# to the test fixtures that call db.create_all().