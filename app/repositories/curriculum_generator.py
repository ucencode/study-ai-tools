import json
from pathlib import Path

from app.models.curriculum_generator import CurriculumGeneratorJob


FILEPATH = Path("data/jobs/curriculum_generator")


class CurriculumGeneratorRepository:
    def __init__(self):
        self.directory = FILEPATH
        self.directory.mkdir(parents=True, exist_ok=True)

    def select_all(self) -> list[CurriculumGeneratorJob]:
        jobs: list[CurriculumGeneratorJob] = []

        for path in self.directory.glob("*/job.json"):
            with path.open("r", encoding="utf-8") as file:
                jobs.append(json.load(file))

        return jobs

    def select_by_id(self, id: str) -> CurriculumGeneratorJob | None:
        path = self._get_path(id)

        if not path.exists():
            return None

        with path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def create(
        self,
        data: CurriculumGeneratorJob,
    ) -> CurriculumGeneratorJob:
        path = self._get_path(data["id"])

        if path.exists():
            raise FileExistsError(f"Job {data['id']} already exists")

        path.parent.mkdir(parents=True, exist_ok=True)

        self._write(path, data)

        return data

    def update(
        self,
        id: str,
        data: CurriculumGeneratorJob,
    ) -> CurriculumGeneratorJob:
        path = self._get_path(id)

        if not path.exists():
            raise FileNotFoundError(f"Job {id} does not exist")

        self._write(path, data)

        return data

    def delete(self, id: str) -> None:
        path = self._get_path(id)

        if not path.exists():
            return

        path.unlink()

        # Remove the job directory if it's now empty.
        try:
            path.parent.rmdir()
        except OSError:
            pass

    def _get_path(self, id: str) -> Path:
        return self.directory / id / "job.json"

    def _write(
        self,
        path: Path,
        data: CurriculumGeneratorJob,
    ) -> None:
        temporary_path = path.with_suffix(".tmp")

        with temporary_path.open("w", encoding="utf-8") as file:
            json.dump(
                data,
                file,
                indent=2,
                ensure_ascii=False,
            )

        temporary_path.replace(path)