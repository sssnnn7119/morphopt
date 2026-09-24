"""Dialogs used to choose and resume optimization runs."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
)

from ..application import RunSourceKind
from ..i18n import T


class ContinueDialog(QDialog):
    """Choose the persisted iteration from which a result should resume."""

    def __init__(self, max_step: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle(T("继续优化", "Continue Optimization"))
        self.setMinimumWidth(380)
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                T(
                    f"当前结果已完成至第 {max_step} 步。请选择续跑起始位置：",
                    f"The result has reached step {max_step}. "
                    "Choose where to resume:",
                )
            )
        )
        self.last_step = QRadioButton(
            T("从结果最后一步续跑", "Resume from the last step")
        )
        self.last_step.setChecked(True)
        self.chosen_step = QRadioButton(
            T("从指定步骤续跑：", "Resume from a chosen step:")
        )
        self.step = QSpinBox()
        self.step.setRange(1, max(1, max_step))
        self.step.setValue(max(1, max_step))
        self.step.setEnabled(False)
        self.last_step.toggled.connect(
            lambda selected: self.step.setEnabled(not selected)
        )

        step_row = QHBoxLayout()
        step_row.addWidget(self.chosen_step)
        step_row.addWidget(self.step)
        layout.addWidget(self.last_step)
        layout.addLayout(step_row)

        buttons = QHBoxLayout()
        accept = QPushButton(T("继续", "Continue"))
        accept.clicked.connect(self.accept)
        cancel = QPushButton(T("取消", "Cancel"))
        cancel.clicked.connect(self.reject)
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(accept)
        layout.addLayout(buttons)

    def target_iteration(self) -> int | None:
        return self.step.value() if self.chosen_step.isChecked() else None


class SourceDialog(QDialog):
    """Choose the source consumed by the next optimization run."""

    def __init__(self, has_definition: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle(T("选择任务来源", "Choose task source"))
        self.setMinimumWidth(480)
        self._chosen: RunSourceKind | None = None
        layout = QVBoxLayout(self)
        caption = QLabel(
            T(
                "选择本次优化/运行的任务来源：",
                "Choose the task source for this run:",
            )
        )
        caption.setStyleSheet("color:#9aa4b2;")
        layout.addWidget(caption)

        options = (
            (
                RunSourceKind.DEFINITION,
                T("从当前定义优化（全新）", "Optimize current definition (fresh)"),
                T(
                    "使用定义页给出的定义，导出 .py 后从头运行。",
                    "Use the definition from the definition page; export .py "
                    "and run from scratch.",
                ),
            ),
            (
                RunSourceKind.PYTHON,
                T("从定义脚本 (.py) 优化", "Optimize from a definition script (.py)"),
                T(
                    "选择已有可运行的 .py，按脚本自身设置从头运行。",
                    "Pick an existing runnable .py; run from scratch with its "
                    "own settings.",
                ),
            ),
            (
                RunSourceKind.CONTINUE,
                T("从已有结果继续优化", "Continue an existing result"),
                T(
                    "选择已有结果目录，从最后一步或指定步续跑。",
                    "Pick an existing result folder; continue from the last or "
                    "a chosen step.",
                ),
            ),
        )
        for kind, title, description in options:
            if kind is RunSourceKind.DEFINITION and not has_definition:
                continue
            button = QPushButton(title)
            button.setToolTip(description)
            button.setStyleSheet("text-align:left; padding:8px 12px;")
            button.clicked.connect(
                lambda _checked=False, selected=kind: self._accept(selected)
            )
            layout.addWidget(button)

        if not has_definition:
            note = QLabel(
                T(
                    "提示：尚未收到定义页定义，“从当前定义优化”不可用。",
                    "Note: no definition received, so the current-definition "
                    "option is unavailable.",
                )
            )
            note.setStyleSheet("color:#7f8c8d;")
            layout.addWidget(note)

        cancel = QPushButton(T("取消", "Cancel"))
        cancel.clicked.connect(self.reject)
        layout.addWidget(cancel)

    def _accept(self, kind: RunSourceKind) -> None:
        self._chosen = kind
        self.accept()

    def chosen(self) -> RunSourceKind | None:
        return self._chosen
