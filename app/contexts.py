"""Who is looking at the page, expressed as a LaunchDarkly context.

There is no login in this demo. The browser picks one of the preset
visitors below and sends only its key; the server builds the context.

Every evaluation uses a multi-context: the person (`user`) plus the shipper
they work for (`organization`). Targeting rules in LaunchDarkly match on
organization attributes such as plan and region, which is how a B2B portal
is usually rolled out.
"""

from dataclasses import dataclass

from ldclient import Context


@dataclass(frozen=True)
class Visitor:
    key: str
    name: str
    email: str
    role: str
    anonymous: bool
    org_key: str
    org_name: str
    plan: str  # free | pro | enterprise | internal
    region: str  # US | CA
    fleet_size: int
    beta_tester: bool


# Fictional shippers. The comment on each line is the hours-of-service value
# it should get once the flag is set up as described in docs/LAUNCHDARKLY_SETUP.md.
VISITORS: dict[str, Visitor] = {
    v.key: v
    for v in [
        # canada: rule "enterprise in CA"
        Visitor(
            key="dana",
            name="Dana",
            email="dana@prairiehaul.example",
            role="dispatcher",
            anonymous=False,
            org_key="prairie-haul",
            org_name="Prairie Haul",
            plan="enterprise",
            region="CA",
            fleet_size=120,
            beta_tester=False,
        ),
        # us: rule "enterprise in US"
        Visitor(
            key="sam",
            name="Sam",
            email="sam@lonestarfreight.example",
            role="dispatcher",
            anonymous=False,
            org_key="lone-star-freight",
            org_name="Lone Star Freight",
            plan="enterprise",
            region="US",
            fleet_size=300,
            beta_tester=False,
        ),
        # us: individual target on the organization
        Visitor(
            key="riley",
            name="Riley",
            email="riley@lakeshore.example",
            role="ops lead",
            anonymous=False,
            org_key="lakeshore-logistics",
            org_name="Lakeshore Logistics",
            plan="pro",
            region="US",
            fleet_size=40,
            beta_tester=True,
        ),
        # off: matches nothing
        Visitor(
            key="alex",
            name="Alex",
            email="alex@mapleroute.example",
            role="owner",
            anonymous=False,
            org_key="maple-route",
            org_name="Maple Route",
            plan="free",
            region="CA",
            fleet_size=8,
            beta_tester=False,
        ),
        # off: ABC Freight's own QA tester. Part 1 releases eta-predictions to this
        # organization first (an individual target), then to everyone.
        Visitor(
            key="quinn",
            name="Quinn",
            email="quinn@abcfreight.example",
            role="QA engineer",
            anonymous=False,
            org_key="abc-freight",
            org_name="ABC Freight",
            plan="internal",
            region="US",
            fleet_size=0,
            beta_tester=True,
        ),
        # off: anonymous visitor on the public site
        Visitor(
            key="guest",
            name="Guest",
            email="",
            role="visitor",
            anonymous=True,
            org_key="public",
            org_name="Public",
            plan="free",
            region="US",
            fleet_size=0,
            beta_tester=False,
        ),
    ]
}

DEFAULT_VISITOR = "guest"


def get_visitor(key: str | None) -> Visitor:
    """Return the preset visitor, falling back to the anonymous guest."""
    return VISITORS.get(key or "", VISITORS[DEFAULT_VISITOR])


def build_context(visitor: Visitor) -> Context:
    """Build the user + organization multi-context for one visitor."""
    user = Context.builder(f"user-{visitor.key}").kind("user").name(visitor.name)
    user.set("role", visitor.role)
    if visitor.anonymous:
        # Anonymous contexts are evaluated normally but kept off the Contexts list.
        # Every guest in this demo shares one key. In production, give each anonymous
        # visitor its own key (for example a random ID kept in a cookie); otherwise
        # percentage rollouts and experiments treat all guests as one person.
        user.anonymous(True)
    else:
        user.set("email", visitor.email)
        # Private: used for evaluation, never sent to LaunchDarkly analytics.
        user.private("email")

    org = (
        Context.builder(visitor.org_key)
        .kind("organization")
        .name(visitor.org_name)
        .set("plan", visitor.plan)
        .set("region", visitor.region)
        .set("fleet_size", visitor.fleet_size)
        .set("beta_tester", visitor.beta_tester)
    )
    return Context.create_multi(user.build(), org.build())
