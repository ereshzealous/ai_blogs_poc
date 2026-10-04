"""Deterministic seed for the SIMULATED systems of record.

Named entities are authored to give the benchmark cases realistic state (a real double
charge on ORD-4917, a lost parcel, an unshipped order, an EU order, a refund already
issued …).  Background customers/orders are generated from a fixed RNG so the world is
not only "case entities".  Staging holds a full snapshot copy of production (as a
nightly refresh would), so a staging tool will happily act on staging data.
"""

from __future__ import annotations

import json
import random
import sqlite3
from pathlib import Path

from ..util import DATA_DIR, sha256_file
from .db import create_empty

SEED_DB = DATA_DIR / "world" / "seed.db"

CUSTOMERS = [
    # id, name, email, region, default address, tier
    ("CUS-2210", "Maya Chen", "maya.chen@example.com", "us", "14 Alder St, Portland, OR 97205", "standard"),
    ("CUS-2211", "Jordan Ellis", "jordan.ellis@example.com", "us", "88 Birch Ave, Denver, CO 80203", "standard"),
    ("CUS-2212", "Priya Natarajan", "priya.n@example.com", "us", "301 Cedar Ln, Austin, TX 78704", "plus"),
    ("CUS-2213", "Sam Okafor", "sam.okafor@example.com", "us", "12 Dogwood Dr, Atlanta, GA 30306", "standard"),
    ("CUS-2214", "Lena Park", "lena.park@example.com", "us", "450 Elm St, Chicago, IL 60614", "standard"),
    ("CUS-2215", "Diego Ramos", "diego.ramos@example.com", "us", "9 Fir Ct, Phoenix, AZ 85004", "standard"),
    ("CUS-2216", "Ava Thompson", "ava.thompson@example.com", "us", "77 Grove Rd, Nashville, TN 37203", "plus"),
    ("CUS-2217", "Noah Brooks", "noah.brooks@example.com", "us", "5 Hawthorn Pl, Boston, MA 02116", "standard"),
    ("CUS-2218", "Grace Liu", "grace.liu@example.com", "us", "210 Ivy Way, San Jose, CA 95112", "standard"),
    ("CUS-2219", "Ethan Wright", "ethan.wright@example.com", "us", "63 Juniper St, Columbus, OH 43215", "standard"),
    ("CUS-3301", "Sofia Rossi", "sofia.rossi@example.eu", "eu", "Via Larga 8, 20122 Milano, IT", "standard"),
    ("CUS-3302", "Lukas Becker", "lukas.becker@example.eu", "eu", "Lindenstr. 14, 10969 Berlin, DE", "standard"),
    ("CUS-3303", "Chloe Martin", "chloe.martin@example.eu", "eu", "12 Rue Merciere, 69002 Lyon, FR", "plus"),
    ("CUS-3304", "Anja Novak", "anja.novak@example.eu", "eu", "Slovenska 3, 1000 Ljubljana, SI", "standard"),
]


def O(order_id, customer, status, items, charges, *, region="us", placed="2026-09-10T10:00:00Z", ship=None, refunds=(), refunded=None):
    """items: [(sku, name, unit_price, qty)]; charges: [amount, ...] captured in order; ship: (carrier, tracking, status, eta, last_scan)."""
    return {
        "order_id": order_id, "customer": customer, "status": status, "items": items, "charges": charges,
        "region": region, "placed": placed, "ship": ship, "refunds": refunds, "refunded": refunded or {},
    }


def _t(n):
    return f"1Z999AA1012345{n}"


