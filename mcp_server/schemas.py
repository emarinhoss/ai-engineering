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
# airfoil2d (Task 10, task10_tasks.md): the SU2 section family of the drone study's high level.
AIRFOIL_BOUNDS = {"camber_pct": (0.0, 6.0), "thickness_pct": (8.0, 15.0),
                  "reynolds": (8.0e4, 5.0e5), "alpha_deg": (-4.0, 16.0)}
AIRFOIL_FIELDS = (*AIRFOIL_BOUNDS, "transition")
# drone (Task 10): the sizing study's low-level family; camber_pct and thickness_pct are shared with airfoil2d.
DRONE_BOUNDS = {"span_m": (1.2, 3.0), "aspect_ratio": (6.0, 16.0), "taper_ratio": (0.3, 1.0),
                "battery_fraction": (0.20, 0.45), "camber_pct": (0.0, 6.0), "thickness_pct": (8.0, 15.0)}
# Fields of the supersonic families, not allowed for airfoil2d; filled with these defaults otherwise.
SUPERSONIC_DEFAULTS = {"mach": 4.0, "altitude_km": 30, "T_wall_K": 300.0, "solver": "NAVIER_STOKES"}
MAX_ITER_DEFAULT = {"airfoil2d": 6000}            # all families 6000; airfoil2d was 3000 until decision 6 (2026-11-08)


class CaseParams(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    family: Literal["inlet2r", "inlet3r", "wedge", "cylinder", "airfoil2d", "drone"]
    theta1_deg: float | None = Field(None, allow_inf_nan=False)    # inlet2r, wedge
    theta2_deg: float | None = Field(None, allow_inf_nan=False)    # inlet2r, inlet3r
    theta3_deg: float | None = Field(None, allow_inf_nan=False)    # inlet3r only
    radius_m: float | None = Field(None, allow_inf_nan=False)      # cylinder only, default 0.010
    # mach, altitude_km, T_wall_K, solver and max_iter default to None and are filled in by
    # _family_rules (SUPERSONIC_DEFAULTS, MAX_ITER_DEFAULT), so airfoil2d can forbid the first four.
    mach: float | None = Field(None, ge=3.0, le=5.0, allow_inf_nan=False)
    # int | float so that 30 stays the integer 30 in the params (case_id is a hash of them).
    altitude_km: int | float | None = Field(None, allow_inf_nan=False)
    T_wall_K: float | None = Field(None, ge=250.0, le=1200.0, allow_inf_nan=False)
    solver: Literal["NAVIER_STOKES", "EULER", "RANS_SA"] | None = None
    camber_pct: float | None = Field(None, allow_inf_nan=False)       # airfoil2d only
    thickness_pct: float | None = Field(None, allow_inf_nan=False)    # airfoil2d only
    airfoil: str | None = Field(None, pattern=r"^[a-z0-9_-]{1,32}$")  # airfoil2d only: file name
    reynolds: float | None = Field(None, allow_inf_nan=False)         # airfoil2d only
    alpha_deg: float | None = Field(None, allow_inf_nan=False)        # airfoil2d only
    transition: Literal["BCM", "LM", "NONE"] | None = None           # airfoil2d only, default BCM
    span_m: float | None = Field(None, allow_inf_nan=False)           # drone only
    aspect_ratio: float | None = Field(None, allow_inf_nan=False)     # drone only
    taper_ratio: float | None = Field(None, allow_inf_nan=False)      # drone only
    battery_fraction: float | None = Field(None, allow_inf_nan=False) # drone only
    save_restart: bool | None = None                                  # airfoil2d only: write restart_flow.csv
    restart_from: str | None = Field(None, pattern=r"^airfoil2d-[0-9a-f]{10}$")  # airfoil2d only: donor case id
    # airfoil2d only, experiment S1/S2: unset means the recorded solver setting (cases/config.py)
    cfl_max: float | None = Field(None, ge=1.0, le=1000.0, allow_inf_nan=False)       # CFL ceiling
    linear_tol: float | None = Field(None, ge=1e-8, le=1e-1, allow_inf_nan=False)     # LINEAR_SOLVER_ERROR
    cauchy_elems: int | None = Field(None, ge=50, le=2000)                            # CONV_CAUCHY_ELEMS
    cauchy_eps: float | None = Field(None, ge=1e-9, le=1e-3, allow_inf_nan=False)     # CONV_CAUCHY_EPS
    fidelity: Literal["low", "high"] | None = None                    # drone only, default low
    mesh_level: Literal["coarse", "medium", "fine"] | None = None     # default medium; not for drone
    save_volume: bool = False
    tag: str = Field(pattern=r"^[a-z0-9_-]{1,32}$")
    max_iter: int | None = Field(None, ge=100, le=20000)

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

        if fam == "drone":
            for name in ("theta1_deg", "theta2_deg", "theta3_deg", "radius_m", "mesh_level", "max_iter",
                         *SUPERSONIC_DEFAULTS, "reynolds", "alpha_deg", "transition", "airfoil", "save_restart", "restart_from",
                         "cfl_max", "linear_tol", "cauchy_elems", "cauchy_eps"):
                forbid(name)
            for name, bounds in DRONE_BOUNDS.items():
                need(name, bounds)
            if self.fidelity is None:
                self.fidelity = "low"
            if errs:
                raise ValueError("\n".join(errs))
            return self
        forbid("fidelity")
        for name in ("span_m", "aspect_ratio", "taper_ratio", "battery_fraction"):
            forbid(name)
        if self.mesh_level is None:
            self.mesh_level = "medium"
        if self.max_iter is None:
            self.max_iter = MAX_ITER_DEFAULT.get(fam, 6000)
        if fam == "airfoil2d":
            for name in ("theta1_deg", "theta2_deg", "theta3_deg", "radius_m", *SUPERSONIC_DEFAULTS):
                forbid(name)
            if self.airfoil is not None:
                if self.camber_pct is not None or self.thickness_pct is not None:
                    errs.append("airfoil: give either airfoil or camber_pct and thickness_pct, not both")
                bounds_now = {k: v for k, v in AIRFOIL_BOUNDS.items()
                              if k not in ("camber_pct", "thickness_pct")}
            else:
                bounds_now = AIRFOIL_BOUNDS
            for name, bounds in bounds_now.items():
                need(name, bounds)
            if self.transition is None:
                self.transition = "BCM"
            if errs:
                raise ValueError("\n".join(errs))
            return self
        for name in (*AIRFOIL_FIELDS, "airfoil", "save_restart", "restart_from",
                     "cfl_max", "linear_tol", "cauchy_elems", "cauchy_eps"):
            forbid(name)
        for name, value in SUPERSONIC_DEFAULTS.items():
            if getattr(self, name) is None:
                setattr(self, name, value)
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
    if model.mach is not None and model.mach != 4.0 and model.family != "inlet3r":
        warnings.append(f"mach = {model.mach:g}: the design table and validation are for Mach 4.0")
    return model, [], warnings


def to_params(model):
    """Plain dict of JSON types, defaults filled in, fields that do not apply left out."""
    return model.model_dump(exclude_none=True)
