from sqlalchemy import Column, Integer, String, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import relationship
from app.models.base import Base
from app.domain.enums import Gender

class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    name = Column(String, nullable=False)
    gender = Column(SAEnum(Gender, native_enum=False), nullable=False)
    phone = Column(String, nullable=False)
    
    user = relationship("User")

class Driver(Base):
    __tablename__ = "drivers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    name = Column(String, nullable=False)
    license_no = Column(String, nullable=False)
    
    user = relationship("User")

class Vehicle(Base):
    __tablename__ = "vehicles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    reg_no = Column(String, unique=True, nullable=False)
    model = Column(String, nullable=False)
