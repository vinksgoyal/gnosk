"""Deterministic validators for PII categories.

Order of operations in VaultScan: validators run first, the model runs
second. Anything a validator can decide with certainty should never be
sent to the model.
"""
