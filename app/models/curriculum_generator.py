from typing import Literal, TypedDict

from app.models._job import Job

class CurriculumGeneratorData(TypedDict):
    title: str
    course: str
    credits: int | None
    topics: list[str]
    outcomes: list[str]
    topics_count: int
    outcomes_count: int
    estimated_weeks: int
    tags: list[str]


class CurriculumGeneratorJob(Job):
    data: CurriculumGeneratorData