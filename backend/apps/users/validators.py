"""
Custom password validators for the IOMS project.
"""
import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


class StrongPasswordValidator:
    """
    Enforce uppercase, digit, and special-character requirements.
    Used alongside Django's built-in MinimumLengthValidator.
    """

    SPECIAL_RE = re.compile(r'[!@#$%^&*()\-_=+\[\]{};:\'",.<>/?\\|`~]')

    def validate(self, password, user=None):
        errors = []
        if not re.search(r'[A-Z]', password):
            errors.append(
                ValidationError(
                    _("Password must contain at least one uppercase letter."),
                    code="password_no_upper",
                )
            )
        if not re.search(r'\d', password):
            errors.append(
                ValidationError(
                    _("Password must contain at least one digit."),
                    code="password_no_digit",
                )
            )
        if not self.SPECIAL_RE.search(password):
            errors.append(
                ValidationError(
                    _("Password must contain at least one special character."),
                    code="password_no_special",
                )
            )
        if errors:
            raise ValidationError(errors)

    def get_help_text(self):
        return _(
            "Your password must contain at least one uppercase letter, "
            "one digit, and one special character."
        )
