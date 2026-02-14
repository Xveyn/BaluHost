from app.core.database import SessionLocal
from app.models.sync_state import SyncState, SyncMetadata


def main():
    db = SessionLocal()
    try:
        ss_count = db.query(SyncState).count()
        sm_count = db.query(SyncMetadata).count()
        print(f"SyncState rows: {ss_count}")
        print(f"SyncMetadata rows: {sm_count}")

        if ss_count:
            print('\nSample SyncState rows:')
            for s in db.query(SyncState).limit(5).all():
                print(f"id={s.id} user_id={s.user_id} device_id={s.device_id} last_sync={s.last_sync}")

        if sm_count:
            print('\nSample SyncMetadata rows:')
            for m in db.query(SyncMetadata).limit(5).all():
                print(f"id={m.id} file_metadata_id={m.file_metadata_id} sync_state_id={m.sync_state_id} conflict={m.conflict_detected} is_deleted={m.is_deleted}")
    except Exception as e:
        print('Error querying DB:', e)
    finally:
        db.close()


if __name__ == '__main__':
    main()
