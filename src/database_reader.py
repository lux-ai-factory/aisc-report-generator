from sqlalchemy import select

from resources.sql_alchemy import Evaluation, LegalRequirement, Observation, Project, Tool

class DatabaseReader:
    def __init__(self, session):
        self.session = session

    def _resolve_project(self, project: int | str) -> tuple[int, str]:
        if isinstance(project, int):
            project_id = project
            project_name_stmt = select(Project.name).where(Project.id == project_id)
            project_name = self.session.scalar(project_name_stmt) or str(project_id)
            return project_id, project_name

        stmt = select(Project.id, Project.name).where(Project.name == project)
        row = self.session.execute(stmt).first()
        if row is None:
            raise ValueError(f"Project '{project}' not found")
        return int(row[0]), str(row[1])

    def get_tools_in_db(self) -> set[str]:
        stmt = select(Tool.name).distinct()
        return {name for name in self.session.scalars(stmt).all()}

    def get_project_evaluations(self, project: int | str) -> list[Evaluation]:
        project_id, _ = self._resolve_project(project)
        
        stmt = (
            select(Evaluation)
            .where(Evaluation.project_id == project_id)
            .order_by(Evaluation.id)
        )
        return list(self.session.scalars(stmt).all())

    def get_tools_for_evaluation(self, evaluation_id: int) -> list[tuple[int, str]]:
        stmt = (
            select(Tool)
            .join(Observation, Observation.tool_id == Tool.id)
            .where(Observation.eval_id == evaluation_id)
            .distinct(Tool.id)
            .order_by(Tool.name)
        )

        tools = self.session.scalars(stmt).all()
        return [(tool.id, tool.name) for tool in tools]

    def get_summary(self, project: int | str) -> dict[str, object]:
        project_id, project_name = self._resolve_project(project)
        evaluations = self.get_project_evaluations(project_id)

        legal_req_stmt = (
            select(LegalRequirement)
            .where(LegalRequirement.project_1_id == project_id)
            .order_by(LegalRequirement.id)
        )
        legal_requirements = []
        for req in self.session.scalars(legal_req_stmt).all():
            parts = [
                req.legal_ref or "",
                req.standard or "",
                req.principle or "",
            ]
            requirement_label = " - ".join([part for part in parts if part])
            legal_requirements.append(requirement_label or f"Requirement #{req.id}")

        rows: list[dict[str, object]] = []
        for evaluation in evaluations:
            tools = self.get_tools_for_evaluation(evaluation.id)
            rows.append(
                {
                    "evaluation_id": evaluation.id,
                    "tools": [{"id": tool_id, "name": tool_name} for tool_id, tool_name in tools],
                    "legal_requirements": legal_requirements,
                }
            )

        return {
            "project_id": project_id,
            "project_name": project_name,
            "rows": rows,
        }