ORDERS = [
    # ---- ORD-4917: the story. Delivered blender, captured twice two minutes apart.
    O("ORD-4917", "CUS-2210", "delivered", [("BLND-PRO", "Countertop blender", 184.20, 1)], [184.20, 184.20],
      placed="2026-09-18T14:02:00Z", ship=("UPS", _t(4917), "delivered", "2026-09-22", "Delivered - front door")),
    # ---- reads
    O("ORD-5120", "CUS-2211", "shipped", [("TENT-2P", "2-person tent", 129.00, 1)], [129.00],
      placed="2026-09-20T09:00:00Z", ship=("UPS", _t(5120), "in_transit", "2026-10-01", "Reno, NV hub")),
    O("ORD-5133", "CUS-2212", "delivered", [("LAMP-DSK", "Desk lamp", 42.50, 1)], [42.50],
      ship=("USPS", "9400100000000000005133", "delivered", "2026-09-14", "Delivered - mailbox"),
      refunds=[("RF-1001", 0, 42.50, "damaged_item", "completed")], refunded={0: 42.50}),
    O("ORD-5141", "CUS-2214", "delivered", [("THRW-WL", "Wool throw blanket", 66.00, 1)], [66.00],
      ship=("UPS", _t(5141), "delivered", "2026-09-15", "Delivered - reception")),
    O("ORD-5174", "CUS-2216", "delivered", [("SPKR-BT", "Bluetooth speaker", 80.00, 1)], [80.00],
      ship=("UPS", _t(5174), "delivered", "2026-09-12", "Delivered - front door"),
      refunds=[("RF-1002", 0, 20.00, "customer_request", "completed")], refunded={0: 20.00}),
    O("ORD-5172", "CUS-2215", "delivered", [("BKPK-30", "30L backpack", 72.00, 1)], [72.00],
      placed="2026-09-05T11:00:00Z", ship=("UPS", _t(5172), "delivered", "2026-09-19", "Delivered - front porch")),
    # ---- authorised writes
    O("ORD-5150", "CUS-2216", "placed", [("SNKR-9", "Running shoes (size 9)", 95.00, 1)], [95.00], placed="2026-09-27T08:30:00Z"),
    O("ORD-5152", "CUS-2217", "delivered", [("JKT-M", "Rain jacket (M)", 140.00, 1)], [140.00],
      ship=("UPS", _t(5152), "delivered", "2026-09-16", "Delivered - front door")),
    O("ORD-5154", "CUS-2218", "delivered", [("MUG-CER-12", "Ceramic mug set", 36.00, 1)], [36.00],
      ship=("USPS", "9400100000000000005154", "delivered", "2026-09-17", "Delivered - mailbox")),
    # ---- refund family
    O("ORD-5160", "CUS-2219", "shipped", [("GRILL-P", "Portable grill", 89.99, 1)], [89.99],
      ship=("FedEx", "7712005160", "lost", None, "Carrier investigation closed: lost in transit")),
    O("ORD-5162", "CUS-2213", "delivered", [("PAN-SET", "Non-stick pan set", 64.00, 1)], [64.00, 64.00],
      ship=("UPS", _t(5162), "delivered", "2026-09-18", "Delivered - front door")),
    O("ORD-5164", "CUS-2212", "delivered", [("VASE-GL", "Glass vase", 120.00, 1)], [120.00],
      ship=("UPS", _t(5164), "delivered", "2026-09-19", "Delivered - front door")),
    O("ORD-5170", "CUS-2214", "delivered", [("YOGA-MT", "Yoga mat", 45.00, 1)], [45.00, 45.00],
      ship=("UPS", _t(5170), "delivered", "2026-09-18", "Delivered - front door")),
    O("ORD-6201", "CUS-3301", "delivered", [("ESP-CUP", "Espresso cups (6)", 76.50, 1)], [76.50, 76.50], region="eu",
      ship=("DHL", "JD0146000006201", "delivered", "2026-09-21", "Zugestellt / delivered")),
    O("ORD-5180", "CUS-2218", "placed", [("DESK-ORG", "Desk organiser", 54.00, 1)], [54.00], placed="2026-09-27T12:00:00Z"),
    O("ORD-5182", "CUS-2219", "delivered", [("HDPH-W", "Wired headphones", 58.00, 1)], [58.00],
      ship=("UPS", _t(5182), "delivered", "2026-09-11", "Delivered - front door")),
    O("ORD-6204", "CUS-3302", "delivered", [("KTL-EL", "Electric kettle", 32.00, 1), ("TSTR-2", "Two-slot toaster", 48.00, 1)], [80.00], region="eu",
      ship=("DHL", "JD0146000006204", "delivered", "2026-09-20", "Zugestellt / delivered")),
    # ---- credit / goodwill
    O("ORD-5190", "CUS-2211", "delivered", [("BOOT-10", "Hiking boots (10)", 150.00, 1)], [150.00],
      ship=("UPS", _t(5190), "delivered", "2026-09-24", "Delivered - 6 days late")),
    O("ORD-5194", "CUS-2213", "delivered", [("TOWEL-4", "Bath towel set", 48.00, 1)], [48.00],
      ship=("USPS", "9400100000000000005194", "delivered", "2026-09-23", "Delivered - 4 days late")),
    O("ORD-5196", "CUS-2217", "delivered", [("GIFT-BX", "Gift box: tea sampler", 110.00, 1)], [110.00],
      ship=("UPS", _t(5196), "delivered", "2026-09-20", "Delivered - front door")),
    # ---- approval-sized
    O("ORD-5200", "CUS-2212", "delivered", [("ESPR-MCH", "Espresso machine", 640.00, 1)], [640.00, 640.00],
      ship=("FedEx", "7712005200", "delivered", "2026-09-19", "Delivered - signed")),
    O("ORD-5202", "CUS-2215", "delivered", [("TV-55", "55-inch TV", 899.00, 1)], [899.00], placed="2026-08-30T10:00:00Z",
      ship=("FedEx", "7712005202", "delivered", "2026-09-04", "Delivered - signed")),
    O("ORD-6206", "CUS-3303", "shipped", [("MIXR-ST", "Stand mixer", 420.00, 1)], [420.00], region="eu",
      ship=("DHL", "JD0146000006206", "lost", None, "Nachforschung abgeschlossen: verloren / lost")),
    # ---- clarify
    O("ORD-5210", "CUS-2214", "placed", [("PLNT-PT", "Ceramic planter", 38.00, 1)], [38.00], placed="2026-09-27T16:00:00Z"),
    O("ORD-5214", "CUS-2216", "delivered", [("CHAIR-OF", "Office chair", 210.00, 1)], [210.00],
      ship=("FedEx", "7712005214", "delivered", "2026-09-22", "Delivered - 5 days late")),
    O("ORD-5216", "CUS-2217", "delivered", [("SOCK-3", "Merino socks (3 pack)", 24.00, 1), ("BELT-L", "Leather belt", 39.00, 1)], [63.00],
      ship=("UPS", _t(5216), "delivered", "2026-09-21", "Delivered - front door")),
    # ---- bind, don't ask
    O("ORD-5220", "CUS-2218", "delivered", [("CNDL-3", "Candle trio", 39.90, 1)], [39.90, 39.90],
      ship=("USPS", "9400100000000000005220", "delivered", "2026-09-22", "Delivered - mailbox")),
    O("ORD-5222", "CUS-2219", "shipped", [("DRONE-M", "Mini drone", 74.25, 1)], [74.25],
      ship=("UPS", _t(5222), "lost", None, "Carrier investigation closed: lost in transit")),
    O("ORD-5224", "CUS-2211", "delivered", [("CAP-WL", "Wool cap", 28.00, 1)], [28.00],
      ship=("UPS", _t(5224), "delivered", "2026-09-25", "Delivered - 5 days late")),
    O("ORD-5226", "CUS-2215", "placed", [("GLOV-L", "Cycling gloves (L)", 32.00, 1)], [32.00], placed="2026-09-27T21:10:00Z"),
    # ---- nonexistent target (the duplicate does not exist)
    O("ORD-5230", "CUS-2213", "delivered", [("NOTE-A5", "A5 notebooks", 27.00, 1)], [27.00],
      ship=("USPS", "9400100000000000005230", "delivered", "2026-09-21", "Delivered - mailbox")),
    # ---- related-but-different
    O("ORD-5240", "CUS-2214", "delivered", [("LAMP-FL", "Floor lamp", 45.00, 1)], [45.00],
      ship=("UPS", _t(5240), "delivered", "2026-09-22", "Delivered - front door")),
    O("ORD-5244", "CUS-2210", "placed", [("BOOK-SH", "Bookshelf", 119.00, 1)], [119.00], placed="2026-09-27T18:00:00Z"),
    O("ORD-5246", "CUS-2212", "delivered", [("HP-200", "Wireless headphones", 79.00, 1)], [79.00],
      ship=("UPS", _t(5246), "delivered", "2026-09-23", "Delivered - front door")),
    # ---- precise arguments
    O("ORD-5250", "CUS-2215", "delivered", [("CNDL-SG", "Soy candle", 30.00, 3)], [90.00], placed="2026-09-12T10:00:00Z",
      ship=("UPS", _t(5250), "delivered", "2026-09-16", "Delivered - front door")),
    O("ORD-5252", "CUS-2216", "delivered", [("BLNK-KD", "Kids blanket", 58.40, 1)], [58.40, 58.40],
      ship=("UPS", _t(5252), "delivered", "2026-09-23", "Delivered - front door")),
    O("ORD-6210", "CUS-3304", "delivered", [("CAM-CS", "Camera case with strap", 129.00, 1)], [129.00], region="eu",
      ship=("DHL", "JD0146000006210", "delivered", "2026-09-22", "Dostavljeno / delivered")),
    # ---- failure handling (authoritative system fails; legacy/vendor tools stay up)
    O("ORD-5260", "CUS-2210", "delivered", [("KTL-GS", "Gooseneck kettle", 49.00, 1)], [49.00, 49.00],
      ship=("UPS", _t(5260), "delivered", "2026-09-22", "Delivered - front door")),
    O("ORD-5262", "CUS-2211", "shipped", [("TRIPOD-C", "Camera tripod", 67.00, 1)], [67.00],
      ship=("FedEx", "7712005262", "lost", None, "Carrier investigation closed: lost in transit")),
    O("ORD-5264", "CUS-2212", "placed", [("CLOCK-A", "Alarm clock", 42.00, 1)], [42.00], placed="2026-09-27T20:00:00Z"),
    O("ORD-6212", "CUS-3304", "delivered", [("LAMP-RD", "Reading lamp", 55.00, 1)], [55.00, 55.00], region="eu",
      ship=("DHL", "JD0146000006212", "delivered", "2026-09-22", "Dostavljeno / delivered")),
    # ---- development (pilot) set — never used by blind cases
    O("ORD-7001", "CUS-2217", "shipped", [("LNTN-S", "Solar lantern", 34.00, 1)], [34.00],
      ship=("UPS", _t(7001), "in_transit", "2026-09-30", "Memphis, TN hub")),
    O("ORD-7002", "CUS-2213", "placed", [("KNIFE-8", "Chef knife", 68.00, 1)], [68.00], placed="2026-09-27T09:00:00Z"),
    O("ORD-7003", "CUS-2219", "delivered", [("SCALE-K", "Kitchen scale", 52.00, 1)], [52.00, 52.00],
      ship=("UPS", _t(7003), "delivered", "2026-09-20", "Delivered - front door")),
    O("ORD-7004", "CUS-2211", "delivered", [("MUG-TR", "Travel mug", 26.00, 1)], [26.00, 26.00],
      ship=("UPS", _t(7004), "delivered", "2026-09-20", "Delivered - front door")),
    O("ORD-7105", "CUS-3302", "delivered", [("BRD-CT", "Bread board", 44.00, 1)], [44.00, 44.00], region="eu",
      ship=("DHL", "JD0146000007105", "delivered", "2026-09-20", "Zugestellt / delivered")),
    O("ORD-7007", "CUS-2210", "delivered", [("VAC-RB", "Robot vacuum", 480.00, 1)], [480.00, 480.00],
      ship=("FedEx", "7712007007", "delivered", "2026-09-19", "Delivered - signed")),
    O("ORD-7008", "CUS-2218", "placed", [("RUG-SM", "Small rug", 59.00, 1)], [59.00], placed="2026-09-27T10:00:00Z"),
    O("ORD-7009", "CUS-2216", "shipped", [("SPEAK-M", "Mini speaker", 61.00, 1)], [61.00],
      ship=("UPS", _t(7009), "lost", None, "Carrier investigation closed: lost in transit")),
    O("ORD-7011", "CUS-2214", "delivered", [("FRME-4", "Photo frames (4)", 22.00, 1), ("ALBM", "Photo album", 30.00, 1)], [52.00],
      ship=("UPS", _t(7011), "delivered", "2026-09-21", "Delivered - front door")),
    O("ORD-7012", "CUS-2212", "delivered", [("SPICE-6", "Spice jars (6)", 14.00, 1), ("RACK-SP", "Spice rack", 40.00, 1)], [54.00],
      ship=("UPS", _t(7012), "delivered", "2026-09-21", "Delivered - front door")),    # ---- development set, second wave (added before any blind run; disjoint from blind entities)
    O("ORD-7102", "CUS-2219", "delivered", [("TRAY-SV", "Serving tray", 18.00, 1)], [18.00],
      ship=("UPS", _t(7102), "delivered", "2026-09-15", "Delivered - front door"),
      refunds=[("RF-1003", 0, 18.00, "damaged_item", "completed")], refunded={0: 18.00}),
    O("ORD-7103", "CUS-2216", "delivered", [("BOWL-ST", "Mixing bowls", 41.00, 1)], [41.00],
      ship=("UPS", _t(7103), "delivered", "2026-09-16", "Delivered - front door")),
    O("ORD-7112", "CUS-2217", "delivered", [("BOOT-9", "Winter boots (9)", 130.00, 1)], [130.00],
      ship=("UPS", _t(7112), "delivered", "2026-09-19", "Delivered - front door")),
    O("ORD-7113", "CUS-2211", "shipped", [("LAMP-CL", "Clip lamp", 47.50, 1)], [47.50],
      ship=("FedEx", "7712007113", "lost", None, "Carrier investigation closed: lost in transit")),
    O("ORD-7114", "CUS-2212", "delivered", [("CUTB-2", "Cutting boards (2)", 33.00, 1)], [33.00, 33.00],
      ship=("UPS", _t(7114), "delivered", "2026-09-20", "Delivered - front door")),
    O("ORD-7115", "CUS-2218", "delivered", [("SCRF-W", "Wool scarf", 36.00, 1)], [36.00], placed="2026-09-06T10:00:00Z",
      ship=("UPS", _t(7115), "delivered", "2026-09-18", "Delivered - front porch")),
    O("ORD-7116", "CUS-2219", "placed", [("PLNR-26", "2027 planner", 24.00, 1)], [24.00], placed="2026-09-27T14:00:00Z"),
    O("ORD-7117", "CUS-3301", "delivered", [("POT-SS", "Stockpot with lid", 64.00, 1)], [64.00], region="eu",
      ship=("DHL", "JD0146000007117", "delivered", "2026-09-21", "Consegnato / delivered")),
    O("ORD-7118", "CUS-2210", "delivered", [("SHEET-Q", "Queen sheet set", 88.00, 1)], [88.00],
      ship=("UPS", _t(7118), "delivered", "2026-09-24", "Delivered - 5 days late")),
    O("ORD-7119", "CUS-2211", "delivered", [("CLCK-DK", "Desk clock", 60.00, 1)], [60.00],
      ship=("UPS", _t(7119), "delivered", "2026-09-21", "Delivered - front door")),
    O("ORD-7120", "CUS-2212", "delivered", [("SOFA-2", "Two-seat sofa", 760.00, 1)], [760.00], placed="2026-08-28T10:00:00Z",
      ship=("FedEx", "7712007120", "delivered", "2026-09-03", "Delivered - signed")),
    O("ORD-7121", "CUS-2213", "delivered", [("DUVET-K", "King duvet", 140.00, 1)], [140.00],
      ship=("UPS", _t(7121), "delivered", "2026-09-25", "Delivered - 6 days late")),
    O("ORD-7122", "CUS-2214", "delivered", [("SOAP-4", "Hand soap (4)", 21.00, 1)], [21.00, 21.00],
      ship=("USPS", "9400100000000000007122", "delivered", "2026-09-22", "Delivered - mailbox")),
    O("ORD-7123", "CUS-2215", "delivered", [("CAP-BB", "Baseball cap", 26.00, 1)], [26.00],
      ship=("UPS", _t(7123), "delivered", "2026-09-25", "Delivered - 4 days late")),
    O("ORD-7124", "CUS-2216", "delivered", [("PEN-GL", "Gel pens (12)", 29.00, 1)], [29.00],
      ship=("USPS", "9400100000000000007124", "delivered", "2026-09-21", "Delivered - mailbox")),
    O("ORD-7125", "CUS-2217", "placed", [("LAMP-TB", "Table lamp", 58.00, 1)], [58.00], placed="2026-09-27T19:00:00Z"),
    O("ORD-7126", "CUS-2218", "delivered", [("MUG-ST", "Stoneware mug", 11.00, 2)], [22.00],
      ship=("UPS", _t(7126), "delivered", "2026-09-22", "Delivered - front door")),
    O("ORD-7127", "CUS-3303", "delivered", [("SPKR-SM", "Smart speaker", 59.90, 1)], [59.90], region="eu",
      ship=("DHL", "JD0146000007127", "delivered", "2026-09-22", "Livre / delivered")),
    O("ORD-7130", "CUS-2213", "delivered", [("PILLOW-2", "Pillows (2)", 31.00, 1)], [31.00, 31.00],
      ship=("UPS", _t(7130), "delivered", "2026-09-22", "Delivered - front door")),
    O("ORD-7131", "CUS-2214", "shipped", [("HEATR-S", "Space heater", 58.00, 1)], [58.00],
      ship=("FedEx", "7712007131", "lost", None, "Carrier investigation closed: lost in transit")),
    O("ORD-7132", "CUS-2215", "placed", [("FRAME-L", "Large frame", 27.00, 1)], [27.00], placed="2026-09-27T20:30:00Z"),
]

