from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.rooms.models import PokerRoom


class GameType(models.TextChoices):
    NLHE = "NLHE", _("No-Limit Hold'em")
    PLO = "PLO", _("Pot-Limit Omaha")
    PLO5 = "PLO5", _("5-card PLO")
    PLO8 = "PLO8", _("Omaha Hi/Lo (8-or-better)")
    STUD = "STUD", _("Stud")
    MIXED = "MIXED", _("Mixed")
    OTHER = "OTHER", _("Other")


class TournamentFormat(models.TextChoices):
    FREEZEOUT = "freezeout", _("Freezeout")
    REBUY = "rebuy", _("Rebuy")
    REENTRY = "reentry", _("Re-entry")
    BOUNTY = "bounty", _("Bounty")
    KO = "ko", _("Knockout")
    PKO = "pko", _("Progressive KO")
    SATELLITE = "satellite", _("Satellite")
    SITNGO = "sitngo", _("Sit & Go")


class TableSize(models.TextChoices):
    HEADS_UP = "hu", _("Heads-Up")
    SIX_MAX = "6max", _("6-max")
    NINE_MAX = "9max", _("9-max (Full Ring)")
    OTHER = "other", _("Other")


class Tournament(models.Model):
    """A scheduled online poker tournament.

    Tournaments are entered manually through the admin. `(room,
    external_id)` is unique so the same template-id from a poker room
    can't be added twice; admins typically use the room's own tournament
    ID for `external_id` to keep parity with the source.
    """

    # --- identification -------------------------------------------------
    room = models.ForeignKey(
        PokerRoom,
        on_delete=models.CASCADE,
        related_name="tournaments",
        verbose_name=_("room"),
    )
    external_id = models.CharField(
        _("external id"),
        max_length=128,
        help_text=_("Stable identifier from the source room (tournament ID)."),
    )
    name = models.CharField(_("name"), max_length=200)

    # --- structure ------------------------------------------------------
    game_type = models.CharField(
        _("game type"),
        max_length=8,
        choices=GameType.choices,
        default=GameType.NLHE,
    )
    tournament_format = models.CharField(
        _("format"),
        max_length=16,
        choices=TournamentFormat.choices,
        default=TournamentFormat.FREEZEOUT,
    )
    table_size = models.CharField(
        _("table size"),
        max_length=8,
        choices=TableSize.choices,
        default=TableSize.NINE_MAX,
    )
    # Buy-ins are stored in minor units (cents) to avoid float rounding and
    # make SQL-side range filters cheap. Currency is kept per-tournament
    # because rooms vary: $, €, ₽, ¥.
    buy_in_cents = models.BigIntegerField(
        _("buy-in (cents)"),
        validators=[MinValueValidator(0)],
    )
    rake_cents = models.BigIntegerField(
        _("rake (cents)"),
        default=0,
        validators=[MinValueValidator(0)],
    )
    currency = models.CharField(
        _("currency"),
        max_length=3,
        default="USD",
        help_text=_("ISO 4217 code, e.g. USD, EUR, RUB."),
    )
    starting_stack = models.PositiveIntegerField(
        _("starting stack"),
        null=True,
        blank=True,
    )

    # --- time -----------------------------------------------------------
    start_at = models.DateTimeField(_("start time"))
    late_reg_minutes = models.PositiveIntegerField(
        _("late registration (minutes)"),
        null=True,
        blank=True,
    )
    blind_level_minutes = models.PositiveIntegerField(
        _("blind level duration (minutes)"),
        null=True,
        blank=True,
    )
    estimated_duration_minutes = models.PositiveIntegerField(
        _("estimated duration (minutes)"),
        null=True,
        blank=True,
    )

    # --- final table ----------------------------------------------------
    final_table_size = models.PositiveSmallIntegerField(
        _("final table size"),
        default=9,
    )
    blind_reset_at_final = models.BooleanField(
        _("blind reset at final table"),
        default=False,
    )
    blind_reset_level = models.PositiveSmallIntegerField(
        _("blind reset level"),
        null=True,
        blank=True,
        help_text=_("Level the blinds reset to when the final table forms."),
    )

    # --- derived historical metrics -------------------------------------
    # Populated by `apps.analytics` from TournamentResult rows. If no
    # observations exist we fall back to estimate_metrics() at query time.
    avg_entrants = models.PositiveIntegerField(
        _("average entrants"),
        null=True,
        blank=True,
    )
    avg_blinds_at_ft = models.DecimalField(
        _("average BB at final table"),
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
    )

    # --- meta -----------------------------------------------------------
    # `submitted_for_review` is set by an ADMIN; `verified_by_admin` is set
    # by a SUPERADMIN. The two booleans together encode the workflow state
    # (draft → pending → verified) without a dedicated enum.
    submitted_for_review = models.BooleanField(_("submitted for review"), default=False)
    verified_by_admin = models.BooleanField(_("verified by superadmin"), default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("tournament")
        verbose_name_plural = _("tournaments")
        ordering = ("start_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("room", "external_id"),
                name="uniq_room_external_id",
            ),
        ]
        indexes = [
            models.Index(fields=("start_at",)),
            models.Index(fields=("room", "start_at")),
            models.Index(fields=("buy_in_cents",)),
        ]

    def __str__(self) -> str:
        return f"{self.room.name} — {self.name}"

    @property
    def buy_in(self) -> Decimal:
        return Decimal(self.buy_in_cents) / Decimal(100)

    @property
    def total_cost(self) -> Decimal:
        return Decimal(self.buy_in_cents + self.rake_cents) / Decimal(100)


