"""
Go-Back-N ARQ Protocol Simulator — Entry point.

A visual, interactive simulator demonstrating the core mechanics
of the Go-Back-N sliding-window protocol.
"""

from app import GBNLabApp
from splash import SplashScreen


def main():
    app = GBNLabApp()
    app.withdraw()  # hide main window until splash is done
    SplashScreen(app)  # shows, animates, auto-destroys

    # Show main window once splash closes
    def _show_app():
        app.deiconify()
        app.lift()
        app.focus_force()

    app.after(1800, _show_app)
    app.mainloop()


if __name__ == "__main__":
    main()
