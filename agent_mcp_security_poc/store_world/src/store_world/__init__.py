"""Northwind Goods: a deterministic simulated store and its anchor case, ORD-4917.

    from store_world import load_catalog, StoreWorld
    catalog = load_catalog()
    world = StoreWorld(run_id="my-run")

The store is fictional, seeded (4917) and offline. `DATA-CONTRACT.md` says what a note may depend on.
"""

from store_world.catalog import SEED, Catalog, catalog_digest, load_catalog
from store_world.faults import Faults
from store_world.inventory import Inventory
from store_world.world import StoreWorld

__all__ = ["SEED", "Catalog", "Faults", "Inventory", "StoreWorld", "catalog_digest", "load_catalog"]
