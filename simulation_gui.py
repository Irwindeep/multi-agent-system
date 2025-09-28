import tkinter as tk
from tkinter import ttk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
from simulation import run_simulation
import threading
import time
import signal
import sys  # needed to exit the process

class SimulationGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("MAS Traffic Simulation")

        # Matplotlib figure for congestion risk
        self.fig, self.ax = plt.subplots(figsize=(6, 4))
        self.line, = self.ax.plot([], [], marker='o', color='blue')
        self.ax.set_xlim(0, 10)
        self.ax.set_ylim(0, 1)
        self.ax.set_xlabel("Round")
        self.ax.set_ylabel("Congestion Risk")
        self.ax.set_title("Congestion Risk Over Time")
        self.ax.grid(True)

        self.canvas = FigureCanvasTkAgg(self.fig, master=root)
        self.canvas.get_tk_widget().pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Table for exit slots
        self.table_frame = tk.Frame(root)
        self.table_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        self.tree = ttk.Treeview(self.table_frame, columns=("Classroom", "Exit Slots"), show="headings")
        self.tree.heading("Classroom", text="Classroom")
        self.tree.heading("Exit Slots", text="Exit Slots")
        self.tree.pack(fill=tk.BOTH, expand=True)

        # Buttons frame
        self.button_frame = tk.Frame(root)
        self.button_frame.pack(side=tk.BOTTOM, fill=tk.X)

        # Start simulation button
        self.start_button = tk.Button(self.button_frame, text="Start Simulation", command=self.start_simulation_thread)
        self.start_button.pack(side=tk.LEFT, padx=5, pady=5)

        # Exit simulation button
        self.exit_button = tk.Button(self.button_frame, text="Exit Simulation", command=self.exit_simulation)
        self.exit_button.pack(side=tk.RIGHT, padx=5, pady=5)

        self.congestion_history = []
        self.simulation_running = False

    def start_simulation_thread(self):
        if not self.simulation_running:
            self.simulation_running = True
            threading.Thread(target=self.run_simulation_real_time, daemon=True).start()

    def run_simulation_real_time(self):
        rounds_data = run_simulation(num_rounds=20, sleep_time=0)
        self.congestion_history = []

        # Clear previous table
        for item in self.tree.get_children():
            self.tree.delete(item)

        for i, round_info in enumerate(rounds_data):
            if not self.simulation_running:
                break  # stop immediately if exit pressed

            self.congestion_history.append(round_info["congestion"])

            # Update plot
            self.line.set_data(range(len(self.congestion_history)), self.congestion_history)
            self.ax.set_xlim(0, max(10, len(self.congestion_history)))
            self.canvas.draw()

            # Update table
            for cls, slots in round_info["exit_slots"].items():
                self.tree.insert("", tk.END, values=(cls, ", ".join(slots)))

            time.sleep(0.5)

        self.simulation_running = False

    def exit_simulation(self):
        """Stop simulation and exit the entire Python process."""
        self.simulation_running = False
        self.root.destroy()  # close GUI
        print("Exiting simulation...")
        sys.exit(0)  # terminate Python process completely

# Handle Ctrl+C in terminal
def handler(sig, frame):
    print("Exiting simulation (Ctrl+C)...")
    sys.exit(0)

signal.signal(signal.SIGINT, handler)

if __name__ == "__main__":
    root = tk.Tk()
    gui = SimulationGUI(root)
    root.mainloop()
