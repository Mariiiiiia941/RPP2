import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(service, module):
    spec = importlib.util.spec_from_file_location(f"{service}_{module}", ROOT / service / "app" / f"{module}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def ev(**kw):
    base = dict(operation_id="o", type="purchase", customer_id="C1", store_id="S1",
                status="applied", points_delta=124, balance_after=1530, reject_reason=None)
    base.update(kw)
    return base


def test_notification_texts():
    build_text = load("notifier", "logic").build_text
    assert build_text(ev()) == "Начислено 124 баллов, баланс 1530"
    assert build_text(ev(type="redeem", points_delta=-50, balance_after=10)) == "Списано 50 баллов, баланс 10"
    assert build_text(ev(status="rejected", points_delta=0, reject_reason="limit_exceeded")) == \
        "Операция отклонена: limit_exceeded"


def test_analytics_aggregation():
    logic = load("analytics", "logic")
    stores = {}
    for e in [ev(), ev(type="return", points_delta=-124), ev(type="redeem", points_delta=-30),
              ev(status="rejected", points_delta=0, reject_reason="x"), ev(store_id="S2")]:
        logic.apply_event(stores, e)
    s1 = stores["S1"].to_dict()
    assert s1 == dict(store_id="S1", accepted_purchases=1, accepted_returns=1, accepted_redeems=1,
                      rejected_operations=1, points_accrued=124, points_returned=124, points_redeemed=30)
    assert stores["S2"].accepted_purchases == 1
