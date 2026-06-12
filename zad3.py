import tkinter as tk
from tkinter import ttk, messagebox
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import time
from datetime import datetime
from collections import deque

# Importujemy moduł z Zadania 2 (upewnij się, że plik daq_module.py jest w tym samym folderze)
try:
    from daq_module import ContinuousDAQ
except ImportError:
    messagebox.showerror("Błąd", "Brak pliku daq_module.py z klasą ContinuousDAQ w katalogu!")
    exit()

class TestSystemApp:
    def __init__(self, root):
        self.root = root
        self.root.title("System Akwizycji i Testowania")
        self.root.geometry("1100x600")
        
        # --- Zmienne sterujące ---
        self.daq = None
        self.current_state = "IDLE"  # Stany: IDLE, ACQUIRING, MEASURING, WAITING
        
        self.freq_var = tk.IntVar(value=1000)
        self.duration_var = tk.DoubleVar(value=5.0)
        self.min_limit_var = tk.DoubleVar(value=-2.0)
        self.max_limit_var = tk.DoubleVar(value=2.0)
        self.auto_mode_var = tk.BooleanVar(value=False)
        self.delay_var = tk.DoubleVar(value=3.0)
        
        # --- Bufory danych ---
        self.plot_y = deque(maxlen=2000)  # Bufor do ciągłego wyświetlania
        
        self.meas_y = []       # Bufor na dane z aktualnego pomiaru (do zapisu)
        self.meas_start_time = 0
        self.wait_start_time = 0
        self.limit_failed = False
        self.samples_collected = 0

        self._build_gui()
        
        # Pętla odświeżania logiki i interfejsu (co 100ms)
        self.root.after(100, self.update_loop)

    def _build_gui(self):
        # Podział okna: Lewy (Ustawienia i Sterowanie), Środkowy (Status), Prawy (Wykres)
        self.left_frame = ttk.LabelFrame(self.root, text="Ustawienia i Sterowanie", padding=10)
        self.left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)

        self.mid_frame = ttk.LabelFrame(self.root, text="Status Systemu", padding=10)
        self.mid_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)

        self.right_frame = ttk.LabelFrame(self.root, text="Podgląd Sygnału (AI)", padding=10)
        self.right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        # ==================== LEWY PANEL ====================
        ttk.Label(self.left_frame, text="Częstotliwość (Hz):").pack(anchor="w")
        ttk.Entry(self.left_frame, textvariable=self.freq_var).pack(fill=tk.X, pady=(0, 10))

        ttk.Label(self.left_frame, text="Długość pomiaru (s):").pack(anchor="w")
        ttk.Entry(self.left_frame, textvariable=self.duration_var).pack(fill=tk.X, pady=(0, 10))

        ttk.Label(self.left_frame, text="Limit MIN (V):").pack(anchor="w")
        ttk.Entry(self.left_frame, textvariable=self.min_limit_var).pack(fill=tk.X, pady=(0, 10))

        ttk.Label(self.left_frame, text="Limit MAX (V):").pack(anchor="w")
        ttk.Entry(self.left_frame, textvariable=self.max_limit_var).pack(fill=tk.X, pady=(0, 10))
        
        ttk.Separator(self.left_frame, orient="horizontal").pack(fill=tk.X, pady=10)
        
        ttk.Checkbutton(self.left_frame, text="Praca automatyczna", variable=self.auto_mode_var).pack(anchor="w")
        ttk.Label(self.left_frame, text="Opóźnienie między (s):").pack(anchor="w")
        ttk.Entry(self.left_frame, textvariable=self.delay_var).pack(fill=tk.X, pady=(0, 10))

        ttk.Separator(self.left_frame, orient="horizontal").pack(fill=tk.X, pady=10)

        self.btn_start_acq = ttk.Button(self.left_frame, text="Start Akwizycji", command=self.start_acquisition)
        self.btn_start_acq.pack(fill=tk.X, pady=2)
        
        self.btn_stop_acq = ttk.Button(self.left_frame, text="Stop Akwizycji", command=self.stop_acquisition, state=tk.DISABLED)
        self.btn_stop_acq.pack(fill=tk.X, pady=2)

        self.btn_start_meas = ttk.Button(self.left_frame, text="START Pomiaru", command=self.start_measurement, state=tk.DISABLED)
        self.btn_start_meas.pack(fill=tk.X, pady=(15, 2))
        
        self.btn_stop_meas = ttk.Button(self.left_frame, text="PRZERWIJ Pomiar", command=self.stop_measurement, state=tk.DISABLED)
        self.btn_stop_meas.pack(fill=tk.X, pady=2)

        # ==================== ŚRODKOWY PANEL ====================
        self.lbl_state = tk.Label(self.mid_frame, text="GOTOWY", font=("Arial", 16, "bold"), bg="gray", fg="white", width=15, pady=10)
        self.lbl_state.pack(pady=(0, 20))

        ttk.Label(self.mid_frame, text="Aktualne wartości:", font=("Arial", 10, "bold")).pack(anchor="w")
        self.lbl_ai_val = ttk.Label(self.mid_frame, text="AI: --- V", font=("Arial", 12))
        self.lbl_ai_val.pack(anchor="w", pady=5)
        
        self.lbl_di_val = ttk.Label(self.mid_frame, text="DI: ---", font=("Arial", 12))
        self.lbl_di_val.pack(anchor="w", pady=5)

        ttk.Separator(self.mid_frame, orient="horizontal").pack(fill=tk.X, pady=20)

        ttk.Label(self.mid_frame, text="Ocena w trakcie pomiaru:").pack(anchor="w")
        self.lbl_eval = tk.Label(self.mid_frame, text="BRAK", font=("Arial", 14, "bold"), bg="lightgray", width=15, pady=10)
        self.lbl_eval.pack(pady=5)

        self.lbl_progress = ttk.Label(self.mid_frame, text="Czas: 0.0s / 0.0s")
        self.lbl_progress.pack(pady=10)

        # ==================== PRAWY PANEL (Wykres) ====================
        self.fig, self.ax = plt.subplots(figsize=(6, 4))
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.right_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.ax.set_ylim(-10, 10)
        self.ax.grid(True, linestyle="--", alpha=0.6)

    # --- FUNKCJE STERUJĄCE ---
    def start_acquisition(self):
        try:
            freq = self.freq_var.get()
            # Inicjalizacja modułu z zadania 2 (możesz dostosować kanały)
            self.daq = ContinuousDAQ(ai_channel="Dev1/ai0", di_channel="Dev1/port0/line0", sample_rate=freq)
            self.daq.start()
            
            self.current_state = "ACQUIRING"
            self.update_ui_state()
        except Exception as e:
            messagebox.showerror("Błąd DAQ", f"Nie udało się uruchomić akwizycji:\n{e}")

    def stop_acquisition(self):
        if self.daq:
            self.daq.stop()
            self.daq = None
        self.current_state = "IDLE"
        self.update_ui_state()

    def start_measurement(self):
        if self.current_state != "ACQUIRING" and self.current_state != "WAITING":
            return
            
        self.meas_y.clear()
        self.limit_failed = False
        self.samples_collected = 0
        self.meas_start_time = time.time()
        
        self.current_state = "MEASURING"
        self.lbl_eval.config(text="W NORMIE", bg="green", fg="white")
        self.update_ui_state()

    def stop_measurement(self):
        if self.current_state == "MEASURING":
            self.finish_measurement(manual_stop=True)

    def finish_measurement(self, manual_stop=False):
        # 1. Zapis do pliku
        if len(self.meas_y) > 0:
            freq = self.freq_var.get()
            # Odtworzenie osi czasu na podstawie częstotliwości
            t_axis = np.linspace(0, len(self.meas_y) / freq, len(self.meas_y), endpoint=False)
            df = pd.DataFrame({'time': t_axis, 'ai_value': self.meas_y})
            
            filename = f"pomiar_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            try:
                df.to_csv(filename, sep=';', index=False)
                print(f"Zapisano plik: {filename}")
            except Exception as e:
                print(f"Błąd zapisu: {e}")

        # 2. Aktualizacja wizualna oceny na koniec pomiaru
        if self.limit_failed:
            self.lbl_eval.config(text="NOK (Poza limitem)", bg="red", fg="white")
        else:
            self.lbl_eval.config(text="OK (W limicie)", bg="green", fg="white")

        # 3. Logika przejścia stanu
        if manual_stop or not self.auto_mode_var.get():
            self.current_state = "ACQUIRING"
        else:
            self.current_state = "WAITING"
            self.wait_start_time = time.time()
            
        self.update_ui_state()

    # --- PĘTLA GŁÓWNA LOKIGI (wywoływana co 100ms) ---
    def update_loop(self):
        if self.daq and self.daq.is_running:
            # 1. Pobranie najnowszych danych z klasy
            data = self.daq.get_samples()
            ai_chunk = data['ai']
            di_chunk = data['di']
            
            if len(ai_chunk) > 0:
                # Aktualizacja tekstowa (bierzemy średnią z paczki dla czytelności)
                avg_ai = sum(ai_chunk) / len(ai_chunk)
                last_di = di_chunk[-1] if len(di_chunk) > 0 else 0
                self.lbl_ai_val.config(text=f"AI: {avg_ai:.3f} V")
                self.lbl_di_val.config(text=f"DI: {'HIGH' if last_di else 'LOW'}")

                # Dodanie do bufora wyświetlania
                self.plot_y.extend(ai_chunk)

                # 2. Obsługa stanu POMIARU
                if self.current_state == "MEASURING":
                    self.meas_y.extend(ai_chunk)
                    self.samples_collected += len(ai_chunk)
                    
                    elapsed = time.time() - self.meas_start_time
                    self.lbl_progress.config(text=f"Czas: {elapsed:.1f}s / {self.duration_var.get()}s")
                    
                    # Weryfikacja limitów w locie
                    min_l = self.min_limit_var.get()
                    max_l = self.max_limit_var.get()
                    
                    # Jeśli jakakolwiek próbka w paczce wyszła poza zakres
                    if any(val < min_l or val > max_l for val in ai_chunk):
                        self.limit_failed = True
                        self.lbl_eval.config(text="BŁĄD LIMITU", bg="red", fg="white")

                    # Zakończenie pomiaru po czasie
                    if elapsed >= self.duration_var.get():
                        self.finish_measurement()

            # 3. Rysowanie wykresu
            self.ax.clear()
            # Rysujemy limity poziome
            self.ax.axhline(self.max_limit_var.get(), color='red', linestyle='--', linewidth=1)
            self.ax.axhline(self.min_limit_var.get(), color='red', linestyle='--', linewidth=1)
            
            if len(self.plot_y) > 0:
                self.ax.plot(self.plot_y, color='blue')
                
            self.ax.set_ylim(-10, 10)
            self.ax.set_title("Podgląd sygnału na żywo")
            self.fig.tight_layout()
            self.canvas.draw()

        # 4. Obsługa stanu OCZEKIWANIA (Tryb Auto)
        if self.current_state == "WAITING":
            wait_elapsed = time.time() - self.wait_start_time
            self.lbl_progress.config(text=f"Odliczanie do startu: {self.delay_var.get() - wait_elapsed:.1f}s")
            
            if wait_elapsed >= self.delay_var.get():
                self.start_measurement()

        self.root.after(100, self.update_loop)

    def update_ui_state(self):
        """Aktualizuje dostępność przycisków i etykietę stanu."""
        if self.current_state == "IDLE":
            self.lbl_state.config(text="BEZCZYNNOŚĆ", bg="gray", fg="white")
            self.btn_start_acq.config(state=tk.NORMAL)
            self.btn_stop_acq.config(state=tk.DISABLED)
            self.btn_start_meas.config(state=tk.DISABLED)
            self.btn_stop_meas.config(state=tk.DISABLED)
            self.lbl_progress.config(text="Czas: 0.0s / 0.0s")
            
        elif self.current_state == "ACQUIRING":
            self.lbl_state.config(text="AKWIZYCJA", bg="#008CBA", fg="white")
            self.btn_start_acq.config(state=tk.DISABLED)
            self.btn_stop_acq.config(state=tk.NORMAL)
            self.btn_start_meas.config(state=tk.NORMAL)
            self.btn_stop_meas.config(state=tk.DISABLED)
            self.lbl_progress.config(text="Czas: 0.0s / 0.0s")
            
        elif self.current_state == "MEASURING":
            self.lbl_state.config(text="POMIAR TRWA", bg="#4CAF50", fg="white")
            self.btn_start_acq.config(state=tk.DISABLED)
            self.btn_stop_acq.config(state=tk.DISABLED)
            self.btn_start_meas.config(state=tk.DISABLED)
            self.btn_stop_meas.config(state=tk.NORMAL)
            
        elif self.current_state == "WAITING":
            self.lbl_state.config(text="OCZEKIWANIE", bg="#FF9800", fg="white")
            self.btn_start_acq.config(state=tk.DISABLED)
            self.btn_stop_acq.config(state=tk.NORMAL)
            self.btn_start_meas.config(state=tk.DISABLED)
            self.btn_stop_meas.config(state=tk.DISABLED)

if __name__ == "__main__":
    root = tk.Tk()
    app = TestSystemApp(root)
    
    # Przechwycenie zamknięcia okna "X" w celu prawidłowego zwolnienia DAQ
    def on_closing():
        if app.daq:
            app.daq.stop()
        root.destroy()
        
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()