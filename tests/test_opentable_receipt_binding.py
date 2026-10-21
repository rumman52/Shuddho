"""TX-05 OpenTable receipt-to-approved-preview matching (no provider I/O)."""
import pytest

from services.coworker.opentable_actions import (
    reservation_receipt_matches_approved_preview,
)

APPROVED = {
    "restaurant_id": 123456,
    "restaurant_name": "Example Bistro",
    "date_time": "2026-12-01T19:00:00+06:00",
    "time_zone": "Asia/Dhaka",
    "party_size": 2,
    "reservation_attribute": "default",
    "dining_area_id": 55,
    "environment": "Indoor",
}
RECEIPT = {**APPROVED, "date_time": "2026-12-01T19:00:00"}


def test_receipt_accepts_matching_booking_with_provider_naive_local_time():
    assert reservation_receipt_matches_approved_preview(RECEIPT, APPROVED)


@pytest.mark.parametrize(
    ("field", "wrong"),
    [
        ("restaurant_id", 999999),
        ("restaurant_name", "Other Bistro"),
        ("party_size", 4),
        ("time_zone", "America/New_York"),
        ("reservation_attribute", "outdoor"),
        ("dining_area_id", 56),
        ("environment", "Outdoor"),
        ("date_time", "2026-12-01T20:00:00"),
    ],
)
def test_receipt_rejects_modified_booking_detail(field, wrong):
    assert not reservation_receipt_matches_approved_preview(
        {**RECEIPT, field: wrong}, APPROVED
    )


@pytest.mark.parametrize(
    ("receipt", "payload"),
    [
        (None, APPROVED),
        (RECEIPT, None),
        ({**RECEIPT, "date_time": "not-date"}, APPROVED),
        ({**RECEIPT, "restaurant_id": True}, APPROVED),
    ],
)
def test_receipt_rejects_noncanonical_values(receipt, payload):
    assert not reservation_receipt_matches_approved_preview(receipt, payload)
