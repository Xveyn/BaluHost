from __future__ import annotations

from typing import Protocol

from app.schemas.system import (
    AvailableDisksResponse,
    CreateArrayRequest,
    DeleteArrayRequest,
    FormatDiskRequest,
    RaidActionResponse,
    RaidOptionsRequest,
    RaidSimulationRequest,
    RaidStatusResponse,
)


class RaidBackend(Protocol):
    def get_status(self) -> RaidStatusResponse:
        ...

    def degrade(self, payload: RaidSimulationRequest) -> RaidActionResponse:
        ...

    def rebuild(self, payload: RaidSimulationRequest) -> RaidActionResponse:
        ...

    def finalize(self, payload: RaidSimulationRequest) -> RaidActionResponse:
        ...

    def configure(self, payload: RaidOptionsRequest) -> RaidActionResponse:
        ...

    def get_available_disks(self) -> AvailableDisksResponse:
        ...

    def format_disk(self, payload: FormatDiskRequest) -> RaidActionResponse:
        ...

    def create_array(self, payload: CreateArrayRequest) -> RaidActionResponse:
        ...

    def delete_array(self, payload: DeleteArrayRequest) -> RaidActionResponse:
        ...
