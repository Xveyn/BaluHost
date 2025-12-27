"""Run due sync schedules and print the generated plans (test runner).

This runner calls the service's `_execute_sync` for each due schedule and
updates schedule timestamps similar to the background worker.
"""
import asyncio
from datetime import datetime

from app.core.database import SessionLocal
from app.models.sync_progress import SyncSchedule
from app.services.sync_scheduler import SyncSchedulerService


def main():
    db = SessionLocal()
    svc = SyncSchedulerService(db)

    now = datetime.utcnow()
    due = db.query(SyncSchedule).filter(
        SyncSchedule.is_active == True,
        SyncSchedule.next_run_at <= now
    ).all()

    if not due:
        print('No due schedules found')
        return

    for s in due:
        print(f"Executing schedule id={s.id} device={s.device_id} next_run_at={s.next_run_at}")
        try:
            result = asyncio.run(svc._execute_sync(s))
            print('Plan result:', result)
        except Exception as e:
            print(f'Error executing schedule {s.id}:', e)
            continue

        # mark last run and calculate next run
        s.last_run_at = now
        svc._calculate_next_run(s)
        db.commit()
        print(f"Schedule {s.id} updated. next_run_at={s.next_run_at}")


if __name__ == '__main__':
    main()
