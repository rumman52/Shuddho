import json
from uuid import UUID

import pytest
from pydantic import ValidationError
from services.coworker.task_brief_schemas import MemoryPin, TaskBriefMemorySelection


@pytest.mark.parametrize("version", [True, 1.0, "1", "01", "1.0", False, 0, -1, 1.5, None])
def test_memory_pin_version_rejects_non_positive_or_non_integer_json(version):
    fact_id = "00000000-0000-4000-8000-000000000001"
    with pytest.raises(ValidationError):
        TaskBriefMemorySelection.model_validate_json(json.dumps({
            "memory_pins": [{"fact_id": fact_id, "expected_version": version}],
        }))


@pytest.mark.parametrize("version", [1, 2, 20])
def test_memory_pin_version_preserves_positive_integer(version):
    fact_id = UUID("00000000-0000-4000-8000-000000000001")
    pin = MemoryPin(fact_id=fact_id, expected_version=version)
    assert pin.model_dump(mode="json") == {"fact_id": str(fact_id), "expected_version": version}
