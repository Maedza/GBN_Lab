"""
Go-Back-N ARQ Protocol Simulator — Entry point.

A visual, interactive simulator demonstrating the core mechanics
of the Go-Back-N sliding-window protocol.
"""

import customtkinter as ctk
from app import GBNLabApp


def main():
    app = GBNLabApp()
    app.mainloop()


if __name__ == "__main__":
    main()
