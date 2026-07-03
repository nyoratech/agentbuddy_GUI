import reflex as rx


class liveinstruments(rx.Model, table=True):
    """The instrument model."""
    ticker: str
    weight: float
    notional: float
    close: float
    #last_price: float
    #pl: float
    sector: str
    industry: str
    description: str
    side_long: int
    side_short: int
    #portfolio: str