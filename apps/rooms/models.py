from django.db import models
from django.utils.translation import gettext_lazy as _


class Network(models.Model):
    """Shared poker network that hosts traffic for multiple rooms.

    Example: the GGNetwork hosts GGPoker, Pokerok, BetKings, etc. Players at
    different skins can share the same tables, which matters for how we
    deduplicate tournaments and attribute traffic.
    """

    name = models.CharField(_("name"), max_length=64, unique=True)
    slug = models.SlugField(_("slug"), max_length=64, unique=True)
    website = models.URLField(_("website"), blank=True)

    class Meta:
        verbose_name = _("network")
        verbose_name_plural = _("networks")
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class PokerRoom(models.Model):
    """A user-facing poker room (skin) whose schedule we aggregate."""

    name = models.CharField(_("name"), max_length=64, unique=True)
    slug = models.SlugField(
        _("slug"),
        max_length=64,
        unique=True,
        help_text=_("Stable identifier used in URLs and external references."),
    )
    network = models.ForeignKey(
        Network,
        on_delete=models.PROTECT,
        related_name="rooms",
        verbose_name=_("network"),
    )
    website = models.URLField(_("website"), blank=True)
    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_("When false, the room is hidden from filters and the public list."),
    )

    class Meta:
        verbose_name = _("poker room")
        verbose_name_plural = _("poker rooms")
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name
