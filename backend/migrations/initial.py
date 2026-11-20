from src.config.database import Base, engine
from src import models


# Columns added after the first release. create_all never alters existing tables.
ADDED_COLUMNS = {
    'jobs': {
        'root_id': 'INTEGER',
        'revision': 'INTEGER NOT NULL DEFAULT 1',
        'supplements': 'JSON NOT NULL DEFAULT \'[]\'',
        'fingerprint': 'VARCHAR(64) NOT NULL DEFAULT \'\'',
        'approved_at': 'DOUBLE PRECISION',
        'superseded_by': 'INTEGER',
    },
}


def _add_missing_columns():
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    for table, columns in ADDED_COLUMNS.items():
        if table not in inspector.get_table_names():
            continue
        existing = {column['name'] for column in inspector.get_columns(table)}
        with engine.begin() as connection:
            for name, ddl in columns.items():
                if name not in existing:
                    connection.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {ddl}'))
            if table == 'jobs':
                connection.execute(text('UPDATE jobs SET root_id = id WHERE root_id IS NULL'))
                connection.execute(text("UPDATE jobs SET revision = 1 WHERE revision IS NULL"))
                connection.execute(text("UPDATE jobs SET supplements = '[]' WHERE supplements IS NULL"))


def migrate():
    Base.metadata.create_all(engine)
    _add_missing_columns()
    _add_fingerprint_index()


def _add_fingerprint_index():
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    if 'jobs' not in inspector.get_table_names():
        return
    names = {index['name'] for index in inspector.get_indexes('jobs')}
    names |= {constraint['name'] for constraint in inspector.get_unique_constraints('jobs')}
    with engine.begin() as connection:
        if 'uq_job_root_fingerprint' not in names:
            connection.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS uq_job_root_fingerprint ON jobs (root_id, fingerprint)'))
        if 'uq_job_root_revision' not in names:
            connection.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS uq_job_root_revision ON jobs (root_id, revision)'))
if __name__=='__main__':migrate()
