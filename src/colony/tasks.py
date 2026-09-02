"""Avida-style computational tasks paid from an environmental reward faucet."""

from dataclasses import dataclass, field


MASK = 0xFF


@dataclass
class TaskEnvironment:
    rewards: dict[str, float] = field(default_factory=lambda: {
        # 2026-08-23 experiment: rewards raised so a computed circuit beats the
        # harvest instructions it displaces. harvest_rate=6.0/instruction, so a
        # ~10-op xor circuit must out-earn ~10 harvests to be worth genome space.
        # Gradient steepened (6x nand->xor, was 3x) to pay for climbing complexity.
        # Baseline was: nand 3.0, not 4.0, and 6.0, or 6.0, orn 7.0, xor 9.0
        "nand": 6.0, "not": 8.0, "and": 12.0, "or": 12.0,
        "orn": 14.0, "xor": 18.0,
    })

    # ── dynamic scarcity pricing ──────────────────────────────────────────
    # A task's value falls as the colony crowds onto it and rises while it sits
    # unworked. Nobody sets how many specialists of each class exist; crowding
    # sets prices and the population finds its own distribution. This also
    # re-couples income to a finite resource: total task earnings are bounded,
    # so the faucet can no longer replace the world (see 2026-08-23 runaway).
    # HARD BUDGET: pricing alone does not bound income — a floor price times an
    # unbounded solve rate is still unbounded (epoch 21 ran to pop 10,237).
    # Each task holds an energy pool that refills at a fixed rate; a solve draws
    # min(price, pool). Drained pool pays ZERO. Total colony task income can
    # therefore never exceed sum(refill) per tick, whatever the base rewards.
    budget: dict[str, float] = field(default_factory=dict)
    # Discovery is paid richly; farming is not. A large ceiling lets an UNWORKED
    # task bank a windfall for whichever lineage first evolves the circuit, while
    # the slow refill keeps sustained farming bounded. Rewards innovation over
    # exploitation without naming which innovation is wanted.
    refill_per_tick: float = 20.0   # energy/tick per task (7 tasks -> <=140/tick)
    budget_ceiling: float = 2500.0  # windfall an unworked task banks

    solve_rate: dict[str, float] = field(default_factory=dict)
    rate_decay: float = 0.995      # per-tick decay of the solve-rate EMA
    target_rate: float = 2.0       # solves/tick a task is "expected" to carry
    price_floor: float = 0.15      # crowded task keeps 15% of base
    price_ceiling: float = 2.5     # unworked task pays 250% of base

    def decay_rates(self) -> None:
        """Once per tick: refill task pools and let unworked tasks regain price."""
        for name in ("nand", "not", "and", "or", "orn", "xor", "forecast"):
            self.budget[name] = min(self.budget_ceiling,
                                    self.budget.get(name, 0.0) + self.refill_per_tick)
        for name in list(self.solve_rate):
            self.solve_rate[name] *= self.rate_decay
            if self.solve_rate[name] < 1e-6:
                del self.solve_rate[name]

    def price(self, name: str, base: float) -> float:
        """Scarcity price, then clipped to what the task pool can actually pay."""
        rate = self.solve_rate.get(name, 0.0)
        scale = self.target_rate / (rate + self.target_rate * 0.25)
        want = base * max(self.price_floor, min(self.price_ceiling, scale))
        pool = self.budget.get(name, 0.0)
        paid = min(want, pool)
        self.budget[name] = pool - paid
        return paid

    def record_solve(self, name: str) -> None:
        self.solve_rate[name] = self.solve_rate.get(name, 0.0) + 1.0

    def inputs(self, tick: int, organism_id: int,
               weather_cue: int | None = None) -> tuple[int, int]:
        a = (tick * 73 + organism_id * 29 + 17) & MASK
        b = (tick * 31 + organism_id * 47 + 91) & MASK
        return a, b

    def evaluate(self, value: int, inputs: tuple[int, int]) -> tuple[str | None, float]:
        a, b = inputs
        expected = {
            "nand": (~(a & b)) & MASK,
            "not": (~a) & MASK,
            "and": a & b,
            "or": a | b,
            "orn": a | ((~b) & MASK),
            "xor": a ^ b,
        }
        for name, answer in expected.items():
            if value & MASK == answer:
                self.record_solve(name)
                return name, self.price(name, self.rewards[name])
        return None, 0.0


@dataclass
class TemporalTaskEnvironment(TaskEnvironment):
    """Colony Two's delayed forecast niche.

    A fresh input pair defines a future value, but the value cannot be redeemed
    immediately.  The organism has to retain the computed sum until the delay
    expires, then recover it from scratch memory.  The window is deliberately
    broad enough for evolution to discover loops rather than requiring one
    exact hand-authored genome.
    """

    forecast_delay: int = 24
    forecast_window: int = 32
    # 2026-08-23: raised with the logic-task rewards to KEEP the gradient correct.
    # The delayed forecast needs store/load memory held across forecast_delay ticks
    # — strictly harder than combinational xor — so it must out-pay xor (48.0).
    # Original value: 18.0 (which was 2x the old xor of 9.0; ratio preserved).
    forecast_reward: float = 36.0
    storm_interval: int = 1000
    storm_warning: int = 100

    def inputs(self, tick: int, organism_id: int,
               weather_cue: int | None = None) -> tuple[int, int]:
        # Weather is not globally broadcast. A world-local scout may receive a
        # movement direction toward the coming bloom; everyone else sees the
        # ordinary computational challenge. Repeating the direction makes a
        # single INPUT -> SIGNAL mutation useful without prescribing it.
        if weather_cue is not None:
            return weather_cue, weather_cue
        return super().inputs(tick, organism_id)

    def forecast_target(self, inputs: tuple[int, int]) -> int:
        return (inputs[0] + inputs[1]) & MASK

    def evaluate_forecast(self, value: int, target: int) -> tuple[str | None, float]:
        if value & MASK == target & MASK:
            self.record_solve("forecast")
            return "forecast", self.price("forecast", self.forecast_reward)
        return None, 0.0
