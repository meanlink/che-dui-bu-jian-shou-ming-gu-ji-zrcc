from sqlalchemy import String, JSON, Double, ForeignKey, Boolean, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from src.config.database import Base
class Job(Base):
    __tablename__ = 'jobs'
    __table_args__ = (UniqueConstraint('root_id', 'fingerprint', name='uq_job_root_fingerprint'), UniqueConstraint('root_id', 'revision', name='uq_job_root_revision'))
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    dataset_id: Mapped[int] = mapped_column(ForeignKey('datasets.id'))
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default='queued')
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(String(1000), default='')
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[float] = mapped_column(Double)
    finished_at: Mapped[float | None] = mapped_column(Double, nullable=True)
    # Version chain: every supplement report that narrows an interval creates a new Job row.
    root_id: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    supplements: Mapped[list] = mapped_column(JSON, default=list)
    fingerprint: Mapped[str] = mapped_column(String(64), default='')
    approved_at: Mapped[float | None] = mapped_column(Double, nullable=True)
    superseded_by: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
