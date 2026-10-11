from abc import ABC, abstractmethod
from typing import ClassVar
from app.domain.dtos import TripContext, ViolationCandidate

class Rule(ABC):
    code: ClassVar[str]

    @abstractmethod
    def evaluate(self, ctx: TripContext) -> list[ViolationCandidate]:
        ...
