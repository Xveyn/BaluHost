"""Drop old VCL tables from database."""
from sqlalchemy import create_engine, text

engine = create_engine('sqlite:///./baluhost.db')

with engine.connect() as conn:
    conn.execute(text('DROP TABLE IF EXISTS file_versions'))
    conn.execute(text('DROP TABLE IF EXISTS version_blobs'))
    conn.execute(text('DROP TABLE IF EXISTS vcl_settings'))
    conn.execute(text('DROP TABLE IF EXISTS vcl_stats'))
    conn.commit()
    
print('✅ Alte VCL Tabellen gelöscht')
