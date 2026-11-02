"""Case parameter schema (pydantic v2), the table in docs/specs/01_interfaces.md.

validate(dict) never raises: it returns (model or None, errors, warnings).
to_params(model) returns the complete parameter dict (defaults filled in) that is handed to the
mesher, the physics gates and worker.make_case.case_id. Because case_id is computed on that
complete dict, it depends on the defaults: adding a default later changes every case_id.
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

# Bounds that depend on the family: (low, high) inclusive.
THETA1_BOUNDS = {"inlet2r": (5.0, 12.0), "wedge": (2.0, 20.0)}
THETA2_BOUNDS = (5.0, 14.0)
RADIUS_BOUNDS = (0.002, 0.05)


class CaseParams(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    family: Literal["inlet2r", "wedge", "cylinder"]
    theta1_deg: float | None = Field(None, allow_inf_nan=False)    # inlet2r, wedge
    theta2_deg: float | None = Field(None, allow_inf_nan=False)    # inlet2r only
    radius_m: float | None = Field(None, allow_inf_nan=False)      # cylinder only, default 0.010
    mach: float = Field(4.0, ge=3.0, le=5.0, allow_inf_nan=False)
    altitude_km: Literal[30] = 30
    T_wall_K: float = Field(300.0, ge=250.0, le=1200.0, allow_inf_nan=False)
    solver: Literal["NAVIER_STOKES", "EULER", "RANS_SA"] = "NAVIER_STOKES"
    mesh_level: Literal["coarse", "medium", "fine"] = "medium"
    save_volume: bool = False
    tag: str = Field(pattern=r"^[a-z0-9_-]{1,32}$")
    max_iter: int = Field(6000, ge=100, le=20000)

    @model_validator(mode="after")
    def _family_rules(self):
        """Bounds and presence of the fields that depend on the family."""
        fam, errs = self.family, []

        def need(name, bounds):
            v = getattr(self, name)
            if v is None:
                errs.append(f"{name}: required for family {fam}")
            elif not bounds[0] <= v <= bounds[1]:
                errs.append(f"{name}: {v:g} outside [{bounds[0]:g}, {bounds[1]:g}] for family {fam}")

        def forbid(name):
            if getattr(self, name) is not None:
                errs.append(f"{name}: not allowed for family {fam}")

        if fam == "cylinder":
            forbid("theta1_deg")
            if self.radius_m is None:
                self.radius_m = 0.010
            need("radius_m", RADIUS_BOUNDS)
        else:
            need("theta1_deg", THETA1_BOUNDS[fam])
            forbid("radius_m")
        if fam == "inlet2r":
            need("theta2_deg", THETA2_BOUNDS)
        else:
            forbid("theta2_deg")
        if errs:
            raise ValueError("\n".join(errs))
        return self


def validate(params):
    """(model | None, errors, warnings). Never raises."""
    if not isinstance(params, dict):
        return None, ["params must be a JSON object"], []
    try:
        model = CaseParams.model_validate(params)
    except ValidationError as exc:
        errors = []
        for e in exc.errors():
            where = ".".join(str(x) for x in e["loc"])
            msg = e["msg"].removeprefix("Value error, ")
            for line in msg.split("\n"):
                errors.append(f"{where}: {line}" if where else line)
        return None, errors, []
    except Exception as exc:  # noqa: BLE001  (validate must never raise)
        return None, [f"unexpected error while validating: {exc!r}"], []
    warnings = []
    if model.mach != 4.0:
        warnings.append(f"mach = {model.mach:g}: the design table and validation are for Mach 4.0")
    return model, [], warnings


def to_params(model):
    """Plain dict of JSON types, defaults filled in, fields that do not apply left out."""
    return model.model_dump(exclude_none=True)
