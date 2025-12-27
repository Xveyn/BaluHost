from app.core.database import SessionLocal
from app.models.sync_state import SyncState, SyncMetadata
from app.models.file_metadata import FileMetadata
from datetime import datetime


def main():
    db = SessionLocal()
    try:
        sync_state = db.query(SyncState).first()
        if not sync_state:
            print('No SyncState found, aborting')
            return

        print(f'Using SyncState id={sync_state.id} device_id={sync_state.device_id} user_id={sync_state.user_id}')

        # Ensure there is a FileMetadata for this user
        fm = db.query(FileMetadata).filter(FileMetadata.owner_id == sync_state.user_id).first()
        if not fm:
            fm = FileMetadata(
                path=f"/test-sync/{sync_state.device_id}-test.txt",
                name=f"{sync_state.device_id}-test.txt",
                owner_id=sync_state.user_id,
                size_bytes=123,
                is_directory=False
            )
            db.add(fm)
            db.commit()
            db.refresh(fm)
            print(f'Created FileMetadata id={fm.id} path={fm.path}')
        else:
            print(f'Found existing FileMetadata id={fm.id} path={fm.path}')

        # Create a SyncMetadata row for this sync_state + file
        now = datetime.utcnow()
        sm = SyncMetadata(
            file_metadata_id=fm.id,
            sync_state_id=sync_state.id,
            content_hash='deadbeef'*8,
            file_size=fm.size_bytes,
            local_modified_at=now,
            server_modified_at=now,
            is_deleted=False,
            conflict_detected=False
        )
        db.add(sm)
        db.commit()
        db.refresh(sm)
        print(f'Created SyncMetadata id={sm.id} for file_metadata_id={sm.file_metadata_id}')

    except Exception as e:
        print('Error seeding sample sync metadata:', e)
    finally:
        db.close()


if __name__ == '__main__':
    main()
