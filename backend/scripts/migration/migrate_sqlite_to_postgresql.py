#!/usr/bin/env python3
"""
SQLite to PostgreSQL Migration Script

Migriert Daten von SQLite zu PostgreSQL.
Wird nach erfolgreichen Tests durchgeführt.

Usage:
    python migrate_sqlite_to_postgresql.py \
        --source baluhost.db \
        --target postgresql://user:pass@localhost:5432/baluhost \
        --verify \
        --backup
"""

import argparse
import logging
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Any
import shutil

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SQLiteToPostgreSQLMigrator:
    """Migriert SQLite Datenbank zu PostgreSQL."""
    
    def __init__(
        self,
        source_path: str,
        target_url: str,
        backup: bool = True,
        dry_run: bool = False
    ):
        self.source_path = Path(source_path)
        self.target_url = target_url
        self.backup = backup
        self.dry_run = dry_run
        self.migration_log: List[Dict[str, Any]] = []
    
    def backup_sqlite_database(self) -> Optional[Path]:
        """Erstelle Backup der SQLite Datenbank."""
        if not self.backup or not self.source_path.exists():
            return None
        
        logger.info("📦 Erstelle SQLite Backup...")
        
        try:
            backup_dir = Path("dev-backups")
            backup_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_path = backup_dir / f"baluhost_sqlite_{timestamp}.db"
            
            shutil.copy2(self.source_path, backup_path)
            
            logger.info(f"✅ Backup erstellt: {backup_path}")
            self.migration_log.append({
                "step": "backup",
                "status": "success",
                "file": str(backup_path),
                "timestamp": datetime.now().isoformat()
            })
            
            return backup_path
            
        except Exception as e:
            logger.error(f"❌ Backup fehlgeschlagen: {e}")
            self.migration_log.append({
                "step": "backup",
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            })
            raise
    
    def verify_sqlite_database(self) -> bool:
        """Verifiziere SQLite Datenbank."""
        logger.info("🔍 Verifiziere SQLite Datenbank...")
        
        try:
            if not self.source_path.exists():
                logger.error(f"❌ SQLite Datei nicht gefunden: {self.source_path}")
                return False
            
            # Prüfe ob es eine echte SQLite Datei ist
            with open(self.source_path, 'rb') as f:
                header = f.read(16)
                if not header.startswith(b'SQLite format 3'):
                    logger.error("❌ Datei ist keine gültige SQLite Datenbank")
                    return False
            
            logger.info("✅ SQLite Datenbank ist gültig")
            self.migration_log.append({
                "step": "verify_sqlite",
                "status": "success",
                "timestamp": datetime.now().isoformat()
            })
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Verifikation fehlgeschlagen: {e}")
            self.migration_log.append({
                "step": "verify_sqlite",
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            })
            return False
    
    def migrate_database(self) -> bool:
        """Führe Datenbank-Migration durch."""
        logger.info("🔄 Starte Datenbank-Migration...")
        
        try:
            from sqlalchemy import create_engine, inspect, text, MetaData, Table
            
            # Verbindungen erstellen
            sqlite_engine = create_engine(f"sqlite:///{self.source_path}")
            postgres_engine = create_engine(self.target_url, echo=False)
            
            # 1. Verifiziere PostgreSQL Verbindung
            logger.info("📡 Teste PostgreSQL Verbindung...")
            try:
                with postgres_engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                logger.info("✅ PostgreSQL Verbindung erfolgreich")
            except Exception as e:
                logger.error(f"❌ PostgreSQL Verbindung fehlgeschlagen: {e}")
                logger.error("   Stelle sicher, dass PostgreSQL läuft")
                logger.error("   Oder führe aus: docker-compose -f deployment/docker-compose.yml up -d")
                return False
            
            # 2. Lese SQLite Struktur
            logger.info("📖 Lese SQLite Struktur...")
            inspector = inspect(sqlite_engine)
            tables = inspector.get_table_names()
            
            if not tables:
                logger.warning("⚠️  Keine Tabellen in SQLite gefunden")
                return True
            
            logger.info(f"📋 Gefundene Tabellen: {tables}")
            
            # 3. Migriere Tabellen
            for table_name in tables:
                logger.info(f"🚀 Migriere Tabelle: {table_name}")
                
                try:
                    # Lese Daten aus SQLite
                    with sqlite_engine.connect() as sqlite_conn:
                        # Für SQLite mit echten Daten
                        try:
                            result = sqlite_conn.execute(text(f"SELECT * FROM {table_name}"))
                            rows = result.fetchall()
                            columns = result.keys()
                        except Exception:
                            logger.warning(f"⚠️  Konnte Tabelle {table_name} nicht lesen")
                            continue
                    
                    logger.info(f"   → {len(rows)} Zeilen zu migrieren")
                    
                    if len(rows) == 0:
                        logger.info(f"   → Tabelle ist leer, skip data insert")
                        self.migration_log.append({
                            "step": f"migrate_table_{table_name}",
                            "status": "success",
                            "rows": 0,
                            "timestamp": datetime.now().isoformat()
                        })
                        continue
                    
                    # Migriere Daten zu PostgreSQL
                    if not self.dry_run:
                        with postgres_engine.begin() as postgres_conn:
                            for i, row in enumerate(rows):
                                try:
                                    # Baue INSERT Statement
                                    placeholders = ", ".join(["%s"] * len(columns))
                                    column_names = ", ".join(columns)
                                    query = f"INSERT INTO {table_name} ({column_names}) VALUES ({placeholders})"
                                    
                                    postgres_conn.execute(text(query), row)
                                    
                                    if (i + 1) % 100 == 0:
                                        logger.debug(f"   → {i + 1} Zeilen inserted")
                                        
                                except Exception as e:
                                    logger.warning(f"   ⚠️  Zeile {i} konnte nicht migriert werden: {e}")
                    
                    self.migration_log.append({
                        "step": f"migrate_table_{table_name}",
                        "status": "success",
                        "rows": len(rows),
                        "dry_run": self.dry_run,
                        "timestamp": datetime.now().isoformat()
                    })
                    
                except Exception as e:
                    logger.error(f"❌ Fehler bei Tabelle {table_name}: {e}")
                    self.migration_log.append({
                        "step": f"migrate_table_{table_name}",
                        "status": "error",
                        "error": str(e),
                        "timestamp": datetime.now().isoformat()
                    })
                    return False
            
            logger.info("✅ Migration erfolgreich abgeschlossen")
            return True
            
        except ImportError:
            logger.error("❌ SQLAlchemy nicht installiert")
            logger.error("   Führe aus: pip install sqlalchemy")
            return False
        except Exception as e:
            logger.error(f"❌ Migration fehlgeschlagen: {e}")
            self.migration_log.append({
                "step": "migrate",
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            })
            return False
    
    def run(self, verify: bool = True) -> bool:
        """Führe komplette Migration durch."""
        try:
            logger.info("=" * 60)
            logger.info("  SQLite → PostgreSQL Migration")
            logger.info("=" * 60)
            
            if self.dry_run:
                logger.info("🧪 DRY-RUN MODE (keine Daten werden geschrieben)")
            
            # 1. Backup
            self.backup_sqlite_database()
            
            # 2. Verifiziere SQLite
            if verify and not self.verify_sqlite_database():
                logger.error("❌ SQLite Verifikation fehlgeschlagen")
                return False
            
            # 3. Migriere Daten
            if not self.migrate_database():
                logger.error("❌ Migration fehlgeschlagen")
                return False
            
            logger.info("=" * 60)
            logger.info("  ✅ Migration erfolgreich abgeschlossen!")
            logger.info("=" * 60)
            
            self.save_migration_log()
            return True
            
        except Exception as e:
            logger.error(f"❌ Kritischer Fehler: {e}")
            self.save_migration_log()
            return False
    
    def save_migration_log(self):
        """Speichere Migrations-Log."""
        log_dir = Path("dev-backups")
        log_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_path = log_dir / f"migration_{timestamp}.json"
        
        log_data = {
            "migration_type": "sqlite_to_postgresql",
            "timestamp": datetime.now().isoformat(),
            "source": str(self.source_path),
            "target": self.target_url,
            "dry_run": self.dry_run,
            "steps": self.migration_log
        }
        
        with open(log_path, "w") as f:
            json.dump(log_data, f, indent=2)
        
        logger.info(f"📝 Log gespeichert: {log_path}")


async def main():
    """Main Entry Point."""
    parser = argparse.ArgumentParser(
        description="Migriere SQLite zu PostgreSQL"
    )
    parser.add_argument(
        "--source",
        default="baluhost.db",
        help="SQLite Datenbank Datei (default: baluhost.db)"
    )
    parser.add_argument(
        "--target",
        default="postgresql://baluhost_user:baluhost_password@localhost:5432/baluhost",
        help="PostgreSQL Datenbank URL"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        default=True,
        help="Verifiziere SQLite vor Migration"
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        default=True,
        help="Erstelle Backup vor Migration"
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip Backup"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Zeige was würde migriert, aber schreibe keine Daten"
    )
    
    args = parser.parse_args()
    
    backup = not args.no_backup
    
    migrator = SQLiteToPostgreSQLMigrator(
        source_path=args.source,
        target_url=args.target,
        backup=backup,
        dry_run=args.dry_run
    )
    
    success = migrator.run(verify=args.verify)
    
    return 0 if success else 1


if __name__ == "__main__":
    import asyncio
    import sys
    
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
