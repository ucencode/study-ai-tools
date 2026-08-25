from typing import Literal

from app.models._job import Job, Strict

GenerationMode = Literal["short", "full"]

SERVICE = "curriculum_generator"


class Question(Strict):
    id: int
    topic: str = ""
    question: str


class Answer(Strict):
    id: int
    known: bool


class CurriculumGeneratorSettings(Strict):
    """The part of a run a preset can fix: everything except the curriculum itself.

    Params is this plus the source, so a new option is presettable by default.
    """

    model: str
    lang: str = "auto"
    mode: GenerationMode = "short"

    # The plan is always generated — it produces the chapter order. This only controls
    # whether it is rendered into the final document.
    include_plan: bool = True


class CurriculumGeneratorParams(CurriculumGeneratorSettings):
    source_name: str

    # Extra direction per topic, keyed by topic name.
    topic_context: dict[str, str] = {}

    questions: list[Question] = []
    answers: list[Answer] = []


class CurriculumGeneratorResult(Strict):
    title: str = ""
    course: str = ""
    course_code: str = ""
    credits: int = 0
    topics: list[str] = []
    outcomes: list[str] = []
    topics_count: int = 0
    outcomes_count: int = 0
    estimated_weeks: int = 0
    tags: list[str] = []


class OutlineEntry(Strict):
    topic: str
    scope: str = ""
    # Names of EARLIER topics this chapter genuinely requires. Empty means it stands alone.
    depends_on: list[str] = []


class ChapterState(Strict):
    topic: str
    file: str
    # Terms/notation this chapter fixed, for the chapters that depend on it.
    established: list[str] = []


class CurriculumGeneratorJob(Job):
    service: str = SERVICE
    params: CurriculumGeneratorParams
    result: CurriculumGeneratorResult | None = None
    outline: list[OutlineEntry] = []
    chapters: list[ChapterState] = []
