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
import ftplib
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
        "btn_get_name": "🌐 Get Name",
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
        "lbl_keyword": "Keyword or Value (e.g. Health or 50):",
        "btn_search": "🔎 Search SDK Code",
        "btn_find_paths": "🧭 Find Paths (--find)",
        "warn_find_paths": "Select a session folder (section 2) and enter a keyword/value.",
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
        "msg_open_folder": "The trainer was created successfully. Do you want to open the cheats folder?",
        "msg_error_title": "Process Error / Warning",
        "msg_error_details": "An error or issue was detected during execution:\n\n",
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
        "lbl_diff_offset": "Comparison Mode / Options:",
        "btn_run_diff": "🔍 Run Diff / Backtracking",
        "btn_cancel_diff": "🛑 Cancel Process",
        "btn_export_diff": "💾 Export Diff Results",
        "btn_clear_diff": "🗑️ Clear",
        "warn_diff_files": "Please select both dump JSON files to compare.",
        "live_warn_title": "⚠️ Live Edit Warning",
        "live_warn_msg": "IMPORTANT:\nThe memory dump and current console session MUST be from the same game build/session.\n\nIf the console or game has been restarted, ensure layouts match!"
    },
    "Español": {
        "title": "PS4 / PS5 Unity IL2CPP Dumper y Generador de Cheats",
        "frame_dumper": " 1. Dump de Memoria y Extracción SDK IL2CPP ",
        "lbl_ip": "Dirección IP de la Consola:",
        "btn_new": "🔄 Nuevo",
        "btn_load": "📂 Cargar Carpeta Sesión",
        "btn_ps4dump": "⚡ 1. Dump Inicial (ps4dump)",
        "btn_il2mem": "📥 2. Extraer SDK (il2mem + dumper)",
        "btn_get_name": "🌐 Obtener Nombre",
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
        "lbl_keyword": "Palabra clave o valor (ej. Health o 50):",
        "btn_search": "🔎 Buscar en SDK",
        "btn_find_paths": "🧭 Buscar Rutas (--find)",
        "warn_find_paths": "Selecciona una carpeta de sesión (sección 2) e introduce un término o valor.",
        "lbl_results_hdr": "Resultados (Ctrl+F para navegar Siguiente/Anterior):",
        "btn_export_finder": "💾 Exportar Resultados",
        "btn_clear_finder": "🗑️ Limpiar",
        "warn_ip": "Por favor, introduce la IP de la consola.",
        "warn_fields": "Por favor, completa los campos y al menos una regla válida de cheat.",
        "warn_finder": "Por favor, selecciona una carpeta de sesión válida con carpeta SDK e introduce una palabra clave.",
        "warn_empty_export": "No hay contenido para exportar.",
        "lbl_language": "Idioma / Language / Sprache:",
        "status_running": "Estado: Ejecutando proceso... Tiempo transcurrido: ",
        "status_idle": "Status: En espera",
        "msg_dump_title": "Proceso Completado",
        "msg_dump_success": "¡El proceso ha finalizado con éxito! SDK y dump.cs listos.",
        "msg_cheat_title": "Trainer Generado",
        "msg_cheat_success": "¡El archivo trainer .TLH se ha generado correctamente!",
        "msg_open_folder": "El trainer se ha creado con éxito. ¿Deseas abrir la carpeta de cheats?",
        "msg_error_title": "Error / Advertencia en el Proceso",
        "msg_error_details": "Se ha detectado un problema durante la ejecución:\n\n",
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
        "lbl_diff_offset": "Modo de Comparación / Opciones:",
        "btn_run_diff": "🔍 Ejecutar Diff / Backtracking",
        "btn_cancel_diff": "🛑 Cancelar Proceso",
        "btn_export_diff": "💾 Exportar Resultados Diff",
        "btn_clear_diff": "🗑️ Limpiar",
        "warn_diff_files": "Por favor, selecciona ambos archivos JSON de dump para comparar.",
        "live_warn_title": "⚠️ Advertencia para Envío en Vivo",
        "live_warn_msg": "IMPORTANTE:\nEl dump de memoria y la sesión activa de la consola DEBEN PERTENECER a la misma compilación.\n\nSi el juego se ha reiniciado, asegúrate de actualizar los dumps."
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

        threading.Thread(target=self.auto_detect_running_game, daemon=True).start()

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
            "keyword": "Health"
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
                "keyword": self.entry_keyword.get().strip()
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
        self.root.after(50, self._pump)

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

    def auto_detect_running_game(self):
        ip = self.entry_ip.get().strip()
        if not ip or ip == "192.168.1.XXX":
            return
        
        self.log(f"[AUTO-DETECT] Comprobando juegos activos por FTP en {ip}...")
        try:
            ftp = ftplib.FTP()
            ftp.connect(ip, 2121, timeout=3)
            ftp.login()
            ftp.cwd("/mnt/sandbox")
            dirs = ftp.nlst()
            ftp.quit()
        except Exception:
            try:
                ftp = ftplib.FTP()
                ftp.connect(ip, 21, timeout=3)
                ftp.login()
                ftp.cwd("/mnt/sandbox")
                dirs = ftp.nlst()
                ftp.quit()
            except Exception as e:
                self.log(f"[AUTO-DETECT] No se pudo conectar por FTP para auto-detectar: {e}")
                return

        active_game_id = None
        for d in dirs:
            match = re.search(r"([A-Z]{4}\d{5})", d)
            if match:
                active_game_id = match.group(1)
                break

        if not active_game_id:
            self.log("[AUTO-DETECT] No se encontró ningún juego activo válido en /mnt/sandbox.")
            return

        self.log(f"[AUTO-DETECT] Juego detectado en la consola: {active_game_id}")

        if os.path.exists(DUMPS_DIR):
            for item in os.listdir(DUMPS_DIR):
                if active_game_id in item:
                    candidate_dir = os.path.join(DUMPS_DIR, item)
                    dump_bin = os.path.join(candidate_dir, "dump.bin")
                    if os.path.exists(dump_bin):
                        rel_path = os.path.relpath(candidate_dir, TOOLS_DIR)
                        self.log(f"[AUTO-DETECT] ¡Coincidencia encontrada en dumps! Abriendo carpeta: {item}")
                        self.root.after(0, lambda p=rel_path: self.load_detected_project(p))
                        return

    def load_detected_project(self, rel_path):
        self.entry_dump_path.config(state="normal")
        self.entry_dump_path.delete(0, tk.END)
        self.entry_dump_path.insert(0, rel_path)
        self.entry_dump_path.config(state="readonly")
        self.process_dump_metadata(rel_path)

    def reset_new_session(self):
        self.entry_dump_path.config(state="normal")
        self.entry_dump_path.delete(0, tk.END)
        self.entry_dump_path.config(state="readonly")
        self.lbl_game_info.config(text="")
        self.lbl_cover.config(image="")
        self.cover_image_tk = None
        self.current_game_key = "default"
        
        for row in self.cheat_rows:
            row['frame'].destroy()
        self.cheat_rows.clear()
        
        self.add_cheat_row("", "", "")
        
        self.finder_results.delete("1.0", tk.END)
        self.lbl_res_count.config(text="Results: 0")
        self.console.delete("1.0", tk.END)

    def manual_fetch_metadata(self):
        dump_path = self.entry_dump_path.get().strip()
        if not dump_path:
            messagebox.showwarning("Warning", "Selecciona o crea una carpeta de sesión primero.")
            return
        self.process_dump_metadata(dump_path, force_online=True)

    def load_game_session_folder(self):
        t = TRANSLATIONS[self.current_lang]
        initial_dir = DUMPS_DIR if os.path.exists(DUMPS_DIR) else BASE_DIR
        dir_path = filedialog.askdirectory(
            title="Seleccionar Carpeta de Sesión de Juego (Unity)",
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
        self.diff_win.geometry("950x740")
        self.diff_win.resizable(True, True)
        self.diff_win.minsize(750, 550)

        self.q_running = False
        self.diff_proc = None

        frame_quick = ttk.LabelFrame(self.diff_win, text=" Dumps Generation ")
        frame_quick.pack(fill="x", padx=10, pady=8)

        lbl_dip = ttk.Label(frame_quick, text=t["lbl_diff_ip"])
        lbl_dip.grid(row=0, column=0, sticky="w", padx=10, pady=6)
        entry_dip = ttk.Entry(frame_quick, width=22)
        entry_dip.insert(0, self.entry_ip.get())
        entry_dip.grid(row=0, column=1, sticky="w", padx=5, pady=6)

        # Botón Dump1
        btn_dump1 = ttk.Button(frame_quick, text="⚡ Dump1", command=lambda: run_quick_dump_task("dump1.json", entry_d1))
        btn_dump1.grid(row=0, column=2, padx=10, pady=6)

        # Botón Dump2 al lado de Dump2 (Dump1 y Dump2)
        btn_dump2 = ttk.Button(frame_quick, text="⚡ Dump2", command=lambda: run_quick_dump_task("dump2.json", entry_d2))
        btn_dump2.grid(row=0, column=3, padx=10, pady=6)

        lbl_timer_diff = ttk.Label(frame_quick, text="", font=("Arial", 9, "italic"), foreground="blue")
        lbl_timer_diff.grid(row=0, column=4, padx=10, pady=6)

        frame_top = ttk.LabelFrame(self.diff_win, text=" Setup JSON Dumps & il2diff Comparison ")
        frame_top.pack(fill="x", padx=10, pady=5)

        lbl1 = ttk.Label(frame_top, text=t["lbl_diff_dump1"])
        lbl1.grid(row=0, column=0, sticky="w", padx=10, pady=6)
        entry_d1 = ttk.Entry(frame_top, width=45)
        entry_d1.grid(row=0, column=1, padx=5, pady=6, sticky="ew")
        btn_b1 = ttk.Button(frame_top, text="...", width=5, command=lambda: browse_diff_json(entry_d1))
        btn_b1.grid(row=0, column=2, padx=5, pady=6)

        lbl2 = ttk.Label(frame_top, text=t["lbl_diff_dump2"])
        lbl2.grid(row=1, column=0, sticky="w", padx=10, pady=6)
        entry_d2 = ttk.Entry(frame_top, width=45)
        entry_d2.grid(row=1, column=1, padx=5, pady=6, sticky="ew")
        btn_b2 = ttk.Button(frame_top, text="...", width=5, command=lambda: browse_diff_json(entry_d2))
        btn_b2.grid(row=1, column=2, padx=5, pady=6)

        frame_params = ttk.Frame(frame_top)
        frame_params.grid(row=2, column=0, columnspan=3, sticky="ew", padx=10, pady=6)

        lbl_mode = ttk.Label(frame_params, text="Mode:")
        lbl_mode.pack(side="left", padx=(0, 4))
        combo_mode = ttk.Combobox(frame_params, values=["--eq", "--changed"], state="readonly", width=12)
        combo_mode.set("--eq")
        combo_mode.pack(side="left", padx=(0, 10))

        lbl_va = ttk.Label(frame_params, text="Val A/B or Class:")
        lbl_va.pack(side="left", padx=(0, 2))
        entry_va = ttk.Entry(frame_params, width=12)
        entry_va.insert(0, "50")
        entry_va.pack(side="left", padx=(0, 10))

        lbl_vb = ttk.Label(frame_params, text="Val B:")
        lbl_vb.pack(side="left", padx=(0, 2))
        entry_vb = ttk.Entry(frame_params, width=12)
        entry_vb.insert(0, "77")
        entry_vb.pack(side="left", padx=(0, 5))

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
                    txt_res.insert(tk.END, "\n[!] Process cancelled by user.\n")
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
                try:
                    # Guardamos únicamente el nombre base del archivo (ej. dump1.json) 
                    # ya que il2diff.py lo busca directamente dentro del Dumpdir seleccionado.
                    base_name = os.path.basename(file_path)
                    entry_widget.delete(0, tk.END)
                    entry_widget.insert(0, base_name)
                except Exception:
                    entry_widget.delete(0, tk.END)
                    entry_widget.insert(0, file_path)

        def run_quick_dump_task(prefix_name, target_entry_widget):
            ip = entry_dip.get().strip()
            if not ip or ip == "192.168.1.XXX":
                messagebox.showwarning("Warning", t["warn_ip"], parent=self.diff_win)
                return

            if self.q_running:
                return

            dump_path = self.entry_dump_path.get().strip()
            if not dump_path:
                messagebox.showwarning("Warning", "Selecciona primero una carpeta de sesión en la interfaz principal.", parent=self.diff_win)
                return

            abs_out_dir = os.path.abspath(os.path.join(TOOLS_DIR, dump_path))
            os.makedirs(abs_out_dir, exist_ok=True)

            # out_base debe ir SIN extensión (ej: .../PPSA35399/dump1)
            # ps4dump le añadirá automáticamente .bin y .json
            out_base = os.path.join(abs_out_dir, prefix_name)

            txt_res.insert(tk.END, f"\n> Ejecutando: ps4dump.py --host {ip} -o {out_base}\n")
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
                        # El archivo JSON creado por ps4dump se llamará prefix_name + ".json" (ej: dump1.json)
                        json_filename = f"{prefix_name}.json"
                        
                        target_entry_widget.delete(0, tk.END)
                        target_entry_widget.insert(0, json_filename)
                        txt_res.insert(tk.END, f"\n[SUCCESS] ¡Volcado completado! Creados {prefix_name}.bin y {json_filename}\n")
                except Exception as e:
                    txt_res.insert(tk.END, f"\n[ERROR] {e}\n")
                
                self.q_running = False
                if lbl_timer_diff.winfo_exists():
                    lbl_timer_diff.config(text="Done!")

            threading.Thread(target=q_thread, daemon=True).start()

        def run_il2diff_task():
            d1 = entry_d1.get().strip()
            d2 = entry_d2.get().strip()
            mode = combo_mode.get().strip()
            va = entry_va.get().strip()
            vb = entry_vb.get().strip()

            if not d1 or not d2:
                messagebox.showwarning("Warning", t["warn_diff_files"], parent=self.diff_win)
                return

            dump_path = self.entry_dump_path.get().strip()
            if not dump_path:
                messagebox.showwarning("Warning", "Selecciona una carpeta de sesión primero.", parent=self.diff_win)
                return

            abs_dump_dir = os.path.abspath(os.path.join(TOOLS_DIR, dump_path))
            txt_res.delete("1.0", tk.END)
            txt_res.insert(tk.END, f"> Running il2diff.py comparison:\n  - Dumpdir: {abs_dump_dir}\n  - A: {d1}\n  - B: {d2}\n  - Mode: {mode}\n" + "-"*50 + "\n")

            script_path = os.path.join(TOOLS_DIR, "il2diff.py")
            if not os.path.exists(script_path):
                txt_res.insert(tk.END, f"\n[ERROR] il2diff.py not found in {TOOLS_DIR}\n")
                return

            args = [script_path, abs_dump_dir, d1, d2]
            if mode == "--eq":
                args.extend(["--eq", va, vb])
            else:
                args.append("--changed")
                if va:
                    args.extend(["--class", va])

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
        self.entry_keyword.bind("<Return>", lambda event: self.find_paths())

        self.btn_search = ttk.Button(keyword_frame, command=self.search_sdk_keyword)
        self.btn_search.pack(side="right")

        self.btn_find_paths = ttk.Button(keyword_frame, command=self.find_paths)
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
            messagebox.showwarning("Warning", "Selecciona una carpeta de sesión en la sección 2 primero.")
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
            messagebox.showwarning("Warning", "Selecciona una carpeta de sesión primero.")
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
            messagebox.showwarning("Warning", "Selecciona una carpeta de sesión primero.")
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
        
        # Localizar dump.cs en la raíz o dentro de la carpeta sdk
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

    def find_paths(self):
        dump_path = self.entry_dump_path.get().strip()
        keyword = self.entry_keyword.get().strip()
        if not dump_path or not keyword:
            messagebox.showwarning("Warning", TRANSLATIONS[self.current_lang]["warn_find_paths"])
            return
        abs_dump_dir = os.path.abspath(os.path.join(TOOLS_DIR, dump_path))
        self.finder_results.delete("1.0", tk.END)
        script_path = os.path.join(TOOLS_DIR, "il2live.py")
        args = [script_path, abs_dump_dir, "--find", keyword]

        def task():
            r = subprocess.run([sys.executable, "-u"] + args, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=TOOLS_DIR)
            self.events.put(("paths", (keyword, r.stdout + r.stderr)))

        threading.Thread(target=task, daemon=True).start()

    def show_paths(self, keyword, output):
        self.finder_results.delete("1.0", tk.END)
        found = 0
        for line in output.splitlines():
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            path, ftype, val = parts[0], parts[1], parts[2]
            found += 1
            tag = f"path_{found}"
            self.finder_results.tag_config(tag, foreground="#00FFFF", underline=True)
            self.finder_results.tag_bind(tag, "<Button-1>", lambda e, i={"name": path.split("::")[-1].split(".")[0], "path": path, "value": val}: self.add_suggestion_to_rules(i))
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
            folder_name = simpledialog.askstring("Session Folder", "Introduce el nombre de la carpeta de sesión del juego (ej. ealimit):", parent=self.root)
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
        dump_path = self.entry_dump_path.get().strip()
        if not dump_path:
            messagebox.showwarning("Warning", "Selecciona o crea una carpeta de sesión primero.")
            return

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

            # Comprobamos si los archivos ya existen para evitar re-extraerlos
            files_exist = os.path.exists(elf_file) and os.path.exists(meta_file)

            if files_exist:
                self.events.put(("log", "\n[INFO] Los archivos 'Il2CppUserAssemblies.prx.elf' y 'global-metadata.dat' ya existen. Omitiendo Paso 1 (il2mem)..."))
                p1_success = True
            else:
                # Paso 1: il2mem.py
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

            # Paso 2: Il2CppDumper.exe
            sdk_dir = os.path.join(abs_dump_dir, "sdk")

            if not os.path.exists(elf_file) or not os.path.exists(meta_file):
                self.events.put(("log", f"[WARNING] No se encontraron {elf_file} o {meta_file}."))
                self.events.put(("done", (True, True, [])))
                return

            if not os.path.exists(dumper_exe):
                self.events.put(("log", f"[WARNING] No se encontró Il2CppDumper.exe en {dumper_exe}."))
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

        save_path = filedialog.asksaveasfilename(title="Save IL2CPP Trainer .TLH", initialdir=CHEATS_DIR, defaultextension=".TLH", filetypes=[("TLH files", "*.TLH")], initialfile=f"{self.current_game_key}_trainer.TLH", parent=self.root)
        if not save_path:
            return

        target_tlh_path = os.path.relpath(save_path, TOOLS_DIR)
        self.save_config()
        abs_dump_dir = os.path.abspath(os.path.join(TOOLS_DIR, dump_path))

        script_path = os.path.join(TOOLS_DIR, "il2cheat.py")
        args = [script_path, abs_dump_dir, target_tlh_path, "--game", self.current_game_key, "--version", "1.00"] + cheat_rules
        self.execute_command_in_thread(args, is_dump=False)

if __name__ == "__main__":
    root = tk.Tk()
    app = IL2CppDumperGUI(root)
    root.mainloop()
