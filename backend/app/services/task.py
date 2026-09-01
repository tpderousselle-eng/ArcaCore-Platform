from backend.app.core.base_service import BaseService
from backend.app.crud.task import TaskCRUD
from backend.app.schemas.task import (
    TaskCreate,
    TaskUpdate,
)


class TaskService(BaseService):
    crud_class = TaskCRUD

    def create_task(
        self,
        project_id: int,
        user_id: int,
        task: TaskCreate,
    ):
        return self.crud.create_task(
            project_id=project_id,
            user_id=user_id,
            title=task.title,
            slug=task.slug,
            description=task.description,
            assigned_to=task.assigned_to,
            start_date=task.start_date,
            due_date=task.due_date,
        )

    def list_tasks(
        self,
        project_id: int,
    ):
        return self.crud.list_tasks(
            project_id,
        )

    def get_task(
        self,
        task_id: int,
    ):
        task = self.crud.get_task(task_id)

        if task is None:
            raise ValueError("Task not found.")

        return task

    def update_task(
        self,
        task_id: int,
        update: TaskUpdate,
    ):
        task = self.get_task(task_id)

        return self.crud.update_task(
            task,
            **update.model_dump(exclude_unset=True),
        )

    def delete_task(
        self,
        task_id: int,
    ):
        task = self.get_task(task_id)

        self.crud.delete_task(task)

        return {
            "message": "Task deleted successfully."
        }