class BlindStructure(models.Model):
    """A single level inside a tournament's blind schedule.

    Optional — populated only when a room exposes the structure. Listed in
    `level` order; `duration_minutes` overrides the tournament-level default
    for uneven schedules (e.g. longer finals).
    """

    tournament = models.ForeignKey(
        Tournament,
        on_delete=models.CASCADE,
        related_name="blind_levels",
        verbose_name=_("tournament"),
    )
    level = models.PositiveSmallIntegerField(_("level"))
    small_blind = models.PositiveIntegerField(_("small blind"))
    big_blind = models.PositiveIntegerField(_("big blind"))
    ante = models.PositiveIntegerField(_("ante"), default=0)
    duration_minutes = models.PositiveIntegerField(
        _("duration (minutes)"),
        null=True,
        blank=True,
        help_text=_("Overrides the tournament default for this level only."),
    )

    class Meta:
        verbose_name = _("blind level")
        verbose_name_plural = _("blind levels")
        ordering = ("tournament", "level")
        constraints = [
            models.UniqueConstraint(
                fields=("tournament", "level"),
                name="uniq_tournament_level",
            ),
        ]

    def __str__(self) -> str:
        return f"L{self.level}: {self.small_blind}/{self.big_blind}"


class TournamentResult(models.Model):
    """Observed outcome of one running of a recurring tournament.

    Feeds the historical-metrics pipeline: scrolling averages of entrants
    and final-table BB counts are computed from rows here. `(tournament,
    instance_started_at)` keeps inserts idempotent.
    """

    tournament = models.ForeignKey(
        Tournament,
        on_delete=models.CASCADE,
        related_name="results",
        verbose_name=_("tournament"),
    )
    instance_started_at = models.DateTimeField(_("actual start"))
    entrants = models.PositiveIntegerField(_("entrants"))
    final_table_avg_bb = models.DecimalField(
        _("average BB at final table"),
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
    )
    total_prize_pool_cents = models.BigIntegerField(
        _("total prize pool (cents)"),
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("tournament result")
        verbose_name_plural = _("tournament results")
        ordering = ("-instance_started_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("tournament", "instance_started_at"),
                name="uniq_tournament_instance",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.tournament.name} @ {self.instance_started_at:%Y-%m-%d}"
