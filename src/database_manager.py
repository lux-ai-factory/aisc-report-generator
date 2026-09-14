from sqlalchemy import create_engine, event, exists
from sqlalchemy.engine import URL
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session, sessionmaker, with_loader_criteria
from sqlalchemy.exc import NoSuchModuleError

from resources.sql_alchemy import Dataset, Element, Evaluation, LegalRequirement, Measure, Observation, Project, Tool


@event.listens_for(Session, "before_flush")
@event.listens_for(Session, "do_orm_execute")
def _read_only(*args):
    first_arg = args[0]

    if hasattr(first_arg, "is_select"):
        execute_state = first_arg

        if execute_state.is_insert or execute_state.is_update or execute_state.is_delete:
            raise PermissionError("Database session is read-only. Modifications are not allowed.")
        return

    raise PermissionError("Database session is read-only. Modifications are not allowed.")

class DatabaseManager:
    def __init__(self, db_url: str | URL):
        self.db_url = db_url if isinstance(db_url, URL) else make_url(db_url)
        self.engine = create_engine(self.db_url, echo=False)

        self.validate_connection()

        # session for the db reader to retrieve global statistics from the db
        self._session_factory = sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
            autoflush=False
        )

        # separate session factory to apply project, evaluation, and tool/plugin specific restrictions
        # multi-tenant pattern
        self.restricted_session_factory = sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
            autoflush=False
        )

        event.listen(self.restricted_session_factory, "do_orm_execute", self._restrict_plugin_queries)

        
        self.global_session = self._session_factory()

        

    def validate_connection(self) -> bool:
        """
        Check whether a connection to the db can be established, and raise an informative error if the driver is missing.
        """
        try:
            with self.engine.connect():
                pass
        except NoSuchModuleError:
            driver_name = self.db_url.drivername.split('+', 1)[1] if '+' in self.db_url.drivername else self.db_url.drivername
            raise ImportError(f"Missing driver: Please run 'pip install {driver_name}' to use this database.")    
    
    def get_session(self) -> Session:
        return self.global_session
    
    """
    Restrict the sessions that are passed to workers to a given project and evaluation, and so workers can only retrieve data that are tied to the plugin they are generating the report section for.
    """
    
    def get_plugin_restricted_session(self, project_id: int, evaluation_id: int, tool_id: int) -> Session:
        session = self.restricted_session_factory()
        session.info.update({
            'project_id': project_id,
            'evaluation_id': evaluation_id,
            'tool_id': tool_id
        })
        return session

    def _restrict_plugin_queries(self, execute_state):
        if not execute_state.is_select:
            return

        conf = execute_state.session.info
        project_id = conf.get('project_id')
        evaluation_id = conf.get('evaluation_id')
        tool_id = conf.get('tool_id')

        if project_id is None or evaluation_id is None or tool_id is None:
            raise ValueError(
                "Restricted session is missing scope information. Expected project_id, evaluation_id, and tool_id."
            )

        execute_state.statement = execute_state.statement.options(
            with_loader_criteria(
                Project,
                lambda cls, project_id=project_id: cls.id == project_id,
                include_aliases=True,
            ),
            with_loader_criteria(
                Evaluation,
                lambda cls, project_id=project_id, evaluation_id=evaluation_id: (
                    cls.id == evaluation_id
                ) & (cls.project_id == project_id),
                include_aliases=True,
            ),
            with_loader_criteria(
                Observation,
                lambda cls, evaluation_id=evaluation_id, tool_id=tool_id: (
                    cls.eval_id == evaluation_id
                ) & (cls.tool_id == tool_id),
                include_aliases=True,
            ),
            with_loader_criteria(
                Tool,
                lambda cls, tool_id=tool_id: cls.id == tool_id,
                include_aliases=True,
            ),
            with_loader_criteria(
                Element,
                lambda cls, project_id=project_id: cls.project_id == project_id,
                include_aliases=True,
            ),
            with_loader_criteria(
                Measure,
                lambda cls, evaluation_id=evaluation_id, tool_id=tool_id: exists().where(
                    Observation.id == cls.observation_id,
                    Observation.eval_id == evaluation_id,
                    Observation.tool_id == tool_id,
                ).correlate_except(Observation),
                include_aliases=True,
            ),
            with_loader_criteria(
                Dataset,
                lambda cls, evaluation_id=evaluation_id, tool_id=tool_id: exists().where(
                    Observation.dataset_id == cls.id,
                    Observation.eval_id == evaluation_id,
                    Observation.tool_id == tool_id,
                ).correlate_except(Observation),
                include_aliases=True,
            ),
            with_loader_criteria(
                LegalRequirement,
                lambda cls, project_id=project_id: cls.project_1_id == project_id,
                include_aliases=True,
            ),
        )

