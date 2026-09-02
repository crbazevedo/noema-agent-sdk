"""Authentication boundary for explicit reconsideration mandates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .models import (
    MandateIssuerKind,
    ReconsiderationMandate,
    ReconsiderationMandateRevocation,
)


class ReconsiderationAuthority(Protocol):
    @property
    def authority_id(self) -> str: ...

    def authenticates_mandate(self, mandate: ReconsiderationMandate) -> bool: ...

    def authenticates_revocation(
        self,
        revocation: ReconsiderationMandateRevocation,
    ) -> bool: ...


@dataclass(frozen=True, slots=True)
class StaticReconsiderationAuthority:
    """Exact deterministic authority fixture; deployments supply real authentication."""

    authority_id: str
    authorized_issuers: tuple[tuple[str, MandateIssuerKind], ...]

    def __post_init__(self) -> None:
        if not self.authority_id.strip():
            raise ValueError("reconsideration authority id must be non-empty")
        if not self.authorized_issuers:
            raise ValueError("reconsideration authority requires authorized issuers")
        if any(not issuer.strip() for issuer, _kind in self.authorized_issuers):
            raise ValueError("authorized reconsideration issuer must be non-empty")
        if len(set(self.authorized_issuers)) != len(self.authorized_issuers):
            raise ValueError("authorized reconsideration issuers must be unique")

    def authenticates_mandate(self, mandate: ReconsiderationMandate) -> bool:
        return (
            mandate.authority_id == self.authority_id
            and (
                mandate.issuer_id,
                mandate.issuer_kind,
            )
            in self.authorized_issuers
        )

    def authenticates_revocation(
        self,
        revocation: ReconsiderationMandateRevocation,
    ) -> bool:
        return revocation.authority_id == self.authority_id and any(
            issuer_id == revocation.issuer_id for issuer_id, _kind in self.authorized_issuers
        )
