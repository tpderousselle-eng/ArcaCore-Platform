from sqlalchemy.orm import Session

from backend.app.core.base_crud import BaseCRUD
from backend.app.models.project import Project
from backend.app.models.task import Task


class TaskCRUD(BaseCRUD[Task]):
    def __init__(
        self,
        db: Session,
    ):
        super().__init__(
            db=db,
            model=Task,
        )

    def create_task(
        self,
        project_id: int,
        user_id: int,
        title: str,
        slug: str,
        description: str | None,
        assigned_to: int | None,
        start_date,
        due_date,
    ) -> Task:

        project = (
            self.db.query(Project)
            .filter(Project.id == project_id)
            .first()
        )

        if project is None:
            raise ValueError("Project not found.")

        return self.create(
            project_id=project_id,
            title=title,
            slug=slug,
            description=description,
            status="todo",
            priority="medium",
            created_by=user_id,
            assigned_to=assigned_to,
            start_date=start_date,
            due_date=due_date,
        )

    def list_tasks(
        self,
        project_id: int,
    ) -> list[Task]:

        return (
            self.db.query(Task)
            .filter(Task.project_id == project_id)
            .all()
        )

    def get_task(
        self,
        task_id: int,
    ) -> Task | None:

        return self.get(task_id)

    def update_task(
        self,
        task: Task,
        **kwargs,
    ) -> Task:

        return self.update(
            task,
            **kwargs,
        )

    def delete_task(
        self,
        task: Task,
    ) -> None:

        self.delete(task)