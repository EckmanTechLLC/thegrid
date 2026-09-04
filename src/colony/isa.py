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
    SALVAGE = 29
    PUBLISH = 30
    CALL = 31
    WRITE = 32
    POST = 33
    FETCH = 34
    LOCATE = 35
    LINK = 36
    BURN = 37
    OFFER = 38
    DEFINE = 39
    MACRO0 = 40
    MACRO1 = 41
    MACRO2 = 42
    MACRO3 = 43
    MACRO4 = 44
    MACRO5 = 45
    MACRO6 = 46
    MACRO7 = 47
    STEAL = 48
    CORRUPT = 49


@dataclass(frozen=True)
class Instruction:
    name: str
    cost: float
    doc: str


ISA = [
    # nop is FREE: neutral drift space. Carrying material that is not useful YET
    # must be survivable or chance has nowhere to accumulate and duplications get
    # stripped before they can diverge. Bloat stays braked by replication cost
    # (every word costs 0.55 to copy), so genomes cannot pad without limit.
    Instruction("nop", 0.0, "do nothing"),
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
    Instruction("signal", 0.0, "broadcast A locally for other organisms"),
    Instruction("listen", 0.0, "read the strongest local signal into A"),
    Instruction("build", 1.00, "spend energy improving the current resource patch"),
    Instruction("peek", 0.55, "read a neighbouring genome word into A"),
    Instruction("copyn", 0.65, "copy a neighbouring genome word into the child"),
    Instruction("add", 0.30, "set A to A plus B modulo 256"),
    Instruction("sub", 0.30, "set A to A minus B modulo 256"),
    Instruction("xor", 0.30, "set A to bitwise A XOR B"),
    Instruction("load", 0.35, "load scratch byte B modulo 8 into A"),
    Instruction("store", 0.45, "store A in scratch byte B modulo 8"),
    Instruction("jmpr", 0.30, "jump relative by C modulo 15 minus 7"),
    Instruction("salvage", 0.55, "reclaim decaying scrap from the current tile"),
    # ── computer-system laws biology does not have ────────────────────────
    # publish/call: code is REFERENCED, not copied. A routine costs one word in
    # the genome no matter how long it is, so complexity stops being re-paid on
    # every replication. There is no linker in biology; there is one here.
    Instruction("publish", 1.20, "publish 8 words of own genome into shared code slot A"),
    Instruction("call", 0.25, "splice the routine in shared code slot A into execution"),
    # write: self-modification during life. Because COPY reads from the genome,
    # acquired edits are inherited — Lamarckian, impossible biologically.
    Instruction("write", 0.50, "write A into own genome at position B"),
    # post/fetch: a shared data bus. Signalling is spatial -- it decays with
    # distance and cannot cross a quadrant -- which is how a chemical gradient
    # works, not how a machine does. Programs leave values at an ADDRESS and
    # any other program reads that address from anywhere. This is the only
    # channel in the world with no geometry, so it is the only way a sensor in
    # one biome can inform a forager in another without either of them moving.
    # Nothing enforces honesty: an address is equally available for a true
    # reading, a stale one, or a deliberate lie.
    Instruction("post", 0.40, "publish A to shared bus address B"),
    Instruction("fetch", 0.20, "read shared bus address B into A"),
    # locate: a program can ask where it is running. Without it a fetched band
    # is unusable in principle -- knowing that quadrant 1 will burn tells you
    # nothing unless you can ask whether you are standing in quadrant 1. Every
    # other link in that chain already exists (input, post, fetch, sub, ifzero,
    # move); this is the one that was missing.
    Instruction("locate", 0.15, "read the current quadrant into A"),
    # link: the unit that reproduces stops being the single program. Bound
    # programs are copied together by whichever member replicates, so a member
    # may drop its own alloc/copy/fork and spend that genome space on something
    # else and still be inherited. Every major jump in complexity has been a
    # change in what counts as an individual; nothing here could change it.
    #
    # Deliberately neutral to adopt: each member pays its own copy, so two
    # identical programs bound together cost exactly what they cost apart.
    # Drift can establish it before it pays for anything. Binding is also
    # unilateral - you may attach yourself to a group that did not invite you,
    # which makes freeloading reachable rather than designed out.
    Instruction("link", 0.60, "bind to an adjacent organism; the group is copied as one"),
    # burn: spend real CPU. The colony already senses this machine's heat and
    # spare capacity; nothing let it CHANGE them. Burning cycles warms the chip
    # and eats scheduler time, which raises the cost of every instruction and
    # lowers everyone's income - including the burner's. Niche construction on
    # real silicon, and a weapon for anything less dependent on regeneration
    # than its neighbours.
    Instruction("burn", 0.50, "spend real CPU cycles on this machine"),
    # offer: escrow A energy at bus address B for the value in C. Whoever posts
    # that value to that address collects. Avida's ceiling was its authored task
    # list; this lets the population decide what is worth paying for. Pure
    # transfer - escrow leaves the offerer and reaches the claimant or nobody.
    Instruction("offer", 0.40, "escrow A energy at address B for the value in C"),
    # define: name an abstraction. publish/call share code but a call needs its
    # slot number in a register at the moment of use; a macro is ONE genome word,
    # so mutation can wire it anywhere the way it wires any other opcode. The
    # instruction set stays fixed at 48 - what eight of those opcodes MEAN is
    # authored by the population rather than by me.
    Instruction("define", 1.00, "define macro slot A from own genome at B, length 4-8"),
    *[Instruction(f"macro{i}", 0.20, f"run macro slot {i}, if anything has defined it")
      for i in range(8)],
    # steal/corrupt: the first things one organism can do TO another against its
    # will. Everything until now was cooperative or neutral - read a neighbour,
    # copy it, pay it, call its code, bind to it - so nothing ever needed
    # defending and every strategy had a stable cheapest answer that evolution
    # found once and then coasted on forever. Physics is static; it demands a
    # solution once. Other organisms adapt back, which is the only force in this
    # world that can keep a problem from being solved.
    #
    # Neither is rewarded. They are capabilities, priced like any other, and
    # selection decides whether predation pays. Both need an adjacent target.
    #
    # steal is a strict transfer - the thief gains exactly what the victim loses,
    # no minting, that mistake is not being repeated - which makes hoarding
    # dangerous, movement valuable, and peek worth doing before you settle.
    Instruction("steal", 0.70, "take energy from an adjacent organism"),
    # corrupt is write aimed at somebody else: memory corruption across a
    # process boundary. It destroys structure rather than moving energy, and
    # the only defence reachable from this ISA is redundancy - which
    # segment_duplication already produces, and which has had no reason to
    # persist until now.
    Instruction("corrupt", 0.90, "write A into an adjacent organism's genome at B"),
]

