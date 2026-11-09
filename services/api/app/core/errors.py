from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from psycopg.errors import UndefinedTable
from sqlalchemy.exc import OperationalError, ProgrammingError

log = logging.getLogger(__name__)


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        self.status_code, self.code, self.message = status_code, code, message


def _body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return JSONResponse(status_code=exc.status_code, content=_body(exc.code, exc.message))

    @app.exception_handler(RequestValidationError)
    async def _invalid(_: Request, exc: RequestValidationError):
        problems = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'][1:]) or 'request'}: {e['msg']}"
            for e in exc.errors()
        )
        return JSONResponse(status_code=422, content=_body("invalid_parameter", problems))

    @app.exception_handler(ProgrammingError)
    async def _schema_missing(_: Request, exc: ProgrammingError):
        # A database without our tables (migrations not run, or the API pointed at the
        # wrong database) is a deployment state, not a bug: say so instead of a bare 500.
        if isinstance(exc.orig, UndefinedTable):
            log.warning("Schema missing: %s", exc.orig)
            return JSONResponse(status_code=503, content=_body(
                "schema_missing",
                "The database has no data tables yet. Run the migrations / weekly job, "
                "and check that the API's DATABASE_URL points at the loaded database."))
        raise exc

    @app.exception_handler(OperationalError)
    async def _db_down(_: Request, exc: OperationalError):
        log.warning("Database unavailable: %s", exc.orig)
        return JSONResponse(
            status_code=503,
            content=_body("database_unavailable", "The database is not reachable."),
        )
