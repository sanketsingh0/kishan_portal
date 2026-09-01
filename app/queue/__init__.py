"""Queue management package.

Responsible for:

    - queue ordering / queue position
    - "next token" operation (staff)
    - estimated waiting time (farmers ahead x average processing time)
    - emitting Flask-SocketIO events so connected dashboards update live

Realtime is owned by Flask-SocketIO (the primary mechanism); Supabase
Realtime stays an optional future capability.

No queue logic is implemented yet - this module ships as an empty package.
"""