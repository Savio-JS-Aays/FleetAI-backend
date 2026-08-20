from sqlalchemy import Column, String, Integer, Float, Boolean, Date, ForeignKey
from .database import Base

class Vehicle(Base):
    __tablename__ = "vehicles"

    vin = Column(String, primary_key=True, index=True)
    model = Column(String, nullable=False)
    region = Column(String, nullable=False)
    registration_date = Column(Date, nullable=False)
    total_km = Column(Integer, nullable=False)


class Part(Base):
    __tablename__ = "parts"

    part_code = Column(String, primary_key=True, index=True)
    part_name = Column(String, nullable=False)
    category = Column(String, nullable=False)
    design_life_km = Column(Integer, nullable=False)


class JobCard(Base):
    __tablename__ = "job_cards"

    job_card_id = Column(String, primary_key=True, index=True)
    vin = Column(String, ForeignKey("vehicles.vin"), nullable=False)
    part_code = Column(String, ForeignKey("parts.part_code"), nullable=False)
    failure_date = Column(Date, nullable=False)
    odometer_at_failure = Column(Integer, nullable=False)
    replaced = Column(Boolean, default=True)


class Telematics(Base):
    __tablename__ = "telematics"

    telematics_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    vin = Column(String, ForeignKey("vehicles.vin"), nullable=False)
    week_start_date = Column(Date, nullable=False)
    
    # 9 Normalized Signals
    coolant_temp_variance = Column(Float, nullable=False)
    oil_pressure_dips = Column(Integer, nullable=False)
    battery_voltage_sag = Column(Float, nullable=False)
    dtc_recurrence_rate = Column(Float, nullable=False)
    harsh_braking_frequency = Column(Float, nullable=False)
    overload_duty_share = Column(Float, nullable=False)
    high_rpm_dwell_time = Column(Float, nullable=False)
    short_trip_ratio = Column(Float, nullable=False)
    idle_time_pct = Column(Float, nullable=False)


class RuleConfig(Base):
    __tablename__ = "rule_configs"

    rule_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    part_code = Column(String, ForeignKey("parts.part_code"), nullable=False)
    signal_name = Column(String, nullable=False)
    correlation_weight = Column(Float, nullable=False)
    is_included = Column(Boolean, default=True)


class Prediction(Base):
    __tablename__ = "predictions"

    prediction_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    vin = Column(String, ForeignKey("vehicles.vin"), nullable=False)
    part_code = Column(String, ForeignKey("parts.part_code"), nullable=False)
    failure_probability_pct = Column(Float, nullable=False)
    risk_tier = Column(String, nullable=False)
    top_signal = Column(String, nullable=True)
    rul_km = Column(Integer, nullable=False)
    computed_date = Column(Date, nullable=False)