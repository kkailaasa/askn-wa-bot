# app/scheduler/maintenance.py

from celery import Celery
from celery.schedules import crontab
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
import logging
import os
from decouple import config

logger = logging.getLogger(__name__)

app = Celery('maintenance', broker='redis://redis:6379/0', backend='redis://redis:6379/0')

class LogMaintenance:
    def __init__(self):
        # Get base directory
        self.base_dir = Path(__file__).resolve().parent.parent.parent

        # Define paths to both databases
        self.app_log_db = self.base_dir / 'app_data' / 'app.db'
        self.chat_db = self.base_dir / 'app_data' / 'chat.db'

        # Ensure directories exist
        self.app_log_db.parent.mkdir(exist_ok=True)
        self.chat_db.parent.mkdir(exist_ok=True)

    def cleanup_old_logs(self, days: int = 30):
        """Delete logs older than specified days from both databases"""
        cutoff_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
        deleted_counts = {'app_logs': 0, 'chat_logs': 0}

        # Clean app logs
        try:
            if self.app_log_db.exists():
                with sqlite3.connect(str(self.app_log_db)) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "DELETE FROM logs WHERE timestamp < ?",
                        (cutoff_date,)
                    )
                    deleted_counts['app_logs'] = cursor.rowcount
                    conn.commit()
        except Exception as e:
            logger.error(f"Error cleaning app logs: {e}")

        # Clean chat logs
        try:
            if self.chat_db.exists():
                with sqlite3.connect(str(self.chat_db)) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "DELETE FROM message_logs WHERE created_at < ?",
                        (cutoff_date,)
                    )
                    deleted_counts['chat_logs'] = cursor.rowcount
                    conn.commit()
        except Exception as e:
            logger.error(f"Error cleaning chat logs: {e}")

        return deleted_counts

    def vacuum_databases(self):
        """Optimize both databases by vacuuming"""
        for db_path in [self.app_log_db, self.chat_db]:
            try:
                if db_path.exists():
                    with sqlite3.connect(str(db_path)) as conn:
                        conn.execute("VACUUM")
                    logger.info(f"Vacuum completed for {db_path.name}")
            except Exception as e:
                logger.error(f"Error vacuuming {db_path.name}: {e}")

    def get_log_stats(self):
        """Get statistics about both log databases"""
        stats = {
            'app_logs': {},
            'chat_logs': {}
        }

        # Get app log stats
        try:
            if self.app_log_db.exists():
                with sqlite3.connect(str(self.app_log_db)) as conn:
                    cursor = conn.cursor()

                    # Total count
                    cursor.execute("SELECT COUNT(*) FROM logs")
                    stats['app_logs']['total_count'] = cursor.fetchone()[0]

                    # Count by level
                    cursor.execute(
                        "SELECT level, COUNT(*) FROM logs GROUP BY level"
                    )
                    stats['app_logs']['by_level'] = dict(cursor.fetchall())

                    # Date range
                    cursor.execute(
                        """SELECT
                            MIN(timestamp) as oldest,
                            MAX(timestamp) as newest
                            FROM logs"""
                    )
                    oldest, newest = cursor.fetchone()
                    stats['app_logs']['date_range'] = {
                        'oldest': oldest,
                        'newest': newest
                    }

                    # Size
                    stats['app_logs']['size'] = self.app_log_db.stat().st_size
        except Exception as e:
            logger.error(f"Error getting app log stats: {e}")

        # Get chat log stats
        try:
            if self.chat_db.exists():
                with sqlite3.connect(str(self.chat_db)) as conn:
                    cursor = conn.cursor()

                    # Total count
                    cursor.execute("SELECT COUNT(*) FROM message_logs")
                    stats['chat_logs']['total_count'] = cursor.fetchone()[0]

                    # Count by status
                    cursor.execute(
                        "SELECT status, COUNT(*) FROM message_logs GROUP BY status"
                    )
                    stats['chat_logs']['by_status'] = dict(cursor.fetchall())

                    # Date range
                    cursor.execute(
                        """SELECT
                            MIN(created_at) as oldest,
                            MAX(created_at) as newest
                            FROM message_logs"""
                    )
                    oldest, newest = cursor.fetchone()
                    stats['chat_logs']['date_range'] = {
                        'oldest': oldest,
                        'newest': newest
                    }

                    # Size
                    stats['chat_logs']['size'] = self.chat_db.stat().st_size
        except Exception as e:
            logger.error(f"Error getting chat log stats: {e}")

        return stats

@app.task
def scheduled_maintenance():
    """Scheduled maintenance task"""
    logger.info("Starting scheduled log maintenance")
    maintenance = LogMaintenance()

    # Get stats before cleanup
    before_stats = maintenance.get_log_stats()

    # Clean old logs (30 days by default)
    retention_days = config('LOG_RETENTION_DAYS', default=30, cast=int)
    deleted = maintenance.cleanup_old_logs(days=retention_days)

    # Vacuum databases
    maintenance.vacuum_databases()

    # Get stats after cleanup
    after_stats = maintenance.get_log_stats()

    logger.info(
        f"Maintenance completed: Deleted {deleted['app_logs']} app logs "
        f"and {deleted['chat_logs']} chat logs"
    )
    return {
        'deleted_counts': deleted,
        'before_stats': before_stats,
        'after_stats': after_stats
    }

# Schedule maintenance to run daily at 3 AM
app.conf.beat_schedule = {
    'daily-log-maintenance': {
        'task': 'app.scheduler.maintenance.scheduled_maintenance',
        'schedule': crontab(hour=3, minute=0),  # Run at 3 AM
    },
}