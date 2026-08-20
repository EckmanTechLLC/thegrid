"""Avida-style computational tasks paid from an environmental reward faucet."""

from dataclasses import dataclass, field


MASK = 0xFF


@dataclass
class TaskEnvironment:
    rewards: dict[str, float] = field(default_factory=lambda: {
        "nand": 3.0, "not": 4.0, "and": 6.0, "or": 6.0,
        "orn": 7.0, "xor": 9.0,
    })

    def inputs(self, tick: int, organism_id: int) -> tuple[int, int]:
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
                return name, self.rewards[name]
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
    forecast_reward: float = 18.0
    storm_interval: int = 1000
    storm_warning: int = 100

    def inputs(self, tick: int, organism_id: int) -> tuple[int, int]:
        phase = tick % self.storm_interval
        if phase >= self.storm_interval - self.storm_warning:
            upcoming_cycle = tick // self.storm_interval + 1
            drought = upcoming_cycle % 4
            return drought, (drought + 2) % 4
        return super().inputs(tick, organism_id)

    def forecast_target(self, inputs: tuple[int, int]) -> int:
        return (inputs[0] + inputs[1]) & MASK

    def evaluate_forecast(self, value: int, target: int) -> tuple[str | None, float]:
        if value & MASK == target & MASK:
            return "forecast", self.forecast_reward
        return None, 0.0
