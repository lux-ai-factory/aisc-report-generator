"""Where the renderer reads.

Every read goes through one of the modules of this package; each public function takes the
project and the pinned system version first, so no block can read without a scope.

One database per project: REPORT_PLATFORM_DATABASE_URL is read for
core.project and pg_database only; the versions (project.system) and every module's rows are read from
the project's own database, REPORT_PROJECT_DB_URL with `{database}` = project_<hex>, where the database
is the project scope. A missing project database, module schema or table reads as nothing (`empty`).
"""
from __future__ import annotations

from dataclasses import dataclass, field

_REQUIRED = ("REPORT_PLATFORM_DATABASE_URL", "REPORT_SUPERSET_DATABASE_URL", "REPORT_PROJECT_DB_URL",
             "REPORT_AIRO_VOCAB_PATH", "REPORT_OBJECTIVES_CSV_PATH")


@dataclass(frozen=True)
class Sources:
    platform_dsn: str = field(repr=False)
    superset_dsn: str = field(repr=False)
    project_db_template: str = field(repr=False)
    airo_vocab_path: str
    objectives_csv_path: str
    #: the generated VAIR labels; unset, a VAIR term shows as its id
    vair_vocab_path: str | None = None
    #: link base for charts ("Open in the dashboard")
    superset_url: str | None = None

    @classmethod
    def from_env(cls, env) -> "Sources":
        for name in _REQUIRED:
            if not env.get(name):
                raise ValueError(f"{name} is not set")
        return cls(
            platform_dsn=env["REPORT_PLATFORM_DATABASE_URL"],
            superset_dsn=env["REPORT_SUPERSET_DATABASE_URL"],
            project_db_template=env["REPORT_PROJECT_DB_URL"],
            airo_vocab_path=env["REPORT_AIRO_VOCAB_PATH"],
            objectives_csv_path=env["REPORT_OBJECTIVES_CSV_PATH"],
            vair_vocab_path=env.get("REPORT_VAIR_VOCAB_PATH") or None,
            superset_url=env.get("REPORT_SUPERSET_PUBLIC_URL") or env.get("REPORT_SUPERSET_URL") or None,
        )

    def project_dsn(self, database: str) -> str:
        return self.project_db_template.replace("{database}", database)
