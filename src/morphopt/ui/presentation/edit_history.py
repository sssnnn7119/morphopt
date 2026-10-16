"""Localized descriptions for document-edit history entries."""

from ..application.edit_history import EditSnapshot
from ..i18n import tr


def edit_description(snapshot: EditSnapshot) -> str:
    """Format an edit's action and target in the active UI language."""
    return tr(
        f"ui.history.operation_{snapshot.operation}",
        target=snapshot.description,
    )
