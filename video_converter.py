#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Convertisseur Vidéo — interface graphique style Apple
=======================================================

Fonctionnalités :
- Glisser-déposer un fichier vidéo (ou clic pour parcourir)
- Choix du codec vidéo (H.264, H.265/HEVC, ProRes, VP9, copie sans ré-encodage)
- Choix du format de sortie (mp4, mov, mkv, webm)
- Choix de l'emplacement de sortie via un bouton "Sélectionner"
- Bouton "Convertir" qui lance ffmpeg en arrière-plan (thread séparé)
- Message "Terminé" + boutons "Ouvrir le nouveau fichier" et "Convertir un autre"

Dépendances :
    pip install tkinterdnd2 --break-system-packages   # pour le drag & drop (optionnel)
    ffmpeg doit être installé sur le système (sudo apt install ffmpeg)

Lancement :
    python3 video_converter.py
"""

import os
import sys
import shlex
import queue
import shutil
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, ttk

# --- Drag & drop optionnel -------------------------------------------------
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_AVAILABLE = True
except ImportError:
    DND_AVAILABLE = False


# --- Palette "Apple" --------------------------------------------------------
BG = "#f5f5f7"
CARD_BG = "#ffffff"
TEXT_MAIN = "#1d1d1f"
TEXT_SUB = "#6e6e73"
ACCENT = "#0071e3"
ACCENT_HOVER = "#0077ed"
BORDER = "#d2d2d7"
GREEN = "#28c840"
YELLOW = "#febc2e"
RED = "#ff5f57"
FONT_FAMILY = "Helvetica Neue" if sys.platform == "darwin" else "Segoe UI"

CODECS = {
    "H.264 (libx264)": "libx264",
    "H.265 / HEVC (libx265)": "libx265",
    "ProRes 422 (prores_ks)": "prores_ks",
    "VP9 (libvpx-vp9)": "libvpx-vp9",
    "Copie (sans ré-encodage)": "copy",
}
FORMATS = ["mp4", "mov", "mkv", "webm"]


# --- Widgets custom ----------------------------------------------------------
def round_rect(canvas, x1, y1, x2, y2, r=18, **kwargs):
    points = [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


class RoundedButton(tk.Canvas):
    def __init__(self, parent, text, command=None, bg=ACCENT, fg="white",
                 hover=ACCENT_HOVER, width=180, height=40, font_size=13, **kw):
        super().__init__(parent, width=width, height=height, bg=parent["bg"],
                          highlightthickness=0, **kw)
        self.command = command
        self.bg_color = bg
        self.hover_color = hover
        self.fg_color = fg
        self.w, self.h = width, height
        self.shape = round_rect(self, 1, 1, width - 1, height - 1, r=height // 2, fill=bg, outline="")
        self.label = self.create_text(width / 2, height / 2, text=text, fill=fg,
                                       font=(FONT_FAMILY, font_size, "bold"))
        self.bind("<Enter>", lambda e: self._set_color(self.hover_color))
        self.bind("<Leave>", lambda e: self._set_color(self.bg_color))
        self.bind("<Button-1>", self._on_click)

    def _set_color(self, color):
        if self["state"] != "disabled":
            self.itemconfig(self.shape, fill=color)

    def _on_click(self, event):
        if self.command and self["state"] != "disabled":
            self.command()

    def set_enabled(self, enabled):
        self.configure(state="normal" if enabled else "disabled")
        self.itemconfig(self.shape, fill=self.bg_color if enabled else BORDER)
        self.itemconfig(self.label, fill=self.fg_color if enabled else TEXT_SUB)


class DropZone(tk.Canvas):
    def __init__(self, parent, on_file, width=560, height=140):
        super().__init__(parent, width=width, height=height, bg=parent["bg"],
                          highlightthickness=0)
        self.on_file = on_file
        self.w, self.h = width, height
        self._draw("Glissez-déposez votre vidéo ici", TEXT_SUB, BORDER)
        self.bind("<Button-1>", lambda e: self._browse())
        if DND_AVAILABLE:
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_drop)

    def _draw(self, message, text_color, border_color, filename=None):
        self.delete("all")
        round_rect(self, 2, 2, self.w - 2, self.h - 2, r=20,
                   fill=CARD_BG, outline=border_color, width=2, dash=(6, 4))
        icon_y = self.h / 2 - 18
        self.create_text(self.w / 2, icon_y, text="⬆", font=(FONT_FAMILY, 22), fill=ACCENT)
        if filename:
            self.create_text(self.w / 2, self.h / 2 + 16, text=filename,
                              font=(FONT_FAMILY, 12, "bold"), fill=TEXT_MAIN)
        else:
            self.create_text(self.w / 2, self.h / 2 + 16, text=message,
                              font=(FONT_FAMILY, 12), fill=text_color)
            self.create_text(self.w / 2, self.h / 2 + 36, text="(ou cliquez pour parcourir)",
                              font=(FONT_FAMILY, 10), fill=TEXT_SUB)

    def show_file(self, path):
        self._draw(None, TEXT_SUB, ACCENT, filename=os.path.basename(path))

    def reset(self):
        self._draw("Glissez-déposez votre vidéo ici", TEXT_SUB, BORDER)

    def _browse(self):
        path = filedialog.askopenfilename(
            title="Choisir une vidéo",
            filetypes=[("Fichiers vidéo", "*.mp4 *.mov *.mkv *.avi *.webm *.m4v *.flv"),
                       ("Tous les fichiers", "*.*")])
        if path:
            self.on_file(path)

    def _on_drop(self, event):
        path = event.data.strip("{}")
        if os.path.isfile(path):
            self.on_file(path)


# --- Application principale --------------------------------------------------
class ConverterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Convertisseur Vidéo")
        self.root.configure(bg=BG)
        self.root.geometry("640x640")
        self.root.resizable(False, False)

        self.input_path = None
        self.output_path_var = tk.StringVar()
        self.msg_queue = queue.Queue()
        self.process = None

        self._build_titlebar()
        self._build_card()
        self.root.after(100, self._poll_queue)

    # -- Barre de titre décorative (feux tricolores) --
    def _build_titlebar(self):
        bar = tk.Canvas(self.root, height=44, bg=BG, highlightthickness=0)
        bar.pack(fill="x")
        for i, color in enumerate([RED, YELLOW, GREEN]):
            cx = 22 + i * 22
            bar.create_oval(cx - 6, 22 - 6, cx + 6, 22 + 6, fill=color, outline="")
        bar.create_text(320, 22, text="Convertisseur Vidéo",
                         font=(FONT_FAMILY, 13, "bold"), fill=TEXT_MAIN)

    def _build_card(self):
        card = tk.Frame(self.root, bg=CARD_BG)
        card.place(x=32, y=54, width=576, height=560)
        self._round_bg(card, 576, 560)

        inner = tk.Frame(card, bg=CARD_BG)
        inner.pack(padx=28, pady=24, fill="both", expand=True)

        # Zone de dépôt
        self.drop_zone = DropZone(inner, self._set_file, width=520, height=130)
        self.drop_zone.pack(pady=(0, 20))

        # Codec
        self._label(inner, "Codec vidéo")
        self.codec_var = tk.StringVar(value=list(CODECS.keys())[0])
        self._combobox(inner, self.codec_var, list(CODECS.keys()))

        # Format
        self._label(inner, "Format de sortie")
        self.format_var = tk.StringVar(value=FORMATS[0])
        self._combobox(inner, self.format_var, FORMATS)

        # Emplacement
        self._label(inner, "Emplacement du fichier de sortie")
        loc_frame = tk.Frame(inner, bg=CARD_BG)
        loc_frame.pack(fill="x", pady=(4, 18))
        entry = tk.Entry(loc_frame, textvariable=self.output_path_var,
                          font=(FONT_FAMILY, 11), bg="#f0f0f2", relief="flat",
                          highlightthickness=1, highlightbackground=BORDER,
                          highlightcolor=ACCENT, fg=TEXT_MAIN)
        entry.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 8))
        RoundedButton(loc_frame, "Sélectionner", command=self._choose_output,
                      width=120, height=34, bg="#e8e8ed", fg=TEXT_MAIN,
                      hover="#dcdce1", font_size=11).pack(side="left")

        # Bouton Convertir
        self.convert_btn = RoundedButton(inner, "Convertir", command=self._start_conversion,
                                          width=520, height=44, font_size=14)
        self.convert_btn.pack(pady=(4, 14))

        # Statut
        self.status_label = tk.Label(inner, text="", font=(FONT_FAMILY, 12),
                                      bg=CARD_BG, fg=TEXT_SUB)
        self.status_label.pack(pady=(2, 6))

        self.progress = ttk.Progressbar(inner, mode="indeterminate", length=520)

        # Boutons post-conversion
        self.result_frame = tk.Frame(inner, bg=CARD_BG)
        self.open_btn = RoundedButton(self.result_frame, "Ouvrir le nouveau fichier",
                                       command=self._open_output, width=250, height=40,
                                       bg="#e8e8ed", fg=TEXT_MAIN, hover="#dcdce1")
        self.again_btn = RoundedButton(self.result_frame, "Convertir un autre",
                                        command=self._reset, width=250, height=40)
        self.open_btn.pack(side="left", padx=(0, 10))
        self.again_btn.pack(side="left")

    def _round_bg(self, frame, w, h):
        c = tk.Canvas(frame, width=w, height=h, bg=BG, highlightthickness=0)
        c.place(x=0, y=0)
        round_rect(c, 1, 1, w - 1, h - 1, r=24, fill=CARD_BG, outline=BORDER, width=1)
        # Le canvas est créé avant le reste du contenu de la carte, il est donc
        # déjà en dessous dans l'ordre d'empilement Tk — pas besoin d'appeler lower().

    def _label(self, parent, text):
        tk.Label(parent, text=text, font=(FONT_FAMILY, 11, "bold"),
                  bg=CARD_BG, fg=TEXT_MAIN, anchor="w").pack(fill="x", pady=(2, 4))

    def _combobox(self, parent, var, values):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Apple.TCombobox", fieldbackground="#f0f0f2",
                         background="#f0f0f2", bordercolor=BORDER, arrowsize=14)
        box = ttk.Combobox(parent, textvariable=var, values=values,
                            state="readonly", style="Apple.TCombobox",
                            font=(FONT_FAMILY, 11))
        box.pack(fill="x", pady=(0, 16), ipady=4)

    # -- Logique --
    def _set_file(self, path):
        self.input_path = path
        self.drop_zone.show_file(path)
        base, _ = os.path.splitext(path)
        ext = self.format_var.get()
        self.output_path_var.set(f"{base}_converted.{ext}")

    def _choose_output(self):
        ext = self.format_var.get()
        initial = self.output_path_var.get() or f"sortie.{ext}"
        path = filedialog.asksaveasfilename(
            defaultextension=f".{ext}",
            initialfile=os.path.basename(initial),
            initialdir=os.path.dirname(initial) if initial else None,
            filetypes=[(f"Fichier {ext.upper()}", f"*.{ext}")])
        if path:
            self.output_path_var.set(path)

    def _build_ffmpeg_command(self):
        codec = CODECS[self.codec_var.get()]
        input_path = self.input_path
        output_path = self.output_path_var.get()

        cmd = ["ffmpeg", "-y", "-i", input_path]
        if codec == "copy":
            cmd += ["-c", "copy"]
        else:
            cmd += ["-c:v", codec]
            if codec == "prores_ks":
                cmd += ["-profile:v", "3", "-c:a", "pcm_s16le"]
            else:
                cmd += ["-c:a", "aac", "-b:a", "192k"]
        cmd.append(output_path)
        return cmd

    def _start_conversion(self):
        if not self.input_path:
            self.status_label.config(text="⚠️ Sélectionnez d'abord un fichier vidéo.", fg=RED)
            return
        if not self.output_path_var.get():
            self.status_label.config(text="⚠️ Choisissez un emplacement de sortie.", fg=RED)
            return
        if shutil.which("ffmpeg") is None:
            self.status_label.config(text="⚠️ ffmpeg est introuvable (sudo apt install ffmpeg).", fg=RED)
            return

        self.convert_btn.set_enabled(False)
        self.result_frame.pack_forget()
        self.progress.pack(pady=(4, 8))
        self.progress.start(12)
        self.status_label.config(text="Conversion en cours…", fg=TEXT_SUB)

        cmd = self._build_ffmpeg_command()
        thread = threading.Thread(target=self._run_ffmpeg, args=(cmd,), daemon=True)
        thread.start()

    def _run_ffmpeg(self, cmd):
        try:
            self.process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                universal_newlines=True)
            _, _ = self.process.communicate()
            code = self.process.returncode
            self.msg_queue.put(("done", code))
        except Exception as e:
            self.msg_queue.put(("error", str(e)))

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()
                if kind == "done":
                    self.progress.stop()
                    self.progress.pack_forget()
                    self.convert_btn.set_enabled(True)
                    if payload == 0:
                        self.status_label.config(text="✅ Terminé", fg=GREEN)
                        self.result_frame.pack(pady=(4, 4))
                    else:
                        self.status_label.config(
                            text="❌ Échec de la conversion (voir le terminal).", fg=RED)
                elif kind == "error":
                    self.progress.stop()
                    self.progress.pack_forget()
                    self.convert_btn.set_enabled(True)
                    self.status_label.config(text=f"❌ Erreur : {payload}", fg=RED)
        except queue.Empty:
            pass
        self.root.after(150, self._poll_queue)

    def _open_output(self):
        path = self.output_path_var.get()
        if not path or not os.path.exists(path):
            self.status_label.config(text="⚠️ Fichier introuvable.", fg=RED)
            return
        try:
            if sys.platform.startswith("linux"):
                subprocess.Popen(["xdg-open", path])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            elif sys.platform.startswith("win"):
                os.startfile(path)  # type: ignore
        except Exception as e:
            self.status_label.config(text=f"⚠️ Impossible d'ouvrir : {e}", fg=RED)

    def _reset(self):
        self.input_path = None
        self.output_path_var.set("")
        self.drop_zone.reset()
        self.status_label.config(text="")
        self.result_frame.pack_forget()
        self.convert_btn.set_enabled(True)


def main():
    if DND_AVAILABLE:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()
        print("ℹ️  tkinterdnd2 non installé : le glisser-déposer est désactivé "
              "(cliquez sur la zone pour parcourir). "
              "Installez-le avec : pip install tkinterdnd2 --break-system-packages")
    ConverterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
