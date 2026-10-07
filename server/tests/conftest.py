import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select, update
from sqlalchemy.engine import make_url
from sqlmodel import Session, SQLModel

from app.auction.models import Auction, AuctionState
from app.integration.contracts import Adapters
from app.integration.runtime import BackendModules
from app.trading.models import TradeTransaction
from tests.adapters import (
    CatalogAdapter,
    FixedTestBrokerage,
    InventoryAdapter,
    LedgerAdapter,
    MarketAdapter,
    PricingAdapter,
    allocations,
    catalog,
    entries,
    inventory,
    listings,
    metadata,
    rounds,
    wallets,
)


@pytest.fixture(scope="session")
def engine():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to a disposable PostgreSQL *_modules_test database.")
    if not (make_url(url).database or "").endswith("_modules_test"):
        raise RuntimeError("Tests only reset databases named *_modules_test.")
    engine = create_engine(url, isolation_level="READ COMMITTED", pool_size=8, max_overflow=8)
    yield engine
    engine.dispose()


class Environment:
    def __init__(self, engine):
        self.engine = engine
        self.team, self.other_team, self.round, self.widget = (uuid4() for _ in range(4))
        self.listing, self.auction_listing, self.auction = (uuid4() for _ in range(3))
        self.fail_inventory = self.fail_credit = False
        with engine.begin() as c:
            c.execute(rounds.insert().values(id=self.round, state="OPEN"))
            c.execute(catalog.insert().values(id=self.widget))
            c.execute(
                wallets.insert(),
                [dict(team_id=t, balance=5000, reserved=0) for t in (self.team, self.other_team)],
            )
            c.execute(
                listings.insert(),
                [
                    dict(
                        id=self.listing,
                        round_id=self.round,
                        widget_id=self.widget,
                        mode="NORMAL",
                        finite=True,
                        stock=5,
                        price=100,
                    ),
                    dict(
                        id=self.auction_listing,
                        round_id=self.round,
                        widget_id=self.widget,
                        mode="AUCTION",
                        finite=True,
                        stock=0,
                        price=100,
                    ),
                ],
            )
            c.execute(
                allocations.insert().values(
                    auction_id=self.auction,
                    listing_id=self.auction_listing,
                    quantity=1,
                    consumed=False,
                )
            )
        with Session(engine) as s, s.begin():
            s.add(
                Auction(
                    id=self.auction,
                    round_id=self.round,
                    listing_id=self.auction_listing,
                    widget_id=self.widget,
                    quantity=1,
                    state=AuctionState.OPEN,
                    minimum_bid=1,
                    starts_at=datetime.now(timezone.utc) - timedelta(minutes=1),
                    closes_at=datetime.now(timezone.utc) + timedelta(hours=1),
                )
            )
        self.runtime = BackendModules(
            session_factory=lambda: Session(engine),
            adapter_factory=self.adapters,
            brokerage=FixedTestBrokerage(),
        )

    def adapters(self, s):
        return Adapters(
            market=MarketAdapter(s),
            pricing=PricingAdapter(s),
            ledger=LedgerAdapter(s, self),
            inventory=InventoryAdapter(s, self),
            catalog=CatalogAdapter(s),
        )

    def snapshot(self):
        with self.engine.connect() as c:
            w = c.execute(select(wallets).where(wallets.c.team_id == self.team)).mappings().one()
            stock = c.execute(
                select(listings.c.stock).where(listings.c.id == self.listing)
            ).scalar_one()
            owned = (
                c.execute(
                    select(inventory.c.quantity).where(
                        inventory.c.team_id == self.team, inventory.c.widget_id == self.widget
                    )
                ).scalar_one_or_none()
                or 0
            )
            trades = c.execute(
                select(func.count())
                .select_from(TradeTransaction.__table__)
                .where(TradeTransaction.team_id == self.team)
            ).scalar_one()
            return dict(
                balance=w["balance"],
                reserved=w["reserved"],
                stock=stock,
                owned=owned,
                trades=trades,
            )

    def change(self, table, condition, **values):
        with self.engine.begin() as c:
            c.execute(update(table).where(condition).values(**values))

    def set_round(self, value):
        self.change(rounds, rounds.c.id == self.round, state=value)

    def set_balance(self, value):
        self.change(wallets, wallets.c.team_id == self.team, balance=value)

    def set_stock(self, value):
        self.change(listings, listings.c.id == self.listing, stock=value)

    def set_price(self, value):
        self.change(listings, listings.c.id == self.listing, price=value)

    def set_infinite(self):
        self.change(listings, listings.c.id == self.listing, finite=False, stock=None)

    def close_auction(self):
        self.change(
            Auction.__table__,
            Auction.id == self.auction,
            closes_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )

    def total_owned(self):
        with self.engine.connect() as c:
            return c.execute(select(func.sum(inventory.c.quantity))).scalar_one() or 0

    def other_reserved(self):
        with self.engine.connect() as c:
            return c.execute(
                select(wallets.c.reserved).where(wallets.c.team_id == self.other_team)
            ).scalar_one()

    def settlement_debits(self):
        with self.engine.connect() as c:
            return c.execute(
                select(func.count()).select_from(entries).where(entries.c.kind == "AUCTION")
            ).scalar_one()


@pytest.fixture
def env(engine):
    SQLModel.metadata.drop_all(engine)
    metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    metadata.create_all(engine)
    yield Environment(engine)
    SQLModel.metadata.drop_all(engine)
    metadata.drop_all(engine)
