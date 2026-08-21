from app.repositories.jobs import JobRepository

class JobService:
    def __init__(self, job_repo):
        self.job_repo = job_repo()

    def get_all(self):
        return self.job_repo.list()

    def create(self):
        pass

    def update(self):
        pass

    def delete(self):
        pass