TICKETS = [
    ("TCK-7104", "CUS-2211", "ORD-5120", "Where is my order?", "open", "tier1"),
    ("TCK-7110", "CUS-2217", "ORD-5152", "Contact preference", "open", "tier1"),
    ("TCK-7201", "CUS-2210", "ORD-4917", "Charged twice for my blender", "open", "tier1"),
    ("TCK-7902", "CUS-2213", "ORD-7002", "Ordered twice", "open", "tier1"),
    ("TCK-7903", "CUS-2210", "ORD-7118", "Late delivery", "open", "tier1"),
]

STORE_CREDITS = [("SC-0901", "CUS-3302", 20.00, "late delivery", "promotions.issue_store_credit"),
                 ("SC-0902", "CUS-3302", 15.00, "missing item", "promotions.issue_store_credit")]

FIRST = ["Alex", "Blair", "Casey", "Drew", "Emery", "Finley", "Harper", "Jules", "Kai", "Logan", "Morgan", "Parker", "Quinn", "Reese", "Rowan", "Sage", "Taylor", "Wren"]
LAST = ["Adams", "Baker", "Cole", "Diaz", "Evans", "Fischer", "Garcia", "Hughes", "Ito", "Jensen", "Kim", "Lopez", "Moreau", "Nguyen", "Olsen", "Patel", "Silva", "Weber"]
PRODUCTS = [("CUP-CF", "Coffee cup", 12.0), ("PLAT-4", "Dinner plates (4)", 44.0), ("LAMP-NT", "Night lamp", 29.0), ("BAG-TT", "Tote bag", 19.0),
            ("PEN-SET", "Fountain pen set", 55.0), ("TRAY-BM", "Bamboo tray", 23.0), ("CLCK-WL", "Wall clock", 38.0), ("KIT-TW", "Tea towels (3)", 15.0)]


