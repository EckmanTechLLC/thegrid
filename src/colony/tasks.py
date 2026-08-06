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
