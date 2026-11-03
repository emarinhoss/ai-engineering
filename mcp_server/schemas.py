"""Case parameter schema (pydantic v2), the table in docs/specs/01_interfaces.md.

validate(dict) never raises: it returns (model or None, errors, warnings).
to_params(model) returns the complete parameter dict (defaults filled in) that is handed to the
mesher, the physics gates and worker.make_case.case_id. Because case_id is computed on that
complete dict, it depends on the defaults: adding a default later changes every case_id.
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

# Bounds that depend on the family: (low, high) inclusive.
THETA1_BOUNDS = {"inlet2r": (5.0, 12.0), "wedge": (2.0, 20.0), "inlet3r": (3.0, 10.0)}
THETA2_BOUNDS = {"inlet2r": (5.0, 14.0), "inlet3r": (3.0, 10.0)}
THETA3_BOUNDS = (3.0, 10.0)                       # inlet3r only (Task 9)
ALTITUDE_BOUNDS = {"inlet3r": (28.0, 35.0)}       # other families: 30 km only
MACH_BOUNDS = {"inlet3r": (3.5, 4.5)}
T_WALL_BOUNDS = {"inlet3r": (300.0, 600.0)}
RADIUS_BOUNDS = (0.002, 0.05)


class CaseParams(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    family: Literal["inlet2r", "inlet3r", "wedge", "cylinder"]
    theta1_deg: float | None = Field(None, allow_inf_nan=False)    # inlet2r, wedge
    theta2_deg: float | None = Field(None, allow_inf_nan=False)    # inlet2r, inlet3r
    theta3_deg: float | None = Field(None, allow_inf_nan=False)    # inlet3r only
    radius_m: float | None = Field(None, allow_inf_nan=False)      # cylinder only, default 0.010
    mach: float = Field(4.0, ge=3.0, le=5.0, allow_inf_nan=False)
    # int | float so that 30 stays the integer 30 in the params (case_id is a hash of them).
    altitude_km: int | float = Field(30, allow_inf_nan=False)
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
        if fam in ("inlet2r", "inlet3r"):
            need("theta2_deg", THETA2_BOUNDS[fam])
        else:
            forbid("theta2_deg")
        if fam == "inlet3r":
            need("theta3_deg", THETA3_BOUNDS)
            for name, bounds in (("altitude_km", ALTITUDE_BOUNDS), ("mach", MACH_BOUNDS), ("T_wall_K", T_WALL_BOUNDS)):
                need(name, bounds[fam])
        else:
            forbid("theta3_deg")
            if self.altitude_km != 30:
                errs.append(f"altitude_km: {self.altitude_km:g} not allowed for family {fam} (30 km only)")
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
    if model.mach != 4.0 and model.family != "inlet3r":
        warnings.append(f"mach = {model.mach:g}: the design table and validation are for Mach 4.0")
    return model, [], warnings


def to_params(model):
    """Plain dict of JSON types, defaults filled in, fields that do not apply left out."""
    return model.model_dump(exclude_none=True)
