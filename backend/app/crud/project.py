from sqlalchemy.orm import Session

from backend.app.core.base_crud import BaseCRUD
from backend.app.models.project import Project
from backend.app.models.workspace import Workspace


class ProjectCRUD(BaseCRUD[Project]):
    def __init__(
        self,
        db: Session,
    ):
        super().__init__(
            db=db,
            model=Project,
        )

    def create_project(
        self,
        workspace_id: int,
        user_id: int,
        name: str,
        slug: str,
        description: str | None,
    ) -> Project:

        workspace = (
            self.db.query(Workspace)
            .filter(Workspace.id == workspace_id)
            .first()
        )

        if workspace is None:
            raise ValueError("Workspace not found.")

        return self.create(
            workspace_id=workspace_id,
            name=name,
            slug=slug,
            description=description,
            created_by=user_id,
        )

    def list_projects(
        self,
        workspace_id: int,
    ) -> list[Project]:

        return (
            self.db.query(Project)
            .filter(Project.workspace_id == workspace_id)
            .all()
        )

    def get_project(
        self,
        project_id: int,
    ) -> Project | None:

        return self.get(project_id)

    def update_project(
        self,
        project: Project,
        **kwargs,
    ) -> Project:

        return self.update(
            project,
            **kwargs,
        )

    def delete_project(
        self,
        project: Project,
    ) -> None:

        self.delete(project)