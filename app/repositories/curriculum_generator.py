from app.models.curriculum_generator import SERVICE, CurriculumGeneratorJob
from app.repositories._job import JobRepository


class CurriculumGeneratorRepository(JobRepository[CurriculumGeneratorJob]):
    def __init__(self):
        super().__init__(SERVICE, CurriculumGeneratorJob)
