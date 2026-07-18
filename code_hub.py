import os, re, subprocess, sys
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
                              QTreeView, QTabWidget, QPlainTextEdit,
                              QTextEdit, QPushButton, QLabel, QComboBox, QLineEdit,
                              QFileDialog, QMessageBox, QToolBar, QStatusBar, QWidget as W,
                              QPlainTextDocumentLayout)
from PyQt6.QtGui import (QFont, QColor, QTextCharFormat, QSyntaxHighlighter, QPainter,
                          QTextFormat, QAction, QKeySequence, QShortcut, QFileSystemModel)
from PyQt6.QtCore import Qt, QRect, QSize, QRegularExpression, QDir

from themes import THEMES
from workers import ModelWorker

# ---------------------------------------------------------------------------
# Satır numarası + kod editörü
# ---------------------------------------------------------------------------
class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.editor.line_number_area_paint_event(event)


class CodeEditor(QPlainTextEdit):
    def __init__(self, theme, font_family="Consolas", font_size=11):
        super().__init__()
        self.theme = theme
        self.setFont(QFont(font_family, font_size))
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(' '))
        self.line_number_area = LineNumberArea(self)
        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self.highlight_current_line)
        self.update_line_number_area_width(0)
        self.highlight_current_line()
        self.file_path = None
        self.dirty = False
        self.textChanged.connect(self._mark_dirty)

    def _mark_dirty(self):
        self.dirty = True

    def line_number_area_width(self):
        digits = max(2, len(str(max(1, self.blockCount()))))
        return 12 + self.fontMetrics().horizontalAdvance('9') * digits

    def update_line_number_area_width(self, _):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, rect, dy):
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))

    def highlight_current_line(self):
        extra = []
        if not self.isReadOnly():
            sel = QTextEdit.ExtraSelection()
            sel.format.setBackground(QColor(self.theme["widget_bg"]))
            sel.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            sel.cursor = self.textCursor()
            sel.cursor.clearSelection()
            extra.append(sel)
        self.setExtraSelections(extra)

    def line_number_area_paint_event(self, event):
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor(self.theme["scroll_bg"]))
        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        painter.setPen(QColor(self.theme["border"]))
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.drawText(0, top, self.line_number_area.width() - 6, self.fontMetrics().height(),
                                  Qt.AlignmentFlag.AlignRight, str(block_number + 1))
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_number += 1


# ---------------------------------------------------------------------------
# Basit çoklu-dil syntax highlighter
# ---------------------------------------------------------------------------
KEYWORDS = [
    "def","class","return","if","elif","else","for","while","import","from","as","try","except",
    "finally","with","lambda","yield","in","is","not","and","or","None","True","False","self",
    "function","const","let","var","new","this","export","default","async","await","public",
    "private","static","void","int","string","bool","float","double","struct","interface",
    "implements","extends","namespace","using","package","switch","case","break","continue","null"
]

class SimpleHighlighter(QSyntaxHighlighter):
    def __init__(self, document, theme):
        super().__init__(document)
        self.rules = []

        kw_fmt = QTextCharFormat()
        kw_fmt.setForeground(QColor(theme["accent"]))
        kw_fmt.setFontWeight(QFont.Weight.Bold)
        for kw in KEYWORDS:
            self.rules.append((QRegularExpression(rf"\b{kw}\b"), kw_fmt))

        str_fmt = QTextCharFormat()
        str_fmt.setForeground(QColor("#a6e22e"))
        self.rules.append((QRegularExpression(r'"[^"\\]*(\\.[^"\\]*)*"'), str_fmt))
        self.rules.append((QRegularExpression(r"'[^'\\]*(\\.[^'\\]*)*'"), str_fmt))

        num_fmt = QTextCharFormat()
        num_fmt.setForeground(QColor("#fd971f"))
        self.rules.append((QRegularExpression(r"\b[0-9]+\.?[0-9]*\b"), num_fmt))

        com_fmt = QTextCharFormat()
        com_fmt.setForeground(QColor("#75715e"))
        com_fmt.setFontItalic(True)
        self.rules.append((QRegularExpression(r"#[^\n]*"), com_fmt))
        self.rules.append((QRegularExpression(r"//[^\n]*"), com_fmt))

        func_fmt = QTextCharFormat()
        func_fmt.setForeground(QColor("#66d9ef"))
        self.rules.append((QRegularExpression(r"\b[A-Za-z_][A-Za-z0-9_]*(?=\()"), func_fmt))

    def highlightBlock(self, text):
        for pattern, fmt in self.rules:
            it = pattern.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), fmt)


