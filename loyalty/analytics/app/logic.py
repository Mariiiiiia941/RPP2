from dataclasses import asdict, dataclass


@dataclass
class StoreStats:
    store_id: str
    accepted_purchases: int = 0
    accepted_returns: int = 0
    accepted_redeems: int = 0
    rejected_operations: int = 0
    points_accrued: int = 0
    points_returned: int = 0
    points_redeemed: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def apply_event(stores: dict[str, StoreStats], event: dict) -> None:
    stats = stores.setdefault(event["store_id"], StoreStats(event["store_id"]))
    if event["status"] == "rejected":
        stats.rejected_operations += 1
        return
    delta = abs(event["points_delta"])
    if event["type"] == "purchase":
        stats.accepted_purchases += 1
        stats.points_accrued += delta
    elif event["type"] == "return":
        stats.accepted_returns += 1
        stats.points_returned += delta
    elif event["type"] == "redeem":
        stats.accepted_redeems += 1
        stats.points_redeemed += delta
