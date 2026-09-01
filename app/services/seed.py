"""Demo seed data for local development.

Contains ONLY clearly fictional records:
- sample procurement centres (explicitly marked as demo/fictional)
- sample crops (generic agricultural terms, not government data)

No fabricated farmer identities are created here.
"""

from datetime import time

from app.extensions import db
from app.models import Centre, Crop

DEMO_CENTRES = (
    {
        "name": "KisanProcure Demo Mandi - Block A",
        "location": "Demo Sector 1, Demo District (fictional data)",
        "opening_time": time(8, 0),
        "closing_time": time(17, 0),
        "daily_capacity": 200,
        "average_processing_minutes": 15,
        "is_active": True,
    },
    {
        "name": "KisanProcure Demo Mandi - Block B",
        "location": "Demo Sector 2, Demo District (fictional data)",
        "opening_time": time(9, 0),
        "closing_time": time(18, 0),
        "daily_capacity": 150,
        "average_processing_minutes": 20,
        "is_active": True,
    },
    {
        "name": "KisanProcure Demo Mandi - Riverside",
        "location": "Demo Township, Demo District (fictional data)",
        "opening_time": time(7, 30),
        "closing_time": time(16, 30),
        "daily_capacity": 250,
        "average_processing_minutes": 12,
        "is_active": True,
    },
)

DEMO_CROPS = (
    {"name": "Wheat", "category": "Cereals"},
    {"name": "Paddy", "category": "Cereals"},
    {"name": "Maize", "category": "Cereals"},
    {"name": "Soybean", "category": "Oilseeds"},
    {"name": "Cotton", "category": "Fibre"},
    {"name": "Gram", "category": "Pulses"},
)


def seed_demo() -> dict:
    """Idempotently insert demo centres and crops.

    Safe to run repeatedly: existing records (matched by unique name) are
    never duplicated.

    Returns:
        dict with counts of records actually created,
        e.g. {"centres": 3, "crops": 6}
    """
    centres_created = crops_created = 0

    for payload in DEMO_CENTRES:
        exists = db.session.query(Centre.id).filter_by(name=payload["name"]).first()
        if not exists:
            db.session.add(Centre(**payload))
            centres_created += 1

    for payload in DEMO_CROPS:
        exists = db.session.query(Crop.id).filter_by(name=payload["name"]).first()
        if not exists:
            db.session.add(Crop(**payload))
            crops_created += 1

    db.session.commit()
    return {"centres": centres_created, "crops": crops_created}