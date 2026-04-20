from __future__ import annotations

from allauth.account.forms import LoginForm, SignupForm


def _apply_input_class(form: LoginForm | SignupForm) -> None:
    for field in form.fields.values():
        field.widget.attrs.setdefault("class", "form-input")


class StyledLoginForm(LoginForm):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        _apply_input_class(self)


class StyledSignupForm(SignupForm):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        _apply_input_class(self)
