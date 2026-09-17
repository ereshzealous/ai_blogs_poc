"""Renderers: CapabilityResponse → one channel's presentation. Pure functions.

They import only the contract. They cannot reach the platform, a model, a tool or the policy engine (enforced by
`.importlinter`), so presentation never needs reasoning.
"""
