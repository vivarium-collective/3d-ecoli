"""EcoliPackStep — write a parsimony 3D pack of the live cell at declared
simulation times. Appended as a final execution layer to a baseline run; it
runs every tick, packs a snapshot the first time its scheduled time arrives.
"""
from __future__ import annotations

from process_bigraph import Step
from bigraph_schema.contract import ProcessContract

from ecoli_3d.build import (
    pack_from_state, bulk_to_counts, bulk_to_locations,
    chromosome_state_from_live, rnaps_from_live,
)


def _default_core():
    """The real v2ecoli bigraph-schema core (ECOLI_TYPES registered). Used
    only when no ``core`` is supplied (standalone construction / tests); when
    embedded in a real composite the framework passes its own core via
    ``core.register_link``. Must be the real core, not a bare
    ``bigraph_schema.allocate_core()`` — the ``bulk_array``/``full_chromosome``
    port types this Step declares are v2ecoli domain types, registered only
    by ``v2ecoli.core.build_core()``.
    """
    from v2ecoli.core import build_core
    return build_core()


class EcoliPackStep(Step):
    """Pack a parsimony 3D structural snapshot of the live cell the first
    time each declared simulation time (or ``"division_time"``) arrives.

    ``config["snapshots"]`` maps a snapshot name to either a fixed sim-time
    (float, seconds) or the string ``"division_time"``, which resolves against
    the ``full_chromosome`` port's reported division time (the earliest
    positive, i.e. scheduled, ``division_time`` across chromosome rows — set
    once the cell commits to division; see ``v2ecoli/steps/division.py``
    ``MarkDPeriod``). Each name fires at most once, within
    ``config["epsilon_s"]`` of its target time.
    """

    # Formal contract rendered in the Composite Explorer / loom viewer
    # (bigraph_schema.contract.ProcessContract): summary + method equations +
    # port/config semantics. Describes WHAT this Step does (schedule → pack),
    # not the surrounding composite wiring.
    contract = ProcessContract(
        summary=(
            "Captures 3D structural snapshots of the simulated cell at chosen "
            "points in the cell cycle. It watches the running whole-cell model "
            "and, at each requested moment — a fixed time, or the moment of "
            "division — freezes the state into a 3D model: the most abundant "
            "molecules placed at their copy numbers inside a cell-shaped "
            "envelope sized to the current cell volume, with the chromosome(s), "
            "replication forks, and RNA polymerases positioned at their real "
            "genomic locations. Each requested snapshot is captured once."
        ),
        math=[
            "capture when   t ≥ τ − ε                 (each snapshot fires once)",
            "τ = t_div = min( dᵢ : dᵢ > 0 )            (for a snapshot requested 'at division')",
            "V_envelope = V_cell(t)                    (3D envelope sized to the cell's volume)",
            "N = top_n species, ranked by copy number",
        ],
        symbols={
            "t": "simulation time",
            "τ": "the snapshot's scheduled time — either a fixed time, or the cell's division time",
            "ε": "timing tolerance for firing a snapshot (seconds; default 1.0)",
            "dᵢ": "scheduled division time of chromosome copy i (set once the cell commits to dividing); an 'at division' snapshot fires at the earliest of these",
            "V_cell(t)": "the cell's volume at time t, which sets the size of the 3D cell-shaped (capsule) envelope",
            "N": "number of most-abundant molecular species included in the model (config 'top_n', default 40)",
            "scale": "copy-number / packing-density scale factor (default 0.3)",
        },
        inputs={
            "bulk": "Copy numbers (and sub-cellular locations) of the cell's bulk molecules — the material placed into the 3D model.",
            "shape": "Current cell geometry; its volume sizes the 3D cell-shaped envelope.",
            "global_time": "Current simulation time — the scheduler clock.",
            "full_chromosome": "The chromosome copies present, and their scheduled division time (drives 'at division' snapshots and the copy count).",
            "active_RNAP": "Active RNA polymerases with their genomic coordinates — placed at their real loci on the chromosome.",
            "active_replisome": "Active replication forks and their progress along the chromosome.",
            "chromosome_domain": "The replication-domain tree, used to assign each RNA polymerase and fork to the correct chromosome copy.",
        },
        outputs={
            "pack_status": "For each snapshot captured this step, the number of molecules placed. Side effect: writes the 3D model (geometry + metadata) to disk.",
        },
        config={
            "snapshots": "What to capture: a map of snapshot name → time in seconds, or the keyword 'division_time'.",
            "top_n": "How many of the most-abundant molecular species to include (default 40).",
            "scale": "Copy-number / packing-density scale factor (default 0.3).",
            "epsilon_s": "Timing tolerance for firing a snapshot (seconds; default 1.0).",
            "out_dir": "Directory the 3D model files are written to.",
        },
        assumptions=[
            "Each snapshot is a one-time capture: the step runs every cycle but acts only when a scheduled moment is reached, and each named snapshot fires exactly once.",
            "An 'at division' snapshot fires at the earliest scheduled division time across the chromosome copies.",
            "A snapshot waits (and retries) until the cell geometry is available, so its envelope is always sized to a real volume.",
            "Only the most abundant species are placed; the positions of chromosomes, replication forks, and RNA polymerases are taken live from the simulation, not approximated.",
        ],
    )

    # NOTE: this bigraph-schema version has no registered ``any``/``tree[any]``
    # type (parsing "tree[any]" raises — "any" isn't in the type registry), so
    # the loosely-shaped 'snapshots' config uses ``object`` (a generic,
    # unvalidated leaf) instead — it parses under both the real v2ecoli core
    # and a bare bigraph-schema core, mirroring cell_shape.ShapeStep's
    # config_schema dict-form style. The port types below, in contrast, are
    # real v2ecoli domain types (only resolve under v2ecoli.core.build_core()).
    config_schema = {
        "snapshots": "object",          # {name: float sim-time | "division_time"}
        "study": "string",
        "out_dir": "string",
        "top_n": {"_type": "integer", "_default": 40},
        "scale": {"_type": "float", "_default": 0.3},
        "epsilon_s": {"_type": "float", "_default": 1.0},
        "relax": {"_type": "boolean", "_default": False},
        "cache_dir": {"_type": "string", "_default": "out/cache"},
        "relax_params": "object",       # {equil_ps: ..., ...} — see pbg_openmm.relax_in_water
        "envelope": {"_type": "boolean", "_default": True},
    }

    def __init__(self, config=None, core=None):
        super().__init__(config, core or _default_core())
        if not self.config.get("out_dir"):
            self.config["out_dir"] = f"out/pack/{self.config.get('study') or 'snapshot'}"
        self._fired = set()

    def inputs(self):
        # bulk: bulk_array (the live ['bulk'] structured-array store).
        # shape: matches ShapeStep.outputs()'s 'shape' store type exactly —
        # a map[overwrite[float]] (flat dict of floats), so the shared store
        # realizes to one consistent schema.
        # full_chromosome: the v2ecoli unique_array domain type (registered
        # under this exact name in v2ecoli.library.schema_types); NOT the
        # plural 'full_chromosomes' — that's only a port-name convenience
        # alias elsewhere, the actual store/type name is singular.
        # active_RNAP / active_replisome / chromosome_domain: likewise real
        # v2ecoli unique_array domain types (schema_types.BIOLOGICAL_UNIQUE_TYPES),
        # registered under these exact singular names — active_RNAP carries
        # each RNAP's real genomic coordinates/domain/strand (precise
        # placement replacing the old generic scatter); active_replisome
        # carries live replication-fork coordinates (fork_fraction);
        # chromosome_domain carries the domain parent/child tree used to
        # classify an RNAP onto its chromosome copy + daughter status.
        return {"bulk": "bulk_array", "shape": "map[overwrite[float]]",
                "global_time": "float", "full_chromosome": "full_chromosome",
                "active_RNAP": "active_RNAP", "active_replisome": "active_replisome",
                "chromosome_domain": "chromosome_domain"}

    def outputs(self):
        return {"pack_status": "map[float]"}

    def _due(self, name, spec, t, states):
        if name in self._fired:
            return False
        if isinstance(spec, str) and spec == "division_time":
            # full_chromosome arrives as a numpy structured array (one row per
            # chromosome copy); division_time is per-row, 0/unset until
            # MarkDPeriod schedules it. "Scheduled" = some row has a positive
            # division_time; fire at the earliest such time (across rows).
            fc = states.get("full_chromosome")
            if fc is None or len(fc) == 0:
                return False
            scheduled = [float(x) for x in fc["division_time"] if x > 0]
            if not scheduled:               # not scheduled yet
                return False
            return t >= min(scheduled) - self.config["epsilon_s"]
        return t >= float(spec)             # fixed sim-time

    def update(self, state, interval=None):
        t = float(state.get("global_time") or 0.0)
        status = {}
        for name, spec in (self.config.get("snapshots") or {}).items():
            if not self._due(name, spec, t, state):
                continue
            volume_fl = float((state.get("shape") or {}).get("volume_fl") or 0.0)
            if volume_fl <= 0.0:
                # 'shape' store not populated yet this tick (ShapeStep hasn't
                # run/written volume_fl) — Capsule.from_volume_fl(0.0) would
                # raise. Skip WITHOUT marking fired, so this snapshot retries
                # next tick once shape is ready.
                continue
            counts = bulk_to_counts(state.get("bulk"))
            locations = bulk_to_locations(state.get("bulk"))
            # Replication state (real chromosome-copy count + fork progress) and
            # precise RNAP genomic loci, extracted LIVE from this tick's unique-
            # molecule stores — see build.chromosome_state_from_live /
            # build.rnaps_from_live.
            n_chromosomes, fork_fraction = chromosome_state_from_live(
                state.get("full_chromosome"), state.get("active_replisome"))
            rnaps = rnaps_from_live(
                state.get("active_RNAP"), state.get("full_chromosome"),
                state.get("chromosome_domain"))
            res = pack_from_state(self.config["out_dir"], name, counts, volume_fl,
                                  locations=locations,
                                  top_n=self.config["top_n"], scale=self.config["scale"],
                                  relax=self.config.get("relax", False),
                                  cache_dir=self.config.get("cache_dir") or "out/cache",
                                  relax_params=self.config.get("relax_params") or {},
                                  envelope=self.config.get("envelope", True),
                                  rnaps=rnaps, n_chromosomes=n_chromosomes,
                                  fork_fraction=fork_fraction)
            self._fired.add(name)
            status[name] = float((res or {}).get("n_placed") or 0)
        return {"pack_status": status} if status else {}
