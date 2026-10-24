"""Demo shipment data: the original, always-on part of the page.

Static and deterministic so every demo run looks the same. A real portal
would read this from a TMS.
"""

from dataclasses import asdict, dataclass

from app.contexts import Visitor


@dataclass(frozen=True)
class Load:
    id: str
    origin: str
    destination: str
    status: str  # In transit | At pickup | Delivered
    scheduled_arrival: str
    driver: str


_LANES = {
    "US": [
        ("Dallas, TX", "Memphis, TN", "In transit", "Today 16:30", "M. Ortiz"),
        ("Chicago, IL", "Columbus, OH", "In transit", "Today 19:15", "K. Nguyen"),
        ("Houston, TX", "Atlanta, GA", "At pickup", "Tomorrow 09:00", "J. Patel"),
        ("Kansas City, MO", "Denver, CO", "In transit", "Tomorrow 06:45", "R. Brooks"),
        ("Phoenix, AZ", "Los Angeles, CA", "Delivered", "Today 08:10", "S. Kim"),
    ],
    "CA": [
        ("Winnipeg, MB", "Regina, SK", "In transit", "Today 17:40", "A. Tremblay"),
        ("Toronto, ON", "Montreal, QC", "In transit", "Today 20:05", "L. Roy"),
        ("Calgary, AB", "Vancouver, BC", "At pickup", "Tomorrow 10:30", "D. Singh"),
        ("Winnipeg, MB", "Thunder Bay, ON", "In transit", "Tomorrow 07:20", "P. Gagnon"),
        ("Edmonton, AB", "Saskatoon, SK", "Delivered", "Today 07:55", "C. Martin"),
    ],
}


def loads_for(visitor: Visitor) -> list[Load]:
    prefix = "".join(part[0] for part in visitor.org_key.split("-")).upper()
    return [Load(f"{prefix}-{1041 + i}", *lane) for i, lane in enumerate(_LANES[visitor.region])]


def as_dicts(loads: list[Load]) -> list[dict]:
    return [asdict(load) for load in loads]
