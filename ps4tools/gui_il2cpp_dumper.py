"""Tk front end for ps4dump.py, il2mem.py, il2live.py, il2cheat.py and il2diff.py (Unity IL2CPP). By talixme, beta.
    python gui_il2cpp_dumper.py
"""
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext, simpledialog
from PIL import Image, ImageTk

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(TOOLS_DIR)
DUMPS_DIR = os.path.join(BASE_DIR, "dumps")
CHEATS_DIR = os.path.join(BASE_DIR, "cheats")
CONFIG_FILE = os.path.join(BASE_DIR, "config_il2cpp.json")

os.makedirs(DUMPS_DIR, exist_ok=True)
os.makedirs(CHEATS_DIR, exist_ok=True)

TRANSLATIONS = {
    "English": {
        "title": "PS4 / PS5 Unity IL2CPP Dumper & Cheat Generator",
        "frame_dumper": " 1. Memory Dump & IL2CPP SDK Extraction ",
        "lbl_ip": "Console IP Address:",
        "btn_new": "🔄 New",
        "btn_load": "📂 Load Session Folder",
        "btn_ps4dump": "⚡ 1. Initial Dump (ps4dump)",
        "btn_il2mem": "📥 2. Extract SDK (il2mem + dumper)",
        "btn_get_name": "🌐 Get Name & Rename",
        "btn_open_diff": "📊 Open Diff Tool",
        "frame_cheat": " 2. IL2CPP Cheat Generator (il2cheat.py) ",
        "lbl_dump_file": "Game Session Folder:",
        "lbl_cheat_cmd": "Rules (Saved per game):",
        "th_name": "Name",
        "th_path": "IL2CPP Path / Static Root",
        "th_value": "Value",
        "th_test": "Test",
        "btn_add_cheat": "➕ Add Cheat Rule",
        "btn_suggestions": "💡 Common Paths",
        "btn_export_rules": "📤 Export Rules",
        "btn_import_rules": "📥 Import Rules",
        "btn_cheat": "🛠️ Generate .TLH Trainer",
        "btn_test_all": "⚡ Test All Live",
        "frame_console": " Console Output / Terminal ",
        "btn_export_console": "💾 Export Log",
        "btn_clear_console": "🗑️ Clear",
        "frame_finder": " 🔍 IL2CPP SDK & Path Finder (il2live.py) ",
        "lbl_keyword": "Keyword, Value or Address (e.g. Health, 50 or 0x203f12318):",
        "btn_search": "🔎 Search SDK Code",
        "btn_find_paths": "🧭 Find Paths (--find)",
        "btn_find_addr": "🧭 Find Paths (By address)",
        "warn_find_paths": "Select a session folder (section 2) and enter a keyword/value/address.",
        "lbl_results_hdr": "Results (Ctrl+F for Next/Back navigation):",
        "btn_export_finder": "💾 Export Results",
        "btn_clear_finder": "🗑️ Clear",
        "warn_ip": "Please enter the console IP address.",
        "warn_fields": "Please complete all fields and at least one valid cheat rule.",
        "warn_finder": "Please select a valid session folder with an SDK folder and enter a keyword.",
        "warn_empty_export": "There is no content to export.",
        "lbl_language": "Language / Sprache / Idioma:",
        "status_running": "Status: Running process... Elapsed time: ",
        "status_idle": "Status: Idle",
        "msg_dump_title": "Process Completed",
        "msg_dump_success": "The process finished successfully! SDK and dump.cs ready.",
        "msg_cheat_title": "Trainer Generated",
        "msg_cheat_success": "The .TLH trainer file has been generated successfully!",
        "suggestions_title": "Common Unity IL2CPP Cheat Paths",
        "suggestions_add": "Add to Rules",
        "find_dialog_title": "Results Navigator",
        "find_label": "Filter keyword:",
        "find_back": "◀ Back",
        "find_next": "Next ▶",
        "find_matches": "Matches:",
        "msg_export_success": "File exported successfully!",
        "msg_import_success": "Rules imported successfully!",
        "msg_session_loaded": "Session folder loaded successfully from:",
        "warn_no_dump_bin": "The selected folder does not contain a valid 'dump.bin' file.",
        "diff_title": "IL2CPP Diff & Backtracking Tool (il2diff.py)",
        "lbl_diff_ip": "Console IP Address:",
        "btn_quick_dump": "⚡ Quick Dump (dump.bin + json)",
        "lbl_diff_dump1": "Base Dump JSON (dump1.json):",
        "lbl_diff_dump2": "Modified Dump JSON (dump2.json):",
        "lbl_diff_dump3": "Third Dump JSON (--same):",
        "lbl_diff_offset": "Comparison Mode / Options:",
        "btn_run_diff": "🔍 Run Diff / Backtracking",
        "btn_cancel_diff": "🛑 Cancel Process",
        "btn_export_diff": "💾 Export Diff Results",
        "btn_clear_diff": "🗑️ Clear",
        "warn_diff_files": "Please select both dump JSON files to compare.",
        "live_warn_title": "⚠️ Live Edit Warning",
        "live_warn_msg": "IMPORTANT:\nThe memory dump and current console session MUST be from the same game build/session.\n\nIf the console or game has been restarted, ensure layouts match!",
        "dlg_new_session_title": "New Session",
        "dlg_new_session_msg": "Enter Game ID or Session Name (e.g. PPSA35399):",
        "dlg_session_dir_title": "Enter session folder name (e.g. ealimit):",
        "dlg_select_session_title": "Select Game Session Folder (Unity)",
        "dlg_sdk_notice_title": "SDK Extraction Notice",
        "dlg_sdk_notice_msg": "The SDK extraction process can take up to 10 minutes depending on your computer's specs.",
        "dlg_save_tlh_title": "Save IL2CPP Trainer .TLH",
        "warn_select_session_first": "Please select or create a session folder first.",
        "warn_no_json_dump": "No valid dump .json file found in the session folder. Run a Quick Dump first.",
        "warn_enter_addr": "Please select a session folder and enter a valid memory address (e.g. 0x203f12318).",
        "warn_enter_eq_values": "Please enter both values to compare (--eq).",
        "lbl_diff_hops": "Hops (--depth):",
        "lbl_diff_parents": "Parents (--parents):",
        "lbl_diff_mode": "Mode:",
        "lbl_diff_val1": "Val 1:",
        "lbl_diff_val2": "Val 2:"
    },
    "Español": {
        "title": "PS4 / PS5 Unity IL2CPP Dumper y Generador de Cheats",
        "frame_dumper": " 1. Dump de Memoria y Extracción SDK IL2CPP ",
        "lbl_ip": "Dirección IP de la Consola:",
        "btn_new": "🔄 Nuevo",
        "btn_load": "📂 Cargar Carpeta Sesión",
        "btn_ps4dump": "⚡ 1. Dump Inicial (ps4dump)",
        "btn_il2mem": "📥 2. Extraer SDK (il2mem + dumper)",
        "btn_get_name": "🌐 Obtener Nombre y Renombrar",
        "btn_open_diff": "📊 Herramienta Diff",
        "frame_cheat": " 2. Generador de Cheats IL2CPP (il2cheat.py) ",
        "lbl_dump_file": "Carpeta de Sesión del Juego:",
        "lbl_cheat_cmd": "Reglas (Guardadas por juego):",
        "th_name": "Nombre",
        "th_path": "Ruta IL2CPP / Static Root",
        "th_value": "Valor",
        "th_test": "Test",
        "btn_add_cheat": "➕ Añadir Regla",
        "btn_suggestions": "💡 Rutas Comunes",
        "btn_export_rules": "📤 Exportar Reglas",
        "btn_import_rules": "📥 Importar Reglas",
        "btn_cheat": "🛠️ Generar Trainer .TLH",
        "btn_test_all": "⚡ Test All Live",
        "frame_console": " Salida de la Consola / Terminal ",
        "btn_export_console": "💾 Exportar Log",
        "btn_clear_console": "🗑️ Limpiar",
        "frame_finder": " 🔍 Buscador SDK y Rutas IL2CPP (il2live.py) ",
        "lbl_keyword": "Palabra clave, valor o dirección (ej. Health, 50 o 0x203f12318):",
        "btn_search": "🔎 Buscar en SDK",
        "btn_find_paths": "🧭 Buscar Rutas (--find)",
        "btn_find_addr": "🧭 Buscar Rutas (Por dirección)",
        "warn_find_paths": "Selecciona una carpeta de sesión (sección 2) e introduce un término o dirección.",
        "lbl_results_hdr": "Resultados (Ctrl+F para navegar Siguiente/Anterior):",
        "btn_export_finder": "💾 Exportar Resultados",
        "btn_clear_finder": "🗑️ Limpiar",
        "warn_ip": "Por favor, introduce la IP de la consola.",
        "warn_fields": "Por favor, completa los campos y al menos una regla válida de cheat.",
        "warn_finder": "Por favor, selecciona una carpeta de sesión válida con carpeta SDK e introduce una palabra clave.",
        "warn_empty_export": "No hay contenido para exportar.",
        "lbl_language": "Idioma / Language / Sprache:",
        "status_running": "Estado: Ejecutando proceso... Tiempo transcurrido: ",
        "status_idle": "Estado: En espera",
        "msg_dump_title": "Proceso Completado",
        "msg_dump_success": "¡El proceso ha finalizado con éxito! SDK y dump.cs listos.",
        "msg_cheat_title": "Trainer Generado",
        "msg_cheat_success": "¡El archivo trainer .TLH se ha generado correctamente!",
        "suggestions_title": "Sugerencias de Rutas Comunes en Unity IL2CPP",
        "suggestions_add": "Añadir a Reglas",
        "find_dialog_title": "Navegador de Resultados",
        "find_label": "Palabra a filtrar:",
        "find_back": "◀ Anterior",
        "find_next": "Siguiente ▶",
        "find_matches": "Coincidencias:",
        "msg_export_success": "¡Archivo exportado con éxito!",
        "msg_import_success": "¡Reglas importadas con éxito!",
        "msg_session_loaded": "Se ha cargado correctamente la carpeta de sesión desde:",
        "warn_no_dump_bin": "La carpeta seleccionada no contiene ningún archivo 'dump.bin' válido.",
        "diff_title": "Herramienta IL2CPP Diff & Backtracking (il2diff.py)",
        "lbl_diff_ip": "Dirección IP de la Consola:",
        "btn_quick_dump": "⚡ Dump Rápido (dump.bin + json)",
        "lbl_diff_dump1": "Dump Base JSON (dump1.json):",
        "lbl_diff_dump2": "Dump Modificado JSON (dump2.json):",
        "lbl_diff_dump3": "Tercer Dump JSON (--same):",
        "lbl_diff_offset": "Modo de Comparación / Opciones:",
        "btn_run_diff": "🔍 Ejecutar Diff / Backtracking",
        "btn_cancel_diff": "🛑 Cancelar Proceso",
        "btn_export_diff": "💾 Exportar Resultados Diff",
        "btn_clear_diff": "🗑️ Limpiar",
        "warn_diff_files": "Por favor, selecciona ambos archivos JSON de dump para comparar.",
        "live_warn_title": "⚠️ Advertencia para Envío en Vivo",
        "live_warn_msg": "IMPORTANTE:\nEl dump de memoria y la sesión activa de la consola DEBEN PERTENECER a la misma compilación.\n\nSi el juego se ha reiniciado, asegúrate de actualizar los dumps!",
        "dlg_new_session_title": "Nueva Sesión",
        "dlg_new_session_msg": "Introduce el ID o nombre del juego (ej. PPSA35399):",
        "dlg_session_dir_title": "Introduce el nombre de la carpeta de sesión del juego (ej. ealimit):",
        "dlg_select_session_title": "Seleccionar Carpeta de Sesión de Juego (Unity)",
        "dlg_sdk_notice_title": "Aviso de Extracción SDK",
        "dlg_sdk_notice_msg": "El proceso de extracción de SDK puede tardar hasta 10 minutos dependiendo de las características de tu ordenador.",
        "dlg_save_tlh_title": "Guardar Trainer IL2CPP .TLH",
        "warn_select_session_first": "Selecciona o crea una carpeta de sesión primero.",
        "warn_no_json_dump": "No se encontró ningún archivo .json de dump válido en la carpeta de sesión. Realiza un Quick Dump primero.",
        "warn_enter_addr": "Selecciona una carpeta de sesión y escribe una dirección válida (ej. 0x203f12318).",
        "warn_enter_eq_values": "Introduce ambos valores para comparar (--eq).",
        "lbl_diff_hops": "Saltos (--depth):",
        "lbl_diff_parents": "Padres (--parents):",
        "lbl_diff_mode": "Modo:",
        "lbl_diff_val1": "Val 1:",
        "lbl_diff_val2": "Val 2:"
    },
    "Deutsch": {
        "title": "PS4 / PS5 Unity IL2CPP Dumper & Cheat Generator",
        "frame_dumper": " 1. Speicher-Dump & IL2CPP SDK-Extraktion ",
        "lbl_ip": "Konsolen-IP-Adresse:",
        "btn_new": "🔄 Neu",
        "btn_load": "📂 Sitzungsordner laden",
        "btn_ps4dump": "⚡ 1. Initialer Dump (ps4dump)",
        "btn_il2mem": "📥 2. SDK Extrahieren (il2mem + dumper)",
        "btn_get_name": "🌐 Name abrufen & Umbenennen",
        "btn_open_diff": "📊 Diff-Tool öffnen",
        "frame_cheat": " 2. IL2CPP Cheat Generator (il2cheat.py) ",
        "lbl_dump_file": "Spiel-Sitzungsordner:",
        "lbl_cheat_cmd": "Regeln (Pro Spiel gespeichert):",
        "th_name": "Name",
        "th_path": "IL2CPP Pfad / Static Root",
        "th_value": "Wert",
        "th_test": "Testen",
        "btn_add_cheat": "➕ Regel hinzufügen",
        "btn_suggestions": "💡 Häufige Pfade",
        "btn_export_rules": "📤 Regeln exportieren",
        "btn_import_rules": "📥 Regeln importieren",
        "btn_cheat": "🛠️ .TLH Trainer generieren",
        "btn_test_all": "⚡ Alle live testen",
        "frame_console": " Konsolenausgabe / Terminal ",
        "btn_export_console": "💾 Protokoll exportieren",
        "btn_clear_console": "🗑️ Löschen",
        "frame_finder": " 🔍 IL2CPP SDK & Pfadfinder (il2live.py) ",
        "lbl_keyword": "Schlüsselwort, Wert oder Adresse (z.B. Health, 50 oder 0x203f12318):",
        "btn_search": "🔎 SDK-Code durchsuchen",
        "btn_find_paths": "🧭 Pfade finden (--find)",
        "btn_find_addr": "🧭 Pfade finden (Nach Adresse)",
        "warn_find_paths": "Wähle einen Sitzungsordner (Abschnitt 2) und gib einen Begriff oder eine Adresse ein.",
        "lbl_results_hdr": "Ergebnisse (Strg+F für Suche):",
        "btn_export_finder": "💾 Ergebnisse exportieren",
        "btn_clear_finder": "🗑️ Löschen",
        "warn_ip": "Bitte gib die Konsolen-IP ein.",
        "warn_fields": "Bitte fülle alle Felder und mindestens eine gültige Cheat-Regel aus.",
        "warn_finder": "Bitte wähle einen gültigen Sitzungsordner mit SDK-Ordner aus.",
        "warn_empty_export": "Kein Inhalt zum Exportieren vorhanden.",
        "lbl_language": "Sprache / Language / Idioma:",
        "status_running": "Status: Prozess läuft... Verstrichene Zeit: ",
        "status_idle": "Status: Inaktiv",
        "msg_dump_title": "Prozess Abgeschlossen",
        "msg_dump_success": "Prozess erfolgreich beendet! SDK und dump.cs bereit.",
        "msg_cheat_title": "Trainer Generiert",
        "msg_cheat_success": "Die .TLH Trainer-Datei wurde erfolgreich erstellt!",
        "suggestions_title": "Häufige Unity IL2CPP Cheat-Pfade",
        "suggestions_add": "Zu Regeln hinzufügen",
        "find_dialog_title": "Ergebnis-Navigator",
        "find_label": "Suchbegriff:",
        "find_back": "◀ Zurück",
        "find_next": "Weiter ▶",
        "find_matches": "Treffer:",
        "msg_export_success": "Datei erfolgreich exportiert!",
        "msg_import_success": "Regeln erfolgreich importiert!",
        "msg_session_loaded": "Sitzungsordner erfolgreich geladen von:",
        "warn_no_dump_bin": "Der gewählte Ordner enthält keine gültige 'dump.bin'.",
        "diff_title": "IL2CPP Diff & Backtracking Tool (il2diff.py)",
        "lbl_diff_ip": "Konsolen-IP-Adresse:",
        "btn_quick_dump": "⚡ Schnell-Dump (dump.bin + json)",
        "lbl_diff_dump1": "Basis Dump JSON (dump1.json):",
        "lbl_diff_dump2": "Modifizierter Dump JSON (dump2.json):",
        "lbl_diff_dump3": "Dritter Dump JSON (--same):",
        "lbl_diff_offset": "Vergleichsmodus / Optionen:",
        "btn_run_diff": "🔍 Diff / Backtracking ausführen",
        "btn_cancel_diff": "🛑 Prozess abbrechen",
        "btn_export_diff": "💾 Diff-Ergebnisse exportieren",
        "btn_clear_diff": "🗑️ Löschen",
        "warn_diff_files": "Bitte wähle beide JSON-Dump-Dateien zum Vergleichen aus.",
        "live_warn_title": "⚠️ Live-Bearbeitungs-Warnung",
        "live_warn_msg": "WICHTIG:\nSpeicher-Dump und aktive Konsolensitzung MÜSSEN vom selben Build sein!"
    }
}

