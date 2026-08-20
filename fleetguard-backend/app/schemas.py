from pydantic import BaseModel
from typing import List

class SignalWeight(BaseModel):
    signal: str
    weight: float
    is_included: bool = True

class RuleCreate(BaseModel):
    part_code: str
    signals: List[SignalWeight]