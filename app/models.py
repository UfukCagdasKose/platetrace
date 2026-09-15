from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Nokta(Base):
    """Kamera / gecis noktasi."""

    __tablename__ = "nokta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # ad UNIQUE degil: bu bir dogal anahtar degil, sadece bir goruntu adi.
    # synth_scenario.py'yi --load-db ile ayni veritabanina birden fazla kez
    # (birden fazla senaryo/tohum) calistirmak, iki farkli noktanin ayni
    # ismi tasimasina yol acabiliyor (ör. iki ayri "Otoyol Gise (1)") --
    # bu gercek bir is kurali ihlali degil.
    ad: Mapped[str] = mapped_column(String(64))
    enlem: Mapped[float] = mapped_column(Float)
    boylam: Mapped[float] = mapped_column(Float)


class GecisKaydi(Base):
    """Bir aracin bir noktadan gectigi anin kaydi. Sistemin temel birimi."""

    __tablename__ = "gecis_kaydi"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plaka: Mapped[str] = mapped_column(String(16), index=True)
    nokta_id: Mapped[int] = mapped_column(Integer, index=True)
    zaman: Mapped[datetime] = mapped_column(DateTime, index=True)
    guven: Mapped[float] = mapped_column(Float, default=0.0)
    arac_tipi: Mapped[str] = mapped_column(String(32), default="unknown")

    __table_args__ = (
        Index("ix_gecis_plaka_zaman", "plaka", "zaman"),
        Index("ix_gecis_nokta_zaman", "nokta_id", "zaman"),
    )


class ArananArac(Base):
    """Aranan arac listesi (watchlist)."""

    __tablename__ = "aranan_arac"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plaka: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    sebep: Mapped[str] = mapped_column(String(128), default="")