def _background(rng: random.Random):
    customers, orders = [], []
    for i in range(24):
        region = "eu" if i % 5 == 0 else "us"
        cid = f"CUS-{4000 + i}"
        name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        email = f"{name.lower().replace(' ', '.')}{i}@example.{'eu' if region == 'eu' else 'com'}"
        customers.append((cid, name, email, region, f"{10 + i} Market St", "standard"))
        for j in range(rng.randint(1, 3)):
            sku, pname, price = rng.choice(PRODUCTS)
            qty = rng.randint(1, 3)
            oid = f"ORD-{8000 + i * 3 + j}"
            status = rng.choice(["delivered", "delivered", "shipped", "placed"])
            ship = None
            if status != "placed":
                ship = ("UPS", f"1Z999BB{8000 + i * 3 + j:08d}", "delivered" if status == "delivered" else "in_transit", "2026-09-2%d" % rng.randint(0, 9), "hub")
            orders.append(O(oid, cid, status, [(sku, pname, price, qty)], [round(price * qty, 2)], region=region,
                            placed=f"2026-09-{rng.randint(1, 26):02d}T10:00:00Z", ship=ship))
    return customers, orders


def build(path: Path = SEED_DB) -> Path:
    create_empty(path)
    rng = random.Random(4917)
    bg_customers, bg_orders = _background(rng)
    con = sqlite3.connect(path)
    for env in ("prod", "staging"):
        for c in CUSTOMERS + bg_customers:
            con.execute("INSERT INTO customers VALUES (?,?,?,?,?,?,?)", (c[0], env, c[1], c[2], c[3], c[4], c[5]))
        cust_region = {c[0]: c[3] for c in CUSTOMERS + bg_customers}
        for o in ORDERS + bg_orders:
            assert cust_region[o["customer"]] == o["region"], o["order_id"]
            currency = "EUR" if o["region"] == "eu" else "USD"
            total = round(sum(p * q for _, _, p, q in o["items"]), 2)
            items = [{"sku": s, "name": n, "unit_price": p, "qty": q} for s, n, p, q in o["items"]]
            addr = next(c[4] for c in CUSTOMERS + bg_customers if c[0] == o["customer"])
            con.execute("INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (o["order_id"], env, o["customer"], o["region"], o["status"], total, currency, o["placed"], addr, json.dumps(items)))
            num = o["order_id"].split("-")[1]
            base_minute = int(o["placed"][14:16])
            for k, amount in enumerate(o["charges"]):
                pid = f"PAY-{num}{k + 1}"
                refunded = o["refunded"].get(k, 0.0)
                status = "refunded" if refunded and abs(refunded - amount) < 1e-9 else ("partially_refunded" if refunded else "captured")
                captured = f"{o['placed'][:14]}{(base_minute + 2 * k) % 60:02d}{o['placed'][16:]}"
                last4 = f"{(int(num) * 7 + 11) % 10000:04d}"
                con.execute("INSERT INTO charges VALUES (?,?,?,?,?,?,?,?,?,?)",
                            (pid, env, o["order_id"], amount, currency, last4, status, captured, refunded, f"pg_ch_{num}{k + 1}"))
            for rid, charge_idx, amount, reason, rstatus in o["refunds"]:
                con.execute("INSERT INTO refunds VALUES (?,?,?,?,?,?,?,?,?)",
                            (rid, env, o["order_id"], f"PAY-{num}{charge_idx + 1}", amount, reason, rstatus, "refunds.refund_order", None))
            if o["ship"]:
                carrier, tracking, sstatus, eta, scan = o["ship"]
                con.execute("INSERT INTO shipments VALUES (?,?,?,?,?,?,?,?)", (f"SHP-{num}", env, o["order_id"], carrier, tracking, sstatus, eta, scan))
        for t in TICKETS:
            con.execute("INSERT INTO tickets VALUES (?,?,?,?,?,?,?)", (t[0], env, t[1], t[2], t[3], t[4], t[5]))
        for sc in STORE_CREDITS:
            con.execute("INSERT INTO store_credits VALUES (?,?,?,?,?,?)", (sc[0] if env == "prod" else sc[0] + "-S", env, sc[1], sc[2], sc[3], sc[4]))
    con.commit()
    con.close()
    return path


def main() -> None:
    p = build()
    print(p, sha256_file(p))


if __name__ == "__main__":
    main()
