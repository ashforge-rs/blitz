from enum import StrEnum


class ConsentMethod(StrEnum):
    """How the subject expressed their decision.  A profile decides which ones count."""

    CHECKBOX = "checkbox"  # an unticked box the subject ticked
    TOGGLE = "toggle"
    SIGNED_FORM = "signed_form"
    RECORDED_VERBAL = "recorded_verbal"
    DOUBLE_OPT_IN = "double_opt_in"  # e.g. confirmed through a link sent to the subject
    PRE_TICKED_BOX = "pre_ticked_box"
    IMPLIED = "implied"  # e.g. "by continuing you agree"
    INACTIVITY = "inactivity"
