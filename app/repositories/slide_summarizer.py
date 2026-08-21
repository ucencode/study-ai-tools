from app.models.slide_summarizer import SERVICE, SlideSummarizerJob
from app.repositories._job import JobRepository


class SlideSummarizerRepository(JobRepository[SlideSummarizerJob]):
    def __init__(self):
        super().__init__(SERVICE, SlideSummarizerJob)
