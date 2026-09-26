from __future__ import annotations

from datetime import datetime, timedelta

from temporalio.client import (
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleAlreadyRunningError,
    ScheduleCalendarSpec,
    ScheduleOverlapPolicy,
    SchedulePolicy,
    ScheduleRange,
    ScheduleSpec,
    ScheduleState,
    ScheduleUpdate,
)
from temporalio.service import RPCError, RPCStatusCode

from .workflow import AutomationOccurrenceWorkflow


DAY = {"sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6}


def schedule_id(automation_id: str) -> str:
    return "shuddho-automation-" + automation_id


def workflow_base_id(automation_id: str, revision: int) -> str:
    return f"shuddho-automation-{automation_id}-r{revision}"


def temporal_schedule(value: dict, task_queue: str):
    spec = value["schedule"]
    weekdays = [] if spec["kind"] == "daily" else [ScheduleRange(start=DAY[item]) for item in spec["weekdays"]]
    calendar = ScheduleCalendarSpec(
        day_of_week=weekdays or [ScheduleRange(start=0, end=6)],
        hour=[ScheduleRange(start=int(spec["hour"]))],
        minute=[ScheduleRange(start=int(spec["minute"]))],
        second=[ScheduleRange(start=0)],
    )
    overlap = ScheduleOverlapPolicy.BUFFER_ONE if value["overlap_policy"] == "buffer_one" else ScheduleOverlapPolicy.SKIP
    enabled = value["state"] == "active"
    return Schedule(
        action=ScheduleActionStartWorkflow(
            AutomationOccurrenceWorkflow.run,
            {"automation_id": value["id"], "revision": int(value["revision"])},
            id=workflow_base_id(value["id"], int(value["revision"])),
            task_queue=task_queue,
            execution_timeout=timedelta(minutes=5),
        ),
        spec=ScheduleSpec(
            calendars=[calendar],
            time_zone_name=value["timezone"],
            end_at=datetime.fromisoformat(value["expires_at"].replace("Z", "+00:00")) if value.get("expires_at") else None,
        ),
        policy=SchedulePolicy(
            overlap=overlap,
            catchup_window=timedelta(seconds=int(value["catchup_window_seconds"])),
        ),
        state=ScheduleState(
            paused=not enabled,
            note=f"Shuddho PA-02 automation revision {value['revision']}",
        ),
    )


class AutomationScheduleReconciler:
    """Maps PostgreSQL desired state to one Temporal Schedule per automation."""

    def __init__(self, client, task_queue: str):
        self.client = client
        self.task_queue = task_queue

    async def apply(self, value: dict) -> bool:
        sid = schedule_id(value["id"])
        handle = self.client.get_schedule_handle(sid)
        if value["state"] == "cancelled":
            try:
                await handle.delete()
            except RPCError as error:
                if error.status != RPCStatusCode.NOT_FOUND:
                    raise
            return False

        desired = temporal_schedule(value, self.task_queue)
        try:
            await self.client.create_schedule(sid, desired)
        except ScheduleAlreadyRunningError:
            await handle.update(lambda _input: ScheduleUpdate(schedule=desired))
        return value["state"] == "active"
