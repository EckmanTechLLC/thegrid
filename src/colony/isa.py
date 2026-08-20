"""Instruction set for colony organisms."""

from dataclasses import dataclass
from enum import IntEnum


class Op(IntEnum):
    NOP = 0
    HARVEST = 1
    SCAN = 2
    MOVE = 3
    ALLOC = 4
    COPY = 5
    IFNOTDONE = 6
    JMPB = 7
    FORK = 8
    FREE = 9
    INC = 10
    DEC = 11
    SWAP = 12
    INPUT = 13
    NAND = 14
    OUTPUT = 15
    IFZERO = 16
    PUSH = 17
    SIGNAL = 18
    LISTEN = 19
    BUILD = 20
    PEEK = 21
    COPYN = 22
    ADD = 23
    SUB = 24
    XOR = 25
    LOAD = 26
    STORE = 27
    JMPR = 28


@dataclass(frozen=True)
class Instruction:
    name: str
    cost: float
    doc: str


ISA = [
    Instruction("nop", 0.15, "do nothing"),
    Instruction("harvest", 0.35, "draw energy from the current tile"),
    Instruction("scan", 0.45, "sense the richest neighbouring direction into A"),
    Instruction("move", 0.70, "move in direction A mod 4"),
    Instruction("alloc", 0.80, "reserve memory for a child genome"),
    Instruction("copy", 0.55, "copy one genome word into the child buffer"),
    Instruction("ifnotdone", 0.20, "execute next instruction while copying; otherwise skip it"),
    Instruction("jmpb", 0.25, "jump back (C mod 8) + 1 instructions"),
    Instruction("fork", 1.50, "birth the completed child"),
    Instruction("free", 0.25, "release an incomplete child buffer"),
    Instruction("inc", 0.20, "increment A"),
    Instruction("dec", 0.20, "decrement A"),
    Instruction("swap", 0.20, "swap A and B"),
    Instruction("input", 0.30, "read an environmental input into A"),
    Instruction("nand", 0.40, "set A to NAND(A, B)"),
    Instruction("output", 0.35, "submit A to the task environment"),
    Instruction("ifzero", 0.20, "skip next instruction unless A is zero"),
    Instruction("push", 0.20, "copy A into C"),
    Instruction("signal", 0.45, "broadcast A locally for other organisms"),
    Instruction("listen", 0.30, "read the strongest local signal into A"),
    Instruction("build", 1.00, "spend energy improving the current resource patch"),
    Instruction("peek", 0.55, "read a neighbouring genome word into A"),
    Instruction("copyn", 0.65, "copy a neighbouring genome word into the child"),
    Instruction("add", 0.30, "set A to A plus B modulo 256"),
    Instruction("sub", 0.30, "set A to A minus B modulo 256"),
    Instruction("xor", 0.30, "set A to bitwise A XOR B"),
    Instruction("load", 0.35, "load scratch byte B modulo 8 into A"),
    Instruction("store", 0.45, "store A in scratch byte B modulo 8"),
    Instruction("jmpr", 0.30, "jump relative by C modulo 15 minus 7"),
]

NUM_OPS = len(ISA)
NAME_TO_OP = {instruction.name: i for i, instruction in enumerate(ISA)}


def build_ancestor() -> list[int]:
    """A small viable replicator; all later organisms descend from this."""
    return [
        Op.HARVEST, Op.HARVEST, Op.ALLOC, Op.COPY, Op.IFNOTDONE,
        Op.JMPB, Op.FORK, Op.SCAN, Op.MOVE,
    ]


def build_founder_palette() -> list[list[int]]:
    """Twelve viable replicators with different immediately usable traits."""
    core = build_ancestor()
    return [
        core,
        [Op.HARVEST, *core],
        [*core, Op.SCAN, Op.MOVE, Op.HARVEST],
        [*core, Op.BUILD],
        [*core, Op.SIGNAL],
        [*core, Op.LISTEN, Op.MOVE, Op.HARVEST],
        [*core, Op.STORE, Op.LOAD],
        [*core, Op.INC, Op.PUSH, Op.ADD],
        [*core, Op.INPUT, Op.INPUT, Op.OUTPUT],
        [*core, Op.PEEK],
        # COPYN gets a chance to import a neighbour word; COPY remains a
        # fallback when isolated, so this founder is independently viable.
        [Op.HARVEST, Op.HARVEST, Op.ALLOC, Op.COPYN, Op.COPY,
         Op.IFNOTDONE, Op.JMPB, Op.FORK, Op.SCAN, Op.MOVE],
        [Op.HARVEST, Op.NOP, Op.HARVEST, Op.ALLOC, Op.COPY,
         Op.IFNOTDONE, Op.JMPB, Op.FORK, Op.NOP, Op.SCAN, Op.MOVE],
    ]


def disassemble(genome: list[int], annotate: bool = True) -> str:
    lines = []
    for index, word in enumerate(genome):
        name = ISA[word].name if 0 <= word < NUM_OPS else f"invalid({word})"
        lines.append(f"{index:03d}: {name}" if annotate else f"{index}: {name}")
    return "\n".join(lines)
