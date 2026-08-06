# ADR-002 — Colony architecture

**Date:** 2026-08-06
**Status:** Accepted

## Decision

The primary experimental system is a population of self-replicating programs,
not a collection of LLM calls acting as simulated people. Organisms execute a
small deterministic instruction set. Selection arises from shared energy,
memory, and heat constraints.

An LLM may propose a genome variant only at reproduction. Calls are optional,
fall back safely to blind mutation, and carry a metabolic charge. Comparative
claims require seeded controls and reproducible output.

Flux and the browser frontend may be reused as observation infrastructure, but
neither defines the colony's physics. The Python substrate is authoritative.

## Containment

Software-accounted resources remain the default. Any future use of actual CPU,
RSS, or sensor feedback must be opt-in and bounded outside the organism VM.
Organisms never receive host credentials, filesystem access, network access, or
general code execution.

## Provenance

Fable-generated source and recordings are preserved as artifacts. Their claims
remain hypotheses until reproduced by the maintained implementation.
