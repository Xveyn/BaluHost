"""Pydantic models of the steam_gaming routes; field names are the API contract.

NB: no ``from __future__ import annotations`` - see routes.py.
"""
from typing import List, Literal, Optional

from pydantic import BaseModel


class LaunchableGame(BaseModel):
    app_id: str
    name: str


class RunningGame(BaseModel):
    app_id: str
    name: Optional[str]


class GameListResponse(BaseModel):
    games: List[LaunchableGame]
    running: Optional[RunningGame]
    # Information for the client, not a control - the launch route checks itself.
    can_launch_here: bool


class LaunchResponse(BaseModel):
    status: Literal["requested"]
    # Read after the sequence; None when logind cannot tell.
    session_locked: Optional[bool]
