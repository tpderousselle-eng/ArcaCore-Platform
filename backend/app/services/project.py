from backend.app.crud.project import ProjectCRUD
from backend.app.schemas.project import (
    ProjectCreate,
    ProjectUpdate,
)


class ProjectService:
    def __init__(self, db):
        self.crud = ProjectCRUD(db)

    def create_project(
        self,
        workspace_id: int,
        user_id: int,
        project: ProjectCreate,
    ):
        return self.crud.create_project(
            workspace_id=workspace_id,
            user_id=user_id,
            name=project.name,
            slug=project.slug,
            description=project.description,
        )

    def list_projects(
        self,
        workspace_id: int,
    ):
        return self.crud.list_projects(
            workspace_id,
        )

    def get_project(
        self,
        project_id: int,
    ):
        project = self.crud.get_project(project_id)

        if project is None:
            raise ValueError("Project not found.")

        return project

    def update_project(
        self,
        project_id: int,
        update: ProjectUpdate,
    ):
        project = self.get_project(project_id)

        return self.crud.update_project(
            project,
            **update.model_dump(exclude_unset=True),
        )

    def delete_project(
        self,
        project_id: int,
    ):
        project = self.get_project(project_id)

        self.crud.delete_project(project)

        return {
            "message": "Project deleted successfully."
        }