RUNNERS = {
    ".py": [sys.executable],
    ".js": ["node"],
    ".ts": ["ts-node"],
    ".sh": ["bash"],
    ".rb": ["ruby"],
    ".php": ["php"],
}


class CodeHubWindow(QMainWindow):
    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.theme = THEMES.get(cfg.get("theme", "Dark"), THEMES["Dark"])
        self.setWindowTitle("Code Hub – FusionLM")
        self.resize(1300, 820)
        self.project_root = os.getcwd()
        self.ai_worker = None
        self.last_ai_reply = ""
        self.setup_ui()
        self.apply_theme()
        self.new_file()

    # ---------------- UI ----------------
    def setup_ui(self):
        toolbar = QToolBar()
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        def add_btn(text, slot, shortcut=None):
            act = QAction(text, self)
            act.triggered.connect(slot)
            if shortcut:
                act.setShortcut(QKeySequence(shortcut))
            toolbar.addAction(act)
            return act

        add_btn("📁 Open Folder", self.open_folder, "Ctrl+K")
        add_btn("🆕 New File", self.new_file, "Ctrl+N")
        add_btn("💾 Save", self.save_file, "Ctrl+S")
        add_btn("💾 Save As", self.save_file_as, "Ctrl+Shift+S")
        toolbar.addSeparator()
        add_btn("▶ Run", self.run_file, "F5")
        toolbar.addSeparator()

        self.model_cmb = QComboBox()
        self.model_cmb.setEditable(True)
        self.model_cmb.setMinimumWidth(160)
        toolbar.addWidget(QLabel("  Model: "))
        toolbar.addWidget(self.model_cmb)
        self.refresh_models()

        central = QWidget()
        self.setCentralWidget(central)
        root_lay = QHBoxLayout(central)
        root_lay.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root_lay.addWidget(splitter)

        # --- Sol: dosya gezgini ---
        self.fs_model = QFileSystemModel()
        self.fs_model.setRootPath(self.project_root)
        self.tree = QTreeView()
        self.tree.setModel(self.fs_model)
        self.tree.setRootIndex(self.fs_model.index(self.project_root))
        for col in (1, 2, 3):
            self.tree.hideColumn(col)
        self.tree.doubleClicked.connect(self.open_from_tree)
        self.tree.setMinimumWidth(220)
        splitter.addWidget(self.tree)

        # --- Orta: editör sekmeleri + konsol ---
        mid = QWidget()
        mid_lay = QVBoxLayout(mid)
        mid_lay.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        mid_lay.addWidget(self.tabs, 3)

        console_wrap = QWidget()
        cl = QVBoxLayout(console_wrap)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.addWidget(QLabel("Console"))
        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setMaximumBlockCount(2000)
        self.console.setFont(QFont("Consolas", 10))
        cl.addWidget(self.console)
        mid_lay.addWidget(console_wrap, 1)
        splitter.addWidget(mid)

        # --- Sağ: AI kod asistanı ---
        right = QWidget()
        right.setMinimumWidth(320)
        rl = QVBoxLayout(right)
        rl.addWidget(QLabel("🤖 AI Code Assistant"))
        self.ai_log = QTextEdit()
        self.ai_log.setReadOnly(True)
        rl.addWidget(self.ai_log, 3)

        self.ai_input = QPlainTextEdit()
        self.ai_input.setPlaceholderText("Bu dosya hakkında sor, kod iste, hata çözdür...")
        self.ai_input.setMaximumHeight(90)
        rl.addWidget(self.ai_input)

        ai_btn_row = QHBoxLayout()
        self.ask_btn = QPushButton("Sor / Yaz")
        self.ask_btn.clicked.connect(self.ask_ai)
        ai_btn_row.addWidget(self.ask_btn)
        self.include_file_chk = QPushButton("📄 Include current file")
        self.include_file_chk.setCheckable(True)
        self.include_file_chk.setChecked(True)
        ai_btn_row.addWidget(self.include_file_chk)
        rl.addLayout(ai_btn_row)

        ai_apply_row = QHBoxLayout()
        self.insert_btn = QPushButton("⬇ Insert code")
        self.insert_btn.clicked.connect(self.insert_ai_code)
        ai_apply_row.addWidget(self.insert_btn)
        self.replace_btn = QPushButton("♻ Replace file")
        self.replace_btn.clicked.connect(self.replace_with_ai_code)
        ai_apply_row.addWidget(self.replace_btn)
        rl.addLayout(ai_apply_row)

        splitter.addWidget(right)
        splitter.setSizes([220, 720, 360])

        self.status = QStatusBar()
        self.setStatusBar(self.status)

        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self.ask_ai)

    # ---------------- Model listesi ----------------
    def refresh_models(self):
        try:
            import ollama
            models = ollama.list()
            names = [m['name'] for m in models.get('models', [])] if isinstance(models, dict) else []
        except Exception:
            names = []
        self.model_cmb.clear()
        if names:
            self.model_cmb.addItems(names)

    # ---------------- Dosya işlemleri ----------------
    def current_editor(self):
        return self.tabs.currentWidget()

    def new_file(self):
        ed = CodeEditor(self.theme, self.cfg.get("font_family", "Consolas"), self.cfg.get("font_size", 11))
        SimpleHighlighter(ed.document(), self.theme)
        ed.cursorPositionChanged.connect(self.update_status)
        idx = self.tabs.addTab(ed, "untitled")
        self.tabs.setCurrentIndex(idx)
        ed.textChanged.connect(lambda e=ed: self._sync_tab_title(e))
        return ed

    def _sync_tab_title(self, editor):
        i = self.tabs.indexOf(editor)
        if i == -1:
            return
        name = os.path.basename(editor.file_path) if editor.file_path else "untitled"
        self.tabs.setTabText(i, ("● " if editor.dirty else "") + name)

    def open_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Open Project Folder", self.project_root)
        if d:
            self.project_root = d
            self.fs_model.setRootPath(d)
            self.tree.setRootIndex(self.fs_model.index(d))

    def open_from_tree(self, index):
        path = self.fs_model.filePath(index)
        if os.path.isdir(path):
            return
        self.open_path(path)

    def open_path(self, path):
        for i in range(self.tabs.count()):
            ed = self.tabs.widget(i)
            if ed.file_path == path:
                self.tabs.setCurrentIndex(i)
                return
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception as e:
            QMessageBox.warning(self, "Open failed", str(e))
            return
        ed = self.new_file()
        ed.setPlainText(content)
        ed.file_path = path
        ed.dirty = False
        self._sync_tab_title(ed)

    def save_file(self):
        ed = self.current_editor()
        if not ed:
            return
        if not ed.file_path:
            self.save_file_as()
            return
        self._write(ed, ed.file_path)

    def save_file_as(self):
        ed = self.current_editor()
        if not ed:
            return
        fp, _ = QFileDialog.getSaveFileName(self, "Save As", self.project_root)
        if fp:
            self._write(ed, fp)

    def _write(self, ed, path):
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(ed.toPlainText())
            ed.file_path = path
            ed.dirty = False
            self._sync_tab_title(ed)
            self.status.showMessage(f"Saved: {path}", 3000)
        except Exception as e:
            QMessageBox.warning(self, "Save failed", str(e))

    def close_tab(self, index):
        ed = self.tabs.widget(index)
        if ed and ed.dirty:
            resp = QMessageBox.question(self, "Unsaved changes",
                                         "There are unsaved changes. Close anyway?",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if resp == QMessageBox.StandardButton.No:
                return
        self.tabs.removeTab(index)

    def closeEvent(self, event):
        for i in range(self.tabs.count()):
            ed = self.tabs.widget(i)
            if ed.dirty:
                resp = QMessageBox.question(self, "Unsaved changes",
                                             "You have unsaved files. Close Code Hub anyway?",
                                             QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                if resp == QMessageBox.StandardButton.No:
                    event.ignore()
                    return
                break
        event.accept()

    # ---------------- Çalıştırma ----------------
    def run_file(self):
        ed = self.current_editor()
        if not ed:
            return
        if not ed.file_path:
            self.save_file_as()
            if not ed.file_path:
                return
        else:
            self._write(ed, ed.file_path)

        ext = os.path.splitext(ed.file_path)[1]
        runner = RUNNERS.get(ext)
        self.console.clear()
        if not runner:
            self.console.appendPlainText(f"[!] No runner configured for '{ext}' files.")
            return
        self.console.appendPlainText(f"$ {' '.join(runner)} {ed.file_path}\n")
        try:
            result = subprocess.run(runner + [ed.file_path], capture_output=True, text=True,
                                     timeout=30, cwd=os.path.dirname(ed.file_path) or self.project_root)
            if result.stdout:
                self.console.appendPlainText(result.stdout)
            if result.stderr:
                self.console.appendPlainText(result.stderr)
            self.console.appendPlainText(f"\n[process exited with code {result.returncode}]")
        except subprocess.TimeoutExpired:
            self.console.appendPlainText("[!] Process timed out after 30s.")
        except FileNotFoundError:
            self.console.appendPlainText(f"[!] Interpreter for '{ext}' not found on PATH.")
        except Exception as e:
            self.console.appendPlainText(f"[!] {e}")

    # ---------------- AI asistan ----------------
    def ask_ai(self):
        model = self.model_cmb.currentText().strip()
        if not model:
            QMessageBox.warning(self, "No model", "Select a model."); return
        prompt = self.ai_input.toPlainText().strip()
        if not prompt:
            return
        if self.ai_worker and self.ai_worker.isRunning():
            return

        sys_prompt = self.cfg.get("custom_prompts", {}).get(
            "Code Hub",
            "You are a master software architect. Give production-ready, well-explained code."
        )
        ed = self.current_editor()
        user_msg = prompt
        if self.include_file_chk.isChecked() and ed and ed.toPlainText().strip():
            fname = os.path.basename(ed.file_path) if ed.file_path else "current file"
            user_msg = f"Current file ({fname}):\n```\n{ed.toPlainText()}\n```\n\nRequest: {prompt}"

        self.ai_log.append(f"<b>You:</b> {prompt}")
        self.ai_input.clear()
        self.last_ai_reply = ""
        self.ai_log.append("<i>Thinking...</i>")
        self.ask_btn.setEnabled(False)

        messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_msg}]
        self.ai_worker = ModelWorker(model, messages, temperature=0.2, max_tokens=3000)
        self.ai_worker.chunk.connect(self._on_ai_chunk)
        self.ai_worker.done.connect(self._on_ai_done)
        self.ai_worker.err.connect(self._on_ai_err)
        self.ai_worker.start()

    def _on_ai_chunk(self, c):
        self.last_ai_reply += c

    def _on_ai_done(self):
        self.ask_btn.setEnabled(True)
        cursor = self.ai_log.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.ai_log.append(f"<b>AI:</b><br>{self._to_html(self.last_ai_reply)}")

    def _on_ai_err(self, e):
        self.ask_btn.setEnabled(True)
        self.ai_log.append(f"<span style='color:#ff5555'><b>Error:</b> {e}</span>")

    def _to_html(self, text):
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = re.sub(r"```[a-zA-Z]*\n(.*?)```", r"<pre style='background:#222;padding:6px;'>\1</pre>", text, flags=re.S)
        return text.replace("\n", "<br>")

    def _extract_last_code_block(self):
        blocks = re.findall(r"```[a-zA-Z]*\n(.*?)```", self.last_ai_reply, flags=re.S)
        if blocks:
            return blocks[-1].strip()
        return self.last_ai_reply.strip()

    def insert_ai_code(self):
        code = self._extract_last_code_block()
        if not code:
            return
        ed = self.current_editor()
        if not ed:
            ed = self.new_file()
        ed.textCursor().insertText(code)

    def replace_with_ai_code(self):
        code = self._extract_last_code_block()
        if not code:
            return
        ed = self.current_editor()
        if not ed:
            ed = self.new_file()
        resp = QMessageBox.question(self, "Replace file",
                                     "This will replace the entire file content with the AI's code. Continue?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if resp == QMessageBox.StandardButton.Yes:
            ed.setPlainText(code)

    # ---------------- Tema / durum çubuğu ----------------
    def update_status(self):
        ed = self.current_editor()
        if not ed:
            return
        c = ed.textCursor()
        self.status.showMessage(f"Line {c.blockNumber()+1}, Col {c.columnNumber()+1}")

    def apply_theme(self):
        t = self.theme
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{ background-color:{t['main_bg']}; color:{t['text']}; }}
            QPlainTextEdit, QTextEdit {{ background-color:{t['widget_bg']}; color:{t['text']};
                border:1px solid {t['border']}; border-radius:6px; }}
            QTreeView {{ background-color:{t['widget_bg']}; border:1px solid {t['border']}; }}
            QTabWidget::pane {{ border:1px solid {t['border']}; }}
            QPushButton {{ background-color:{t['widget_bg']}; border:1px solid {t['border']};
                border-radius:6px; padding:5px 10px; }}
            QPushButton:hover {{ background-color:{t['button_hover']}; color:{t['main_bg']}; }}
            QToolBar {{ background-color:{t['widget_bg']}; border:none; spacing:4px; }}
        """)