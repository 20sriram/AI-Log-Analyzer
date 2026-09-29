from sqlalchemy import Column, Integer, String, Text
from .database import Base

class Log(Base):
    __tablename__ = "logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(String)
    service = Column(String)
    level = Column(String)
    message = Column(Text)