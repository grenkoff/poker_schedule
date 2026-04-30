from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
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


class _OptionBase(models.Model):
    """Common shape for a small admin-managed lookup table.

    Each option model is a simple list (`unlimited`, `none`, `1x`, `2x`,
    etc.) with a stable `name` slug for code references and a
    human-readable `label` for the dropdown.
    """

    name = models.SlugField(_("name"), max_length=64, unique=True)
    label = models.CharField(_("label"), max_length=200)
    sort_order = models.PositiveIntegerField(_("sort order"), default=0)

    class Meta:
        abstract = True
        ordering = ("sort_order", "label")

    def __str__(self) -> str:
        return self.label


class ReEntryOption(_OptionBase):
    class Meta(_OptionBase.Meta):
        verbose_name = _("re-entry option")
        verbose_name_plural = _("re-entry options")


class BubbleOption(_OptionBase):
    class Meta(_OptionBase.Meta):
        verbose_name = _("bubble option")
        verbose_name_plural = _("bubble options")


class EarlyBirdType(_OptionBase):
    class Meta(_OptionBase.Meta):
        verbose_name = _("early bird type")
        verbose_name_plural = _("early bird types")


class Periodicity(_OptionBase):
    """How often a tournament recurs.

    `interval_seconds=0` means a one-off event. Any positive value means
    the saved Tournament is treated as a series master, and future
    occurrences are materialized as child Tournament rows with their
    `series_master` FK pointing back here.
    """

    interval_seconds = models.PositiveIntegerField(
        _("interval (seconds)"),
        default=0,
        help_text=_("Set to 0 for one-off tournaments. Otherwise, seconds between occurrences."),
    )

    class Meta(_OptionBase.Meta):
        verbose_name = _("periodicity")
        verbose_name_plural = _("periodicities")


class Tournament(models.Model):
    """Manually-entered poker tournament.

    Buy-in is decomposed into three integer-cents fields: `buy_in_total`,
    `buy_in_without_rake`, and `rake`. The admin form lets the editor
    enter any two; the third is auto-derived. All three are stored.
    """

    # --- identification -------------------------------------------------
    room = models.ForeignKey(
        PokerRoom,
        on_delete=models.CASCADE,
        related_name="tournaments",
        verbose_name=_("room"),
    )
    name = models.CharField(_("name"), max_length=200)
    game_type = models.CharField(
        _("game type"),
        max_length=8,
        choices=GameType.choices,
        default=GameType.NLHE,
    )

    # --- money (all in minor units / cents) -----------------------------
    buy_in_total_cents = models.PositiveBigIntegerField(_("buy-in (with rake), cents"))
    buy_in_without_rake_cents = models.PositiveBigIntegerField(_("buy-in (without rake), cents"))
    rake_cents = models.PositiveBigIntegerField(_("rake, cents"))
    guaranteed_dollars = models.PositiveBigIntegerField(
        _("guaranteed prize pool ($)"),
        help_text=_(
            "Whole dollars. Stored separately from buy-ins because GTDs are always quoted in round numbers."
        ),
    )
    payout_percent = models.PositiveSmallIntegerField(
        _("payout distribution (%)"),
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text=_("Percentage of the field that gets paid."),
    )

    # --- stack ----------------------------------------------------------
    starting_stack = models.PositiveIntegerField(_("starting chips"))
    starting_stack_bb = models.PositiveIntegerField(_("starting chips (BB)"))

    # --- time -----------------------------------------------------------
    timezone = models.CharField(
        _("timezone"),
        max_length=64,
        default="UTC",
        help_text=_(
            "IANA timezone name; controls how starting/late-reg times are interpreted on input."
        ),
    )
    starting_time = models.DateTimeField(_("starting time"))
    late_registration_available = models.BooleanField(
        _("late registration available"),
        default=True,
        help_text=_("Uncheck if the tournament has no late-registration."),
    )
    late_reg_at = models.DateTimeField(_("late registration closes at"))
    late_reg_level = models.PositiveSmallIntegerField(
        _("late registration level"),
        default=1,
        validators=[MinValueValidator(1)],
    )
    blind_interval_minutes = models.PositiveSmallIntegerField(_("blind interval (minutes)"))
    break_minutes = models.PositiveSmallIntegerField(_("break time (minutes)"))

    # --- table sizing ---------------------------------------------------
    players_per_table = models.PositiveSmallIntegerField(_("players per table"))
    players_at_final_table = models.PositiveSmallIntegerField(_("players at the final table"))

    # --- field controls -------------------------------------------------
    min_players = models.PositiveIntegerField(_("min players"))
    max_players = models.PositiveIntegerField(_("max players"))
    re_entry = models.ForeignKey(
        ReEntryOption,
        on_delete=models.PROTECT,
        related_name="tournaments",
        verbose_name=_("re-entry"),
    )
    bubble = models.ForeignKey(
        BubbleOption,
        on_delete=models.PROTECT,
        related_name="tournaments",
        verbose_name=_("bubble"),
    )

    # --- recurrence -----------------------------------------------------
    periodicity = models.ForeignKey(
        Periodicity,
        on_delete=models.PROTECT,
        related_name="tournaments",
        verbose_name=_("periodicity"),
    )
    series_master = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        related_name="series_children",
        null=True,
        blank=True,
        verbose_name=_("series master"),
        help_text=_("Filled in for auto-generated occurrences of a recurring tournament."),
    )

    # --- features -------------------------------------------------------
    early_bird = models.BooleanField(_("early bird"))
    early_bird_type = models.ForeignKey(
        EarlyBirdType,
        on_delete=models.PROTECT,
        related_name="tournaments",
        verbose_name=_("early bird type"),
    )
    featured_final_table = models.BooleanField(_("featured final table"))

    # --- workflow (kept from before) ------------------------------------
    verified_by_admin = models.BooleanField(_("verified by superadmin"), default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("tournament")
        verbose_name_plural = _("tournaments")
        ordering = ("starting_time",)
        indexes = [
            models.Index(fields=("starting_time",)),
            models.Index(fields=("room", "starting_time")),
            models.Index(fields=("buy_in_total_cents",)),
        ]

    def __str__(self) -> str:
        return f"{self.room.name} — {self.name}"

    @property
    def buy_in_total(self) -> Decimal:
        return Decimal(self.buy_in_total_cents) / Decimal(100)

    @property
    def buy_in_without_rake(self) -> Decimal:
        return Decimal(self.buy_in_without_rake_cents) / Decimal(100)

    @property
    def rake(self) -> Decimal:
        return Decimal(self.rake_cents) / Decimal(100)


class BlindStructure(models.Model):
    """One row in a tournament's blind schedule.

    A tournament must have at least one level; there's no upper limit.
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
