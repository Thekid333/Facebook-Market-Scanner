"""
gui_scraper.py
--------------
Desktop GUI entry point: an on/off toggle around the same scan cycle the CLI
runs, with a live status label and log box.

The searches and all scan logic live in scanner.py (shared with the CLI).
"""

import asyncio
import random
import threading
import time

import customtkinter as ctk

import marketplace_core as core
import scanner

# Set by the GUI toggle; the background thread scans only while this is set.
run_flag = threading.Event()


def log_status(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


async def run_scraper_cycle(gui_log):
    """Runs ONE complete pass through all searches, then publishes to the Gist."""
    log_status("Starting Batch Scan...")
    store = core.load_store()

    new_count = await scanner.run_scan_cycle(
        store,
        log=log_status,
        on_new=lambda record: gui_log(f"+ {record['title']} ({record['price']})"),
        should_continue=run_flag.is_set,
    )

    # Publish the full feed to the Gist unless the user hit stop mid-batch.
    if run_flag.is_set():
        core.publish_store(store, log=lambda m: (log_status(m), gui_log(m)))
    log_status(f"Batch Scan Complete. {new_count} new this pass.")


def background_loop(status_callback, gui_log):
    """The infinite loop that runs in the background thread."""
    while True:
        if not run_flag.is_set():
            time.sleep(1)
            continue

        try:
            status_callback("Scanning...")
            asyncio.run(run_scraper_cycle(gui_log))

            if run_flag.is_set():
                sleep_time = random.randint(*scanner.CYCLE_SLEEP_RANGE)
                status_callback(f"Sleeping {sleep_time}s...")
                # Sleep in 1s slices so the stop switch reacts quickly.
                for _ in range(sleep_time):
                    if not run_flag.is_set():
                        break
                    time.sleep(1)
        except Exception as e:
            status_callback(f"Error: {str(e)[:30]}...")
            log_status(f"Critical Error: {e}")
            time.sleep(10)


# ==========================================
#              GUI INTERFACE
# ==========================================

class ScraperApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("FB Scraper Bot")
        self.geometry("440x340")

        self.label_title = ctk.CTkLabel(self, text="Marketplace Scraper", font=("Arial", 20, "bold"))
        self.label_title.pack(pady=16)

        # Warn early if the Gist publishing isn't configured.
        gist_state = "Gist: configured ✓" if core.GITHUB_TOKEN else "Gist: NOT configured (set GITHUB_TOKEN in .env)"
        self.label_gist = ctk.CTkLabel(self, text=gist_state, text_color=("green" if core.GITHUB_TOKEN else "orange"))
        self.label_gist.pack()

        self.switch_var = ctk.StringVar(value="off")
        self.switch = ctk.CTkSwitch(
            self, text="Scraper OFF", command=self.toggle_switch,
            variable=self.switch_var, onvalue="on", offvalue="off", font=("Arial", 14),
        )
        self.switch.pack(pady=16)

        self.status_label = ctk.CTkLabel(self, text="Status: Stopped", text_color="gray")
        self.status_label.pack(pady=6)

        self.log_textbox = ctk.CTkTextbox(self, height=120)
        self.log_textbox.pack(pady=10, padx=20, fill="x")
        self.log_textbox.insert("0.0", "Ready. Listings publish to your Gist (no email).\n")

        self.thread = threading.Thread(
            target=background_loop, args=(self.update_status, self.gui_log), daemon=True
        )
        self.thread.start()

    def update_status(self, text):
        # Marshal onto the Tk main thread — the scraper runs on a background thread.
        self.after(0, lambda: self.status_label.configure(text=f"Status: {text}"))

    def gui_log(self, text):
        def _append():
            self.log_textbox.insert("end", f"{text}\n")
            self.log_textbox.see("end")
        self.after(0, _append)

    def toggle_switch(self):
        if self.switch_var.get() == "on":
            run_flag.set()
            self.switch.configure(text="Scraper ON")
            self.status_label.configure(text_color="green")
            self.gui_log(">> Starting...")
        else:
            run_flag.clear()
            self.switch.configure(text="Scraper OFF")
            self.status_label.configure(text_color="red", text="Status: Stopping (wait for scan)...")
            self.gui_log(">> Stopping...")


if __name__ == "__main__":
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")
    app = ScraperApp()
    app.mainloop()
