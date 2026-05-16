from allauth.account.adapter import DefaultAccountAdapter


class SilentAccountAdapter(DefaultAccountAdapter):
    """Suppresses every allauth flash ("signed in", "signed out", etc.).

    The header reflects auth state directly, so these toasts are noise.
    """

    def add_message(self, *args, **kwargs):
        return None
