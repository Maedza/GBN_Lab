"""
Go-Back-N ARQ Protocol Simulator — Entry point.

A visual, interactive simulator demonstrating the core mechanics
of the Go-Back-N sliding-window protocol.
"""

from app import GBNLabApp
from splash import SplashScreen


def main():
    app = GBNLabApp()

    def _show_app():
        app.attributes("-alpha", 1.0)
        app.deiconify()
        app.lift()
        app.focus_force()

    # macOS Toplevel rendering quirk: a Toplevel parented to a withdrawn
    # or unmapped parent window never appears.  Instead of withdraw(), we
    # make the parent fully transparent — it stays mapped so the splash
    # renders, but is invisible to the user.
    app.attributes("-alpha", 0.0)
    app.update_idletasks()  # force the window to map
    splash = SplashScreen(app, on_done=_show_app)
    app.mainloop()


if __name__ == "__main__":
    main()
