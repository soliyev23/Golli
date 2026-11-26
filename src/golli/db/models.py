from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from golli.db.base import Base


class User(Base):
    __tablename__ = "users"

    # Telegram foydalanuvchi ID'si (shaxsiy chatda chat ID bilan bir xil).
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    # NULL — foydalanuvchi hali til tanlamagan: bot avval til so'raydi.
    lang: Mapped[str | None] = mapped_column(String(8))
    # Foydalanuvchi botni bloklasa False bo'ladi — unga xabar yuborilmaydi.
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Provayder bergan nom. Tarjimalari bazada emas, data/team_names.toml faylida.
    name: Mapped[str] = mapped_column(String(128))


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    competition: Mapped[str] = mapped_column(String(16))  # golli.competitions dagi kod
    season: Mapped[int] = mapped_column(SmallInteger)
    round: Mapped[str | None] = mapped_column(String(64))
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    kickoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(16))  # providers.base.MatchStatus qiymati
    minute: Mapped[int | None] = mapped_column(SmallInteger)
    home_score: Mapped[int | None] = mapped_column(SmallInteger)
    away_score: Mapped[int | None] = mapped_column(SmallInteger)
    home_penalties: Mapped[int | None] = mapped_column(SmallInteger)
    away_penalties: Mapped[int | None] = mapped_column(SmallInteger)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # Shu o'yin bo'yicha eslatmalar navbatga qo'yilgan vaqt; NULL — hali qo'yilmagan.
    pre_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Favorite(Base):
    """Foydalanuvchining sevimli klubi. Bir foydalanuvchida bir nechta bo'lishi mumkin."""

    __tablename__ = "favorites"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    # Indeks: klub o'yini bo'yicha eslatma yuborishda shu klub muxlislari qidiriladi.
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), primary_key=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Notification(Base):
    """Yuboriladigan xabarlar navbati.

    Xabar matni bu yerda saqlanmaydi: u yuborish paytida bazadagi joriy ma'lumotdan,
    foydalanuvchi tilida tuziladi. (user_id, dedupe_key) noyob — bitta voqea haqida
    foydalanuvchiga ikki marta xabar ketmaydi.
    """

    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("user_id", "dedupe_key"),
        # Navbatni o'qish uchun: faqat kutayotgan xabarlar indekslanadi.
        Index(
            "ix_notifications_pending",
            "send_after",
            postgresql_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(16))  # morning | pre_match | result
    match_id: Mapped[int | None] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"))
    day: Mapped[date | None] = mapped_column(Date)  # ertalabki xabar uchun futbol kuni
    dedupe_key: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), server_default="pending")
    attempts: Mapped[int] = mapped_column(SmallInteger, server_default="0")
    # Shu vaqtdan oldin yuborilmaydi (qayta urinishni kechiktirish uchun).
    send_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(String(255))


class ExternalRef(Base):
    """Provayder ID'si -> ichki ID.

    Jadvallar (sevimlilar, eslatmalar) faqat ichki ID'ga bog'lanadi, shuning uchun
    provayder almashsa, faqat shu jadvalga yangi moslik qo'shiladi.
    """

    __tablename__ = "external_refs"

    provider: Mapped[str] = mapped_column(String(32), primary_key=True)
    entity: Mapped[str] = mapped_column(String(16), primary_key=True)  # "team" | "match"
    external_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    internal_id: Mapped[int] = mapped_column(Integer)