# Which opcodes each feature gates. organism.execute checks the feature before
# running these, so without it they fall through and execute as a nop. Stated
# once here so recolonisation can ask what is inert at a destination instead of
# a second copy of this list drifting out of step with the first.
FEATURE_OPS = {
    "burn": (Op.BURN,),
    "bounty": (Op.OFFER,),
    "macro": (Op.DEFINE, Op.MACRO0, Op.MACRO1, Op.MACRO2, Op.MACRO3,
              Op.MACRO4, Op.MACRO5, Op.MACRO6, Op.MACRO7),
    "predation": (Op.STEAL, Op.CORRUPT),
}

# Replication a migrant can perform alone. `call` and the macros reach code in
# the shared commons, which does not travel with it, and a passenger relies on
# a groupmate, which does not travel either - a migrant arrives ungrouped into
# an empty commons.
SELF_SUFFICIENT = (Op.ALLOC, Op.COPY, Op.FORK)


def inert_ops(features) -> set[int]:
    """Opcodes that would execute as nops for a colony with these features."""
    enabled = set(features or ())
    return {int(op) for name, ops in FEATURE_OPS.items() if name not in enabled
            for op in ops}


NUM_OPS = len(ISA)
NAME_TO_OP = {instruction.name: i for i, instruction in enumerate(ISA)}


def build_ancestor() -> list[int]:
    """A small viable replicator; all later organisms descend from this."""
    return [
        Op.HARVEST, Op.HARVEST, Op.ALLOC, Op.COPY, Op.IFNOTDONE,
        Op.JMPB, Op.FORK, Op.SCAN, Op.MOVE,
    ]


def build_founder_palette() -> list[list[int]]:
    """Viable replicators with different immediately usable traits."""
    core = build_ancestor()
    return [
        core,
        # two founders seeding the computer-system capabilities, in the same
        # style as the others: ingredients appended, not a working arrangement.
        [*core, Op.PUBLISH, Op.CALL],
        [*core, Op.WRITE],
        [Op.HARVEST, *core],
        [*core, Op.SCAN, Op.MOVE, Op.HARVEST],
        [*core, Op.BUILD],
        [*core, Op.SIGNAL],
        [*core, Op.LISTEN, Op.MOVE, Op.HARVEST],
        [*core, Op.STORE, Op.LOAD],
        # bus ingredients, in the same style as the rest: the words are present
        # and adjacent, but nothing here is a working publish/consume circuit.
        [*core, Op.POST, Op.FETCH],
        [*core, Op.LOCATE, Op.FETCH],
        [*core, Op.LINK],
        [*core, Op.BURN],
        [*core, Op.OFFER],
        [*core, Op.DEFINE, Op.MACRO0],
        [*core, Op.STEAL],
        [*core, Op.CORRUPT],
        [*core, Op.INC, Op.PUSH, Op.ADD],
        [*core, Op.INPUT, Op.INPUT, Op.OUTPUT],
        [*core, Op.PEEK],
        # COPYN gets a chance to import a neighbour word; COPY remains a
        # fallback when isolated, so this founder is independently viable.
        [Op.HARVEST, Op.HARVEST, Op.ALLOC, Op.COPYN, Op.COPY,
         Op.IFNOTDONE, Op.JMPB, Op.FORK, Op.SCAN, Op.MOVE],
        [Op.HARVEST, Op.NOP, Op.HARVEST, Op.ALLOC, Op.COPY,
         Op.IFNOTDONE, Op.JMPB, Op.FORK, Op.NOP, Op.SCAN, Op.MOVE],
        [*core, Op.SALVAGE],
    ]


def disassemble(genome: list[int], annotate: bool = True) -> str:
    lines = []
    for index, word in enumerate(genome):
        name = ISA[word].name if 0 <= word < NUM_OPS else f"invalid({word})"
        lines.append(f"{index:03d}: {name}" if annotate else f"{index}: {name}")
    return "\n".join(lines)
