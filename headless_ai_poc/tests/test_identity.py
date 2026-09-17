"""H5, the resolver half: every channel identity of one person resolves to one principal with one set of roles."""

from __future__ import annotations

import pytest

from headless_ai_platform.contracts import Actor, CapabilityError, ErrorCode
from headless_ai_platform.identity.resolver import IdentityResolver
from headless_ai_platform.platform.layered import LayeredPlatform

ALICE = [("slack", "U04ALICE"), ("web", "oidc|alice-92ab"), ("cli", "alice@company.example"), ("rest", "api|alice")]
BOB = [("slack", "U04BOB"), ("web", "oidc|bob-51cd"), ("cli", "bob@company.example"), ("rest", "api|bob")]


directory = LayeredPlatform.principal  # the layered platform's real principal directory


@pytest.mark.parametrize("who,expected,has_ic", [(ALICE, "alice", True), (BOB, "bob", False)])
def test_every_channel_identity_maps_to_the_same_principal(who, expected, has_ic):
    r = IdentityResolver(directory)
    principals = {r.resolve(Actor(channel=c, channel_subject=s)) for c, s in who}
    assert {p.principal_id for p in principals} == {expected}
    assert len({p.roles for p in principals}) == 1
    assert all(p.has_role("incident-commander") is has_ic for p in principals)


def test_an_identity_from_another_channel_does_not_resolve():
    r = IdentityResolver(directory)
    with pytest.raises(CapabilityError) as exc:
        r.resolve(Actor(channel="slack", channel_subject="oidc|alice-92ab"))  # a web subject presented as a Slack user
    assert exc.value.code is ErrorCode.UNKNOWN_IDENTITY


def test_unlinked_identities_are_refused():
    r = IdentityResolver(directory)
    for channel, subject in [("slack", "U999"), ("teams", "29:alice"), ("event", "unknown-source")]:
        with pytest.raises(CapabilityError) as exc:
            r.resolve(Actor(channel=channel, channel_subject=subject))
        assert exc.value.code is ErrorCode.UNKNOWN_IDENTITY


def test_machine_events_act_for_the_on_call_principal():
    p = IdentityResolver(directory).resolve(Actor(channel="event", channel_subject="alertmanager"), service="checkout-api")
    assert (p.principal_id, p.via) == ("alice", "on-call:checkout-api")
