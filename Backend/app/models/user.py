from sqlalchemy import Column, Integer, String, Text, TIMESTAMP, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()

class ArrtUser(Base):
    __tablename__ = "arrt_users"
    __table_args__ = (UniqueConstraint("detail_token", name="uq_detail_token"),)

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    city = Column(String)
    state = Column(String)
    credential_string = Column(String)
    detail_token = Column(String, nullable=False, unique=True, index=True)
    raw_json = Column(JSONB)  # optional, store the original dict for future use
    fetched_at = Column(TIMESTAMP(timezone=True), default=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<ArrtUser id={self.id} name={self.name!r}>"

