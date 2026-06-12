import time
from daq_module import ContinuousDAQ

def main():
    # Inicjalizacja instancji klasy
    daq = ContinuousDAQ(
        ai_channel="Dev1/ai0", 
        di_channel="Dev1/port0/line0", 
        sample_rate=1000, 
        min_val=-5.0, 
        max_val=5.0
    )

    daq.start()

    try:
        # Główna pętla programu testowego
        for i in range(5):
            time.sleep(0.5) # Symulacja innych zadań w systemie
            
            # Pobranie i wyczyszczenie bufora
            samples = daq.get_samples()
            
            ai_len = len(samples['ai'])
            di_len = len(samples['di'])
            
            print(f"Iteracja {i+1} | Pobrano z bufora: {ai_len} próbek AI oraz {di_len} stanów DI.")
            
            if ai_len > 0:
                # Wyświetlenie wycinka danych dla weryfikacji
                print(f"  -> Próbka AI (początek): {samples['ai'][:3]}")
                print(f"  -> Stan DI: {samples['di']}")

    except KeyboardInterrupt:
        print("\nPrzerwano ręcznie.")
    finally:
        daq.stop()

if __name__ == "__main__":
    main()