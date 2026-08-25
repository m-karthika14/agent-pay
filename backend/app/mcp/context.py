"""
Purpose: Shared request context for MCP tools.

MCP tool functions run outside FastAPI's request/dependency-injection
cycle, so they cannot use `Depends(get_db_session)` the way REST routes do.
This module reuses the exact same session/commit/rollback logic instead of
duplicating it: app.db.session.get_db_session is already an async generator
function shaped for `@asynccontextmanager`, so wrapping it here gives MCP
tools an equivalent `async with mcp_db_session() as session:` usable outside
FastAPI.
"""
from contextlib import asynccontextmanager

from app.db.session import get_db_session

mcp_db_session = asynccontextmanager(get_db_session)
