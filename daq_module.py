import nidaqmx
from nidaqmx.constants import AcquisitionType, LineGrouping
import threading

class ContinuousDAQ:
    def __init__(self, ai_channel="Dev1/ai0", di_channel="Dev1/port0/line0", 
                 sample_rate=1000, min_val=-10.0, max_val=10.0):
        """
        Konfigurowalne parametry wejść, częstotliwości i zakresu napięć.
        """
        self.ai_channel = ai_channel
        self.di_channel = di_channel
        self.sample_rate = sample_rate
        self.min_val = min_val
        self.max_val = max_val
        
        self.is_running = False
        self.thread = None
        
        # Osobne bufory dla danych analogowych i cyfrowych
        self.ai_buffer = []
        self.di_buffer = []
        self.buffer_lock = threading.Lock()

    def start(self):
        """Uruchamia akwizycję w oddzielnym wątku."""
        if self.is_running:
            return
            
        self.is_running = True
        self.thread = threading.Thread(target=self._acquisition_loop, daemon=True)
        self.thread.start()
        print(f"Start akwizycji: AI={self.ai_channel}, DI={self.di_channel}")

    def stop(self):
        """Zatrzymuje akwizycję."""
        self.is_running = False
        if self.thread and self.thread.is_alive():
            self.thread.join()
        print("Zatrzymano akwizycję.")

    def _acquisition_loop(self):
        """Pętla zbierająca dane co 100ms."""
        try:
            with nidaqmx.Task() as ai_task, nidaqmx.Task() as di_task:
                # Konfiguracja AI
                ai_task.ai_channels.add_ai_voltage_chan(
                    self.ai_channel, min_val=self.min_val, max_val=self.max_val)
                ai_task.timing.cfg_samp_clk_timing(
                    rate=self.sample_rate, sample_mode=AcquisitionType.CONTINUOUS)
                
                # Konfiguracja DI
                di_task.di_channels.add_di_chan(
                    self.di_channel, line_grouping=LineGrouping.CHAN_PER_LINE)
                
                # 10% częstotliwości = paczka danych co 100ms
                samples_per_read = int(self.sample_rate * 0.1) 
                
                ai_task.start()
                di_task.start()
                
                while self.is_running:
                    # ai_task.read zablokuje pętlę na ok. 100ms, czekając na próbki
                    ai_data = ai_task.read(number_of_samples_per_channel=samples_per_read)
                    
                    # Odczyt aktualnego stanu cyfrowego (jako pojedyncza wartość/stan)
                    di_data = di_task.read()
                    
                    with self.buffer_lock:
                        self.ai_buffer.extend(ai_data)
                        self.di_buffer.append(di_data)
                        
        except Exception as e:
            print(f"Błąd sprzętowy DAQ: {e}")
        finally:
            self.is_running = False

    def get_samples(self):
        """Pobiera i od razu czyści bufory."""
        with self.buffer_lock:
            # Zwracamy słownik z obiema listami dla wygody
            data_to_return = {
                "ai": self.ai_buffer.copy(),
                "di": self.di_buffer.copy()
            }
            self.ai_buffer.clear()
            self.di_buffer.clear()
            
        return data_to_return   