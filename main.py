from app import GBNLabApp
from splash import SplashScreen


def main():
    app = GBNLabApp()

    def _show_app():
        app.attributes("-alpha", 1.0)
        app.deiconify()
        app.lift()
        app.focus_force()    
    app.attributes("-alpha", 0.0)
    app.update_idletasks()  
    splash = SplashScreen(app, on_done=_show_app)
    app.mainloop()


if __name__ == "__main__":
    main()
