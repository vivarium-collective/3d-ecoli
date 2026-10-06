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
            "Snapshot packer. The Step runs every tick but acts only when a "
            "scheduled snapshot time arrives: for each declared name it waits "
            "until the target sim-time (or the cell's division time) is "
            "reached, then selects the top_n most-abundant species and places "
            "them — together with the live chromosome-copy, replication-fork, "
            "and RNAP-locus state — into a capsule envelope sized from the "
            "cell's current volume, writing a parsimony 3D pack to out_dir. "
            "Each name fires at most once."
        ),
        math=[
            "fire(name)   when   t ≥ τ(name) − ε   and   name ∉ fired        (each name fires once)",
            "τ(name) = spec                                            (fixed sim-time, seconds)",
            "τ(name) = min( d_i > 0 )   over full_chromosome.division_time   (spec = 'division_time')",
            "skip (do NOT fire) when   volume_fl ≤ 0                    (shape not written yet this tick)",
            "pack = place( top_n most-abundant species , scale , envelope(volume_fl) )",
            "(n_chromosomes, fork_fraction) ← (full_chromosome, active_replisome)",
            "rnaps ← (active_RNAP, full_chromosome, chromosome_domain)   (genomic loci → chromosome copy)",
            "pack_status[name] = n_placed",
        ],
        symbols={
            "t": "current simulation time (s), read from the global_time port",
            "τ(name)": "target sim-time for a snapshot (s): the fixed spec, or the resolved division time",
            "ε": "firing tolerance (s), config 'epsilon_s' (default 1.0)",
            "d_i": "per-chromosome-copy division_time (s); positive once MarkDPeriod schedules division",
            "fired": "set of snapshot names already packed (each fires at most once)",
            "top_n": "number of most-abundant species packed, config 'top_n' (default 40)",
            "scale": "structural packing scale factor, config 'scale' (default 0.3)",
            "volume_fl": "current cell volume (fL), read from the shape port (ShapeStep output)",
            "n_chromosomes": "live chromosome-copy count, derived from full_chromosome",
            "fork_fraction": "replication-fork progress (0–1), derived from active_replisome",
            "n_placed": "number of ingredient instances actually placed in the pack",
        },
        inputs={
            "bulk": "Live ['bulk'] structured-array store (bulk_array) — bulk molecule counts and locations.",
            "shape": "Flat cell-geometry dict (map[overwrite[float]]) from ShapeStep; volume_fl sizes the capsule envelope.",
            "global_time": "Current simulation time (s) — the scheduler clock.",
            "full_chromosome": "v2ecoli unique_array of chromosome copies; carries per-copy division_time (used for 'division_time' scheduling) and the copy count.",
            "active_RNAP": "v2ecoli unique_array of active RNAPs with genomic coordinates/domain/strand — precise RNAP placement.",
            "active_replisome": "v2ecoli unique_array of replication forks (fork_fraction) — replication progress.",
            "chromosome_domain": "v2ecoli unique_array domain parent/child tree — classifies each RNAP onto its chromosome copy / daughter.",
        },
        outputs={
            "pack_status": "map[float] {snapshot_name: n_placed} for snapshots packed this tick (empty when nothing fires). Side effect: writes pack.json + meta.json under out_dir.",
        },
        assumptions=[
            "Packing is a snapshot (one-shot per name), not a time-stepping update — the Step runs every tick but acts only when a scheduled time is reached.",
            "Each snapshot name fires at most once, within epsilon_s of its target time; 'division_time' resolves to the earliest positive per-copy division_time.",
            "A snapshot is skipped and retried next tick (NOT marked fired) when volume_fl ≤ 0, i.e. ShapeStep has not yet written geometry this tick.",
            "Only the top_n most-abundant species are packed, at the given scale; placement is into a capsule envelope sized from the live cell volume.",
            "Chromosome-copy count, fork progress, and RNAP loci are read LIVE from the unique-molecule stores at each firing, not approximated.",
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