class IL2CppDumperGUI:
    def __init__(self, root):
        self.root = root
        self.current_lang = "English"
        self.is_running = False
        self.start_time = 0
        self.cheat_rows = []
        self.search_matches = []
        self.current_match_idx = -1
        self.find_win = None
        self.diff_win = None
        self.diff_proc = None
        self.find_proc = None
        self.progress_win = None
        self.current_game_key = "default"
        self.cover_image_tk = None

        self.config = self.load_config()

        self.root.geometry("1280x920")
        self.root.resizable(True, True)
        self.root.minsize(950, 700)

        self.root.bind("<Control-f>", self.open_quick_find_dialog)
        self.root.bind("<Control-F>", self.open_quick_find_dialog)

        self._build_top_bar()

        main_container = ttk.Frame(self.root)
        main_container.pack(fill="both", expand=True, padx=5, pady=5)

        paned = ttk.PanedWindow(main_container, orient=tk.HORIZONTAL)
        paned.pack(fill="both", expand=True)

        left_frame = ttk.Frame(paned)
        right_frame = ttk.Frame(paned)

        paned.add(left_frame, weight=3)
        paned.add(right_frame, weight=2)

        self._build_dumper_section(left_frame)
        self._build_cheat_section(left_frame)
        self._build_console_output(left_frame)

        self._build_finder_section(right_frame)

        self.apply_saved_config()

        self.events = queue.Queue()
        self._pump()
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def center_window(self, win, width=420, height=240):
        win.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (width // 2)
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (height // 2)
        win.geometry(f"{width}x{height}+{x}+{y}")

    def load_config(self):
        default_config = {
            "language": "English",
            "ip": "192.168.1.XXX",
            "games_cheats": {
                "default": [
                    {"name": "Mana", "path": "GameStateManager::_instance._mainCharacterEntity.manas[0]._currentManaStatObject.baseValue", "value": "999"}
                ]
            },
            "dump_path": "",
            "keyword": "Health",
            "find_depth": "6",
            "find_types": "",
            "find_objects": False,
            "find_fields": False
        }
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for k, v in default_config.items():
                        if k not in data:
                            data[k] = v
                    return data
            except Exception:
                pass
        return default_config

    def save_config(self):
        try:
            cheat_list = []
            for item in self.cheat_rows:
                n = item['name'].get().strip()
                p = item['path'].get().strip()
                v = item['value'].get().strip()
                if n or p or v:
                    cheat_list.append({"name": n, "path": p, "value": v})
            
            if not cheat_list:
                cheat_list = [{"name": "Mana", "path": "GameStateManager::_instance._mainCharacterEntity.manas[0]._currentManaStatObject.baseValue", "value": "999"}]

            if "games_cheats" not in self.config:
                self.config["games_cheats"] = {}

            self.config["games_cheats"][self.current_game_key] = cheat_list

            config_data = {
                "language": self.current_lang,
                "ip": self.entry_ip.get().strip(),
                "games_cheats": self.config["games_cheats"],
                "dump_path": self.entry_dump_path.get().strip(),
                "keyword": self.entry_keyword.get().strip(),
                "find_depth": self.config.get("find_depth", "6"),
                "find_types": self.config.get("find_types", ""),
                "find_objects": self.config.get("find_objects", False),
                "find_fields": self.config.get("find_fields", False)
            }
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config_data, f, indent=4)
        except Exception as e:
            print(f"Error saving config: {e}")

    def on_close(self):
        self.save_config()
        self.root.destroy()

    def _pump(self):
        while not self.events.empty():
            kind, payload = self.events.get_nowait()
            if kind == "log":
                self.log(payload)
            elif kind == "paths":
                self.show_paths(*payload)
            else:
                self.finish(*payload)
        
        if self.is_running:
            elapsed = int(time.time() - self.start_time)
            m, s = divmod(elapsed, 60)
            t = TRANSLATIONS[self.current_lang]
            self.lbl_status_timer.config(text=f"{t['status_running']}{m:02d}:{s:02d}")
        else:
            self.lbl_status_timer.config(text="")

        self.root.after(100, self._pump)

    def finish(self, success, is_dump, errors_captured):
        self.is_running = False
        elapsed = int(time.time() - self.start_time)
        m, s = divmod(elapsed, 60)
        time_str = f"{m:02d}:{s:02d}"
        
        t = TRANSLATIONS[self.current_lang]
        if success:
            self.log(f"\n--- Process Finished Successfully in {time_str} ---")
            if is_dump:
                messagebox.showinfo(t["msg_dump_title"], t["msg_dump_success"])
        else:
            self.log(f"\n--- Process Finished with Errors/Warnings in {time_str} ---")
            if errors_captured:
                for err in errors_captured:
                    self.log(f"[ERROR] {err}")

    def _build_top_bar(self):
        top_frame = ttk.Frame(self.root)
        top_frame.pack(fill="x", padx=10, pady=8)

        self.lbl_lang = ttk.Label(top_frame, font=("Arial", 9, "bold"))
        self.lbl_lang.pack(side="left", padx=5)

        self.combo_lang = ttk.Combobox(
            top_frame, 
            values=["English", "Español", "Deutsch"], 
            state="readonly", 
            width=15
        )
        self.combo_lang.set("English")
        self.combo_lang.pack(side="left", padx=5)
        self.combo_lang.bind("<<ComboboxSelected>>", self.on_language_change)

        self.lbl_status_timer = ttk.Label(top_frame, text="", font=("Arial", 9, "italic"), foreground="blue")
        self.lbl_status_timer.pack(side="right", padx=5)

    def _build_dumper_section(self, parent):
        self.frame_dumper = ttk.LabelFrame(parent)
        self.frame_dumper.pack(fill="x", padx=5, pady=4)

        self.lbl_ip = ttk.Label(self.frame_dumper)
        self.lbl_ip.grid(row=0, column=0, sticky="w", padx=10, pady=8)

        self.entry_ip = ttk.Entry(self.frame_dumper, width=18)
        self.entry_ip.grid(row=0, column=1, sticky="w", padx=5, pady=8)

        self.btn_new = ttk.Button(self.frame_dumper, command=self.reset_new_session)
        self.btn_new.grid(row=0, column=2, padx=4, pady=8)

        self.btn_load = ttk.Button(self.frame_dumper, command=self.load_game_session_folder)
        self.btn_load.grid(row=0, column=3, padx=4, pady=8)

        self.btn_ps4dump = ttk.Button(self.frame_dumper, command=self.run_ps4dump)
        self.btn_ps4dump.grid(row=0, column=4, padx=4, pady=8)

        self.btn_il2mem = ttk.Button(self.frame_dumper, command=self.run_il2mem)
        self.btn_il2mem.grid(row=0, column=5, padx=4, pady=8)

        self.btn_get_name = ttk.Button(self.frame_dumper, command=self.manual_fetch_metadata)
        self.btn_get_name.grid(row=0, column=6, padx=4, pady=8)

        self.btn_open_diff = ttk.Button(self.frame_dumper, command=self.open_diff_window)
        self.btn_open_diff.grid(row=0, column=7, padx=4, pady=8)

    def load_detected_project(self, rel_path):
        self.entry_dump_path.config(state="normal")
        self.entry_dump_path.delete(0, tk.END)
        self.entry_dump_path.insert(0, rel_path)
        self.entry_dump_path.config(state="readonly")
        self.process_dump_metadata(rel_path)

    def reset_new_session(self):
        t = TRANSLATIONS[self.current_lang]
        active_game_id = simpledialog.askstring(t["dlg_new_session_title"], t["dlg_new_session_msg"], parent=self.root)
        if not active_game_id:
            return

        active_game_id = active_game_id.strip()
        dump_path = os.path.relpath(os.path.join(DUMPS_DIR, active_game_id), TOOLS_DIR)
        abs_dump_dir = os.path.abspath(os.path.join(TOOLS_DIR, dump_path))
        os.makedirs(abs_dump_dir, exist_ok=True)

        self.update_dump_path_ui(dump_path)
        self.lbl_game_info.config(text=f"🎮 [{active_game_id}]")
        self.lbl_cover.config(image="")
        self.cover_image_tk = None
        self.current_game_key = active_game_id
        
        for row in self.cheat_rows:
            row['frame'].destroy()
        self.cheat_rows.clear()
        
        self.load_rules_for_current_game()
        self.finder_results.delete("1.0", tk.END)
        self.lbl_res_count.config(text="Results: 0")
        self.console.delete("1.0", tk.END)
        self.save_config()
        self.log(f"[NEW SESSION] Sesión creada/cargada para: {active_game_id}")

    def fetch_cover_and_name_by_ppsa(self, ppsa_code):
        url = f"https://prosperopatches.com/{ppsa_code}"
        self.log(f"[GET NAME] Consultando ProsperoPatches: {url}")
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
            with urllib.request.urlopen(req, timeout=10) as response:
                html_content = response.read().decode('utf-8', errors='ignore')
                self.log(f"[GET NAME] Página web cargada correctamente. Extrayendo metadatos...")
                
                game_name = ""
                title_match = re.search(r"<title>(?:[^:]+):\s*([^<\-]+)(?:\s*-\s*[^<]+)?<\/title>", html_content, re.IGNORECASE)
                if title_match:
                    game_name = title_match.group(1).strip()
                else:
                    h1_match = re.search(r"<h1>([^<]+)<\/h1>", html_content, re.IGNORECASE)
                    if h1_match:
                        full_h1 = h1_match.group(1).strip()
                        if ":" in full_h1:
                            game_name = full_h1.split(":", 1)[1].strip()
                        else:
                            game_name = full_h1

                self.log(f"[GET NAME] Nombre extraído: '{game_name}'")
                return game_name
        except urllib.error.HTTPError as e:
            self.log(f"[GET NAME ERROR] HTTP Error {e.code}: {e.reason}")
        except urllib.error.URLError as e:
            self.log(f"[GET NAME ERROR] URL Error (Sin conexión o DNS): {e.reason}")
        except Exception as e:
            self.log(f"[GET NAME ERROR] Excepción inesperada: {e}")
        return ""

    def manual_fetch_metadata(self):
        t = TRANSLATIONS[self.current_lang]
        dump_path = self.entry_dump_path.get().strip()
        if not dump_path:
            messagebox.showwarning("Warning", t["warn_select_session_first"])
            return

        abs_dump_dir = os.path.abspath(os.path.join(TOOLS_DIR, dump_path))
        
        title_id = None
        for filename in os.listdir(abs_dump_dir):
            if filename.endswith(".json"):
                json_path = os.path.join(abs_dump_dir, filename)
                try:
                    with open(json_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read(8192)
                        match = re.search(r"([A-Z]{4}\d{5})", content)
                        if match:
                            title_id = match.group(1)
                            break
                except Exception:
                    pass

        if not title_id:
            folder_name = os.path.basename(abs_dump_dir)
            match = re.search(r"([A-Z]{4}\d{5})", folder_name)
            if match:
                title_id = match.group(1)

        if not title_id:
            messagebox.showwarning("Warning", "No se pudo extraer ningún Title ID (PPSA/CUSA) del archivo dump.json ni de la carpeta.")
            return

        self.log(f"[GET NAME] Title ID detectado: {title_id}. Consultando prosperopatches.com...")

        def fetch_thread():
            game_name = self.fetch_cover_and_name_by_ppsa(title_id)

            if not game_name:
                try:
                    url = f"https://a0.app.np.dl.playstation.net/np/os/pkg/{title_id}/{title_id}-ver.json"
                    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=5) as response:
                        data = json.loads(response.read().decode())
                        if "name" in data:
                            game_name = data["name"]
                except Exception:
                    pass

            if not game_name or game_name.strip() == "" or game_name.upper() == title_id:
                messagebox.showerror("Error", f"No se pudo encontrar el nombre del juego para {title_id} en prosperopatches.com.")
                return

            clean_name = re.sub(r'[\\/*?:"<>|]', "", game_name).strip()
            new_folder_name = f"{title_id} ({clean_name})"
            parent_dir = os.path.dirname(abs_dump_dir)
            new_abs_dir = os.path.join(parent_dir, new_folder_name)

            try:
                if abs_dump_dir != new_abs_dir:
                    if os.path.exists(new_abs_dir):
                        self.log(f"[GET NAME] La carpeta {new_folder_name} ya existe. Omitiendo renombrado.")
                    else:
                        os.rename(abs_dump_dir, new_abs_dir)
                        self.log(f"[GET NAME] Carpeta renombrada con éxito a: {new_folder_name}")
                
                rel_new_path = os.path.relpath(new_abs_dir, TOOLS_DIR)
                self.root.after(0, lambda: self.load_detected_project(rel_new_path))
                self.root.after(0, lambda: messagebox.showinfo("Get Name", f"Juego identificado:\n{game_name}\n\nCarpeta: {new_folder_name}"))
            except Exception as e:
                self.log(f"[ERROR Renombrando carpeta] {e}")

        threading.Thread(target=fetch_thread, daemon=True).start()

    def load_game_session_folder(self):
        t = TRANSLATIONS[self.current_lang]
        initial_dir = DUMPS_DIR if os.path.exists(DUMPS_DIR) else BASE_DIR
        dir_path = filedialog.askdirectory(
            title=t["dlg_select_session_title"],
            initialdir=initial_dir,
            parent=self.root
        )
        if dir_path:
            dump_bin_path = os.path.join(dir_path, "dump.bin")
            if os.path.exists(dump_bin_path):
                try:
                    rel_path = os.path.relpath(dir_path, TOOLS_DIR)
                    self.entry_dump_path.config(state="normal")
                    self.entry_dump_path.delete(0, tk.END)
                    self.entry_dump_path.insert(0, rel_path)
                    self.entry_dump_path.config(state="readonly")
                    self.process_dump_metadata(rel_path)
                    self.save_config()
                    messagebox.showinfo("Sesión Cargada", f"{t['msg_session_loaded']}\n{os.path.basename(dir_path)}")
                except Exception as e:
                    messagebox.showerror("Error", f"No se pudo cargar la sesión: {e}")
            else:
                messagebox.showwarning("Advertencia", t["warn_no_dump_bin"])

    def open_diff_window(self):
        t = TRANSLATIONS[self.current_lang]
        if self.diff_win and self.diff_win.winfo_exists():
            self.diff_win.lift()
            return

        self.diff_win = tk.Toplevel(self.root)
        self.diff_win.title(t["diff_title"])
        self.diff_win.geometry("980x820")
        self.diff_win.resizable(True, True)
        self.diff_win.minsize(780, 600)
        self.center_window(self.diff_win, 980, 820)

        self.q_running = False
        self.diff_proc = None

        frame_quick = ttk.LabelFrame(self.diff_win, text=" Dumps Generation ")
        frame_quick.pack(fill="x", padx=10, pady=8)

        lbl_dip = ttk.Label(frame_quick, text=t["lbl_diff_ip"])
        lbl_dip.grid(row=0, column=0, sticky="w", padx=10, pady=6)
        entry_dip = ttk.Entry(frame_quick, width=22)
        entry_dip.insert(0, self.entry_ip.get())
        entry_dip.grid(row=0, column=1, sticky="w", padx=5, pady=6)

        btn_dump1 = ttk.Button(frame_quick, text="⚡ Dump1", command=lambda: run_quick_dump_task("dump1", entry_d1))
        btn_dump1.grid(row=0, column=2, padx=5, pady=6)

        btn_dump2 = ttk.Button(frame_quick, text="⚡ Dump2", command=lambda: run_quick_dump_task("dump2", entry_d2))
        btn_dump2.grid(row=0, column=3, padx=5, pady=6)

        btn_dump3 = ttk.Button(frame_quick, text="⚡ Dump3", command=lambda: run_quick_dump_task("dump3", entry_d3))

        lbl_timer_diff = ttk.Label(frame_quick, text="", font=("Arial", 9, "italic"), foreground="blue")
        lbl_timer_diff.grid(row=0, column=5, padx=10, pady=6)

        frame_top = ttk.LabelFrame(self.diff_win, text=" Setup JSON Dumps & il2diff Comparison Options ")
        frame_top.pack(fill="x", padx=10, pady=5)

        lbl1 = ttk.Label(frame_top, text=t["lbl_diff_dump1"])
        lbl1.grid(row=0, column=0, sticky="w", padx=10, pady=4)
        entry_d1 = ttk.Entry(frame_top, width=45)
        entry_d1.grid(row=0, column=1, padx=5, pady=4, sticky="ew")
        btn_b1 = ttk.Button(frame_top, text="...", width=5, command=lambda: browse_diff_json(entry_d1))
        btn_b1.grid(row=0, column=2, padx=5, pady=4)

        lbl2 = ttk.Label(frame_top, text=t["lbl_diff_dump2"])
        lbl2.grid(row=1, column=0, sticky="w", padx=10, pady=4)
        entry_d2 = ttk.Entry(frame_top, width=45)
        entry_d2.grid(row=1, column=1, padx=5, pady=4, sticky="ew")
        btn_b2 = ttk.Button(frame_top, text="...", width=5, command=lambda: browse_diff_json(entry_d2))
        btn_b2.grid(row=1, column=2, padx=5, pady=4)

        lbl3 = ttk.Label(frame_top, text=t["lbl_diff_dump3"])
        entry_d3 = ttk.Entry(frame_top, width=45)
        btn_b3 = ttk.Button(frame_top, text="...", width=5, command=lambda: browse_diff_json(entry_d3))

        frame_params = ttk.LabelFrame(frame_top, text=" Parámetros de Comparación ")
        frame_params.grid(row=3, column=0, columnspan=3, sticky="ew", padx=10, pady=8)

        row_mode_frame = ttk.Frame(frame_params)
        row_mode_frame.pack(fill="x", padx=5, pady=4)

        lbl_mode = ttk.Label(row_mode_frame, text=t["lbl_diff_mode"])
        lbl_mode.pack(side="left", padx=(0, 4))
        combo_mode = ttk.Combobox(row_mode_frame, values=["--eq", "--changed"], state="readonly", width=12)
        combo_mode.set("--eq")
        combo_mode.pack(side="left", padx=(0, 15))

        lbl_general_depth = ttk.Label(row_mode_frame, text=t["lbl_diff_hops"])
        lbl_general_depth.pack(side="left", padx=(0, 2))
        entry_general_depth = ttk.Entry(row_mode_frame, width=6)
        entry_general_depth.insert(0, "6")
        entry_general_depth.pack(side="left", padx=(0, 15))

        lbl_general_parents = ttk.Label(row_mode_frame, text=t["lbl_diff_parents"])
        lbl_general_parents.pack(side="left", padx=(0, 2))
        entry_general_parents = ttk.Entry(row_mode_frame, width=6)
        entry_general_parents.insert(0, "30")
        entry_general_parents.pack(side="left", padx=(0, 15))

        eq_input_container = ttk.Frame(row_mode_frame)
        
        lbl_v1 = ttk.Label(eq_input_container, text=t["lbl_diff_val1"])
        lbl_v1.pack(side="left", padx=(0, 2))
        entry_val1 = ttk.Entry(eq_input_container, width=12)
        entry_val1.insert(0, "50")
        entry_val1.pack(side="left", padx=(0, 8))

        lbl_v2 = ttk.Label(eq_input_container, text=t["lbl_diff_val2"])
        lbl_v2.pack(side="left", padx=(0, 2))
        entry_val2 = ttk.Entry(eq_input_container, width=12)
        entry_val2.insert(0, "77")
        entry_val2.pack(side="left", padx=(0, 8))

        row_opts_frame = ttk.Frame(frame_params)

        lbl_paths = ttk.Label(row_opts_frame, text="--paths:")
        lbl_paths.pack(side="left", padx=(0, 2))
        entry_paths = ttk.Entry(row_opts_frame, width=8)
        entry_paths.insert(0, "3")
        entry_paths.pack(side="left", padx=(0, 15))

        lbl_class = ttk.Label(row_opts_frame, text="--class:")
        lbl_class.pack(side="left", padx=(0, 2))
        entry_class = ttk.Entry(row_opts_frame, width=18)
        entry_class.pack(side="left", padx=(0, 5))

        def update_diff_mode_ui(event=None):
            mode = combo_mode.get()
            if mode == "--eq":
                btn_dump3.grid_forget()
                lbl3.grid_forget()
                entry_d3.grid_forget()
                btn_b3.grid_forget()
                row_opts_frame.pack_forget()
                eq_input_container.pack(side="left", fill="x", expand=True)
            elif mode == "--changed":
                eq_input_container.pack_forget()
                btn_dump3.grid(row=0, column=4, padx=5, pady=6)
                lbl3.grid(row=2, column=0, sticky="w", padx=10, pady=4)
                entry_d3.grid(row=2, column=1, padx=5, pady=4, sticky="ew")
                btn_b3.grid(row=2, column=2, padx=5, pady=4)
                row_opts_frame.pack(fill="x", padx=5, pady=4)

        combo_mode.bind("<<ComboboxSelected>>", update_diff_mode_ui)
        update_diff_mode_ui()

        frame_top.columnconfigure(1, weight=1)

        frame_actions = ttk.Frame(self.diff_win)
        frame_actions.pack(fill="x", padx=10, pady=5)

        btn_run = ttk.Button(frame_actions, text=t["btn_run_diff"], command=lambda: run_il2diff_task())
        btn_run.pack(side="left", padx=5)

        btn_cancel = ttk.Button(frame_actions, text=t["btn_cancel_diff"], command=lambda: cancel_process())
        btn_cancel.pack(side="left", padx=5)

        btn_exp = ttk.Button(frame_actions, text=t["btn_export_diff"], command=lambda: export_diff_results())
        btn_exp.pack(side="right", padx=5)

        btn_clear = ttk.Button(frame_actions, text=t["btn_clear_diff"], command=lambda: txt_res.delete("1.0", tk.END))
        btn_clear.pack(side="right", padx=5)

        frame_res = ttk.LabelFrame(self.diff_win, text=" Diff Terminal Output ")
        frame_res.pack(fill="both", expand=True, padx=10, pady=8)

        txt_res = scrolledtext.ScrolledText(frame_res, bg="black", fg="#00FF00", font=("Consolas", 9))
        txt_res.pack(fill="both", expand=True, padx=5, pady=5)

        def cancel_process():
            if self.diff_proc and self.diff_proc.poll() is None:
                try:
                    self.diff_proc.kill()
                    txt_res.insert(tk.END, "\n[!] Proceso cancelado por el usuario.\n")
                except Exception as e:
                    txt_res.insert(tk.END, f"\n[ERROR] {e}\n")
            self.q_running = False

        def browse_diff_json(entry_widget):
            initial_dir = DUMPS_DIR if os.path.exists(DUMPS_DIR) else BASE_DIR
            file_path = filedialog.askopenfilename(
                title="Select Dump JSON",
                initialdir=initial_dir,
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
                parent=self.diff_win
            )
            if file_path:
                entry_widget.delete(0, tk.END)
                entry_widget.insert(0, os.path.basename(file_path))

        def run_quick_dump_task(prefix_name, target_entry_widget):
            ip = entry_dip.get().strip()
            if not ip or ip == "192.168.1.XXX":
                messagebox.showwarning("Warning", t["warn_ip"], parent=self.diff_win)
                return

            if self.q_running:
                return

            dump_path = self.entry_dump_path.get().strip()
            if not dump_path:
                messagebox.showwarning("Warning", t["warn_select_session_first"], parent=self.diff_win)
                return

            abs_out_dir = os.path.abspath(os.path.join(TOOLS_DIR, dump_path))
            os.makedirs(abs_out_dir, exist_ok=True)
            out_base = os.path.join(abs_out_dir, prefix_name)

            txt_res.insert(tk.END, f"\n> Ejecutando volcado: ps4dump.py --host {ip} -o {out_base}\n")
            start_t = time.time()
            self.q_running = True

            def update_diff_timer():
                if self.q_running:
                    el = int(time.time() - start_t)
                    m, s = divmod(el, 60)
                    lbl_timer_diff.config(text=f"Time: {m:02d}:{s:02d}")
                    if self.diff_win.winfo_exists():
                        self.diff_win.after(1000, update_diff_timer)

            update_diff_timer()

            script_path = os.path.join(TOOLS_DIR, "ps4dump.py")
            if not os.path.exists(script_path):
                messagebox.showerror("Error", "ps4dump.py not found in tools directory.", parent=self.diff_win)
                self.q_running = False
                return

            args = [script_path, "--host", ip, "-o", out_base]

            def q_thread():
                try:
                    self.diff_proc = subprocess.Popen([sys.executable, "-u"] + args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                                      text=True, encoding="utf-8", errors="replace", cwd=TOOLS_DIR)
                    for line in self.diff_proc.stdout:
                        txt_res.insert(tk.END, line)
                        txt_res.see(tk.END)
                    self.diff_proc.wait()
                    
                    if self.diff_proc.returncode == 0:
                        json_filename = f"{prefix_name}.json"
                        target_entry_widget.delete(0, tk.END)
                        target_entry_widget.insert(0, json_filename)
                        txt_res.insert(tk.END, f"\n[SUCCESS] ¡Volcado completado! Generados {prefix_name}.bin y {json_filename}\n")
                except Exception as e:
                    txt_res.insert(tk.END, f"\n[ERROR] {e}\n")
                
                self.q_running = False
                if lbl_timer_diff.winfo_exists():
                    lbl_timer_diff.config(text="Done!")

            threading.Thread(target=q_thread, daemon=True).start()

        def run_il2diff_task():
            d1 = entry_d1.get().strip()
            d2 = entry_d2.get().strip()
            d3 = entry_d3.get().strip()
            mode = combo_mode.get().strip()
            val1 = entry_val1.get().strip()
            val2 = entry_val2.get().strip()
            depth = entry_general_depth.get().strip()
            parents = entry_general_parents.get().strip()
            paths = entry_paths.get().strip()
            cls = entry_class.get().strip()

            if not d1 or not d2:
                messagebox.showwarning("Warning", t["warn_diff_files"], parent=self.diff_win)
                return

            dump_path = self.entry_dump_path.get().strip()
            if not dump_path:
                messagebox.showwarning("Warning", t["warn_select_session_first"], parent=self.diff_win)
                return

            abs_dump_dir = os.path.abspath(os.path.join(TOOLS_DIR, dump_path))
            txt_res.delete("1.0", tk.END)
            txt_res.insert(tk.END, f"> Ejecutando comparación il2diff.py:\n  - Dumpdir: {abs_dump_dir}\n  - A: {d1}\n  - B: {d2}\n  - Modo: {mode}\n  - Hops (--depth): {depth}\n  - Parents (--parents): {parents}\n" + "-"*50 + "\n")

            script_path = os.path.join(TOOLS_DIR, "il2diff.py")
            if not os.path.exists(script_path):
                txt_res.insert(tk.END, f"\n[ERROR] il2diff.py no se encuentra en {TOOLS_DIR}\n")
                return

            args = [script_path, abs_dump_dir, d1, d2]

            if depth:
                args.extend(["--depth", depth])
            if parents:
                args.extend(["--parents", parents])

            if mode == "--eq":
                if not val1 or not val2:
                    messagebox.showwarning("Warning", t["warn_enter_eq_values"], parent=self.diff_win)
                    return
                args.extend(["--eq", val1, val2])
            elif mode == "--changed":
                args.append("--changed")
                if paths:
                    args.extend(["--paths", paths])
                if cls:
                    args.extend(["--class", cls])
                if d3:
                    args.extend(["--same", d3])

            def thread_func():
                try:
                    self.diff_proc = subprocess.Popen([sys.executable, "-u"] + args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                                      text=True, encoding="utf-8", errors="replace", cwd=TOOLS_DIR)
                    for line in self.diff_proc.stdout:
                        txt_res.insert(tk.END, line)
                        txt_res.see(tk.END)
                    self.diff_proc.wait()
                except Exception as e:
                    txt_res.insert(tk.END, f"\n[ERROR] {e}\n")

            threading.Thread(target=thread_func, daemon=True).start()

        def export_diff_results():
            content = txt_res.get("1.0", tk.END).strip()
            if not content:
                messagebox.showwarning("Warning", t["warn_empty_export"], parent=self.diff_win)
                return
            file_path = filedialog.asksaveasfilename(
                title="Export Diff Results",
                defaultextension=".txt",
                filetypes=[("Text files", "*.txt"), ("Log files", "*.log"), ("All files", "*.*")],
                initialfile="il2diff_results.txt",
                parent=self.diff_win
            )
            if file_path:
                try:
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(content)
                    messagebox.showinfo("Success", t["msg_export_success"], parent=self.diff_win)
                except Exception as e:
                    messagebox.showerror("Error", f"{e}", parent=self.diff_win)

    def _build_cheat_section(self, parent):
        self.frame_cheat = ttk.LabelFrame(parent)
        self.frame_cheat.pack(fill="x", padx=5, pady=2)

        dump_info_frame = ttk.Frame(self.frame_cheat)
        dump_info_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=5, pady=2)

        self.lbl_dump_file = ttk.Label(dump_info_frame)
        self.lbl_dump_file.pack(side="left", padx=(5, 5))

        self.entry_dump_path = ttk.Entry(dump_info_frame, width=35, state="readonly")
        self.entry_dump_path.pack(side="left", padx=5, fill="x", expand=True)

        self.lbl_game_info = ttk.Label(dump_info_frame, text="", font=("Arial", 9, "bold"), foreground="#007acc")
        self.lbl_game_info.pack(side="right", padx=10)

        cover_container = ttk.Frame(self.frame_cheat)
        cover_container.grid(row=1, column=1, sticky="ne", padx=(5, 10), pady=0)
        
        self.lbl_cover = ttk.Label(cover_container)
        self.lbl_cover.pack(anchor="e")

        self.lbl_cheat_cmd = ttk.Label(self.frame_cheat)
        self.lbl_cheat_cmd.grid(row=1, column=0, sticky="nw", padx=10, pady=2)

        container_frame = ttk.Frame(self.frame_cheat)
        container_frame.grid(row=1, column=1, columnspan=1, sticky="w", padx=5, pady=0)

        headers_frame = ttk.Frame(container_frame)
        headers_frame.pack(fill="x", anchor="w", padx=2, pady=0)
        
        self.lbl_th_name = ttk.Label(headers_frame, font=("Arial", 8, "bold"))
        self.lbl_th_name.pack(side="left", padx=(0, 5))
        
        self.lbl_th_path = ttk.Label(headers_frame, font=("Arial", 8, "bold"))
        self.lbl_th_path.pack(side="left", padx=(140, 5))
        
        self.lbl_th_value = ttk.Label(headers_frame, font=("Arial", 8, "bold"))
        self.lbl_th_value.pack(side="left", padx=(155, 5))

        self.lbl_th_test = ttk.Label(headers_frame, font=("Arial", 8, "bold"))
        self.lbl_th_test.pack(side="left", padx=(42, 5))

        self.cheats_inner_frame = ttk.Frame(container_frame)
        self.cheats_inner_frame.pack(fill="x", anchor="w")

        btn_actions_frame = ttk.Frame(container_frame)
        btn_actions_frame.pack(anchor="w", pady=2, fill="x")

        self.btn_add_cheat = ttk.Button(btn_actions_frame, command=lambda: self.add_cheat_row())
        self.btn_add_cheat.pack(side="left", padx=(0, 6))

        self.btn_suggestions = ttk.Button(btn_actions_frame, command=self.open_suggestions_window)
        self.btn_suggestions.pack(side="left", padx=(0, 6))

        self.btn_export_rules = ttk.Button(btn_actions_frame, command=self.export_game_rules)
        self.btn_export_rules.pack(side="left", padx=(0, 6))

        self.btn_import_rules = ttk.Button(btn_actions_frame, command=self.import_game_rules)
        self.btn_import_rules.pack(side="left")

        action_buttons_row = ttk.Frame(self.frame_cheat)
        action_buttons_row.grid(row=2, column=1, pady=4, sticky="w")

        self.btn_cheat = ttk.Button(action_buttons_row, command=self.run_cheat)
        self.btn_cheat.pack(side="left", padx=(0, 8))

        self.btn_test = ttk.Button(action_buttons_row, command=self.run_test_rules)
        self.btn_test.pack(side="left")

        self.frame_cheat.columnconfigure(1, weight=1)

    def export_game_rules(self):
        t = TRANSLATIONS[self.current_lang]
        cheat_list = []
        for item in self.cheat_rows:
            n = item['name'].get().strip()
            p = item['path'].get().strip()
            v = item['value'].get().strip()
            if n or p or v:
                cheat_list.append({"name": n, "path": p, "value": v})

        if not cheat_list:
            messagebox.showwarning("Warning", t["warn_empty_export"])
            return

        file_path = filedialog.asksaveasfilename(
            title="Export Game Cheat Rules",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile=f"{self.current_game_key}_rules.json",
            parent=self.root
        )
        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump({"game": self.current_game_key, "rules": cheat_list}, f, indent=4)
                messagebox.showinfo("Success", t["msg_export_success"])
            except Exception as e:
                messagebox.showerror("Error", f"{e}")

    def import_game_rules(self):
        t = TRANSLATIONS[self.current_lang]
        file_path = filedialog.askopenfilename(
            title="Import Game Cheat Rules",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            parent=self.root
        )
        if file_path:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    rules = data.get("rules", [])
                    if rules:
                        for row in self.cheat_rows:
                            row['frame'].destroy()
                        self.cheat_rows.clear()
                        for item in rules:
                            self.add_cheat_row(item.get("name", ""), item.get("path", ""), item.get("value", ""))
                        messagebox.showinfo("Success", t["msg_import_success"])
            except Exception as e:
                messagebox.showerror("Error", f"{e}")

    def open_suggestions_window(self):
        t = TRANSLATIONS[self.current_lang]
        sug_win = tk.Toplevel(self.root)
        sug_win.title(t["suggestions_title"])
        sug_win.geometry("780x520")
        sug_win.resizable(True, True)
        sug_win.minsize(650, 400)
        self.center_window(sug_win, 780, 520)

        lbl_info = ttk.Label(sug_win, text=t["suggestions_title"], font=("Arial", 10, "bold"))
        lbl_info.pack(padx=15, pady=(12, 5), anchor="w")

        container_frame = ttk.Frame(sug_win)
        container_frame.pack(fill="both", expand=True, padx=10, pady=5)

        canvas = tk.Canvas(container_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        window_id = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

        def _on_canvas_configure(event):
            canvas.itemconfig(window_id, width=event.width)

        canvas.bind("<Configure>", _on_canvas_configure)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        common_cheats = [
            {"name": "Mana / Energy", "path": "GameStateManager::_instance._mainCharacterEntity.manas[0]._currentManaStatObject.baseValue", "value": "999"},
            {"name": "Health Stat", "path": "GameStateManager::_instance._mainCharacterEntity.CurrentStats{Type=HealthCurrent}.baseValue", "value": "999"},
            {"name": "Player Speed", "path": "PlayerController::_instance.movementSettings.walkSpeed", "value": "15"},
            {"name": "Coins / Currency", "path": "InventoryManager::_instance.playerInventory.currencyAmount", "value": "999999"},
            {"name": "Jump Force", "path": "PlayerController::_instance.jumpForce", "value": "18"}
        ]

        for item in common_cheats:
            row_f = ttk.Frame(scrollable_frame)
            row_f.pack(fill="x", pady=2, padx=5)

            lbl_desc = ttk.Label(
                row_f, 
                text=f"• {item['name']}:\n  {item['path']} = {item['value']}", 
                font=("Consolas", 9, "bold")
            )
            lbl_desc.pack(side="left", padx=10, pady=4, fill="x", expand=True)

            btn_add = ttk.Button(
                row_f, 
                text=t["suggestions_add"], 
                command=lambda i=item: self.add_suggestion_to_rules(i, sug_win)
            )
            btn_add.pack(side="right", padx=10)

    def add_suggestion_to_rules(self, item, win=None):
        if len(self.cheat_rows) == 1 and not self.cheat_rows[0]['name'].get().strip() and not self.cheat_rows[0]['path'].get().strip():
            self.cheat_rows[0]['name'].insert(0, item['name'])
            self.cheat_rows[0]['path'].insert(0, item['path'])
            self.cheat_rows[0]['value'].insert(0, item['value'])
        else:
            self.add_cheat_row(name_val=item['name'], path_val=item['path'], value_val=item['value'])
        if win:
            win.destroy()

    def add_cheat_row(self, name_val="", path_val="", value_val=""):
        row_frame = ttk.Frame(self.cheats_inner_frame)
        row_frame.pack(fill="x", pady=2)

        btn_up = ttk.Button(row_frame, text="⬆", width=2, command=lambda: self.move_cheat_row(row_frame, -1))
        btn_up.pack(side="left", padx=(0, 1))

        btn_down = ttk.Button(row_frame, text="⬇", width=2, command=lambda: self.move_cheat_row(row_frame, 1))
        btn_down.pack(side="left", padx=(0, 4))

        entry_name = ttk.Entry(row_frame, width=16)
        if name_val:
            entry_name.insert(0, name_val)
        entry_name.pack(side="left", padx=(0, 4))

        lbl_eq1 = ttk.Label(row_frame, text="=", font=("Consolas", 10, "bold"))
        lbl_eq1.pack(side="left", padx=2)

        entry_path = ttk.Entry(row_frame, width=52)
        if path_val:
            entry_path.insert(0, path_val)
        entry_path.pack(side="left", padx=4)

        lbl_eq2 = ttk.Label(row_frame, text="=", font=("Consolas", 10, "bold"))
        lbl_eq2.pack(side="left", padx=2)

        entry_value = ttk.Entry(row_frame, width=12)
        if value_val:
            entry_value.insert(0, value_val)
        entry_value.pack(side="left", padx=4)

        btn_single_test = ttk.Button(row_frame, text="✔️", width=3, command=lambda: self.run_single_test_rule(entry_path, entry_value))
        btn_single_test.pack(side="left", padx=(10, 2))

        btn_del = ttk.Button(row_frame, text="✖", width=3, command=lambda: self.remove_cheat_row(row_frame, entry_name))
        btn_del.pack(side="left", padx=(2, 0))

        self.cheat_rows.append({'frame': row_frame, 'name': entry_name, 'path': entry_path, 'value': entry_value})

    def move_cheat_row(self, row_frame, direction):
        idx = next((i for i, item in enumerate(self.cheat_rows) if item['frame'] == row_frame), None)
        if idx is None:
            return

        new_idx = idx + direction
        if 0 <= new_idx < len(self.cheat_rows):
            self.cheat_rows[idx], self.cheat_rows[new_idx] = self.cheat_rows[new_idx], self.cheat_rows[idx]
            for item in self.cheat_rows:
                item['frame'].pack_forget()
                item['frame'].pack(fill="x", pady=2)

    def remove_cheat_row(self, row_frame, entry_name):
        if len(self.cheat_rows) > 1:
            self.cheat_rows = [item for item in self.cheat_rows if item['name'] != entry_name]
            row_frame.destroy()
        else:
            for item in self.cheat_rows:
                if item['name'] == entry_name:
                    item['name'].delete(0, tk.END)
                    item['path'].delete(0, tk.END)
                    item['value'].delete(0, tk.END)

    def _build_console_output(self, parent):
        self.frame_console = ttk.LabelFrame(parent)
        self.frame_console.pack(fill="both", expand=True, padx=5, pady=4)

        self.console = scrolledtext.ScrolledText(self.frame_console, bg="black", fg="#00FF00", font=("Consolas", 9))
        self.console.pack(fill="both", expand=True, padx=5, pady=5)

        console_toolbar = ttk.Frame(self.frame_console)
        console_toolbar.pack(fill="x", padx=5, pady=(0, 5))

        self.btn_export_console = ttk.Button(console_toolbar, command=self.export_console_log)
        self.btn_export_console.pack(side="right", padx=5)

        self.btn_clear_console = ttk.Button(console_toolbar, command=lambda: self.console.delete("1.0", tk.END))
        self.btn_clear_console.pack(side="right", padx=5)

    def _build_finder_section(self, parent):
        self.frame_finder = ttk.LabelFrame(parent)
        self.frame_finder.pack(fill="both", expand=True, padx=5, pady=4)

        self.lbl_keyword = ttk.Label(self.frame_finder)
        self.lbl_keyword.pack(anchor="w", padx=10, pady=(10, 2))

        keyword_frame = ttk.Frame(self.frame_finder)
        keyword_frame.pack(fill="x", padx=10, pady=2)

        self.entry_keyword = ttk.Entry(keyword_frame)
        self.entry_keyword.insert(0, "Health")
        self.entry_keyword.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.entry_keyword.bind("<Return>", lambda event: self.open_find_paths_dialog())

        self.btn_search = ttk.Button(keyword_frame, command=self.search_sdk_keyword)
        self.btn_search.pack(side="right")

        self.btn_find_addr = ttk.Button(keyword_frame, command=self.open_find_addr_dialog)
        self.btn_find_addr.pack(side="right", padx=(0, 4))

        self.btn_find_paths = ttk.Button(keyword_frame, command=self.open_find_paths_dialog)
        self.btn_find_paths.pack(side="right", padx=(0, 4))

        res_header_frame = ttk.Frame(self.frame_finder)
        res_header_frame.pack(fill="x", padx=10, pady=(10, 2))

        self.lbl_res = ttk.Label(res_header_frame, font=("Arial", 9, "bold"))
        self.lbl_res.pack(side="left")

        self.lbl_res_count = ttk.Label(res_header_frame, text="Results: 0", font=("Arial", 9, "bold"), foreground="blue")
        self.lbl_res_count.pack(side="left", padx=10)

        self.btn_export_finder = ttk.Button(res_header_frame, command=self.export_finder_results)
        self.btn_export_finder.pack(side="right")

        self.btn_clear_finder = ttk.Button(res_header_frame, command=lambda: self.clear_finder_results())
        self.btn_clear_finder.pack(side="right", padx=5)

        self.finder_results = scrolledtext.ScrolledText(
            self.frame_finder, bg="#1e1e1e", fg="#dcdcdc", font=("Consolas", 9), wrap=tk.WORD
        )
        self.finder_results.pack(fill="both", expand=True, padx=10, pady=5)
        
        self.finder_results.bind("<Button-3>", self.show_finder_context_menu)

        self.finder_results.tag_config("header", foreground="#00FFFF", font=("Consolas", 9, "bold"))
        self.finder_results.tag_config("keyword_var", foreground="#FFFF00", font=("Consolas", 10, "bold"))
        self.finder_results.tag_config("type_info", foreground="#888888")
        self.finder_results.tag_config("footer", foreground="#00FF00", font=("Consolas", 9, "italic"))
        self.finder_results.tag_config("highlight", background="#FF00FF", foreground="#FFFFFF")

    def clear_finder_results(self):
        self.finder_results.delete("1.0", tk.END)
        self.lbl_res_count.config(text="Results: 0")

    def show_finder_context_menu(self, event):
        try:
            index = self.finder_results.index(f"@{event.x},{event.y}")
            line_start = f"{index} linestart"
            line_end = f"{index} lineend"
            line_text = self.finder_results.get(line_start, line_end).strip()

            if not line_text or line_text.startswith("-") or "paths for" in line_text or "Searching" in line_text:
                return

            parts = line_text.split("\t")
            target_path = parts[0].strip()
            
            if not target_path or "::" not in target_path:
                return

            menu = tk.Menu(self.root, tearoff=0)
            menu.add_command(
                label=f"⚡ Live Edit (il2live.py): {target_path}", 
                command=lambda: self.prompt_and_send_illive(target_path)
            )
            menu.tk_popup(event.x_root, event.y_root)
        except Exception as e:
            print(f"Menu error: {e}")

    def prompt_and_send_illive(self, path):
        t = TRANSLATIONS[self.current_lang]
        messagebox.showwarning(t["live_warn_title"], t["live_warn_msg"], parent=self.root)

        ip = self.entry_ip.get().strip()
        if not ip or ip == "192.168.1.XXX":
            messagebox.showwarning("Warning", t["warn_ip"])
            return

        dump_path = self.entry_dump_path.get().strip()
        if not dump_path:
            messagebox.showwarning("Warning", t["warn_select_session_first"])
            return

        new_value = simpledialog.askstring(
            "IL2CPP Live Editor (il2live.py)", 
            f"Ruta seleccionada:\n{path}\n\nIntroduce el nuevo valor para modificar en vivo:", 
            parent=self.root
        )
        
        if new_value is not None and new_value.strip() != "":
            self.execute_il2live_command(dump_path, ip, path, new_value.strip())

    def execute_il2live_command(self, dump_path, ip, path, value):
        self.log(f"\n[LIVE EDIT] il2live.py -> IP: {ip} | {path} = {value}")
        abs_dump_dir = os.path.abspath(os.path.join(TOOLS_DIR, dump_path))
        script_path = os.path.join(TOOLS_DIR, "il2live.py")
        args = [script_path, abs_dump_dir, path, "--host", ip, "--set", value]
        self.execute_command_in_thread(args, is_dump=False)

    def run_single_test_rule(self, entry_path_widget, entry_val_widget):
        t = TRANSLATIONS[self.current_lang]
        messagebox.showwarning(t["live_warn_title"], t["live_warn_msg"], parent=self.root)

        ip = self.entry_ip.get().strip()
        if not ip or ip == "192.168.1.XXX":
            messagebox.showwarning("Warning", t["warn_ip"])
            return

        dump_path = self.entry_dump_path.get().strip()
        if not dump_path:
            messagebox.showwarning("Warning", t["warn_select_session_first"])
            return

        p = entry_path_widget.get().strip()
        v = entry_val_widget.get().strip()
        if not p or not v:
            return

        abs_dump_dir = os.path.abspath(os.path.join(TOOLS_DIR, dump_path))
        script_path = os.path.join(TOOLS_DIR, "il2live.py")

        def single_thread():
            self.log(f"\n[SINGLE TEST] il2live.py -> {p} = {v}")
            args = [script_path, abs_dump_dir, p, "--host", ip, "--set", v]
            try:
                res = subprocess.run([sys.executable, "-u"] + args, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=TOOLS_DIR)
                if res.stdout:
                    self.log(res.stdout.strip())
                if res.stderr:
                    self.log(res.stderr.strip())
            except Exception as e:
                self.log(f"[ERROR] {e}")
            self.root.after(0, lambda: messagebox.showinfo("Test", "Test Done"))

        threading.Thread(target=single_thread, daemon=True).start()

    def run_test_rules(self):
        t = TRANSLATIONS[self.current_lang]
        messagebox.showwarning(t["live_warn_title"], t["live_warn_msg"], parent=self.root)

        ip = self.entry_ip.get().strip()
        if not ip or ip == "192.168.1.XXX":
            messagebox.showwarning("Warning", t["warn_ip"])
            return

        dump_path = self.entry_dump_path.get().strip()
        if not dump_path:
            messagebox.showwarning("Warning", t["warn_select_session_first"])
            return

        rules_to_test = [(item['path'].get().strip(), item['value'].get().strip()) for item in self.cheat_rows if item['path'].get().strip() and item['value'].get().strip()]
        if not rules_to_test:
            return

        abs_dump_dir = os.path.abspath(os.path.join(TOOLS_DIR, dump_path))
        script_path = os.path.join(TOOLS_DIR, "il2live.py")

        def test_thread():
            for path, val in rules_to_test:
                self.log(f"\n[TEST ALL LIVE EDIT] -> {path} = {val}")
                args = [script_path, abs_dump_dir, path, "--host", ip, "--set", val]
                try:
                    subprocess.run([sys.executable, "-u"] + args, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=TOOLS_DIR)
                except Exception as e:
                    self.log(f"[ERROR] {e}")
                time.sleep(0.5)
            self.root.after(0, lambda: messagebox.showinfo("Test All", "Test Done"))

        threading.Thread(target=test_thread, daemon=True).start()

    def export_console_log(self):
        content = self.console.get("1.0", tk.END).strip()
        if not content:
            return
        file_path = filedialog.asksaveasfilename(defaultextension=".txt", initialfile="console_log.txt")
        if file_path:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

    def export_finder_results(self):
        content = self.finder_results.get("1.0", tk.END).strip()
        if not content:
            return
        file_path = filedialog.asksaveasfilename(defaultextension=".txt", initialfile="finder_results.txt")
        if file_path:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

    def open_quick_find_dialog(self, event=None):
        t = TRANSLATIONS[self.current_lang]
        if self.find_win and self.find_win.winfo_exists():
            self.find_win.lift()
            return "break"

        self.find_win = tk.Toplevel(self.root)
        self.find_win.title(t["find_dialog_title"])
        self.find_win.geometry("420x130")
        self.find_win.resizable(False, False)
        self.center_window(self.find_win, 420, 130)

        lbl = ttk.Label(self.find_win, text=t["find_label"], font=("Arial", 9, "bold"))
        lbl.pack(padx=10, pady=(10, 2), anchor="w")

        entry_find = ttk.Entry(self.find_win, width=48)
        entry_find.pack(padx=10, pady=2)
        entry_find.focus()

        lbl_count = ttk.Label(self.find_win, text=f"{t['find_matches']} 0/0", font=("Arial", 8, "italic"), foreground="gray")
        lbl_count.pack(padx=10, anchor="w")

        self.search_matches = []
        self.current_match_idx = -1

        def update_search():
            query = entry_find.get().strip().lower()
            self.finder_results.tag_remove("highlight", "1.0", tk.END)
            self.search_matches.clear()
            self.current_match_idx = -1

            if not query:
                lbl_count.config(text=f"{t['find_matches']} 0/0")
                return

            idx = "1.0"
            while True:
                idx = self.finder_results.search(query, idx, nocase=1, stopindex=tk.END)
                if not idx:
                    break
                end_idx = f"{idx}+{len(query)}c"
                self.search_matches.append((idx, end_idx))
                idx = end_idx

            if self.search_matches:
                self.current_match_idx = 0
                goto_current_match()

        def goto_current_match():
            if not self.search_matches:
                return
            self.finder_results.tag_remove("highlight", "1.0", tk.END)
            start, end = self.search_matches[self.current_match_idx]
            self.finder_results.tag_add("highlight", start, end)
            self.finder_results.see(start)
            lbl_count.config(text=f"{t['find_matches']} {self.current_match_idx + 1}/{len(self.search_matches)}")

        def next_match():
            if self.search_matches:
                self.current_match_idx = (self.current_match_idx + 1) % len(self.search_matches)
                goto_current_match()

        def prev_match():
            if self.search_matches:
                self.current_match_idx = (self.current_match_idx - 1) % len(self.search_matches)
                goto_current_match()

        entry_find.bind("<KeyRelease>", lambda e: update_search())
        btn_frame = ttk.Frame(self.find_win)
        btn_frame.pack(padx=10, pady=6, fill="x")
        ttk.Button(btn_frame, text=t["find_back"], command=prev_match, width=12).pack(side="left", padx=2)
        ttk.Button(btn_frame, text=t["find_next"], command=next_match, width=12).pack(side="left", padx=2)
        entry_find.bind("<Return>", lambda e: next_match())
        return "break"

    def process_dump_metadata(self, dump_folder_path, force_online=False):
        if not dump_folder_path:
            return
        abs_dump_dir = os.path.abspath(os.path.join(TOOLS_DIR, dump_folder_path))
        folder_name = os.path.basename(abs_dump_dir)
        title_id_match = re.search(r"([A-Z]{4}\d{5})", folder_name)
        self.current_game_key = title_id_match.group(1) if title_id_match else folder_name
        self.lbl_game_info.config(text=f"🎮 [{self.current_game_key}]")
        self.load_rules_for_current_game()

    def update_dump_path_ui(self, rel_path):
        self.entry_dump_path.config(state="normal")
        self.entry_dump_path.delete(0, tk.END)
        self.entry_dump_path.insert(0, rel_path)
        self.entry_dump_path.config(state="readonly")

    def load_rules_for_current_game(self):
        for row in self.cheat_rows:
            row['frame'].destroy()
        self.cheat_rows.clear()
        rules = self.config.get("games_cheats", {}).get(self.current_game_key, [])
        if rules:
            for item in rules:
                self.add_cheat_row(item.get("name", ""), item.get("path", ""), item.get("value", ""))
        else:
            self.add_cheat_row("", "", "")

    def get_auto_sdk_dir(self):
        dump_path = self.entry_dump_path.get().strip()
        if not dump_path:
            return None
        abs_dump_dir = os.path.abspath(os.path.join(TOOLS_DIR, dump_path))
        candidate_sdk = os.path.join(abs_dump_dir, "sdk")
        return candidate_sdk if os.path.exists(candidate_sdk) else abs_dump_dir

    def open_in_notepad(self, file_path, line_num):
        try:
            for npp in ["notepad++", r"C:\Program Files\Notepad++\notepad++.exe", r"C:\Program Files (x86)\Notepad++\notepad++.exe"]:
                try:
                    subprocess.Popen([npp, f"-n{line_num}", file_path])
                    return
                except Exception:
                    continue
            os.startfile(file_path)
        except Exception:
            pass

    def search_sdk_keyword(self):
        t = TRANSLATIONS[self.current_lang]
        dump_path = self.entry_dump_path.get().strip()
        if not dump_path:
            messagebox.showwarning("Warning", t["warn_finder"])
            return

        abs_dump_dir = os.path.abspath(os.path.join(TOOLS_DIR, dump_path))
        
        dump_file = os.path.join(abs_dump_dir, "dump.cs")
        if not os.path.exists(dump_file):
            dump_file = os.path.join(abs_dump_dir, "sdk", "dump.cs")

        keyword_raw = self.entry_keyword.get().strip()
        if not os.path.exists(dump_file) or not keyword_raw:
            messagebox.showwarning("Warning", "No se encuentra el archivo 'dump.cs'. Asegúrate de que el dumper lo haya generado.")
            return

        self.finder_results.delete("1.0", tk.END)
        found_count = 0
        keyword_lower = keyword_raw.lower()

        try:
            with open(dump_file, "r", encoding="utf-8", errors="ignore") as f:
                for line_num, line in enumerate(f, 1):
                    if keyword_lower in line.lower():
                        clean_line = line.strip()
                        if clean_line:
                            found_count += 1
                            link_tag = f"link_{found_count}"
                            self.finder_results.tag_config(link_tag, foreground="#00FFFF", underline=True)
                            self.finder_results.tag_bind(link_tag, "<Button-1>", lambda e, fp=dump_file, ln=line_num: self.open_in_notepad(fp, ln))
                            self.finder_results.insert(tk.END, f"[dump.cs:{line_num}] {clean_line}\n", link_tag)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo leer el archivo dump.cs: {e}")

        self.lbl_res_count.config(text=f"Results: {found_count}")

    def open_find_paths_dialog(self):
        t = TRANSLATIONS[self.current_lang]
        dialog = tk.Toplevel(self.root)
        dialog.title("Advanced Find Paths Settings (--find)")
        dialog.geometry("420x330")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        self.center_window(dialog, 420, 330)

        lbl_depth = ttk.Label(dialog, text="Hops (--depth):", font=("Arial", 9, "bold"))
        lbl_depth.pack(padx=15, pady=(15, 2), anchor="w")
        entry_depth = ttk.Entry(dialog, width=20)
        entry_depth.insert(0, self.config.get("find_depth", "6"))
        entry_depth.pack(padx=15, pady=2, anchor="w")

        lbl_types = ttk.Label(dialog, text="Types (--types):", font=("Arial", 9, "bold"))
        lbl_types.pack(padx=15, pady=(10, 2), anchor="w")
        combo_types = ttk.Combobox(dialog, values=["", "int", "float", "double", "all"], state="readonly", width=25)
        combo_types.set(self.config.get("find_types", ""))
        combo_types.pack(padx=15, pady=2, anchor="w")

        var_objects = tk.BooleanVar(value=self.config.get("find_objects", False))
        chk_objects = ttk.Checkbutton(dialog, text="Include Objects (--objects)", variable=var_objects)
        chk_objects.pack(padx=15, pady=(10, 2), anchor="w")

        var_fields = tk.BooleanVar(value=self.config.get("find_fields", False))
        chk_fields = ttk.Checkbutton(dialog, text="List Object Fields (--fields)", variable=var_fields)
        chk_fields.pack(padx=15, pady=(5, 10), anchor="w")

        def on_accept():
            depth = entry_depth.get().strip() or "6"
            types_val = combo_types.get().strip()
            include_objects = var_objects.get()
            include_fields = var_fields.get()

            self.config["find_depth"] = depth
            self.config["find_types"] = types_val
            self.config["find_objects"] = include_objects
            self.config["find_fields"] = include_fields
            self.save_config()

            dialog.destroy()
            self.execute_find_paths(depth, types_val, include_objects, include_fields)

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(padx=15, pady=10, fill="x")
        ttk.Button(btn_frame, text="Accept", command=on_accept).pack(side="right", padx=5)
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side="right")

    def execute_find_paths(self, depth, types_val, include_objects, include_fields):
        dump_path = self.entry_dump_path.get().strip()
        keyword = self.entry_keyword.get().strip()
        if not dump_path or not keyword:
            messagebox.showwarning("Warning", TRANSLATIONS[self.current_lang]["warn_find_paths"])
            return
        
        abs_dump_dir = os.path.abspath(os.path.join(TOOLS_DIR, dump_path))
        self.finder_results.delete("1.0", tk.END)
        script_path = os.path.join(TOOLS_DIR, "il2live.py")
        
        if types_val == "all":
            types_val = "int,float,double"

        if include_fields:
            args = [script_path, abs_dump_dir, keyword, "--fields"]
            if depth and depth != "6":
                args.extend(["--depth", depth])
        else:
            args = [script_path, abs_dump_dir, "--find", keyword, "--depth", depth]
            if types_val and types_val != "":
                args.extend(["--types", types_val])
            if include_objects:
                args.append("--objects")

        self.log(f"\n> Running: {subprocess.list2cmdline([sys.executable, '-u'] + args)}")

        if self.progress_win and self.progress_win.winfo_exists():
            self.progress_win.destroy()

        self.progress_win = tk.Toplevel(self.root)
        self.progress_win.title("Buscando rutas...")
        self.progress_win.geometry("380x150")
        self.progress_win.resizable(False, False)
        self.progress_win.transient(self.root)
        self.progress_win.grab_set()
        self.center_window(self.progress_win, 380, 150)

        lbl_msg = ttk.Label(self.progress_win, text=f"Buscando: '{keyword}' (Hops: {depth})", font=("Arial", 10, "bold"))
        lbl_msg.pack(padx=15, pady=(15, 5), anchor="w")

        lbl_timer = ttk.Label(self.progress_win, text="Tiempo transcurrido: 00:00", font=("Arial", 9, "italic"), foreground="blue")
        lbl_timer.pack(padx=15, pady=5, anchor="w")

        start_time_find = time.time()
        active_search = {"running": True}

        def update_find_timer():
            if active_search["running"] and self.progress_win and self.progress_win.winfo_exists():
                el = int(time.time() - start_time_find)
                m, s = divmod(el, 60)
                lbl_timer.config(text=f"Tiempo transcurrido: {m:02d}:{s:02d}")
                self.progress_win.after(1000, update_find_timer)

        update_find_timer()

        def cancel_find_process():
            active_search["running"] = False
            if self.find_proc and self.find_proc.poll() is None:
                try:
                    self.find_proc.kill()
                except Exception:
                    pass
            if self.progress_win and self.progress_win.winfo_exists():
                self.progress_win.destroy()
            self.log("[!] Búsqueda cancelada por el usuario.")

        btn_cancel_find = ttk.Button(self.progress_win, text="Cancelar", command=cancel_find_process)
        btn_cancel_find.pack(padx=15, pady=(10, 15), ipadx=10)

        def task():
            try:
                self.find_proc = subprocess.Popen([sys.executable, "-u"] + args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", cwd=TOOLS_DIR)
                out_lines = []
                for line in self.find_proc.stdout:
                    if not active_search["running"]:
                        break
                    out_lines.append(line)
                
                if active_search["running"]:
                    self.find_proc.wait()
                    full_output = "".join(out_lines)
                    self.events.put(("paths", (keyword, full_output)))
            except Exception as e:
                self.events.put(("log", f"[ERROR Find Paths] {e}"))
            
            if self.progress_win and self.progress_win.winfo_exists():
                self.progress_win.destroy()

        threading.Thread(target=task, daemon=True).start()

    def open_find_addr_dialog(self):
        t = TRANSLATIONS[self.current_lang]
        dialog = tk.Toplevel(self.root)
        dialog.title("Advanced Find Paths (By Address) Settings")
        dialog.geometry("400x180")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        self.center_window(dialog, 400, 180)

        lbl_depth = ttk.Label(dialog, text="Hops (--depth):", font=("Arial", 9, "bold"))
        lbl_depth.pack(padx=15, pady=(15, 2), anchor="w")
        entry_depth = ttk.Entry(dialog, width=20)
        entry_depth.insert(0, "6")
        entry_depth.pack(padx=15, pady=2, anchor="w")

        lbl_parents = ttk.Label(dialog, text="Parents (--parents):", font=("Arial", 9, "bold"))
        lbl_parents.pack(padx=15, pady=(10, 2), anchor="w")
        entry_parents = ttk.Entry(dialog, width=20)
        entry_parents.insert(0, "30")
        entry_parents.pack(padx=15, pady=2, anchor="w")

        def on_accept():
            depth = entry_depth.get().strip() or "6"
            parents = entry_parents.get().strip() or "30"
            dialog.destroy()
            self.execute_find_addr(depth, parents)

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(padx=15, pady=10, fill="x")
        ttk.Button(btn_frame, text="Accept", command=on_accept).pack(side="right", padx=5)
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side="right")

    def execute_find_addr(self, depth, parents):
        t = TRANSLATIONS[self.current_lang]
        dump_path = self.entry_dump_path.get().strip()
        address_str = self.entry_keyword.get().strip()
        
        if not dump_path or not address_str:
            messagebox.showwarning("Warning", t["warn_enter_addr"])
            return
        
        abs_dump_dir = os.path.abspath(os.path.join(TOOLS_DIR, dump_path))
        
        json_file = None
        for f in os.listdir(abs_dump_dir):
            if f.endswith(".json") and f != "dump.cs.klasses.json":
                if f == "dump.json":
                    json_file = f
                    break
                elif not json_file:
                    json_file = f
                
        if not json_file:
            messagebox.showwarning("Warning", t["warn_no_json_dump"])
            return

        self.finder_results.delete("1.0", tk.END)
        self.finder_results.insert(tk.END, f"Buscando rutas hacia la dirección {address_str} (Hops: {depth}, Parents: {parents}) usando {json_file}...\n", "type_info")
        
        script_path = os.path.join(TOOLS_DIR, "il2diff.py")
        args = [script_path, abs_dump_dir, json_file, "--addr", address_str, "--depth", depth, "--parents", parents]

        self.log(f"\n> Running: {subprocess.list2cmdline([sys.executable, '-u'] + args)}")

        def task():
            try:
                proc = subprocess.run([sys.executable, "-u"] + args, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=TOOLS_DIR)
                output = proc.stdout + proc.stderr
                self.events.put(("paths", (address_str, output)))
            except Exception as e:
                self.events.put(("log", f"[ERROR Find By Address] {e}"))

        threading.Thread(target=task, daemon=True).start()

    def trigger_field_expansion(self, new_path):
        self.entry_keyword.delete(0, tk.END)
        self.entry_keyword.insert(0, new_path)
        depth = self.config.get("find_depth", "6")
        self.execute_find_paths(depth=depth, types_val="", include_objects=False, include_fields=True)

    def get_parent_path(self, p):
        last_dot = p.rfind('.')
        last_bracket = p.rfind('[')
        last_brace = p.rfind('{')
        idx = max(last_dot, last_bracket, last_brace)
        if idx != -1:
            return p[:idx]
        return None

    def show_paths(self, keyword, output):
        self.finder_results.delete("1.0", tk.END)
        found = 0
        base_path = keyword if "::" in keyword else ""

        parent_path = self.get_parent_path(base_path) if base_path else None
        if parent_path:
            back_tag = "back_link"
            self.finder_results.tag_config(back_tag, foreground="#FF5555", font=("Consolas", 9, "bold"), underline=True)
            self.finder_results.tag_bind(back_tag, "<Button-1>", lambda e, p=parent_path: self.trigger_field_expansion(p))
            self.finder_results.tag_bind(back_tag, "<Enter>", lambda e, w=self.finder_results: w.config(cursor="hand2"))
            self.finder_results.tag_bind(back_tag, "<Leave>", lambda e, w=self.finder_results: w.config(cursor=""))
            self.finder_results.insert(tk.END, f"🔙 [Back to: {parent_path}]\n\n", back_tag)
            found += 1

        for line in output.splitlines():
            clean_line = line.strip()
            if not clean_line:
                continue

            if clean_line.startswith(".") and base_path:
                found += 1
                tag = f"path_{found}"
                parts_line = clean_line.split()
                field_name = parts_line[0]
                next_path = f"{base_path}{field_name}"

                is_primitive = False
                type_name = ""
                for part in parts_line:
                    if part.startswith("(") and part.endswith(")"):
                        type_name = part[1:-1]
                        break
                
                prim_types = {"bool", "sbyte", "byte", "short", "ushort", "int", "uint", "long", "ulong", "float", "double", "char", "IntPtr", "UIntPtr"}
                if type_name in prim_types:
                    is_primitive = True

                self.finder_results.tag_config(tag, foreground="#00FFFF" if not is_primitive else "#FFD700", underline=True)
                
                if is_primitive:
                    item_dict = {
                        "name": field_name.lstrip("."),
                        "path": next_path,
                        "value": parts_line[-1] if "=" in clean_line else "0"
                    }
                    self.finder_results.tag_bind(tag, "<Button-1>", lambda e, i=item_dict: self.add_suggestion_to_rules(i))
                else:
                    self.finder_results.tag_bind(tag, "<Button-1>", lambda e, p=next_path: self.trigger_field_expansion(p))

                self.finder_results.tag_bind(tag, "<Enter>", lambda e, w=self.finder_results: w.config(cursor="hand2"))
                self.finder_results.tag_bind(tag, "<Leave>", lambda e, w=self.finder_results: w.config(cursor=""))

                self.finder_results.insert(tk.END, "  " + field_name, tag)
                self.finder_results.insert(tk.END, clean_line[len(field_name):] + "\n", "type_info")
            else:
                parts = line.split("\t")
                if len(parts) < 3:
                    self.finder_results.insert(tk.END, line + "\n", "type_info")
                    continue
                path, ftype, val = parts[0], parts[1], parts[2]
                found += 1
                tag = f"path_{found}"
                self.finder_results.tag_config(tag, foreground="#00FFFF", underline=True)
                
                item_dict = {
                    "name": path.split("::")[-1].split(".")[0],
                    "path": path,
                    "value": val
                }
                self.finder_results.tag_bind(tag, "<Button-1>", lambda e, i=item_dict: self.add_suggestion_to_rules(i))
                self.finder_results.tag_bind(tag, "<Enter>", lambda e, w=self.finder_results: w.config(cursor="hand2"))
                self.finder_results.tag_bind(tag, "<Leave>", lambda e, w=self.finder_results: w.config(cursor=""))

                self.finder_results.insert(tk.END, path, tag)
                self.finder_results.insert(tk.END, f"    ({ftype}) = {val}\n", "type_info")

        self.lbl_res_count.config(text=f"Results: {found}")

    def apply_saved_config(self):
        saved_lang = self.config.get("language", "English")
        if saved_lang in TRANSLATIONS:
            self.current_lang = saved_lang
            self.combo_lang.set(saved_lang)
        self.entry_ip.delete(0, tk.END)
        self.entry_ip.insert(0, self.config.get("ip", "192.168.1.XXX"))
        saved_dump_path = self.config.get("dump_path", "")
        self.update_dump_path_ui(saved_dump_path)
        if saved_dump_path:
            self.process_dump_metadata(saved_dump_path)
        else:
            self.load_rules_for_current_game()
        self.update_language()

    def on_language_change(self, event):
        self.current_lang = self.combo_lang.get()
        self.update_language()

    def update_language(self):
        t = TRANSLATIONS[self.current_lang]
        self.root.title(t["title"])
        self.lbl_lang.config(text=t["lbl_language"])
        self.frame_dumper.config(text=t["frame_dumper"])
        self.frame_cheat.config(text=t["frame_cheat"])
        self.frame_console.config(text=t["frame_console"])
        self.frame_finder.config(text=t["frame_finder"])
        self.lbl_ip.config(text=t["lbl_ip"])
        self.btn_new.config(text=t["btn_new"])
        self.btn_load.config(text=t["btn_load"])
        self.btn_ps4dump.config(text=t["btn_ps4dump"])
        self.btn_il2mem.config(text=t["btn_il2mem"])
        self.btn_get_name.config(text=t["btn_get_name"])
        self.btn_open_diff.config(text=t["btn_open_diff"])
        self.lbl_dump_file.config(text=t["lbl_dump_file"])
        self.lbl_cheat_cmd.config(text=t["lbl_cheat_cmd"])
        self.btn_add_cheat.config(text=t["btn_add_cheat"])
        self.btn_suggestions.config(text=t["btn_suggestions"])
        self.btn_export_rules.config(text=t["btn_export_rules"])
        self.btn_import_rules.config(text=t["btn_import_rules"])
        self.btn_cheat.config(text=t["btn_cheat"])
        self.btn_test.config(text=t["btn_test_all"])
        self.btn_export_console.config(text=t["btn_export_console"])
        self.btn_clear_console.config(text=t["btn_clear_console"])
        self.btn_export_finder.config(text=t["btn_export_finder"])
        self.btn_clear_finder.config(text=t["btn_clear_finder"])
        self.lbl_th_name.config(text=t["th_name"])
        self.lbl_th_path.config(text=t["th_path"])
        self.lbl_th_value.config(text=t["th_value"])
        self.lbl_th_test.config(text=t["th_test"])
        self.lbl_keyword.config(text=t["lbl_keyword"])
        self.btn_search.config(text=t["btn_search"])
        self.btn_find_paths.config(text=t["btn_find_paths"])
        self.btn_find_addr.config(text=t["btn_find_addr"])
        self.lbl_res.config(text=t["lbl_results_hdr"])

    def log(self, text):
        self.console.insert(tk.END, text + "\n")
        self.console.see(tk.END)

    def execute_command_in_thread(self, args, is_dump=True):
        if self.is_running:
            return
        self.is_running = True
        self.start_time = time.time()
        
        full_cmd = [sys.executable, "-u"] + args
        self.log(f"\n> Running: {subprocess.list2cmdline(full_cmd)}")
        env = dict(os.environ, PYTHONIOENCODING="utf-8")

        def task():
            errors_captured = []
            try:
                process = subprocess.Popen(full_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", cwd=TOOLS_DIR, env=env)
                for line in process.stdout:
                    self.events.put(("log", line.rstrip()))
                success = (process.wait() == 0)
            except Exception as e:
                self.events.put(("log", f"[ERROR] {e}"))
                success = False
            self.events.put(("done", (success, is_dump, errors_captured)))

        threading.Thread(target=task, daemon=True).start()

    def run_ps4dump(self):
        t = TRANSLATIONS[self.current_lang]
        ip = self.entry_ip.get().strip()
        if not ip or ip == "192.168.1.XXX":
            messagebox.showwarning("Warning", t["warn_ip"])
            return

        dump_path = self.entry_dump_path.get().strip()
        if not dump_path:
            folder_name = simpledialog.askstring("Session Folder", t["dlg_session_dir_title"], parent=self.root)
            if not folder_name:
                return
            dump_path = os.path.relpath(os.path.join(DUMPS_DIR, folder_name), TOOLS_DIR)
            self.update_dump_path_ui(dump_path)

        abs_dump_dir = os.path.abspath(os.path.join(TOOLS_DIR, dump_path))
        os.makedirs(abs_dump_dir, exist_ok=True)
        self.save_config()

        script_path = os.path.join(TOOLS_DIR, "ps4dump.py")
        if not os.path.exists(script_path):
            messagebox.showerror("Error", f"No se encuentra 'ps4dump.py' en la carpeta tools:\n{script_path}")
            return

        out_base = os.path.join(abs_dump_dir, "dump")
        self.execute_command_in_thread([script_path, "--host", ip, "-o", out_base], is_dump=True)

    def run_il2mem(self):
        t = TRANSLATIONS[self.current_lang]
        dump_path = self.entry_dump_path.get().strip()
        if not dump_path:
            messagebox.showwarning("Warning", t["warn_select_session_first"])
            return

        messagebox.showinfo(
            t["dlg_sdk_notice_title"], 
            t["dlg_sdk_notice_msg"],
            parent=self.root
        )

        abs_dump_dir = os.path.abspath(os.path.join(TOOLS_DIR, dump_path))
        script_path = os.path.join(TOOLS_DIR, "il2mem.py")
        dumper_exe = os.path.join(TOOLS_DIR, "Il2CppDumper.exe")

        if not os.path.exists(script_path):
            messagebox.showerror("Error", f"No se encuentra 'il2mem.py' en la carpeta tools:\n{script_path}")
            return

        self.save_config()

        if self.is_running:
            return
        self.is_running = True
        self.start_time = time.time()

        def task():
            env = dict(os.environ, PYTHONIOENCODING="utf-8")
            errors_captured = []

            elf_file = os.path.join(abs_dump_dir, "Il2CppUserAssemblies.prx.elf")
            meta_file = os.path.join(abs_dump_dir, "global-metadata.dat")

            files_exist = os.path.exists(elf_file) and os.path.exists(meta_file)

            if files_exist:
                self.events.put(("log", "\n[INFO] Los archivos ya existen. Omitiendo Paso 1 (il2mem)..."))
                p1_success = True
            else:
                cmd_il2mem = [sys.executable, "-u", script_path, abs_dump_dir]
                self.events.put(("log", f"\n> Running Step 1 (il2mem): {subprocess.list2cmdline(cmd_il2mem)}"))
                
                p1_success = False
                try:
                    p1 = subprocess.Popen(cmd_il2mem, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", cwd=TOOLS_DIR, env=env)
                    for line in p1.stdout:
                        self.events.put(("log", line.rstrip()))
                    p1_success = (p1.wait() == 0)
                except Exception as e:
                    self.events.put(("log", f"[ERROR Step 1] {e}"))

            if not p1_success:
                self.events.put(("done", (False, True, ["il2mem.py falló."])))
                return

            sdk_dir = os.path.join(abs_dump_dir, "sdk")

            if not os.path.exists(elf_file) or not os.path.exists(meta_file):
                self.events.put(("log", f"[WARNING] No se encontraron archivos ELF o metadata."))
                self.events.put(("done", (True, True, [])))
                return

            if not os.path.exists(dumper_exe):
                self.events.put(("log", f"[WARNING] No se encontró Il2CppDumper.exe."))
                self.events.put(("done", (True, True, [])))
                return

            os.makedirs(sdk_dir, exist_ok=True)
            cmd_dumper = [dumper_exe, elf_file, meta_file, sdk_dir]
            self.events.put(("log", f"\n> Running Step 2 (Il2CppDumper): {subprocess.list2cmdline(cmd_dumper)}"))

            p2_success = False
            try:
                p2 = subprocess.Popen(cmd_dumper, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", cwd=TOOLS_DIR, env=env)
                stdout, _ = p2.communicate(input="0\n")
                for line in stdout.splitlines():
                    self.events.put(("log", line))
                p2_success = (p2.returncode == 0)
            except Exception as e:
                self.events.put(("log", f"[ERROR Step 2] {e}"))

            self.events.put(("done", (p2_success, True, errors_captured)))

        threading.Thread(target=task, daemon=True).start()

    def run_cheat(self):
        t = TRANSLATIONS[self.current_lang]
        dump_path = self.entry_dump_path.get().strip()
        cheat_rules = [f"{item['name'].get().strip()}={item['path'].get().strip()}={item['value'].get().strip()}" for item in self.cheat_rows if item['name'].get().strip() and item['path'].get().strip() and item['value'].get().strip()]

        if not dump_path or not cheat_rules:
            messagebox.showwarning("Warning", t["warn_fields"])
            return

        creator_name = simpledialog.askstring("Creator Name", "Introduce el nombre del Creador del Trainer:", initialvalue="talixme", parent=self.root)
        if creator_name is None:
            return
        creator_name = creator_name.strip() or "il2cheat"

        abs_dump_dir = os.path.abspath(os.path.join(TOOLS_DIR, dump_path))
        folder_name = os.path.basename(abs_dump_dir)
        initial_filename = f"{folder_name}.TLH" if folder_name else f"{self.current_game_key}.TLH"

        save_path = filedialog.asksaveasfilename(
            title=t["dlg_save_tlh_title"], 
            initialdir=CHEATS_DIR, 
            defaultextension=".TLH", 
            filetypes=[("TLH files", "*.TLH")], 
            initialfile=initial_filename, 
            parent=self.root
        )
        if not save_path:
            return

        target_tlh_path = os.path.relpath(save_path, TOOLS_DIR)
        self.save_config()

        script_path = os.path.join(TOOLS_DIR, "il2cheat.py")
        args = [script_path, abs_dump_dir, target_tlh_path, "--game", self.current_game_key, "--version", "1.00"] + cheat_rules

        if self.is_running:
            return
        self.is_running = True
        self.start_time = time.time()
        
        full_cmd = [sys.executable, "-u"] + args
        self.log(f"\n> Running: {subprocess.list2cmdline(full_cmd)}")
        env = dict(os.environ, PYTHONIOENCODING="utf-8")

        def task():
            errors_captured = []
            try:
                process = subprocess.Popen(full_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", cwd=TOOLS_DIR, env=env)
                for line in process.stdout:
                    self.events.put(("log", line.rstrip()))
                success = (process.wait() == 0)
                
                if success:
                    abs_tlh_path = os.path.abspath(os.path.join(TOOLS_DIR, target_tlh_path))
                    if os.path.exists(abs_tlh_path):
                        try:
                            with open(abs_tlh_path, "r", encoding="utf-8", errors="ignore") as f:
                                content = f.read()
                            
                            content = re.sub(r'Creator="[^"]*"', f'Creator="{creator_name}"', content)
                            content = content.replace('IL2CPP hook (OcclusionManager.Update)', 'Master Code')
                            
                            with open(abs_tlh_path, "w", encoding="utf-8") as f:
                                f.write(content)
                            
                            self.events.put(("log", f"[INFO] Archivo .TLH actualizado con éxito (Creator='{creator_name}', StartUP='Master Code')."))
                            self.root.after(0, lambda: messagebox.showinfo("DONE", "¡Archivo .TLH creado con éxito!"))
                        except Exception as ex:
                            self.events.put(("log", f"[ERROR] No se pudo post-procesar el archivo .TLH: {ex}"))
            except Exception as e:
                self.events.put(("log", f"[ERROR] {e}"))
                success = False
            self.events.put(("done", (success, False, errors_captured)))

        threading.Thread(target=task, daemon=True).start()

if __name__ == "__main__":
    root = tk.Tk()
    
    try:
        if os.path.exists("icon.ico"):
            root.iconbitmap("icon.ico")
    except Exception:
        pass

    app = IL2CppDumperGUI(root)
    root.mainloop()
