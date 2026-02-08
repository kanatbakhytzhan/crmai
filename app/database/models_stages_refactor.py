from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, UniqueConstraint, BigInteger
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database.session import Base

class TenantStage(Base):
    """Owner-managed pipeline stage (Kanban column)"""
    __tablename__ = "tenant_stages"
    
    id = Column(Integer, primary_key=True, index=True) # Using Integer to match SQLAlchemy usually, but BigInteger in DB is fine (Postgres handles it)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    stage_key = Column(String(50), nullable=False)
    title_ru = Column(String(100), nullable=False)
    title_kz = Column(String(100), nullable=False)
    color = Column(String(7), nullable=False, default='#94a3b8')
    order_index = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "stage_key", name="unique_tenant_stage_key"),
    )

    # Relationships
    tenant = relationship("Tenant", back_populates="stages")
